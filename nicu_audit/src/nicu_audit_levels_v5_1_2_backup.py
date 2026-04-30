#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import math
import json
import signal
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import deque

import numpy as np
from scipy import signal as spsig
from scipy.signal import resample_poly
from tflite_runtime.interpreter import Interpreter


CONFIG = {
    "device": "plughw:CARD=USBC,DEV=0",
    "rate": 48000,
    "channels": 1,
    "format": "S16_LE",

    "cal_offset_db": 110.0,
    "calibration_json": "/opt/nicu_audit/config/nicu_calibration.json",

    "use_fir": False,
    "fir_path": "/opt/nicu_audit/config/nicu_eq_fir.npy",

    "data_dir": "/opt/nicu_audit/data",
    "meta_dir": "/opt/nicu_audit/meta",
    "node_id_path": "/etc/saem_node_id",
    "csv_prefix": "nicu_audit_v5_1",

    "int16_fs": 32768.0,
    "clip_threshold": 0.999,

    "tau_fast_s": 0.125,
    "tau_slow_s": 1.0,

    "metrics": {
        "laeq_1s": True,
        "laeq_g60s": True,
        "laeq_g900s": True,
        "laeq_g3600s": True,
        "lafmax_1s": True,
        "lasmax_1s": True,
        "clipped": True,
        "third_octave": False
    },

    "context": {
        "enabled": True,
        "yamnet_path": "/opt/saem/models/yamnet/yamnet.tflite",
        "model_path": "/opt/saem/models/context_model.tflite",
        "labels": ["alarms", "impulsive", "mechanical", "speech"],
        "yamnet_input_len": 15600,
        "trigger_delta_db": 0.0,
        "use_bg_default": True,
        "bg_default_db": 45.0
    },

    "flush_every": 10,
    "script_version": "v5.2"
}

RUNNING = True
LOCAL_TZ = ZoneInfo("Europe/Dublin")


def handle_stop(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)


def node_id(path):
    try:
        return open(path, "r", encoding="utf-8").read().strip()
    except Exception:
        return "NICU_AUDIT_UNKNOWN"


def utc_now():
    return datetime.now(timezone.utc)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def current_day_str_from_dt(dt: datetime):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def csv_path_for_day(data_dir: str, nid: str, prefix: str, day_str: str):
    return os.path.join(data_dir, f"{nid}_{day_str}_{prefix}_1s.csv")


def meta_path_for_day(meta_dir: str, nid: str, prefix: str, day_str: str):
    return os.path.join(meta_dir, f"{nid}_{day_str}_{prefix}_session.txt")


def write_header_if_needed(path: str, fieldnames):
    is_new = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    if is_new:
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()


def db10(x, eps=1e-30):
    return 10.0 * math.log10(max(float(x), eps))


def mean_square(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.mean(x * x))


def energy_from_db(level_db):
    return 10.0 ** (float(level_db) / 10.0)


def db_from_energy(energy, eps=1e-30):
    return 10.0 * math.log10(max(float(energy), eps))


def load_calibration_offset(cfg):
    fallback = float(cfg.get("cal_offset_db", 110.0))
    cal_path = cfg.get("calibration_json", "")

    cal_meta = {
        "calibration_loaded": 0,
        "calibration_path": cal_path,
        "calibration_status": "FALLBACK",
        "calibration_date_utc": "",
        "calibration_notes": ""
    }

    if not cal_path:
        return fallback, cal_meta

    try:
        with open(cal_path, "r", encoding="utf-8") as f:
            j = json.load(f)

        offset = float(j.get("offset_db", fallback))
        cal_meta["calibration_loaded"] = 1
        cal_meta["calibration_status"] = str(j.get("status", "LOADED"))
        cal_meta["calibration_date_utc"] = str(j.get("date_utc", ""))
        cal_meta["calibration_notes"] = str(j.get("notes", ""))
        return offset, cal_meta
    except Exception:
        return fallback, cal_meta


def a_weighting_iir(fs):
    f1 = 20.598997
    f2 = 107.65265
    f3 = 737.86223
    f4 = 12194.217

    w1 = 2 * math.pi * f1
    w2 = 2 * math.pi * f2
    w3 = 2 * math.pi * f3
    w4 = 2 * math.pi * f4

    zeros = [0, 0, 0, 0]
    poles = [-w1, -w1, -w2, -w3, -w4, -w4]
    k = (w4 ** 2) * (10 ** (2.0 / 20.0))

    b_a, a_a = spsig.zpk2tf(zeros, poles, k)
    b, a = spsig.bilinear(b_a, a_a, fs=fs)

    w = 2 * math.pi * 1000 / fs
    _, h = spsig.freqz(b, a, worN=[w])
    b = b / abs(h[0])

    return b, a


class IIRFilter:
    def __init__(self, b, a):
        self.b = np.asarray(b, dtype=np.float64)
        self.a = np.asarray(a, dtype=np.float64)
        self.zi = spsig.lfilter_zi(self.b, self.a) * 0.0

    def process(self, x):
        y, self.zi = spsig.lfilter(self.b, self.a, x, zi=self.zi)
        return y


def load_fir(path: str):
    try:
        taps = np.load(path)
        taps = np.asarray(taps, dtype=np.float64).reshape(-1)
        if taps.size < 2:
            return None
        return taps
    except Exception:
        return None


class RunningLeq:
    def __init__(self, maxlen_s):
        self.buf = deque(maxlen=maxlen_s)
        self.sum_energy = 0.0

    def update_from_level_db(self, level_db):
        e = energy_from_db(level_db)
        if len(self.buf) == self.buf.maxlen:
            self.sum_energy -= self.buf[0]
        self.buf.append(e)
        self.sum_energy += e

    def value_db(self):
        if len(self.buf) == 0:
            return float("nan")
        return db_from_energy(self.sum_energy / len(self.buf))

    def is_full(self):
        return len(self.buf) == self.buf.maxlen


class TimeWeighting:
    def __init__(self, fs, tau_s):
        self.fs = fs
        self.tau_s = tau_s
        self.alpha = math.exp(-(1.0 / fs) / tau_s)
        self.state = 0.0

    def process_block(self, xA, offset_db):
        e = xA * xA
        levels = np.zeros_like(xA, dtype=np.float64)

        s = self.state
        a = self.alpha

        for i, en in enumerate(e):
            s = a * s + (1.0 - a) * float(en)
            levels[i] = db10(s) + offset_db

        self.state = s
        return levels


THIRD_OCTAVE_CENTERS = np.array([
    31.5, 63.0, 125.0, 250.0, 500.0,
    1000.0, 2000.0, 4000.0, 8000.0
], dtype=np.float64)


def third_octave_edges(fc):
    factor = 2 ** (1.0 / 6.0)
    return fc / factor, fc * factor


def design_third_octave_sos(fc, fs, order=4):
    fl, fu = third_octave_edges(fc)
    nyq = fs / 2.0
    low = max(fl / nyq, 1e-6)
    high = min(fu / nyq, 0.999999)
    if low >= high:
        raise ValueError(f"Invalid band edges for fc={fc}")
    return spsig.butter(order, [low, high], btype="bandpass", output="sos")


class ThirdOctaveBank:
    def __init__(self, centers, fs, order=4):
        self.centers = np.asarray(centers, dtype=np.float64)
        self.sos_filters = []
        self.states = []

        for fc in self.centers:
            sos = design_third_octave_sos(fc, fs, order=order)
            zi = spsig.sosfilt_zi(sos) * 0.0
            self.sos_filters.append(sos)
            self.states.append(zi)

    def process_levels_db(self, x, offset_db):
        levels = []
        for i, sos in enumerate(self.sos_filters):
            y, zi = spsig.sosfilt(sos, x, zi=self.states[i])
            self.states[i] = zi

            y = np.asarray(y, dtype=np.float64)
            if not np.all(np.isfinite(y)):
                levels.append(float("nan"))
                continue

            ms = mean_square(y)
            levels.append(db10(ms) + offset_db)

        return np.asarray(levels, dtype=np.float64)


def start_arecord_stream(device, channels, rate, fmt):
    cmd = [
        "arecord",
        "-D", device,
        "-q",
        "-c", str(channels),
        "-r", str(rate),
        "-f", fmt,
        "-t", "raw",
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0
    )


def read_exact(stream, nbytes):
    chunks = []
    got = 0
    while got < nbytes and RUNNING:
        chunk = stream.read(nbytes - got)
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def open_csv_for_day(data_dir, nid, prefix, day_str, fieldnames):
    path = csv_path_for_day(data_dir, nid, prefix, day_str)
    write_header_if_needed(path, fieldnames)
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fieldnames)
    return path, f, w


def write_session_metadata(path, meta):
    with open(path, "w", encoding="utf-8") as f:
        for k, v in meta.items():
            f.write(f"{k}: {v}\n")


def init_context_models(ctx_cfg):
    yamnet = Interpreter(model_path=ctx_cfg["yamnet_path"])
    yam_in0 = yamnet.get_input_details()[0]
    yamnet.resize_tensor_input(yam_in0["index"], [ctx_cfg["yamnet_input_len"]], strict=False)
    yamnet.allocate_tensors()

    ctx_model = Interpreter(model_path=ctx_cfg["model_path"])
    ctx_model.allocate_tensors()

    print("\n=== YAMNET INPUT ===")
    for i, inp in enumerate(yamnet.get_input_details()):
        print(f"Input {i} shape: {inp['shape']}, shape_signature: {inp.get('shape_signature')}")
    print("====================")

    print("\n=== YAMNET OUTPUTS ===")
    for i, o in enumerate(yamnet.get_output_details()):
        print(f"Index {i} -> shape {o['shape']}, shape_signature: {o.get('shape_signature')}")
    print("======================")

    print("\n=== CONTEXT MODEL INPUT ===")
    for i, inp in enumerate(ctx_model.get_input_details()):
        print(f"Input {i} shape: {inp['shape']}, shape_signature: {inp.get('shape_signature')}")
    print("===========================\n")

    return yamnet, ctx_model


def run_context(yamnet, ctx_model, x48, ctx_cfg):
    try:
        x16 = resample_poly(x48, 16000, 48000)

        L = int(ctx_cfg["yamnet_input_len"])
        if len(x16) > L:
            x16 = x16[:L]
        elif len(x16) < L:
            x16 = np.pad(x16, (0, L - len(x16)))

        x16 = np.ascontiguousarray(x16.astype(np.float32))

        yam_in = yamnet.get_input_details()[0]
        yam_outs = yamnet.get_output_details()

        yamnet.set_tensor(yam_in["index"], x16)
        yamnet.invoke()

        emb = None
        for o in yam_outs:
            out = yamnet.get_tensor(o["index"])
            if out.ndim == 2 and out.shape[1] == 1024:
                emb = out
                break

        if emb is None:
            return "error", np.nan

        emb_mean = np.ascontiguousarray(emb[0].astype(np.float32))

        ctx_in = ctx_model.get_input_details()[0]
        ctx_out = ctx_model.get_output_details()[0]

        ctx_input = np.ascontiguousarray(emb_mean.reshape(1, 1024), dtype=np.float32)

        ctx_model.set_tensor(ctx_in["index"], ctx_input)
        ctx_model.invoke()

        out = ctx_model.get_tensor(ctx_out["index"]).reshape(-1)

        idx = int(np.argmax(out))
        label = ctx_cfg["labels"][idx] if 0 <= idx < len(ctx_cfg["labels"]) else f"class_{idx}"
        conf = float(out[idx])

        return label, conf

    except Exception as e:
        print(f"[CTX ERROR] {e}")
        return "error", np.nan


def main():
    cfg = CONFIG
    mcfg = cfg["metrics"]
    ctx_cfg = cfg["context"]

    nid = node_id(cfg["node_id_path"])
    ensure_dir(cfg["data_dir"])
    ensure_dir(cfg["meta_dir"])

    cal_offset_db, cal_meta = load_calibration_offset(cfg)

    fieldnames = ["date", "time"]

    if mcfg.get("laeq_1s", False):
        fieldnames.append("laeq_1s_dbA")
    if mcfg.get("laeq_g60s", False):
        fieldnames.append("laeq_g60s_dbA")
    if mcfg.get("laeq_g900s", False):
        fieldnames.append("laeq_g900s_dbA")
    if mcfg.get("laeq_g3600s", False):
        fieldnames.append("laeq_g3600s_dbA")
    if mcfg.get("lafmax_1s", False):
        fieldnames.append("lafmax_1s_dbA")
    if mcfg.get("lasmax_1s", False):
        fieldnames.append("lasmax_1s_dbA")
    if mcfg.get("clipped", False):
        fieldnames.append("clipped")

    if mcfg.get("third_octave", False):
        for fc in THIRD_OCTAVE_CENTERS:
            fieldnames.append(f"oct_{str(fc).replace('.0','')}_Hz_db")

    # nuevas columnas, sin tocar las viejas
    fieldnames += ["bg_source", "bg_eff_dbA", "trigger", "label", "confidence"]

    bA, aA = a_weighting_iir(cfg["rate"])
    Aflt = IIRFilter(bA, aA)

    fir_taps = load_fir(cfg["fir_path"]) if cfg["use_fir"] else None
    fir_zi = None
    if fir_taps is not None:
        fir_zi = np.zeros(len(fir_taps) - 1, dtype=np.float64)

    band_bank = None
    if mcfg.get("third_octave", False):
        band_bank = ThirdOctaveBank(THIRD_OCTAVE_CENTERS, cfg["rate"], order=4)

    leq_60 = RunningLeq(60)
    leq_900 = RunningLeq(900)
    leq_3600 = RunningLeq(3600)

    fast_tw = TimeWeighting(cfg["rate"], cfg["tau_fast_s"])
    slow_tw = TimeWeighting(cfg["rate"], cfg["tau_slow_s"])

    yamnet = None
    ctx_model = None
    if ctx_cfg.get("enabled", False):
        yamnet, ctx_model = init_context_models(ctx_cfg)

    flush_every = int(cfg.get("flush_every", 10))

    samples_per_chunk = int(cfg["rate"] * 1.0)
    bytes_per_sample = 2
    bytes_per_chunk = samples_per_chunk * bytes_per_sample * cfg["channels"]

    print(f"[NICU] starting logger")
    print(f"[NICU] node_id={nid}")
    print(f"[NICU] device={cfg['device']}")
    print(f"[NICU] rate={cfg['rate']}")
    print(f"[NICU] cal_offset_db={cal_offset_db:.4f}")
    print(f"[NICU] calibration_loaded={cal_meta['calibration_loaded']} | status={cal_meta['calibration_status']}")
    print(f"[NICU] FIR={'loaded' if fir_taps is not None else 'none'} | enabled={cfg['use_fir']}")
    print(f"[NICU] third_octave={'enabled' if band_bank is not None else 'disabled'}")
    print(f"[NICU] context={'enabled' if ctx_cfg.get('enabled', False) else 'disabled'} | trigger_delta={ctx_cfg.get('trigger_delta_db', 6.0)} dB")

    proc = start_arecord_stream(
        cfg["device"],
        cfg["channels"],
        cfg["rate"],
        cfg["format"]
    )

    row_count = 0
    session_start = utc_now().replace(microsecond=0)

    row_ts_init = datetime.now(LOCAL_TZ)
    current_day_str = row_ts_init.strftime("%Y-%m-%d")

    path, f, w = open_csv_for_day(
        cfg["data_dir"], nid, cfg["csv_prefix"], current_day_str, fieldnames
    )

    meta_path = meta_path_for_day(
        cfg["meta_dir"], nid, cfg["csv_prefix"], current_day_str
    )

    print(f"[NICU] csv={path}")
    print(f"[NICU] session_start_utc={session_start.isoformat(timespec='seconds')}")
    print(f"[NICU] local_time_start={row_ts_init.isoformat(timespec='seconds')}")

    try:
        while RUNNING:
            raw = read_exact(proc.stdout, bytes_per_chunk)
            if len(raw) != bytes_per_chunk:
                print("[NICU][ERROR] short read from arecord stream")
                break

            row_ts = datetime.now(LOCAL_TZ)
            row_day_str = row_ts.strftime("%Y-%m-%d")

            if row_day_str != current_day_str:
                try:
                    f.flush()
                    os.fsync(f.fileno())
                    f.close()
                except Exception:
                    pass

                current_day_str = row_day_str
                path, f, w = open_csv_for_day(
                    cfg["data_dir"], nid, cfg["csv_prefix"], current_day_str, fieldnames
                )
                meta_path = meta_path_for_day(cfg["meta_dir"], nid, cfg["csv_prefix"], current_day_str)
                print(f"[NICU] rolled csv={path}")

            x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / cfg["int16_fs"]

            if fir_taps is not None:
                x, fir_zi = spsig.lfilter(fir_taps, [1.0], x, zi=fir_zi)

            # NO CAMBIAR: igual que v4.2
            xA = Aflt.process(x)

            msA = mean_square(xA)
            laeq_1s_dbA = db10(msA) + cal_offset_db

            row = {
                "date": row_ts.strftime("%Y-%m-%d"),
                "time": row_ts.strftime("%H:%M:%S"),
            }

            if mcfg.get("laeq_1s", False):
                row["laeq_1s_dbA"] = round(laeq_1s_dbA, 6)

            # NO CAMBIAR: rolling energético igual que v4.2
            leq_60.update_from_level_db(laeq_1s_dbA)
            leq_900.update_from_level_db(laeq_1s_dbA)
            leq_3600.update_from_level_db(laeq_1s_dbA)

            laeq_bg_run = leq_900.value_db() if leq_900.is_full() else np.nan

            if mcfg.get("laeq_g60s", False):
                row["laeq_g60s_dbA"] = "" if not leq_60.is_full() else round(leq_60.value_db(), 6)
            if mcfg.get("laeq_g900s", False):
                row["laeq_g900s_dbA"] = "" if not leq_900.is_full() else round(leq_900.value_db(), 6)
            if mcfg.get("laeq_g3600s", False):
                row["laeq_g3600s_dbA"] = "" if not leq_3600.is_full() else round(leq_3600.value_db(), 6)

            if mcfg.get("lafmax_1s", False):
                laf_trace = fast_tw.process_block(xA, cal_offset_db)
                row["lafmax_1s_dbA"] = round(float(np.max(laf_trace)), 6)

            if mcfg.get("lasmax_1s", False):
                las_trace = slow_tw.process_block(xA, cal_offset_db)
                row["lasmax_1s_dbA"] = round(float(np.max(las_trace)), 6)

            if mcfg.get("clipped", False):
                row["clipped"] = int(np.max(np.abs(x)) >= cfg["clip_threshold"])

            if band_bank is not None:
                band_levels = band_bank.process_levels_db(x, cal_offset_db)
                for fc, L in zip(THIRD_OCTAVE_CENTERS, band_levels):
                    key = f"oct_{str(fc).replace('.0','')}_Hz_db"
                    row[key] = "" if not np.isfinite(L) else round(float(L), 6)

            # background fijo (OR mode)
            laeq_bg_eff = float(ctx_cfg.get("bg_default_db", 45.0))
            bg_source = "FIX"

            # trigger (SIN CAMBIOS)
            trigger = False
            if ctx_cfg.get("enabled", False) and np.isfinite(laeq_bg_eff):
                trigger = laeq_1s_dbA > laeq_bg_eff

            # context (SIN CAMBIOS)
            if ctx_cfg.get("enabled", False) and trigger:
                label, conf = run_context(yamnet, ctx_model, x, ctx_cfg)
            else:
                label, conf = "background", np.nan

            # ================================
            # 🔥 FILTRO SOLO PARA IMPULSIVE 🔥
            # ================================
            if label == "impulsive":
                laf_val = row.get("lafmax_1s_dbA", 0.0)
                if laf_val < (laeq_bg_eff + 8.0):
                    label = "background"

            # trigger
            trigger = False
            if ctx_cfg.get("enabled", False) and np.isfinite(laeq_bg_eff):
                trigger = laeq_1s_dbA > (laeq_bg_eff + float(ctx_cfg["trigger_delta_db"]))

            # context
            if ctx_cfg.get("enabled", False) and trigger:
                label, conf = run_context(yamnet, ctx_model, x, ctx_cfg)
            else:
                label, conf = "background", np.nan

            row["bg_source"] = bg_source
            row["bg_eff_dbA"] = "" if not np.isfinite(laeq_bg_eff) else round(float(laeq_bg_eff), 6)
            row["trigger"] = int(trigger)
            row["label"] = label
            row["confidence"] = "" if np.isnan(conf) else round(float(conf), 3)

            w.writerow(row)
            row_count += 1

            if row_count % flush_every == 0:
                f.flush()
                os.fsync(f.fileno())

            bg_txt = "..." if not np.isfinite(laeq_bg_eff) else f"{laeq_bg_eff:.2f}"
            conf_txt = "nan" if np.isnan(conf) else f"{conf:.2f}"

            print(
                f"{row['date']} {row['time']} | "
                f"LAeq={row.get('laeq_1s_dbA', '')} | "
                f"BG={bg_txt}({bg_source}) | "
                f"TRG={int(trigger)} | "
                f"{label} ({conf_txt}) | "
                f"rows={row_count}"
            )

    finally:
        session_stop = utc_now().replace(microsecond=0)

        try:
            f.flush()
            os.fsync(f.fileno())
            f.close()
        except Exception:
            pass

        try:
            proc.terminate()
        except Exception:
            pass

        meta = {
            "node_id": nid,
            "script_version": cfg["script_version"],
            "device": cfg["device"],
            "rate_hz": cfg["rate"],
            "channels": cfg["channels"],
            "format": cfg["format"],
            "cal_offset_db": cal_offset_db,
            "fir_enabled": int(fir_taps is not None),
            "calibration_loaded": cal_meta["calibration_loaded"],
            "calibration_status": cal_meta["calibration_status"],
            "calibration_date_utc": cal_meta["calibration_date_utc"],
            "context_enabled": int(ctx_cfg.get("enabled", False)),
            "trigger_delta_db": ctx_cfg.get("trigger_delta_db", 6.0),
            "bg_default_db": ctx_cfg.get("bg_default_db", 45.0),
            "start_time_utc": session_start.isoformat(timespec="seconds"),
            "stop_time_utc": session_stop.isoformat(timespec="seconds"),
            "rows_written": row_count,
            "csv_path": path,
        }
        write_session_metadata(meta_path, meta)

        print(f"[NICU] metadata={meta_path}")
        print("[NICU] stopped cleanly")


if __name__ == "__main__":
    main()

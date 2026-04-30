#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import math
import time
import json
import signal
import subprocess
from datetime import datetime, timezone
from collections import deque

import numpy as np
from scipy import signal as spsig


# ============================================================
# Configuration
# ============================================================

CONFIG = {
    "device": "plughw:CARD=USBC,DEV=0",
    "rate": 48000,
    "channels": 1,
    "format": "S16_LE",
    "chunk_s": 1.0,

    # Default fallback only; real value should come from calibration JSON
    "cal_offset_db": 110.0,
    "calibration_json": "/opt/nicu_audit/config/nicu_calibration.json",

    "use_fir": False,
    "fir_path": "/opt/nicu_audit/config/nicu_eq_fir.npy",

    "data_dir": "/opt/nicu_audit/data",
    "node_id_path": "/etc/saem_node_id",
    "csv_prefix": "nicu_audit_v3",

    "int16_fs": 32768.0,
    "clip_threshold": 0.999,

    "tau_fast_s": 0.125,
    "tau_slow_s": 1.0,

    "metrics": {
        "dbfs_rms_A": True,
        "laeq_1s": True,
        "laeq_60s": True,
        "laeq_900s": True,
        "laeq_3600s": True,
        "laf_end": True,
        "lafmax_dt": True,
        "las_end": True,
        "lasmax_dt": True,
        "lpeak_A": True,
        "clipped": True,
        "third_octave": True
    }
}

RUNNING = True


# ============================================================
# Graceful stop
# ============================================================

def handle_stop(signum, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)


# ============================================================
# Helpers
# ============================================================

def node_id(path):
    try:
        return open(path, "r", encoding="utf-8").read().strip()
    except Exception:
        return "NICU_AUDIT_UNKNOWN"

def utc_now():
    return datetime.now(timezone.utc)

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def csv_path_for_today(data_dir: str, nid: str, prefix: str):
    day = utc_now().strftime("%Y-%m-%d")
    return os.path.join(data_dir, f"{nid}_{day}_{prefix}_1s.csv")

def write_header_if_needed(path: str, fieldnames):
    is_new = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    if not is_new:
        return
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

def db20(x, eps=1e-20):
    return 20.0 * np.log10(np.maximum(np.asarray(x), eps))

def db10(x, eps=1e-30):
    return 10.0 * math.log10(max(float(x), eps))

def mean_square(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.mean(x * x))

def energy_from_db(level_db):
    return 10.0 ** (float(level_db) / 10.0)

def db_from_energy(energy, eps=1e-30):
    return 10.0 * math.log10(max(float(energy), eps))

def dbfs_rms(x):
    return db10(mean_square(x))

def current_day_str():
    return utc_now().strftime("%Y-%m-%d")

def load_calibration_offset(cfg):
    """
    Load offset_db from calibration JSON if available.
    Falls back to CONFIG['cal_offset_db'].
    """
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


# ============================================================
# Audio capture
# ============================================================

def capture_chunk_arecord(device, channels, rate, fmt, chunk_s, int16_fs):
    cmd = [
        "arecord",
        "-D", device,
        "-q",
        "-c", str(channels),
        "-r", str(rate),
        "-f", fmt,
        "-t", "raw",
        "-d", str(int(chunk_s)),
    ]
    raw = subprocess.check_output(cmd)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / int16_fs
    return x


# ============================================================
# A-weighting
# ============================================================

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

    # normalize at 1 kHz
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


# ============================================================
# Running LAeq windows
# ============================================================

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


# ============================================================
# Time weighting
# ============================================================

class TimeWeighting:
    """
    IEC-like time weighting:
    square A-weighted signal -> exponential averaging -> dB
    state preserved across blocks
    """
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


# ============================================================
# 1/3 octave bands (stable SOS implementation)
# ============================================================

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
    low = fl / nyq
    high = fu / nyq

    low = max(low, 1e-6)
    high = min(high, 0.999999)

    if low >= high:
        raise ValueError(f"Invalid band edges for fc={fc}")

    sos = spsig.butter(order, [low, high], btype="bandpass", output="sos")
    return sos

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


# ============================================================
# Main
# ============================================================

def main():
    cfg = CONFIG
    mcfg = cfg["metrics"]

    nid = node_id(cfg["node_id_path"])
    ensure_dir(cfg["data_dir"])

    cal_offset_db, cal_meta = load_calibration_offset(cfg)

    fieldnames = [
        "ts_utc",
        "node_id",
        "device",
        "rate_hz",
        "format",
        "channels",
        "cal_offset_db",
        "fir_enabled",
        "calibration_loaded",
        "calibration_status",
        "calibration_date_utc",
    ]

    if mcfg.get("dbfs_rms_A", False):
        fieldnames.append("dbfs_rms_A")
    if mcfg.get("laeq_1s", False):
        fieldnames.append("laeq_1s_dbA")
    if mcfg.get("laf_end", False):
        fieldnames.append("laf_end_dbA")
    if mcfg.get("lafmax_dt", False):
        fieldnames.append("lafmax_dt_dbA")
    if mcfg.get("las_end", False):
        fieldnames.append("las_end_dbA")
    if mcfg.get("lasmax_dt", False):
        fieldnames.append("lasmax_dt_dbA")
    if mcfg.get("laeq_60s", False):
        fieldnames.append("laeq_60s_dbA")
    if mcfg.get("laeq_900s", False):
        fieldnames.append("laeq_900s_dbA")
    if mcfg.get("laeq_3600s", False):
        fieldnames.append("laeq_3600s_dbA")
    if mcfg.get("lpeak_A", False):
        fieldnames.append("lpeak_A_dbA")
    if mcfg.get("clipped", False):
        fieldnames.append("clipped")

    if mcfg.get("third_octave", False):
        for fc in THIRD_OCTAVE_CENTERS:
            fieldnames.append(f"oct_{str(fc).replace('.0','')}_Hz_db")

    path = csv_path_for_today(cfg["data_dir"], nid, cfg["csv_prefix"])
    write_header_if_needed(path, fieldnames)

    # Filters
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

    last_day = current_day_str()

    print(f"[NICU] starting logger")
    print(f"[NICU] node_id={nid}")
    print(f"[NICU] device={cfg['device']}")
    print(f"[NICU] rate={cfg['rate']}")
    print(f"[NICU] cal_offset_db={cal_offset_db:.4f}")
    print(f"[NICU] calibration_loaded={cal_meta['calibration_loaded']} | status={cal_meta['calibration_status']}")
    print(f"[NICU] FIR={'loaded' if fir_taps is not None else 'none'} | enabled={cfg['use_fir']}")
    print(f"[NICU] 1/3 octave={'enabled' if band_bank is not None else 'disabled'}")
    print(f"[NICU] csv={path}")

    next_tick = math.floor(time.time()) + 1.0

    while RUNNING:
        try:
            today = current_day_str()
            if today != last_day:
                last_day = today
                path = csv_path_for_today(cfg["data_dir"], nid, cfg["csv_prefix"])
                write_header_if_needed(path, fieldnames)

            now = time.time()
            sleep_time = next_tick - now
            if sleep_time > 0:
                time.sleep(sleep_time)

            tick_time = next_tick
            next_tick += 1.0

            ts = datetime.fromtimestamp(tick_time, tz=timezone.utc)
            ts_iso = ts.isoformat(timespec="milliseconds")

            x = capture_chunk_arecord(
                cfg["device"],
                cfg["channels"],
                cfg["rate"],
                cfg["format"],
                cfg["chunk_s"],
                cfg["int16_fs"]
            )

            if fir_taps is not None:
                x, fir_zi = spsig.lfilter(fir_taps, [1.0], x, zi=fir_zi)

            xA = Aflt.process(x)

            row = {
                "ts_utc": ts_iso,
                "node_id": nid,
                "device": cfg["device"],
                "rate_hz": cfg["rate"],
                "format": cfg["format"],
                "channels": cfg["channels"],
                "cal_offset_db": round(cal_offset_db, 6),
                "fir_enabled": int(fir_taps is not None),
                "calibration_loaded": cal_meta["calibration_loaded"],
                "calibration_status": cal_meta["calibration_status"],
                "calibration_date_utc": cal_meta["calibration_date_utc"],
            }

            msA = mean_square(xA)
            laeq_1s_dbA = db10(msA) + cal_offset_db

            if mcfg.get("dbfs_rms_A", False):
                row["dbfs_rms_A"] = round(dbfs_rms(xA), 6)

            if mcfg.get("laeq_1s", False):
                row["laeq_1s_dbA"] = round(laeq_1s_dbA, 6)

            if mcfg.get("laf_end", False) or mcfg.get("lafmax_dt", False):
                laf_trace = fast_tw.process_block(xA, cal_offset_db)
                if mcfg.get("laf_end", False):
                    row["laf_end_dbA"] = round(float(laf_trace[-1]), 6)
                if mcfg.get("lafmax_dt", False):
                    row["lafmax_dt_dbA"] = round(float(np.max(laf_trace)), 6)

            if mcfg.get("las_end", False) or mcfg.get("lasmax_dt", False):
                las_trace = slow_tw.process_block(xA, cal_offset_db)
                if mcfg.get("las_end", False):
                    row["las_end_dbA"] = round(float(las_trace[-1]), 6)
                if mcfg.get("lasmax_dt", False):
                    row["lasmax_dt_dbA"] = round(float(np.max(las_trace)), 6)

            leq_60.update_from_level_db(laeq_1s_dbA)
            leq_900.update_from_level_db(laeq_1s_dbA)
            leq_3600.update_from_level_db(laeq_1s_dbA)

            if mcfg.get("laeq_60s", False):
                row["laeq_60s_dbA"] = "" if not leq_60.is_full() else round(leq_60.value_db(), 6)
            if mcfg.get("laeq_900s", False):
                row["laeq_900s_dbA"] = "" if not leq_900.is_full() else round(leq_900.value_db(), 6)
            if mcfg.get("laeq_3600s", False):
                row["laeq_3600s_dbA"] = "" if not leq_3600.is_full() else round(leq_3600.value_db(), 6)

            if mcfg.get("lpeak_A", False):
                peakA = float(np.max(np.abs(xA)))
                row["lpeak_A_dbA"] = round(float(db20(peakA) + cal_offset_db), 6)

            if mcfg.get("clipped", False):
                row["clipped"] = int(np.max(np.abs(x)) >= cfg["clip_threshold"])

            if band_bank is not None:
                band_levels = band_bank.process_levels_db(x, cal_offset_db)
                for fc, L in zip(THIRD_OCTAVE_CENTERS, band_levels):
                    key = f"oct_{str(fc).replace('.0','')}_Hz_db"
                    row[key] = "" if not np.isfinite(L) else round(float(L), 6)

            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writerow(row)

            parts = [row["ts_utc"]]
            if "laeq_1s_dbA" in row:
                parts.append(f"LAeq,1s={row['laeq_1s_dbA']:6.2f}")
            if "laf_end_dbA" in row:
                parts.append(f"LAF={row['laf_end_dbA']:6.2f}")
            if "lafmax_dt_dbA" in row:
                parts.append(f"LAFmax_dt={row['lafmax_dt_dbA']:6.2f}")
            if "las_end_dbA" in row:
                parts.append(f"LAS={row['las_end_dbA']:6.2f}")
            if "lasmax_dt_dbA" in row:
                parts.append(f"LASmax_dt={row['lasmax_dt_dbA']:6.2f}")
            if "laeq_60s_dbA" in row:
                parts.append(f"LAeq,60s={leq_60.value_db() if leq_60.is_full() else float('nan'):6.2f}")
            if "lpeak_A_dbA" in row:
                parts.append(f"LpeakA={row['lpeak_A_dbA']:6.2f}")
            if "clipped" in row:
                parts.append(f"clip={row['clipped']}")

            print(" | ".join(parts))

        except subprocess.CalledProcessError as e:
            print(f"[NICU][ERROR] arecord failed: {e}")
            time.sleep(0.5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[NICU][ERROR] {e}")
            time.sleep(0.5)

    print("[NICU] stopped cleanly")


if __name__ == "__main__":
    main()

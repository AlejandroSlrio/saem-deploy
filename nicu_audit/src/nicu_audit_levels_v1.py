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

    # Calibration / correction
    "cal_offset_db": 110.0,
    "use_fir": False,
    "fir_path": "/opt/nicu_audit/config/nicu_eq_fir.npy",

    # Output
    "data_dir": "/opt/nicu_audit/data",
    "node_id_path": "/etc/saem_node_id",
    "csv_prefix": "nicu_audit",

    # Thresholds
    "int16_fs": 32768.0,
    "clip_threshold": 0.999,

    # IEC-like time constants
    "tau_fast_s": 0.125,
    "tau_slow_s": 1.0,

    # User-selectable metrics
    "metrics": {
        "laeq_1s": True,
        "laeq_60s": True,
        "laeq_900s": True,
        "laeq_3600s": True,
        "laf_end": True,
        "lafmax_dt": True,
        "las_end": True,
        "lasmax_dt": True,
        "lpeak_A": True,
        "dbfs_rms_A": True,
        "clipped": True
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

def utc_iso():
    return utc_now().isoformat(timespec="milliseconds")

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
    return 10.0 * np.log10(max(float(x), eps))

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

    # Normalize at 1 kHz
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
# Running energy windows
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
    - operates on squared A-weighted signal
    - keeps state across blocks
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

    def end_level_db(self, xA, offset_db):
        levels = self.process_block(xA, offset_db)
        return float(levels[-1])

    def max_level_db(self, xA, offset_db):
        levels = self.process_block(xA, offset_db)
        return float(np.max(levels))


# ============================================================
# Main
# ============================================================

def main():
    cfg = CONFIG
    mcfg = cfg["metrics"]

    nid = node_id(cfg["node_id_path"])
    ensure_dir(cfg["data_dir"])

    rate = cfg["rate"]
    chunk_s = cfg["chunk_s"]

    # Dynamic fieldnames
    fieldnames = [
        "ts_utc",
        "node_id",
        "device",
        "rate_hz",
        "format",
        "channels",
        "cal_offset_db",
        "fir_enabled",
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

    path = csv_path_for_today(cfg["data_dir"], nid, cfg["csv_prefix"])
    write_header_if_needed(path, fieldnames)

    # Filters
    bA, aA = a_weighting_iir(rate)
    Aflt = IIRFilter(bA, aA)

    fir_taps = load_fir(cfg["fir_path"]) if cfg["use_fir"] else None
    fir_zi = None
    if fir_taps is not None:
        fir_zi = np.zeros(len(fir_taps) - 1, dtype=np.float64)

    # Running LAeq windows
    leq_60 = RunningLeq(60)
    leq_900 = RunningLeq(900)
    leq_3600 = RunningLeq(3600)

    # Time-weighting states
    fast_tw = TimeWeighting(rate, cfg["tau_fast_s"])
    slow_tw = TimeWeighting(rate, cfg["tau_slow_s"])

    last_day = current_day_str()

    print(f"[NICU] starting logger")
    print(f"[NICU] node_id={nid}")
    print(f"[NICU] device={cfg['device']}")
    print(f"[NICU] rate={rate}")
    print(f"[NICU] cal_offset_db={cfg['cal_offset_db']}")
    print(f"[NICU] FIR={'loaded' if fir_taps is not None else 'none'} | enabled={cfg['use_fir']}")
    print(f"[NICU] csv={path}")

    while RUNNING:
        try:
            today = current_day_str()
            if today != last_day:
                last_day = today
                path = csv_path_for_today(cfg["data_dir"], nid, cfg["csv_prefix"])
                write_header_if_needed(path, fieldnames)

            x = capture_chunk_arecord(
                cfg["device"],
                cfg["channels"],
                rate,
                cfg["format"],
                chunk_s,
                cfg["int16_fs"]
            )

            if fir_taps is not None:
                x, fir_zi = spsig.lfilter(fir_taps, [1.0], x, zi=fir_zi)

            # A-weighting with state preserved across blocks
            xA = Aflt.process(x)

            row = {
                "ts_utc": utc_iso(),
                "node_id": nid,
                "device": cfg["device"],
                "rate_hz": rate,
                "format": cfg["format"],
                "channels": cfg["channels"],
                "cal_offset_db": round(cfg["cal_offset_db"], 6),
                "fir_enabled": int(fir_taps is not None),
            }

            # Time-averaged LAeq,1s
            msA = mean_square(xA)
            laeq_1s_dbA = db10(msA) + cfg["cal_offset_db"]

            if mcfg.get("dbfs_rms_A", False):
                row["dbfs_rms_A"] = round(dbfs_rms(xA), 6)

            if mcfg.get("laeq_1s", False):
                row["laeq_1s_dbA"] = round(laeq_1s_dbA, 6)

            # Time-weighted Fast / Slow on same A-weighted signal
            if mcfg.get("laf_end", False) or mcfg.get("lafmax_dt", False):
                laf_trace = fast_tw.process_block(xA, cfg["cal_offset_db"])
                if mcfg.get("laf_end", False):
                    row["laf_end_dbA"] = round(float(laf_trace[-1]), 6)
                if mcfg.get("lafmax_dt", False):
                    row["lafmax_dt_dbA"] = round(float(np.max(laf_trace)), 6)

            if mcfg.get("las_end", False) or mcfg.get("lasmax_dt", False):
                las_trace = slow_tw.process_block(xA, cfg["cal_offset_db"])
                if mcfg.get("las_end", False):
                    row["las_end_dbA"] = round(float(las_trace[-1]), 6)
                if mcfg.get("lasmax_dt", False):
                    row["lasmax_dt_dbA"] = round(float(np.max(las_trace)), 6)

            # Running time-averaged windows
            leq_60.update_from_level_db(laeq_1s_dbA)
            leq_900.update_from_level_db(laeq_1s_dbA)
            leq_3600.update_from_level_db(laeq_1s_dbA)

            if mcfg.get("laeq_60s", False):
                row["laeq_60s_dbA"] = "" if not leq_60.is_full() else round(leq_60.value_db(), 6)
            if mcfg.get("laeq_900s", False):
                row["laeq_900s_dbA"] = "" if not leq_900.is_full() else round(leq_900.value_db(), 6)
            if mcfg.get("laeq_3600s", False):
                row["laeq_3600s_dbA"] = "" if not leq_3600.is_full() else round(leq_3600.value_db(), 6)

            # Peak of A-weighted waveform amplitude
            if mcfg.get("lpeak_A", False):
                peakA = float(np.max(np.abs(xA)))
                row["lpeak_A_dbA"] = round(float(db20(peakA) + cfg["cal_offset_db"]), 6)

            if mcfg.get("clipped", False):
                row["clipped"] = int(np.max(np.abs(x)) >= cfg["clip_threshold"])

            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writerow(row)

            print_parts = [
                row["ts_utc"],
                f"LAeq,1s={laeq_1s_dbA:6.2f}"
            ]
            if "laf_end_dbA" in row:
                print_parts.append(f"LAF={row['laf_end_dbA']:6.2f}")
            if "lafmax_dt_dbA" in row:
                print_parts.append(f"LAFmax_dt={row['lafmax_dt_dbA']:6.2f}")
            if "las_end_dbA" in row:
                print_parts.append(f"LAS={row['las_end_dbA']:6.2f}")
            if "laeq_60s_dbA" in row:
                print_parts.append(f"LAeq,60s={leq_60.value_db() if leq_60.is_full() else float('nan'):6.2f}")
            if "laeq_900s_dbA" in row:
                print_parts.append(f"LAeq,900s={leq_900.value_db() if leq_900.is_full() else float('nan'):6.2f}")
            if "laeq_3600s_dbA" in row:
                print_parts.append(f"LAeq,3600s={leq_3600.value_db() if leq_3600.is_full() else float('nan'):6.2f}")
            if "lpeak_A_dbA" in row:
                print_parts.append(f"LpeakA={row['lpeak_A_dbA']:6.2f}")
            if "clipped" in row:
                print_parts.append(f"clip={row['clipped']}")

            print(" | ".join(print_parts))

        except subprocess.CalledProcessError as e:
            print(f"[NICU][ERROR] arecord failed: {e}")
            time.sleep(1.0)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[NICU][ERROR] {e}")
            time.sleep(1.0)

    print("[NICU] stopped cleanly")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import math
import argparse
import subprocess
from datetime import datetime, timezone

import numpy as np
from scipy import signal as spsig


# ============================================================
# Defaults
# ============================================================

DEFAULT_DEVICE = "plughw:CARD=USBC,DEV=0"
DEFAULT_RATE = 48000
DEFAULT_CHANNELS = 1
DEFAULT_FORMAT = "S16_LE"
DEFAULT_INT16_FS = 32768.0

DEFAULT_CAL_DB = 94.0
DEFAULT_CAL_HZ = 1000.0

DEFAULT_USE_FIR = True
DEFAULT_FIR_PATH = "/opt/nicu_audit/config/nicu_eq_fir.npy"
DEFAULT_OUT_JSON = "/opt/nicu_audit/config/nicu_calibration.json"


# ============================================================
# Helpers
# ============================================================

def utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def db10(x, eps=1e-30):
    return 10.0 * math.log10(max(float(x), eps))

def mean_square(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.mean(x * x))

def dbfs_rms(x):
    return db10(mean_square(x))

def capture_arecord(device, channels, rate, fmt, seconds, int16_fs):
    cmd = [
        "arecord",
        "-D", device,
        "-q",
        "-c", str(channels),
        "-r", str(rate),
        "-f", fmt,
        "-t", "raw",
        "-d", str(int(seconds)),
    ]
    raw = subprocess.check_output(cmd)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / int16_fs
    return x

def load_fir(path: str):
    try:
        taps = np.load(path)
        taps = np.asarray(taps, dtype=np.float64).reshape(-1)
        if taps.size < 2:
            return None
        return taps
    except Exception:
        return None

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

def estimate_tone_frequency(x, fs):
    """
    Rough frequency estimate for sanity check.
    """
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 1024:
        return float("nan")

    w = np.hanning(len(x))
    X = np.fft.rfft(x * w)
    freqs = np.fft.rfftfreq(len(x), d=1.0 / fs)
    k = int(np.argmax(np.abs(X)))
    return float(freqs[k])

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="Calibrate microphone level with 94 dB / 1 kHz calibrator")
    ap.add_argument("--device", default=DEFAULT_DEVICE)
    ap.add_argument("--rate", type=int, default=DEFAULT_RATE)
    ap.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    ap.add_argument("--format", default=DEFAULT_FORMAT)
    ap.add_argument("--seconds", type=int, default=5, help="capture duration in seconds")
    ap.add_argument("--repeats", type=int, default=3, help="number of repeated captures")
    ap.add_argument("--int16_fs", type=float, default=DEFAULT_INT16_FS)

    ap.add_argument("--cal_db", type=float, default=DEFAULT_CAL_DB)
    ap.add_argument("--cal_hz", type=float, default=DEFAULT_CAL_HZ)

    ap.add_argument("--use_fir", action="store_true", default=DEFAULT_USE_FIR)
    ap.add_argument("--no_fir", action="store_true", help="disable FIR")
    ap.add_argument("--fir_path", default=DEFAULT_FIR_PATH)

    ap.add_argument("--out_json", default=DEFAULT_OUT_JSON)
    ap.add_argument("--notes", default="94 dB 1 kHz field calibration")
    args = ap.parse_args()

    use_fir = args.use_fir and (not args.no_fir)
    fir_taps = load_fir(args.fir_path) if use_fir else None

    bA, aA = a_weighting_iir(args.rate)

    raw_dbfs_vals = []
    a_dbfs_vals = []
    freq_est_vals = []

    print("[CAL] Starting calibration")
    print(f"[CAL] device={args.device}")
    print(f"[CAL] rate={args.rate}")
    print(f"[CAL] calibrator={args.cal_db:.1f} dB @ {args.cal_hz:.1f} Hz")
    print(f"[CAL] FIR={'enabled' if fir_taps is not None else 'disabled'}")
    print()

    for i in range(args.repeats):
        print(f"[CAL] Capture {i+1}/{args.repeats} ...")
        x = capture_arecord(
            args.device,
            args.channels,
            args.rate,
            args.format,
            args.seconds,
            args.int16_fs
        )

        # remove tiny DC bias
        x = x - np.mean(x)

        freq_est = estimate_tone_frequency(x, args.rate)
        freq_est_vals.append(freq_est)

        raw_dbfs = dbfs_rms(x)

        if fir_taps is not None:
            x_proc = spsig.lfilter(fir_taps, [1.0], x)
        else:
            x_proc = x

        xA = spsig.lfilter(bA, aA, x_proc)
        a_dbfs = dbfs_rms(xA)

        raw_dbfs_vals.append(raw_dbfs)
        a_dbfs_vals.append(a_dbfs)

        print(f"      estimated tone freq = {freq_est:.2f} Hz")
        print(f"      dbfs_rms_raw        = {raw_dbfs:.4f} dBFS")
        print(f"      dbfs_rms_A          = {a_dbfs:.4f} dBFS")
        print()

    raw_dbfs_mean = float(np.mean(raw_dbfs_vals))
    raw_dbfs_std = float(np.std(raw_dbfs_vals, ddof=1)) if len(raw_dbfs_vals) > 1 else 0.0

    a_dbfs_mean = float(np.mean(a_dbfs_vals))
    a_dbfs_std = float(np.std(a_dbfs_vals, ddof=1)) if len(a_dbfs_vals) > 1 else 0.0

    freq_est_mean = float(np.mean(freq_est_vals))
    freq_est_std = float(np.std(freq_est_vals, ddof=1)) if len(freq_est_vals) > 1 else 0.0

    offset_raw = float(args.cal_db - raw_dbfs_mean)
    offset_A = float(args.cal_db - a_dbfs_mean)

    result = {
        "offset_db": offset_A,
        "offset_db_raw": offset_raw,
        "offset_db_A": offset_A,
        "calibrator_db": args.cal_db,
        "calibrator_hz": args.cal_hz,
        "device": args.device,
        "rate_hz": args.rate,
        "channels": args.channels,
        "format": args.format,
        "use_fir": bool(fir_taps is not None),
        "fir_path": args.fir_path if fir_taps is not None else "",
        "dbfs_rms_raw_mean": raw_dbfs_mean,
        "dbfs_rms_raw_std": raw_dbfs_std,
        "dbfs_rms_A_mean": a_dbfs_mean,
        "dbfs_rms_A_std": a_dbfs_std,
        "estimated_tone_hz_mean": freq_est_mean,
        "estimated_tone_hz_std": freq_est_std,
        "repeats": args.repeats,
        "seconds_per_repeat": args.seconds,
        "date_utc": utc_iso(),
        "notes": args.notes,
        "status": "FIELD_94DB_1KHZ"
    }

    print("========== CALIBRATION RESULT ==========")
    print(f"raw mean dBFS      : {raw_dbfs_mean:.4f} ± {raw_dbfs_std:.4f}")
    print(f"A-weighted mean    : {a_dbfs_mean:.4f} ± {a_dbfs_std:.4f}")
    print(f"estimated tone     : {freq_est_mean:.2f} ± {freq_est_std:.2f} Hz")
    print(f"offset_raw         : {offset_raw:.4f} dB")
    print(f"offset_A           : {offset_A:.4f} dB")
    print(f"[CAL] Writing JSON to: {args.out_json}")

    save_json(args.out_json, result)


if __name__ == "__main__":
    main()

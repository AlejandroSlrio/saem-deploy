#!/opt/saem/venv311/bin/python

import os
import csv
import json
import time
import sys
from datetime import datetime

import numpy as np
from scipy.signal import resample_poly

sys.path.append("/opt/saem/LoudnessModel")

import tvl2018 as tvl
import transfer_functions


# =====================
# CONFIG
# =====================
FIFO_PATH = "/tmp/saem_loudness_fifo"

FS_IN = 48000
FS_LOUD = 16000   # 🔥 clave

BYTES_PER_SAMPLE = 4
CHUNK_SAMPLES = FS_IN
CHUNK_BYTES = CHUNK_SAMPLES * BYTES_PER_SAMPLE

NODE_ID = "saem_n1"
DATA_DIR = "/opt/nicu_audit/data"
CAL_PATH = "/opt/nicu_audit/config/nicu_calibration.json"

SILENCE_RMS = 5e-5   # 🔥 más agresivo

os.makedirs(DATA_DIR, exist_ok=True)


# =====================
# CALIBRACIÓN
# =====================
def load_calibration(path):
    try:
        with open(path, "r") as f:
            return float(json.load(f)["offset_db"])
    except:
        return 110.0


CAL_OFFSET_DB = load_calibration(CAL_PATH)
DB_MAX = CAL_OFFSET_DB - 3.0103

print("[WORKER] FINAL STABLE MODE")
print(f"[WORKER] DB_MAX = {DB_MAX:.2f} dB")


# =====================
# LOUDNESS (TU MÉTODO)
# =====================
def compute_features(x):

    loudness, st, lt = tvl.compute_loudness(
        x,
        DB_MAX,
        transfer_functions.ff_32000,
        FS_LOUD
    )

    LL_st = tvl.sone_to_phon_tv2015(st)
    LL_lt = tvl.sone_to_phon_tv2015(lt)

    I_st = 10 ** (LL_st / 10.0)
    I_lt = 10 ** (LL_lt / 10.0)

    ltl_i_mean = float(np.mean(I_lt))
    stl_i_p95 = float(np.percentile(I_st, 95))

    ltl_phon = float(10 * np.log10(max(ltl_i_mean, 1e-12)))
    stl_phon = float(10 * np.log10(max(stl_i_p95, 1e-12)))

    return ltl_i_mean, stl_i_p95, ltl_phon, stl_phon


# =====================
# CSV
# =====================
def csv_path():
    day = datetime.now().strftime("%Y-%m-%d")
    return f"{DATA_DIR}/{NODE_ID}_{day}_perceptual.csv"


def write_row(row):
    path = csv_path()
    new = not os.path.exists(path)

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if new:
            writer.writeheader()
        writer.writerow(row)


# =====================
# MAIN
# =====================
print("[WORKER] Listening...")

with open(FIFO_PATH, "rb") as fifo:

    while True:

        data = fifo.read(CHUNK_BYTES)
        if len(data) != CHUNK_BYTES:
            continue

        t0 = time.time()
        ts = datetime.now()

        x = np.frombuffer(data, dtype=np.float32)

        # =====================
        # SILENCE SKIP
        # =====================
        rms = np.sqrt(np.mean(x**2))
        if rms < SILENCE_RMS:
            continue

        # =====================
        # RESAMPLE
        # =====================
        x16 = resample_poly(x, FS_LOUD, FS_IN)

        # 🔥 REDUCCIÓN CPU EXTRA (sin romper modelo)
        x16 = x16[::2]

        # =====================
        # MONO → STEREO
        # =====================
        x16 = np.repeat(x16[:, None], 2, axis=1)

        # =====================
        # LOUDNESS
        # =====================
        ltl_i, stl_i, ltl_phon, stl_phon = compute_features(x16)

        proc_time = time.time() - t0

        row = {
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%H:%M:%S"),
            "node_id": NODE_ID,
            "ltl_i_mean": round(ltl_i, 6),
            "stl_i_p95": round(stl_i, 6),
            "ltl_phon": round(ltl_phon, 2),
            "stl_phon": round(stl_phon, 2),
            "proc_time_s": round(proc_time, 2)
        }

        write_row(row)

        print(f"[P] {ltl_phon:.1f}/{stl_phon:.1f} | {proc_time:.1f}s")

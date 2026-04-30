#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import glob
import math
import argparse
from typing import List, Optional

import numpy as np
import pandas as pd


DATA_DIR_DEFAULT = "/opt/nicu_audit/data"
OUT_DIR_DEFAULT = "/opt/nicu_audit/summary"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# =============================
# BASIC ACOUSTIC METRICS
# =============================

def energy_mean_db(values_db: pd.Series) -> float:
    x = pd.to_numeric(values_db, errors="coerce").dropna().astype(float)
    if len(x) == 0:
        return float("nan")
    e = np.mean(10.0 ** (x / 10.0))
    return 10.0 * math.log10(e)


def percentile_level(values_db: pd.Series, p_exceed: float) -> float:
    x = pd.to_numeric(values_db, errors="coerce").dropna().astype(float)
    if len(x) == 0:
        return float("nan")
    q = 100.0 - float(p_exceed)
    return float(np.percentile(x, q))


def max_level(values_db: pd.Series) -> float:
    x = pd.to_numeric(values_db, errors="coerce").dropna().astype(float)
    if len(x) == 0:
        return float("nan")
    return float(np.max(x))


def pct_above(values_db: pd.Series, thr: float) -> float:
    x = pd.to_numeric(values_db, errors="coerce").dropna().astype(float)
    if len(x) == 0:
        return float("nan")
    return float(100.0 * np.mean(x > thr))


def sum_clipped(values) -> int:
    x = pd.to_numeric(values, errors="coerce").fillna(0).astype(int)
    return int(x.sum())


# =============================
# TIME SPLITS
# =============================

def build_timestamp(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str),
        errors="coerce",
        utc=True
    )


def split_day_night(df: pd.DataFrame):
    hours = df["timestamp"].dt.hour
    day_df = df[(hours >= 7) & (hours < 22)].copy()
    night_df = df[(hours < 7) | (hours >= 22)].copy()
    return day_df, night_df


def split_operating_hours(df: pd.DataFrame):
    hours = df["timestamp"].dt.hour
    return df[(hours >= 8) & (hours < 18)].copy()


# =============================
# CONTEXT SUMMARY (🔥 NUEVO)
# =============================

def summarize_context(df: pd.DataFrame, prefix: str = "") -> dict:
    out = {}

    if not {"trigger", "label", "laeq_1s_dbA"}.issubset(df.columns):
        return out

    df_ctx = df[df["trigger"] == 1].copy()

    if len(df_ctx) == 0:
        return out

    total_rows = len(df)

    total_energy = np.sum(
        10 ** (pd.to_numeric(df["laeq_1s_dbA"], errors="coerce") / 10)
    )

    labels = ["alarms", "impulsive", "mechanical", "speech"]

    for lbl in labels:
        df_l = df_ctx[df_ctx["label"] == lbl]

        if len(df_l) == 0:
            out[f"{prefix}ctx_pct_time_{lbl}"] = 0.0
            out[f"{prefix}ctx_energy_pct_{lbl}"] = 0.0
            continue

        # % tiempo
        out[f"{prefix}ctx_pct_time_{lbl}"] = round(
            100.0 * len(df_l) / total_rows, 6
        )

        # energía
        energy_lbl = np.sum(
            10 ** (pd.to_numeric(df_l["laeq_1s_dbA"], errors="coerce") / 10)
        )

        out[f"{prefix}ctx_energy_pct_{lbl}"] = round(
            100.0 * energy_lbl / total_energy, 6
        )

    out[f"{prefix}ctx_pct_time_active"] = round(
        100.0 * len(df_ctx) / total_rows, 6
    )

    return out


# =============================
# PERIOD SUMMARY
# =============================

def summarize_period(df: pd.DataFrame, prefix: str = "") -> dict:
    out = {}

    laeq_col = "laeq_1s_dbA"
    laf_col = "lafmax_1s_dbA"
    las_col = "lasmax_1s_dbA"

    if laeq_col in df.columns:
        out[f"{prefix}laeq_dbA"] = round(energy_mean_db(df[laeq_col]), 6)
        out[f"{prefix}l10_dbA"] = round(percentile_level(df[laeq_col], 10), 6)
        out[f"{prefix}l50_dbA"] = round(percentile_level(df[laeq_col], 50), 6)
        out[f"{prefix}l90_dbA"] = round(percentile_level(df[laeq_col], 90), 6)
        out[f"{prefix}pct_time_laeq_gt_45"] = round(pct_above(df[laeq_col], 45.0), 6)
        out[f"{prefix}pct_time_laeq_gt_50"] = round(pct_above(df[laeq_col], 50.0), 6)

    if laf_col in df.columns:
        out[f"{prefix}lafmax_dbA"] = round(max_level(df[laf_col]), 6)

    if las_col in df.columns:
        out[f"{prefix}lasmax_dbA"] = round(max_level(df[las_col]), 6)

    if "clipped" in df.columns:
        out[f"{prefix}n_clipped"] = sum_clipped(df["clipped"])

    out[f"{prefix}rows_valid"] = int(len(df))

    return out


# =============================
# MAIN PROCESS
# =============================

def process_file(csv_path: str):
    df = pd.read_csv(csv_path)

    df["timestamp"] = build_timestamp(df)
    df = df.dropna(subset=["timestamp"]).copy()
    df = df.sort_values("timestamp")

    date_str = str(df["date"].iloc[0])

    day_df, night_df = split_day_night(df)
    or_df = split_operating_hours(df)

    daily = {
        "date": date_str,
        "source_file": os.path.basename(csv_path),
    }

    # =============================
    # ACOUSTIC METRICS
    # =============================
    daily.update(summarize_period(df, "d24_"))
    daily.update(summarize_period(day_df, "day_"))
    daily.update(summarize_period(night_df, "night_"))
    daily.update(summarize_period(or_df, "or_"))

    # =============================
    # CONTEXT (🔥 NUEVO)
    # =============================
    daily.update(summarize_context(df, "d24_"))
    daily.update(summarize_context(day_df, "day_"))
    daily.update(summarize_context(night_df, "night_"))
    daily.update(summarize_context(or_df, "or_"))

    return daily


# =============================
# RUN
# =============================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default=DATA_DIR_DEFAULT)
    parser.add_argument("--out_dir", default=OUT_DIR_DEFAULT)
    parser.add_argument("--pattern", default="*_v5_2_1s.csv")
    args = parser.parse_args()

    ensure_dir(args.out_dir)

    files = sorted(glob.glob(os.path.join(args.data_dir, args.pattern)))

    if not files:
        print("No files found")
        return

    rows = []

    for f in files:
        try:
            rows.append(process_file(f))
            print("OK:", f)
        except Exception as e:
            print("ERROR:", f, e)

    df = pd.DataFrame(rows)
    out_path = os.path.join(args.out_dir, "daily_summary_v5_2.csv")
    df.to_csv(out_path, index=False)

    print("Saved:", out_path)


if __name__ == "__main__":
    main()

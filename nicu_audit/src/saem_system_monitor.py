#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess

OUT_FILE = "/tmp/saem_sys.txt"
CSV_FILE = "/opt/nicu_audit/data/system_monitor.csv"


def get_cpu_load():
    try:
        return os.getloadavg()[0]
    except Exception:
        return -1.0


def get_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        pass

    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        return float(out.replace("temp=", "").replace("'C\n", ""))
    except Exception:
        pass

    return -1.0


def ensure_csv_header():
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        with open(CSV_FILE, "w") as f:
            f.write("date,time,cpu,temp\n")


def write_status(load, temp):
    with open(OUT_FILE, "w") as f:
        f.write(f"{load:.2f},{temp:.2f}")


def append_csv(load, temp):
    ts = time.strftime("%Y-%m-%d,%H:%M:%S")
    with open(CSV_FILE, "a") as f:
        f.write(f"{ts},{load:.2f},{temp:.2f}\n")


def main():
    print("[SYS] monitoring started")
    ensure_csv_header()

    while True:
        load = get_cpu_load()
        temp = get_temp_c()

        try:
            write_status(load, temp)
            append_csv(load, temp)
            print(f"[SYS] load={load:.2f} | temp={temp:.1f}C")
        except Exception as e:
            print(f"[SYS][ERROR] {e}")

        time.sleep(10)


if __name__ == "__main__":
    main()

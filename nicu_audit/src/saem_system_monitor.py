#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess

OUT_FILE = "/tmp/saem_sys.txt"

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

def get_temp():
    return get_temp_c()

def write_status(load, temp):
    try:
        with open(OUT_FILE, "w") as f:
            f.write(f"{load:.2f},{temp:.2f}")
    except Exception:
        pass

def main():
    print("[SYS] monitoring started")

    while True:
        load = get_cpu_load()
        temp = get_temp()

        write_status(load, temp)
        print(f"[SYS] load={load:.2f} | temp={temp:.1f}C")

        time.sleep(10)

if __name__ == "__main__":
    main()

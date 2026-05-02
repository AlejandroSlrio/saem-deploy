#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess

OUT_FILE = "/tmp/saem_sys.txt"
CSV_FILE = "/opt/nicu_audit/data/system_monitor.csv"

def append_csv(load, temp):
    try:
        ts = time.strftime("%Y-%m-%d,%H:%M:%S")
        with open(CSV_FILE, "a") as f:
            f.write(f"{ts},{load:.2f},{temp:.2f}\n")
    except:
        pass

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
	append_csv(load, temp)
        print(f"[SYS] load={load:.2f} | temp={temp:.1f}C")
	
	if not os.path.exists(CSV_FILE):
    	    with open(CSV_FILE, "w") as f:
                f.write("date,time,cpu,temp\n")
        
	time.sleep(10)

if __name__ == "__main__":
    main()

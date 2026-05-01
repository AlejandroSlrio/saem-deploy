#!/usr/bin/env python3

import time
import os
import subprocess
from datetime import datetime

OUT = "/opt/nicu_audit/data/system_monitor.csv"


# =====================
# TEMPERATURE
# =====================
def get_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return -1.0

# =====================
# CPU LOAD
# =====================
def get_load():
    try:
        return os.getloadavg()[0]  # 1-min average
    except Exception:
        return -1.0


# =====================
# CSV WRITE
# =====================
def write_row(ts, load, temp):

    new = not os.path.exists(OUT)

    try:
        with open(OUT, "a") as f:

            if new:
                f.write("date,time,load,temp\n")

            f.write(
                f"{ts.strftime('%Y-%m-%d')},"
                f"{ts.strftime('%H:%M:%S')},"
                f"{load:.2f},"
                f"{temp:.2f}\n"
            )

    except Exception:
        # nunca romper el loop por IO
        pass


# =====================
# MAIN
# =====================
print("[SYS] monitoring started")

while True:

    ts = datetime.now().replace(microsecond=0)

    load = get_load()
    temp = get_temp()

    write_row(ts, load, temp)

    print(f"[SYS] load={load:.2f} | temp={temp:.1f}C")

    time.sleep(10)   # cada 10 s (muy ligero)

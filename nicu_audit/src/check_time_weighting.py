#!/usr/bin/env python3
import math
import numpy as np
from scipy import signal

FS = 48000
CAL_OFFSET_DB = 110.0
TAU_FAST = 0.125
TAU_SLOW = 1.0

def design_A_weighting(fs: int):
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

    b_a, a_a = signal.zpk2tf(zeros, poles, k)
    b, a = signal.bilinear(b_a, a_a, fs=fs)

    # normalize at 1 kHz
    w = 2 * math.pi * 1000 / fs
    _, h = signal.freqz(b, a, worN=[w])
    b = b / abs(h[0])

    return b, a

def mean_square(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.mean(x * x))

def db_from_ms(ms, offset_db=0.0):
    return 10.0 * math.log10(max(float(ms), 1e-30)) + offset_db

def laeq_from_signal(x, bA, aA, offset_db=0.0):
    xA = signal.lfilter(bA, aA, x)
    msA = mean_square(xA)
    return db_from_ms(msA, offset_db)

def time_weighted_levels(xA, fs, tau_s, offset_db=0.0):
    """
    IEC-like time weighting:
    - square A-weighted signal
    - apply exponential smoothing to squared signal
    - convert to dB
    """
    alpha = math.exp(-(1.0 / fs) / tau_s)
    y = np.zeros_like(xA, dtype=np.float64)
    state = 0.0

    e = xA * xA
    for i, en in enumerate(e):
        state = alpha * state + (1.0 - alpha) * float(en)
        y[i] = db_from_ms(state, offset_db)

    return y

# Build test signal
# 1 s silence
# 2 s sine A1
# 2 s sine A2 = 2*A1
# 2 s silence

A1 = 0.1
A2 = 0.2

seg1 = np.zeros(FS)
t2 = np.arange(2 * FS) / FS
seg2 = A1 * np.sin(2 * np.pi * 1000 * t2)
seg3 = A2 * np.sin(2 * np.pi * 1000 * t2)
seg4 = np.zeros(2 * FS)

x = np.concatenate([seg1, seg2, seg3, seg4])

bA, aA = design_A_weighting(FS)
xA = signal.lfilter(bA, aA, x)

# Whole-segment reference LAeq values
L_eq_seg2 = laeq_from_signal(seg2, bA, aA, CAL_OFFSET_DB)
L_eq_seg3 = laeq_from_signal(seg3, bA, aA, CAL_OFFSET_DB)

# Time-weighted traces
LAF = time_weighted_levels(xA, FS, TAU_FAST, CAL_OFFSET_DB)
LAS = time_weighted_levels(xA, FS, TAU_SLOW, CAL_OFFSET_DB)

# Sample useful times
times_s = [
    1.0,   # just when tone starts
    1.1,
    1.5,
    2.0,
    2.5,
    3.0,   # after 2 s at A1
    3.1,   # after jump to A2
    3.5,
    4.0,
    5.0,   # after 2 s at A2
    5.1,   # silence starts
    5.5,
    6.0,
]

print("Reference steady-state LAeq values")
print(f"LAeq seg2 (A1) = {L_eq_seg2:.6f} dB")
print(f"LAeq seg3 (A2) = {L_eq_seg3:.6f} dB")
print()

print(f"{'t(s)':>6} {'LAF(dB)':>12} {'LAS(dB)':>12}")
for ts in times_s:
    idx = min(int(ts * FS), len(LAF) - 1)
    print(f"{ts:6.2f} {LAF[idx]:12.6f} {LAS[idx]:12.6f}")

print("\nChecks")
print("1) LAF should rise faster than LAS after level changes.")
print("2) In steady-state, both should approach the segment LAeq.")
print("3) After the signal stops, LAF should decay faster than LAS.")

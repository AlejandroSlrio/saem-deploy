#!/usr/bin/env python3
import math
import numpy as np
from scipy import signal

FS = 48000
DUR = 1.0
N = int(FS * DUR)
CAL_OFFSET_DB = 110.0

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

def laeq_from_signal(x, bA, aA, offset_db=0.0):
    xA = signal.lfilter(bA, aA, x)
    msA = mean_square(xA)
    return 10.0 * math.log10(msA + 1e-30) + offset_db

def db_from_energy(levels_db):
    levels_db = np.asarray(levels_db, dtype=np.float64)
    e = np.mean(10.0 ** (levels_db / 10.0))
    return 10.0 * math.log10(e)

# A-weighting
bA, aA = design_A_weighting(FS)

# Time base
t = np.arange(N) / FS

# -------------------------
# Test 1: 1 kHz sine, amp=A
# -------------------------
A1 = 0.1
x1 = A1 * np.sin(2 * np.pi * 1000 * t)
L1 = laeq_from_signal(x1, bA, aA, CAL_OFFSET_DB)

# -------------------------
# Test 2: 1 kHz sine, amp=2A
# Expected +6.0206 dB
# -------------------------
A2 = 0.2
x2 = A2 * np.sin(2 * np.pi * 1000 * t)
L2 = laeq_from_signal(x2, bA, aA, CAL_OFFSET_DB)
delta_12 = L2 - L1

# -------------------------
# Test 3: two half-second blocks
# first half amp=A, second half amp=2A
# Compare:
#   correct full-block LAeq
#   energy average of separate halves
#   WRONG arithmetic average in dB
# -------------------------
Nh = N // 2
th = np.arange(Nh) / FS

x_half1 = A1 * np.sin(2 * np.pi * 1000 * th)
x_half2 = A2 * np.sin(2 * np.pi * 1000 * th)

L_half1 = laeq_from_signal(x_half1, bA, aA, CAL_OFFSET_DB)
L_half2 = laeq_from_signal(x_half2, bA, aA, CAL_OFFSET_DB)

x_full = np.concatenate([x_half1, x_half2])
L_full_direct = laeq_from_signal(x_full, bA, aA, CAL_OFFSET_DB)

L_full_energy = db_from_energy([L_half1, L_half2])
L_full_wrong_avg = 0.5 * (L_half1 + L_half2)

print("=== TEST 1 ===")
print(f"L1 (1 kHz, amp={A1}) = {L1:.6f} dB")

print("\n=== TEST 2 ===")
print(f"L2 (1 kHz, amp={A2}) = {L2:.6f} dB")
print(f"Delta L2-L1          = {delta_12:.6f} dB")
print("Expected             = 6.020600 dB")

print("\n=== TEST 3 ===")
print(f"L_half1              = {L_half1:.6f} dB")
print(f"L_half2              = {L_half2:.6f} dB")
print(f"L_full_direct        = {L_full_direct:.6f} dB")
print(f"L_full_energy        = {L_full_energy:.6f} dB")
print(f"L_full_wrong_avg     = {L_full_wrong_avg:.6f} dB")
print(f"Direct - Energy      = {L_full_direct - L_full_energy:.9f} dB")
print(f"Direct - WrongAvg    = {L_full_direct - L_full_wrong_avg:.6f} dB")

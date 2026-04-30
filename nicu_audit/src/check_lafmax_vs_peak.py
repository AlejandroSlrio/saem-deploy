#!/usr/bin/env python3
import math
import numpy as np
from scipy import signal

FS = 48000
CAL_OFFSET_DB = 110.0
TAU_FAST = 0.125

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

def db20(x, eps=1e-20):
    return 20.0 * np.log10(max(float(x), eps))

def db10(x, eps=1e-30):
    return 10.0 * np.log10(max(float(x), eps))

def laf_trace_from_xA(xA, fs, tau_s=0.125, offset_db=0.0):
    alpha = math.exp(-(1.0 / fs) / tau_s)
    state = 0.0
    out = np.zeros_like(xA, dtype=np.float64)

    for i, s in enumerate(xA):
        p2 = float(s * s)
        state = alpha * state + (1.0 - alpha) * p2
        out[i] = db10(state) + offset_db

    return out

def lpeak_from_xA(xA, offset_db=0.0):
    # Peak of A-weighted waveform amplitude, converted with 20log10
    return db20(np.max(np.abs(xA))) + offset_db

bA, aA = design_A_weighting(FS)

# ------------------------------------------------
# Create three signals with same peak amplitude
# but different duration
# ------------------------------------------------
dur_total = 1.0
N = int(FS * dur_total)
t = np.arange(N) / FS

amp = 0.5
f0 = 1000.0

# 1) very short burst: 5 ms
burst_5ms = np.zeros(N)
n1 = int(0.005 * FS)
burst_5ms[:n1] = amp * np.sin(2 * np.pi * f0 * t[:n1])

# 2) medium burst: 100 ms
burst_100ms = np.zeros(N)
n2 = int(0.100 * FS)
burst_100ms[:n2] = amp * np.sin(2 * np.pi * f0 * t[:n2])

# 3) long tone: full 1 s
tone_1s = amp * np.sin(2 * np.pi * f0 * t)

signals = [
    ("burst_5ms", burst_5ms),
    ("burst_100ms", burst_100ms),
    ("tone_1s", tone_1s),
]

print(f"{'Signal':>12} {'Lpeak_A(dB)':>14} {'LAFmax(dB)':>14}")
for name, x in signals:
    xA = signal.lfilter(bA, aA, x)
    laf = laf_trace_from_xA(xA, FS, TAU_FAST, CAL_OFFSET_DB)
    lafmax = float(np.max(laf))
    lpeakA = float(lpeak_from_xA(xA, CAL_OFFSET_DB))
    print(f"{name:>12} {lpeakA:14.6f} {lafmax:14.6f}")

print("\nExpected behavior:")
print("- All three signals should have similar Lpeak_A because they share the same waveform peak.")
print("- LAFmax should be MUCH lower for the 5 ms burst than for the 100 ms burst.")
print("- LAFmax should be highest for the 1 s tone because Fast time weighting has time to build up.")

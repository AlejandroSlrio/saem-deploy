#!/usr/bin/env python3
import math
import numpy as np
from scipy import signal

FS = 48000

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

def a_weighting_analog_db(f):
    f = np.asarray(f, dtype=float)
    f2 = f * f
    ra_num = (12194.217 ** 2) * (f2 ** 2)
    ra_den = (
        (f2 + 20.598997 ** 2)
        * np.sqrt((f2 + 107.65265 ** 2) * (f2 + 737.86223 ** 2))
        * (f2 + 12194.217 ** 2)
    )
    ra = ra_num / ra_den
    a_db = 20 * np.log10(ra) + 2.0
    return a_db

b, a = design_A_weighting(FS)

test_freqs = np.array([20, 31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000], dtype=float)
w = 2 * np.pi * test_freqs / FS
_, h = signal.freqz(b, a, worN=w)

digital_db = 20 * np.log10(np.abs(h))
target_db = a_weighting_analog_db(test_freqs)
err_db = digital_db - target_db

print(f"{'Freq(Hz)':>10} {'Target(dB)':>12} {'Digital(dB)':>12} {'Error(dB)':>10}")
for f, t, d, e in zip(test_freqs, target_db, digital_db, err_db):
    print(f"{f:10.1f} {t:12.3f} {d:12.3f} {e:10.3f}")

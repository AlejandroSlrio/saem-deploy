#!/usr/bin/env python3
import numpy as np

txt_path = "/opt/nicu_audit/config/FIR_v3_coefficients.txt"
npy_path = "/opt/nicu_audit/config/nicu_eq_fir.npy"

taps = np.loadtxt(txt_path, dtype=np.float64)

print(f"Loaded {taps.size} taps")
print(f"First 5 taps: {taps[:5]}")
print(f"Last 5 taps:  {taps[-5:]}")
print(f"Symmetry check max abs diff: {np.max(np.abs(taps - taps[::-1])):.6e}")
print(f"Sum of taps (DC gain): {np.sum(taps):.6f}")

np.save(npy_path, taps)
print(f"Saved to: {npy_path}")

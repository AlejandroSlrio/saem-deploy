#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import signal
import subprocess
import math
import numpy as np

from scipy import signal as spsig
from scipy.signal import resample_poly
from tflite_runtime.interpreter import Interpreter


# =============================
# CONFIG
# =============================
DEVICE = "plughw:CARD=USBC,DEV=0"
RATE = 48000
INT16_FS = 32768.0

YAMNET_PATH = "/opt/saem/models/yamnet/yamnet.tflite"
MODEL_PATH = "/opt/saem/models/context_model.tflite"

LABELS = ["alarms", "impulsive", "mechanical", "speech"]
CAL_OFFSET_DB = 110.0
YAMNET_INPUT_LEN = 15600

RUNNING = True


# =============================
# SIGNAL HANDLING
# =============================
def stop(sig, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)


# =============================
# UTILS
# =============================
def db10(x, eps=1e-30):
    return 10.0 * math.log10(max(float(x), eps))


def mean_square(x):
    return float(np.mean(x * x))


# =============================
# A-WEIGHTING
# =============================
def a_weighting_iir(fs):
    f1, f2, f3, f4 = 20.6, 107.7, 737.9, 12194.2
    zeros = [0, 0, 0, 0]
    poles = [-f1, -f1, -f2, -f3, -f4, -f4]
    k = f4 ** 2

    b, a = spsig.zpk2tf(zeros, poles, k)
    b, a = spsig.bilinear(b, a, fs)
    return b, a


class IIRFilter:
    def __init__(self, b, a):
        self.b = b
        self.a = a
        self.zi = spsig.lfilter_zi(b, a) * 0

    def process(self, x):
        y, self.zi = spsig.lfilter(self.b, self.a, x, zi=self.zi)
        return y


# =============================
# MODEL INIT
# =============================
def init_models():
    yamnet = Interpreter(model_path=YAMNET_PATH)

    # 🔥 IMPORTANTE: YAMNet tiene input variable, pero hay que fijarlo
    yam_in0 = yamnet.get_input_details()[0]
    yamnet.resize_tensor_input(yam_in0["index"], [YAMNET_INPUT_LEN], strict=False)
    yamnet.allocate_tensors()

    ctx_model = Interpreter(model_path=MODEL_PATH)
    ctx_model.allocate_tensors()

    print("\n=== YAMNET INPUT ===")
    for i, inp in enumerate(yamnet.get_input_details()):
        print(f"Input {i} shape: {inp['shape']}, shape_signature: {inp.get('shape_signature')}")
    print("====================")

    print("\n=== YAMNET OUTPUTS ===")
    for i, o in enumerate(yamnet.get_output_details()):
        print(f"Index {i} -> shape {o['shape']}, shape_signature: {o.get('shape_signature')}")
    print("======================")

    print("\n=== CONTEXT MODEL INPUT ===")
    for i, inp in enumerate(ctx_model.get_input_details()):
        print(f"Input {i} shape: {inp['shape']}, shape_signature: {inp.get('shape_signature')}")
    print("===========================\n")

    return yamnet, ctx_model


# =============================
# CONTEXT LAYER
# =============================
def run_context(yamnet, ctx_model, x48):
    try:
        # 1) Resample 48k -> 16k
        x16 = resample_poly(x48, 16000, 48000)

        # 2) Ajustar longitud exacta
        if len(x16) > YAMNET_INPUT_LEN:
            x16 = x16[:YAMNET_INPUT_LEN]
        elif len(x16) < YAMNET_INPUT_LEN:
            x16 = np.pad(x16, (0, YAMNET_INPUT_LEN - len(x16)))

        # 3) YAMNet espera 1D
        x16 = np.ascontiguousarray(x16.astype(np.float32))

        yam_in = yamnet.get_input_details()[0]
        yam_outs = yamnet.get_output_details()

        yamnet.set_tensor(yam_in["index"], x16)
        yamnet.invoke()

        # 4) Buscar embeddings
        emb = None
        for o in yam_outs:
            out = yamnet.get_tensor(o["index"])
            if out.ndim == 2 and out.shape[1] == 1024:
                emb = out
                break

        if emb is None:
            raise RuntimeError("Embeddings not found in YAMNet outputs")

        emb_mean = np.ascontiguousarray(emb[0].astype(np.float32))  # (1024,)

        # 5) Context model espera (1,1024)
        ctx_in = ctx_model.get_input_details()[0]
        ctx_out = ctx_model.get_output_details()[0]

        ctx_input = np.ascontiguousarray(emb_mean.reshape(1, 1024), dtype=np.float32)

        ctx_model.set_tensor(ctx_in["index"], ctx_input)
        ctx_model.invoke()

        out = ctx_model.get_tensor(ctx_out["index"])
        out = np.asarray(out, dtype=np.float32).reshape(-1)

        idx = int(np.argmax(out))
        conf = float(out[idx])
        label = LABELS[idx] if 0 <= idx < len(LABELS) else f"class_{idx}"

        return label, conf

    except Exception as e:
        print("[CTX ERROR]", e)
        return "error", float("nan")


# =============================
# AUDIO
# =============================
def start_audio():
    cmd = [
        "arecord",
        "-D", DEVICE,
        "-c", "1",
        "-r", str(RATE),
        "-f", "S16_LE",
        "-t", "raw",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


# =============================
# MAIN
# =============================
def main():
    yamnet, ctx_model = init_models()

    bA, aA = a_weighting_iir(RATE)
    Aflt = IIRFilter(bA, aA)

    proc = start_audio()

    samples = int(RATE * 1.0)
    bytes_chunk = samples * 2  # int16 mono

    print("[SAEM v4.3] running (YAMNet resized fix)")

    try:
        while RUNNING:
            raw = proc.stdout.read(bytes_chunk)
            if len(raw) != bytes_chunk:
                print("[ERROR] audio read failed")
                break

            x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / INT16_FS

            # Physical layer
            xA = Aflt.process(x)
            laeq = db10(mean_square(xA)) + CAL_OFFSET_DB

            # Context layer
            label, conf = run_context(yamnet, ctx_model, x)

            print(f"LAeq={laeq:.2f} dB(A) | {label} ({conf:.2f})")

    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from tflite_runtime.interpreter import Interpreter

YAMNET_PATH = "/opt/saem/models/yamnet/yamnet.tflite"
MODEL_PATH = "/opt/saem/models/context_model.tflite"

def show_model(path, name):
    print(f"\n=== {name} ===")
    interp = Interpreter(model_path=path)
    interp.allocate_tensors()

    print("INPUTS:")
    for i, d in enumerate(interp.get_input_details()):
        print(
            f"  {i}: name={d['name']}, shape={d['shape']}, "
            f"shape_signature={d.get('shape_signature')}, dtype={d['dtype']}"
        )

    print("OUTPUTS:")
    for i, d in enumerate(interp.get_output_details()):
        print(
            f"  {i}: name={d['name']}, shape={d['shape']}, "
            f"shape_signature={d.get('shape_signature')}, dtype={d['dtype']}"
        )

show_model(YAMNET_PATH, "YAMNET")
show_model(MODEL_PATH, "CONTEXT MODEL")

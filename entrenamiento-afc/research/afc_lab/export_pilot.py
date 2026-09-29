"""Export the exploratory GRU with explicit streaming state; not an Engine release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import numpy as np
import torch
import onnx
import onnxruntime as ort
from .checkpoint import load_checkpoint
from .corpus import sha256
from .models import CausalSpectralGru


def export(checkpoint, destination):
    checkpoint, destination = Path(checkpoint), Path(destination)
    if destination.exists():
        raise FileExistsError("Refusing to overwrite an exported model")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = payload["config"]
    if config.get("model") != "causal_gru_pipeline_pilot_not_l3c":
        raise ValueError("Only the documented GRU prototype is supported by this exporter")
    model = CausalSpectralGru(hidden=config["hidden"]).eval()
    load_checkpoint(checkpoint, model, expected_config=config, restore_rng=False)
    torch.set_num_threads(1)
    torch.manual_seed(918)
    spectrum = torch.randn(1, 7, 1026)
    initial = torch.randn(1, 1, config["hidden"]) * 0.1
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.onnx")
    torch.onnx.export(model, (spectrum, initial), str(temporary),
                      input_names=["spectrum", "state_in"], output_names=["enhanced", "state_out"],
                      dynamic_axes={"spectrum": {1: "frames"}, "enhanced": {1: "frames"}},
                      opset_version=17, dynamo=False)
    onnx.checker.check_model(str(temporary))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(str(temporary), sess_options=options, providers=["CPUExecutionProvider"])
    with torch.no_grad():
        expected, expected_state = model(spectrum, initial)
    whole, whole_state = session.run(None, {"spectrum": spectrum.numpy(), "state_in": initial.numpy()})
    state = initial.numpy()
    pieces = []
    for frame in spectrum.numpy().transpose(1, 0, 2):
        piece, state = session.run(None, {"spectrum": frame[:, None, :], "state_in": state})
        pieces.append(piece)
    streamed = np.concatenate(pieces, axis=1)
    for actual, reference in ((whole, expected.numpy()), (whole_state, expected_state.numpy()),
                              (streamed, whole), (state, whole_state)):
        np.testing.assert_allclose(actual, reference, atol=1e-5, rtol=1e-4)
    frame = spectrum[:, :1].numpy()
    for _ in range(20):
        _, state = session.run(None, {"spectrum": frame, "state_in": state})
    durations = []
    for _ in range(200):
        start = perf_counter()
        _, state = session.run(None, {"spectrum": frame, "state_in": state})
        durations.append((perf_counter() - start) * 1000)
    del session
    temporary.replace(destination)
    metadata = {
        "schema_version": 1, "model": config["model"], "engine_release": False,
        "reason": "Exploratory GRU; L3C architecture and low-latency audio synthesis still pending",
        "sample_rate": 48000, "frame_samples": 960, "hop_samples": 240, "fft_samples": 1024,
        "analysis_window": "hann_symmetric", "input_layout": "batch,time,interleaved_real_imag",
        "input_shape": [1, "frames", 1026], "state_shape": [1, 1, config["hidden"]],
        "initial_state": "zeros_at_stream_start_only", "target": "source_before_forward_gain_and_delay",
        "checkpoint_sha256": sha256(checkpoint), "onnx_sha256": sha256(destination),
        "maximum_torch_onnx_error": float(np.max(np.abs(whole - expected.numpy()))),
        "maximum_streaming_error": float(np.max(np.abs(streamed - whole))),
        "inference_only_cpu_ms": {f"p{q}": float(np.percentile(durations, q)) for q in (50, 95, 99)},
        "latency_warning": "Inference timings exclude STFT, synthesis, queues, and audio hardware",
        "torch": str(torch.__version__), "onnxruntime": ort.__version__,
    }
    destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.checkpoint, args.output), indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np


def _frames(signal: np.ndarray, frame: int = 960, hop: int = 240, fft: int = 1024) -> np.ndarray:
    count = 1 + max(0, (signal.size - frame) // hop)
    indices = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    windowed = signal[indices] * np.hanning(frame)[None, :]
    spectrum = np.fft.rfft(windowed, n=fft, axis=1)
    return np.stack((spectrum.real, spectrum.imag), axis=-1).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and export AFC spectral candidates")
    parser.add_argument("dataset", help="NPZ containing input and target arrays [items, samples]")
    parser.add_argument("--model", choices=("mlp", "gru", "deepmfc"), default="gru")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--output", default="models/candidate.onnx")
    args = parser.parse_args()

    try:
        import torch
        from torch import nn
        from .models import create_model
    except ImportError as exc:
        raise SystemExit(str(exc)) from exc

    dataset = np.load(args.dataset)
    inputs = np.stack([_frames(item) for item in dataset["input"]])
    targets = np.stack([_frames(item) for item in dataset["target"]])
    model = create_model(args.model)
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    loss_function = nn.MSELoss()
    x = torch.from_numpy(inputs)
    y = torch.from_numpy(targets)
    if args.model in ("mlp", "gru"):
        x = x.reshape(-1, x.shape[-2] * 2)
        y = y.reshape(-1, y.shape[-2] * 2)
        if args.model == "gru":
            x = x.reshape(inputs.shape[0], inputs.shape[1], -1)
            y = y.reshape(targets.shape[0], targets.shape[1], -1)
    for _ in range(args.epochs):
        optimizer.zero_grad()
        prediction = model(x)
        if isinstance(prediction, tuple):
            prediction = prediction[0]
        loss = loss_function(prediction, y)
        loss.backward()
        optimizer.step()

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    example = x[:1]
    dynamic_axes = (
        {"spectrum": {0: "frames"}, "enhanced": {0: "frames"}}
        if args.model == "mlp"
        else {"spectrum": {1: "frames"}, "enhanced": {1: "frames"}}
    )
    torch.onnx.export(
        model,
        example,
        str(destination),
        input_names=["spectrum"],
        output_names=["enhanced", "state"] if args.model != "mlp" else ["enhanced"],
        dynamic_axes=dynamic_axes,
        opset_version=17,
    )
    import onnxruntime as ort

    with torch.no_grad():
        torch_output = model(example)
        if isinstance(torch_output, tuple):
            torch_output = torch_output[0]
    session = ort.InferenceSession(str(destination), providers=["CPUExecutionProvider"])
    onnx_output = session.run(None, {"spectrum": example.numpy()})[0]
    maximum_error = float(np.max(np.abs(torch_output.numpy() - onnx_output)))
    if maximum_error > 1.0e-4:
        raise RuntimeError(f"PyTorch/ONNX mismatch: max_abs_error={maximum_error}")
    print(f"exported {destination}; max_abs_error={maximum_error:.3e}")


if __name__ == "__main__":
    main()

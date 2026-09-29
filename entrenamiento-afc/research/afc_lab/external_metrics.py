from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np

from .io import write_wav


def stoi(reference: np.ndarray, estimate: np.ndarray, sample_rate: int, extended: bool = False) -> float:
    try:
        from pystoi import stoi as calculate
    except ImportError as exc:
        raise RuntimeError("Install pystoi to calculate STOI/ESTOI") from exc
    return float(calculate(reference, estimate, sample_rate, extended=extended))


def pesq_voice(reference: np.ndarray, estimate: np.ndarray, sample_rate: int) -> float:
    if sample_rate not in (8000, 16000):
        raise ValueError("PESQ is only evaluated at 8 or 16 kHz; resample voice explicitly")
    try:
        from pesq import pesq as calculate
    except ImportError as exc:
        raise RuntimeError("Install pesq to calculate PESQ") from exc
    mode = "wb" if sample_rate == 16000 else "nb"
    return float(calculate(sample_rate, reference, estimate, mode))


def visqol(reference: np.ndarray, estimate: np.ndarray, sample_rate: int = 48_000) -> float:
    executable = shutil.which("visqol")
    if executable is None:
        raise RuntimeError("ViSQOL executable was not found on PATH")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        reference_path = root / "reference.wav"
        estimate_path = root / "estimate.wav"
        write_wav(reference_path, reference, sample_rate)
        write_wav(estimate_path, estimate, sample_rate)
        completed = subprocess.run(
            [executable, "--reference_file", str(reference_path),
             "--degraded_file", str(estimate_path), "--use_speech_mode=false"],
            check=True, capture_output=True, text=True,
        )
    for line in completed.stdout.splitlines():
        if "MOS-LQO" in line:
            return float(line.rsplit(" ", 1)[-1])
    raise RuntimeError("ViSQOL output did not contain MOS-LQO")

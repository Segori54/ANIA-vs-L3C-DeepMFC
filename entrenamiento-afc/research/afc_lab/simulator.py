from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable
import numpy as np


Processor = Callable[[float, float], float]


@dataclass(frozen=True)
class SimulationResult:
    microphone: np.ndarray
    output: np.ndarray
    feedback: np.ndarray
    elapsed_seconds: float
    clipped_samples: int


def maximum_stable_gain(path: np.ndarray, fft_size: int = 16_384) -> float:
    response = np.fft.rfft(path, n=fft_size)
    return float(1.0 / (np.max(np.abs(response)) + 1.0e-12))


def simulate_closed_loop(
    source: np.ndarray,
    path: np.ndarray,
    gain_margin_db: float,
    processor: Processor | None = None,
    changed_path: np.ndarray | None = None,
    change_sample: int | None = None,
    limiter: float = 0.98,
) -> SimulationResult:
    """Sample-accurate mono feedback loop with an optional AFC processor."""
    path = np.asarray(path, dtype=np.float32)
    alternate = np.asarray(changed_path, dtype=np.float32) if changed_path is not None else None
    max_length = max(path.size, alternate.size if alternate is not None else 0)
    history = np.zeros(max_length, dtype=np.float32)
    microphone = np.zeros_like(source, dtype=np.float32)
    output = np.zeros_like(source, dtype=np.float32)
    feedback = np.zeros_like(source, dtype=np.float32)
    base_gain = maximum_stable_gain(path) * 10.0 ** (-gain_margin_db / 20.0)
    clipped = 0
    start = perf_counter()

    for index, wanted in enumerate(source):
        active_path = alternate if alternate is not None and change_sample is not None and index >= change_sample else path
        feedback_sample = float(np.dot(active_path, history[: active_path.size]))
        mic_sample = float(wanted) + feedback_sample
        previous_output = float(history[0]) if history.size else 0.0
        clean = processor(mic_sample, previous_output) if processor is not None else mic_sample
        emitted = base_gain * clean
        if abs(emitted) > limiter:
            emitted = float(np.clip(emitted, -limiter, limiter))
            clipped += 1
        history[1:] = history[:-1]
        history[0] = emitted
        microphone[index] = mic_sample
        feedback[index] = feedback_sample
        output[index] = emitted

    return SimulationResult(microphone, output, feedback, perf_counter() - start, clipped)

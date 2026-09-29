from __future__ import annotations

from dataclasses import dataclass
import numpy as np


def estimate_fir(
    probe: np.ndarray,
    microphone: np.ndarray,
    filter_length: int,
    regularisation: float = 1.0e-6,
) -> np.ndarray:
    """Estimate a causal feedback path from an independent short probe.

    This solves the regularised Wiener least-squares problem. It is the
    reproducible reference estimator used to validate the real-time C++ path.
    """
    if probe.ndim != 1 or microphone.ndim != 1:
        raise ValueError("probe and microphone must be mono vectors")
    if probe.size != microphone.size or probe.size < filter_length:
        raise ValueError("probe and microphone lengths must match and cover the FIR")
    padded = np.pad(probe.astype(np.float64), (filter_length - 1, 0))
    windows = np.lib.stride_tricks.sliding_window_view(padded, filter_length)
    design = windows[:, ::-1]
    gram = design.T @ design
    rhs = design.T @ microphone.astype(np.float64)
    ridge = regularisation * max(float(np.trace(gram)) / filter_length, 1.0)
    return np.linalg.solve(gram + ridge * np.eye(filter_length), rhs).astype(np.float32)


@dataclass
class FixedAfc:
    coefficients: np.ndarray

    def __post_init__(self) -> None:
        self.coefficients = np.asarray(self.coefficients, dtype=np.float32)
        self.history = np.zeros(self.coefficients.size, dtype=np.float32)

    def reset(self) -> None:
        self.history.fill(0.0)

    def cancel_sample(self, microphone_sample: float, loudspeaker_reference: float) -> float:
        self.history[1:] = self.history[:-1]
        self.history[0] = loudspeaker_reference
        estimate = float(np.dot(self.coefficients, self.history))
        return microphone_sample - estimate


@dataclass
class ReactiveAfc:
    """Frozen FIR that adopts a newly calibrated path after a detected change."""

    initial_coefficients: np.ndarray
    recalibrated_coefficients: np.ndarray
    change_sample: int
    detection_samples: int
    calibration_samples: int

    def __post_init__(self) -> None:
        self._sample = 0
        self._active = FixedAfc(self.initial_coefficients)

    @property
    def recovery_sample(self) -> int:
        return self.change_sample + self.detection_samples + self.calibration_samples

    def cancel_sample(self, microphone_sample: float, loudspeaker_reference: float) -> float:
        if self._sample == self.recovery_sample:
            self._active = FixedAfc(self.recalibrated_coefficients)
        output = self._active.cancel_sample(microphone_sample, loudspeaker_reference)
        self._sample += 1
        return output


def calibration_response(probe: np.ndarray, path: np.ndarray) -> np.ndarray:
    return np.convolve(probe, path, mode="full")[: probe.size].astype(np.float32)

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class HowlingResult:
    detected: bool
    frequency_hz: float
    peak_to_average_db: float
    persistence: int


class HowlingDetector:
    """Low-cost PAPR + inter-frame persistence detector."""

    def __init__(
        self,
        sample_rate: int,
        frame_size: int = 1024,
        threshold_db: float = 18.0,
        required_frames: int = 3,
        frequency_tolerance_bins: int = 1,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.threshold_db = threshold_db
        self.required_frames = required_frames
        self.frequency_tolerance_bins = frequency_tolerance_bins
        self.window = np.hanning(frame_size).astype(np.float32)
        self._last_bin = -10_000
        self._persistence = 0

    def reset(self) -> None:
        self._last_bin = -10_000
        self._persistence = 0

    def process_frame(self, frame: np.ndarray) -> HowlingResult:
        if frame.size != self.frame_size:
            raise ValueError(f"expected {self.frame_size} samples")
        power = np.abs(np.fft.rfft(frame * self.window)) ** 2
        if power.size <= 2:
            return HowlingResult(False, 0.0, 0.0, 0)
        power[0] = 0.0
        peak_bin = int(np.argmax(power))
        average = float(np.mean(power[1:])) + 1.0e-30
        ratio_db = 10.0 * np.log10(float(power[peak_bin]) / average + 1.0e-30)
        if ratio_db >= self.threshold_db and abs(peak_bin - self._last_bin) <= self.frequency_tolerance_bins:
            self._persistence += 1
        elif ratio_db >= self.threshold_db:
            self._persistence = 1
        else:
            self._persistence = 0
        self._last_bin = peak_bin
        frequency = peak_bin * self.sample_rate / self.frame_size
        return HowlingResult(
            self._persistence >= self.required_frames,
            float(frequency),
            float(ratio_db),
            self._persistence,
        )

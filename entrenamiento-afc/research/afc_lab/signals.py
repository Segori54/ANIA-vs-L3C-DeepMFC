from __future__ import annotations

import numpy as np


def voice_like(sample_rate: int, samples: int, rng: np.random.Generator) -> np.ndarray:
    """Deterministic voiced/unvoiced surrogate used for tests without external datasets."""
    time = np.arange(samples, dtype=np.float64) / sample_rate
    f0 = 120.0 + 35.0 * np.sin(2.0 * np.pi * 0.7 * time)
    phase = 2.0 * np.pi * np.cumsum(f0) / sample_rate
    signal = np.zeros(samples, dtype=np.float64)
    for harmonic in range(1, 9):
        signal += np.sin(harmonic * phase + 0.17 * harmonic) / harmonic
    envelope = 0.5 * (1.0 + np.sin(2.0 * np.pi * 2.3 * time))
    envelope *= (np.sin(2.0 * np.pi * 0.45 * time) > -0.55).astype(np.float64)
    unvoiced = rng.standard_normal(samples) * 0.04
    result = 0.18 * envelope * signal + unvoiced * (1.0 - 0.7 * envelope)
    peak = np.max(np.abs(result))
    return (result / max(peak, 1.0e-12) * 0.35).astype(np.float32)


def make_feedback_path(
    length: int, direct_delay: int, decay: float, rng: np.random.Generator
) -> np.ndarray:
    path = np.zeros(length, dtype=np.float64)
    indices = np.arange(length - direct_delay, dtype=np.float64)
    tail = rng.standard_normal(indices.size) * np.exp(-decay * indices)
    tail[0] += 1.0
    path[direct_delay:] = tail
    path /= max(np.linalg.norm(path), 1.0e-12)
    return (0.28 * path).astype(np.float32)


def add_noise_at_snr(
    signal: np.ndarray, snr_db: float | None, rng: np.random.Generator
) -> np.ndarray:
    if snr_db is None:
        return signal.copy()
    noise = rng.standard_normal(signal.size).astype(np.float64)
    signal_power = float(np.mean(np.square(signal, dtype=np.float64)))
    noise_power = float(np.mean(noise * noise))
    scale = np.sqrt(signal_power / (noise_power * 10.0 ** (snr_db / 10.0) + 1.0e-30))
    return (signal + scale * noise).astype(np.float32)


def probe_noise(samples: int, level_dbfs: float, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(samples).astype(np.float64)
    noise /= max(np.sqrt(np.mean(noise * noise)), 1.0e-12)
    return (noise * 10.0 ** (level_dbfs / 20.0)).astype(np.float32)

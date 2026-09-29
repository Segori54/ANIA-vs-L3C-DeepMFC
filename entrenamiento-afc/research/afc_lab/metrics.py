from __future__ import annotations

import numpy as np


EPS = 1.0e-12


def _aligned(reference: np.ndarray, estimate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = min(reference.size, estimate.size)
    return reference[:length].astype(np.float64), estimate[:length].astype(np.float64)


def snr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    ref, est = _aligned(reference, estimate)
    return float(10.0 * np.log10((np.sum(ref * ref) + EPS) / (np.sum((ref - est) ** 2) + EPS)))


def sdr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    return snr_db(reference, estimate)


def si_sdr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    ref, est = _aligned(reference, estimate)
    ref -= np.mean(ref)
    est -= np.mean(est)
    scale = float(np.dot(est, ref) / (np.dot(ref, ref) + EPS))
    target = scale * ref
    residual = est - target
    return float(10.0 * np.log10((np.sum(target * target) + EPS) / (np.sum(residual * residual) + EPS)))


def erle_db(feedback: np.ndarray, residual: np.ndarray) -> float:
    original, remaining = _aligned(feedback, residual)
    return float(10.0 * np.log10((np.sum(original * original) + EPS) / (np.sum(remaining * remaining) + EPS)))


def log_spectral_distance_db(reference: np.ndarray, estimate: np.ndarray, fft_size: int = 1024) -> float:
    ref, est = _aligned(reference, estimate)
    frames = max(1, (ref.size + fft_size - 1) // fft_size)
    ref = np.pad(ref, (0, frames * fft_size - ref.size))
    est = np.pad(est, (0, frames * fft_size - est.size))
    ref_spectrum = np.abs(np.fft.rfft(ref.reshape(frames, fft_size), axis=1)) + EPS
    est_spectrum = np.abs(np.fft.rfft(est.reshape(frames, fft_size), axis=1)) + EPS
    difference = 20.0 * np.log10(ref_spectrum) - 20.0 * np.log10(est_spectrum)
    return float(np.mean(np.sqrt(np.mean(difference * difference, axis=1))))


def confidence_interval_95(values: list[float]) -> tuple[float, float, float]:
    data = np.asarray(values, dtype=np.float64)
    mean = float(np.mean(data))
    if data.size < 2:
        return mean, mean, mean
    half_width = 1.96 * float(np.std(data, ddof=1)) / np.sqrt(data.size)
    return mean, mean - half_width, mean + half_width

from __future__ import annotations

import argparse
import json
import shutil
import wave
from pathlib import Path

import numpy as np


DEMO_FILES = {
    "01_objetivo.wav": "target.wav",
    "02_sin_procesamiento.wav": "bypass_output.wav",
    "03_patel_calibracion_manual.wav": "patel_manual_output.wav",
    "04_patel_cambio_de_camino.wav": "patel_reactive_output.wav",
}


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError(f"expected mono 16-bit PCM WAV: {path}")
        sample_rate = stream.getframerate()
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
    return samples.astype(np.float64) / 32768.0, sample_rate


def _normalise_rms(signal: np.ndarray, target_dbfs: float = -20.0) -> np.ndarray:
    """Match demonstration clips by RMS, then enforce a conservative peak ceiling."""
    rms = float(np.sqrt(np.mean(np.square(signal))) + 1.0e-12)
    target_rms = 10.0 ** (target_dbfs / 20.0)
    adjusted = signal * (target_rms / rms)
    peak = float(np.max(np.abs(adjusted)) + 1.0e-12)
    ceiling = 10.0 ** (-1.0 / 20.0)
    if peak > ceiling:
        adjusted *= ceiling / peak
    fade_samples = min(960, adjusted.size // 4)
    if fade_samples:
        ramp = np.linspace(0.0, 1.0, fade_samples, endpoint=False)
        adjusted[:fade_samples] *= ramp
        adjusted[-fade_samples:] *= ramp[::-1]
    return adjusted


def _write_wav(path: Path, signal: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.round(np.clip(signal, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm.tobytes())


def export_demo(raw_dir: Path, destination: Path) -> None:
    audio_dir = destination / "audio_ab"
    audio_dir.mkdir(parents=True, exist_ok=True)
    sample_rates: set[int] = set()
    for output_name, input_name in DEMO_FILES.items():
        signal, sample_rate = _read_wav(raw_dir / "audio" / input_name)
        sample_rates.add(sample_rate)
        _write_wav(audio_dir / output_name, _normalise_rms(signal), sample_rate)
    if sample_rates != {48_000}:
        raise ValueError(f"unexpected sample rates: {sorted(sample_rates)}")

    evidence_dir = destination / "evidencia"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "results.csv", "summary.json"):
        shutil.copy2(raw_dir / name, evidence_dir / name)

    metadata = {
        "purpose": "Muestra demostrativa para presentaciones; excluida de entrenamiento.",
        "signal": "Señal sintética determinista tipo voz (voice_like).",
        "normalisation": "RMS individual a -20 dBFS, techo de pico -1 dBFS y fundidos de 20 ms.",
        "interpretation": "Resultados preliminares en simulación; no constituyen la campaña final.",
        "sample_rate_hz": 48_000,
        "seed": 20260826,
        "playback_order": list(DEMO_FILES),
    }
    (destination / "demo_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the thesis presentation A/B package")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export_demo(args.raw_dir, args.destination)


if __name__ == "__main__":
    main()

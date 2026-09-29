from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
import numpy as np

from . import __version__
from .config import ExperimentConfig
from .io import write_json, write_metric_svg, write_wav
from .metrics import erle_db, log_spectral_distance_db, si_sdr_db, snr_db
from .patel import FixedAfc, ReactiveAfc, calibration_response, estimate_fir
from .signals import add_noise_at_snr, make_feedback_path, probe_noise, voice_like
from .simulator import maximum_stable_gain, simulate_closed_loop
from .howling import HowlingDetector


def _howling_statistics(signal: np.ndarray, sample_rate: int) -> tuple[int, float]:
    detector = HowlingDetector(sample_rate)
    frames = signal.size // detector.frame_size
    detections = 0
    first_ms = -1.0
    active = False
    for index in range(frames):
        frame = signal[index * detector.frame_size:(index + 1) * detector.frame_size]
        detected = detector.process_frame(frame).detected
        if detected and not active:
            detections += 1
            if first_ms < 0.0:
                first_ms = (index + 1) * detector.frame_size * 1000.0 / sample_rate
        active = detected
    return detections, first_ms


def _evaluate(
    method: str,
    source: np.ndarray,
    target: np.ndarray,
    path: np.ndarray,
    config: ExperimentConfig,
    processor=None,
    changed_path: np.ndarray | None = None,
) -> tuple[dict[str, float | str], Any]:
    change_sample = None
    if config.patel.path_change_seconds is not None:
        change_sample = int(config.patel.path_change_seconds * config.sample_rate)
    result = simulate_closed_loop(
        source,
        path,
        config.gain_margin_db,
        processor=processor,
        changed_path=changed_path,
        change_sample=change_sample,
    )
    # The processed output includes the loop gain.  Returning it to the
    # processor-input domain isolates the feedback component left after AFC.
    loop_gain = maximum_stable_gain(path) * 10.0 ** (-config.gain_margin_db / 20.0)
    residual_feedback = result.output / max(loop_gain, 1.0e-12) - source
    output_snr = snr_db(target, result.output)
    input_domain_snr = snr_db(target, loop_gain * result.microphone)
    episodes, first_detection_ms = _howling_statistics(result.microphone, config.sample_rate)
    row: dict[str, float | str] = {
        "method": method,
        "snr_db": output_snr,
        "delta_snr_db": output_snr - input_domain_snr,
        "si_sdr_db": si_sdr_db(target, result.output),
        "lsd_db": log_spectral_distance_db(target, result.output),
        "erle_db": erle_db(result.feedback, residual_feedback),
        "elapsed_seconds": result.elapsed_seconds,
        "rtf": result.elapsed_seconds / config.duration_seconds,
        "clipped_samples": float(result.clipped_samples),
        "howling_episodes": float(episodes),
        "first_howling_detection_ms": first_detection_ms,
    }
    return row, result


def run_experiment(config: ExperimentConfig) -> list[dict[str, float | str]]:
    rng = np.random.default_rng(config.seed)
    samples = int(config.duration_seconds * config.sample_rate)
    clean_source = voice_like(config.sample_rate, samples, rng)
    source = add_noise_at_snr(clean_source, config.snr_db, rng)
    path = make_feedback_path(
        config.path.length, config.path.direct_delay, config.path.decay, rng
    )
    changed_path = make_feedback_path(
        config.path.length,
        min(config.path.direct_delay + 11, config.path.length - 1),
        config.path.decay * 0.8,
        rng,
    )
    gain = maximum_stable_gain(path) * 10.0 ** (-config.gain_margin_db / 20.0)
    target = gain * source

    probe_samples = int(config.patel.probe_duration_ms * config.sample_rate / 1000)
    probe = probe_noise(probe_samples, config.patel.probe_level_dbfs, rng)
    calibration_mic = calibration_response(probe, path)
    estimated = estimate_fir(
        probe,
        calibration_mic,
        config.patel.filter_length,
        config.patel.regularisation,
    )

    rows: list[dict[str, float | str]] = []
    outputs: dict[str, Any] = {}
    bypass_row, bypass = _evaluate("bypass", source, target, path, config)
    rows.append(bypass_row)
    outputs["bypass"] = bypass

    manual_filter = FixedAfc(estimated)
    manual_row, manual = _evaluate(
        "patel_manual", source, target, path, config, manual_filter.cancel_sample
    )
    rows.append(manual_row)
    outputs["patel_manual"] = manual

    if config.patel.reactive:
        changed_estimated = estimate_fir(
            probe,
            calibration_response(probe, changed_path),
            config.patel.filter_length,
            config.patel.regularisation,
        )
        path_change = (
            int(config.patel.path_change_seconds * config.sample_rate)
            if config.patel.path_change_seconds is not None else samples + 1
        )
        reactive_filter = ReactiveAfc(
            estimated,
            changed_estimated,
            path_change,
            detection_samples=1024 * 3,
            calibration_samples=probe_samples,
        )
        reactive_row, reactive = _evaluate(
            "patel_reactive",
            source,
            target,
            path,
            config,
            reactive_filter.cancel_sample,
            changed_path=changed_path,
        )
        rows.append(reactive_row)
        reactive_row["detection_ms"] = 1024 * 3 * 1000.0 / config.sample_rate
        reactive_row["recovery_ms"] = (
            1024 * 3 + probe_samples
        ) * 1000.0 / config.sample_rate
        outputs["patel_reactive"] = reactive

    destination = Path(config.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "afc_lab_version": __version__,
        "config": config.to_dict(),
        "derived": {
            "samples": samples,
            "open_loop_gain": gain,
            "maximum_stable_gain": maximum_stable_gain(path),
            "estimated_fir_error": float(
                np.linalg.norm(estimated - path[: estimated.size])
                / (np.linalg.norm(path[: estimated.size]) + 1.0e-12)
            ),
        },
    }
    write_json(destination / "manifest.json", manifest)
    write_json(destination / "summary.json", rows)
    with (destination / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    write_wav(destination / "audio" / "source.wav", source, config.sample_rate)
    write_wav(destination / "audio" / "target.wav", target, config.sample_rate)
    write_wav(destination / "audio" / "probe.wav", probe, config.sample_rate)
    for method, result in outputs.items():
        write_wav(destination / "audio" / f"{method}_microphone.wav", result.microphone, config.sample_rate)
        write_wav(destination / "audio" / f"{method}_output.wav", result.output, config.sample_rate)
    write_metric_svg(destination / "metrics.svg", rows)
    return rows

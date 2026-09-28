from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
import numpy as np

from afc_lab.config import ExperimentConfig, PatelConfig, PathConfig
from afc_lab.dataset import deterministic_group_split
from afc_lab.howling import HowlingDetector
from afc_lab.metrics import si_sdr_db, snr_db
from afc_lab.patel import calibration_response, estimate_fir
from afc_lab.runner import run_experiment
from afc_lab.runtime import benchmark_blocks
from afc_lab.signals import make_feedback_path, probe_noise


class LabTests(unittest.TestCase):
    def test_fir_estimator_recovers_known_path(self) -> None:
        rng = np.random.default_rng(7)
        path = make_feedback_path(64, 8, 0.08, rng)
        probe = probe_noise(12_000, -20.0, rng)
        response = calibration_response(probe, path)
        estimate = estimate_fir(probe, response, 64)
        relative_error = np.linalg.norm(path - estimate) / np.linalg.norm(path)
        self.assertLess(relative_error, 0.02)

    def test_metrics_reward_identical_signal(self) -> None:
        signal = np.linspace(-0.5, 0.5, 4096, dtype=np.float32)
        self.assertGreater(snr_db(signal, signal), 100.0)
        self.assertGreater(si_sdr_db(signal, signal), 100.0)

    def test_howling_detector_persists(self) -> None:
        detector = HowlingDetector(48_000, required_frames=3)
        time = np.arange(1024) / 48_000
        frame = np.sin(2 * np.pi * 1500 * time).astype(np.float32)
        self.assertFalse(detector.process_frame(frame).detected)
        self.assertFalse(detector.process_frame(frame).detected)
        self.assertTrue(detector.process_frame(frame).detected)

    def test_smoke_experiment_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = ExperimentConfig(
                duration_seconds=0.1,
                output_dir=directory,
                path=PathConfig(length=64, direct_delay=8, decay=0.08),
                patel=PatelConfig(probe_duration_ms=50, filter_length=64, reactive=False),
            )
            rows = run_experiment(config)
            self.assertEqual([row["method"] for row in rows], ["bypass", "patel_manual"])
            self.assertTrue((Path(directory) / "manifest.json").exists())
            self.assertTrue((Path(directory) / "results.csv").exists())

    def test_group_split_never_leaks_identity(self) -> None:
        groups = ["speaker-a", "speaker-b", "speaker-a", "singer-c"]
        first = deterministic_group_split(groups, 42)
        second = deterministic_group_split(list(reversed(groups)), 42)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)

    def test_runtime_benchmark_reports_percentiles(self) -> None:
        result = benchmark_blocks(lambda block: block, 64, blocks=10)
        self.assertLessEqual(result["p50_ms"], result["p99_ms"])
        self.assertGreater(result["period_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()

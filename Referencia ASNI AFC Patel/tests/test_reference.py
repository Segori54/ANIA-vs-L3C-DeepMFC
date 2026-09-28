import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from referencia.fixtures import make_case
from referencia.oracle import (CausalReplay, correlate, engine_matched, paper_core,
                               predict, relative_error, solve, toeplitz)
from referencia.storage import (ROOT, Bridge, load_signal, new_id, read_json, save_model,
                                save_signal, write_json)


class ReferenceTests(unittest.TestCase):
    def test_lag_direction_and_zero_extension(self):
        np.testing.assert_array_equal(correlate([0, 0, 2, 3], [1, 0], 6), [0, 0, 2, 3, 0, 0])
        np.testing.assert_array_equal(correlate([1, 2, 3], [4, 5], 4), [14, 23, 12, 0])

    def test_correlations_match_explicit_scalar_sum(self):
        rng = np.random.default_rng(12)
        y, f = rng.normal(size=21), rng.normal(size=13)
        expected = [sum(y[n] * f[n-l] for n in range(len(y)) if 0 <= n-l < len(f)) for l in range(25)]
        np.testing.assert_allclose(correlate(y, f, 25), expected, atol=1e-14)

    def test_known_systems(self):
        for size in (1, 4, 16, 64):
            r = .75 ** np.arange(size)
            known = np.random.default_rng(size).normal(size=size)
            actual, residual = solve(r, toeplitz(r) @ known)
            self.assertLess(relative_error(actual, known), 1e-10)
            self.assertLess(residual, 1e-12)

    def test_paper_core_recovers_fir(self):
        p = np.pad(np.random.default_rng(9).normal(size=1000), (0, 20))
        h = [0, .3, -.1, .05]
        m = predict(p, h)
        model = paper_core(p, m, len(h))
        np.testing.assert_allclose(model["coefficients"], h, atol=1e-12)

    def test_blocks_are_causal_and_partition_invariant(self):
        x = np.random.default_rng(45).normal(size=1003)
        expected = predict(x, [.2, -.1, .03], 9)
        for sizes in ((1,), (64,), (128,), (256,), (1, 17, 64, 3, 256, 129)):
            replay = CausalReplay([.2, -.1, .03], 9)
            chunks, index, turn = [], 0, 0
            self.assertEqual(len(replay.process([])), 0)
            while index < len(x):
                count = sizes[turn % len(sizes)]
                chunks.append(replay.process(x[index:index + count]))
                index += count
                turn += 1
            np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-14)
        altered = x.copy()
        altered[500:] *= 30
        np.testing.assert_array_equal(predict(x, [.2, .1], 9)[:500], predict(altered, [.2, .1], 9)[:500])

    def test_seeds_and_physical_times(self):
        for rate, taps in ((16000, 683), (48000, 2048)):
            a, cfg, h, delay = make_case(rate, "simple", 1729)
            b, _, _, _ = make_case(rate, "simple", 1729)
            for key in a:
                np.testing.assert_array_equal(a[key], b[key])
            self.assertEqual(cfg["maximumFilterLength"], taps)
            self.assertEqual(delay, round(.004 * rate))
            self.assertEqual(len(a["probe"]), rate + cfg["maximumDelaySamples"] + taps)
            self.assertFalse(np.array_equal(a["probe"][:100], a["validationProbe"][:100]))
            short, scfg, _, _ = make_case(rate, "short160", 1729)
            self.assertEqual(len(short["probe"]) - sum((scfg["maximumDelaySamples"], scfg["maximumFilterLength"])), round(rate*.16))

    def test_rejection_and_shape_validation(self):
        for condition, status in (("no_return", "noReturn"), ("clipped", "clipped"), ("nonfinite", "invalid")):
            signals, cfg, _, _ = make_case(16000, condition, 1729)
            self.assertEqual(engine_matched(signals, cfg)["result"], status)
        signals["microphone"] = signals["microphone"][:-1]
        self.assertEqual(engine_matched(signals, cfg)["result"], "invalid")

    def test_float32_roundtrip_hash_and_csv(self):
        (ROOT / "build/tests").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "build/tests") as tmp:
            path = Path(tmp)
            values = np.array([0., -0., .1, 1e-30, np.inf, np.nan], dtype=np.float32)
            spec = save_signal(path / "signal.f32", values, 48000)
            np.testing.assert_array_equal(values.view(np.uint32), load_signal(spec).view(np.uint32))
            model = {"delaySamples": 3, "coefficients": [.1, -.2]}
            save_model(path / "model.json", model)
            self.assertEqual(read_json(path / "model.json"), model)
            exported = np.loadtxt(path / "model.csv", delimiter=",", skiprows=1)
            np.testing.assert_array_equal(exported[:, 1], model["coefficients"])
            (path / "signal.f32").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                load_signal(spec)
        self.assertNotEqual(new_id(), new_id())


class CppIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = Bridge()  # Missing comparator is a failure, never a silent skip.
        (ROOT / "build/tests").mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "build/tests")
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_solver_and_preservation(self):
        req = {"operation": "solve", "r": [1., .5, .25], "b": [1., 2., 3.]}
        result = self.bridge.call(req, self.path / "solver")
        h, _ = solve(req["r"], req["b"])
        self.assertTrue(result["ok"])
        self.assertLessEqual(relative_error(result["solution"], h), 1e-8)
        before = (self.path / "solver/response.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.bridge.call(req, self.path / "solver")
        self.assertEqual(before, (self.path / "solver/response.json").read_bytes())
        invalid = self.bridge.call({"operation": "solve", "r": [1., 2.], "b": [1., 2.]}, self.path / "indefinite")
        self.assertFalse(invalid["ok"])

    def test_estimate_actual_engine_both_rates(self):
        for rate in (16000, 48000):
            signals, cfg, _, delay = make_case(rate, "short160", 1729)
            specs = {k: save_signal(self.path / str(rate) / f"{k}.f32", v, rate) for k, v in signals.items()}
            request = {"operation": "estimate", "sample_rate": rate, "config": cfg, "signals": specs}
            result = self.bridge.call(request, self.path / str(rate) / "operation")
            oracle = engine_matched(signals, cfg)
            self.assertEqual(result["result"], "accepted")
            self.assertLessEqual(abs(result["delaySamples"] - delay), 1)
            from referencia.oracle import complete
            self.assertLess(relative_error(complete(result), complete(oracle)), 1e-3)
            specs["probe"]["sample_rate"] = 44100
            with self.assertRaises(RuntimeError):
                self.bridge.call(request, self.path / str(rate) / "bad_rate")

    def test_estimator_rejects_invalid_captures(self):
        for condition, status in (("no_return", "noReturn"), ("clipped", "clipped"), ("nonfinite", "invalid")):
            signals, cfg, _, _ = make_case(16000, condition, 1729)
            specs = {k: save_signal(self.path / condition / f"{k}.f32", v, 16000) for k, v in signals.items()}
            result = self.bridge.call({"operation": "estimate", "sample_rate": 16000, "config": cfg, "signals": specs},
                                      self.path / condition / "operation")
            self.assertEqual(result["result"], status)

    def test_stale_comparator_is_not_accepted(self):
        with patch("referencia.storage.digest", return_value="different-source"):
            with self.assertRaisesRegex(RuntimeError, "fingerprint"):
                self.bridge.call({"operation": "solve", "r": [1.], "b": [.2]}, self.path / "stale")


class CliTests(unittest.TestCase):
    def test_discrepancy_returns_nonzero_and_all_runs_both_rates(self):
        from referencia.__main__ import main
        with patch("sys.argv", ["referencia", "all"]), patch("referencia.__main__.run") as run_mock, patch("referencia.__main__.compare") as compare_mock:
            run_mock.side_effect = [(False, "run16"), (True, "run48")]
            compare_mock.return_value = (False, Path("report"))
            self.assertEqual(main(), 1)
            self.assertEqual([call.args[0] for call in run_mock.call_args_list], [16000, 48000])
            compare_mock.assert_called_once_with({16000: "run16", 48000: "run48"})


if __name__ == "__main__":
    unittest.main()

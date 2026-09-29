from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
TRAINING_DEPS = all(importlib.util.find_spec(name) for name in ("soundfile", "scipy"))
if TRAINING_DEPS:
    import soundfile as sf
    from afc_lab.corpus import identify, inspect_audio, split_records, identity_splits
    from afc_lab.dataset import read_mono_wav
    from afc_lab.training_pairs import loop_pair, path_for, prepare
    from afc_lab.corpus import sha256


@unittest.skipUnless(TRAINING_DEPS, "Optional training/audio dependencies")
class CorpusTests(unittest.TestCase):
    def test_pcm24_and_flac_preserve_low_level_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            signal = np.array([0, 2**-20, -2**-20, 0.125], dtype=np.float32)
            for suffix in (".wav", ".flac"):
                path = Path(directory) / ("voice" + suffix)
                sf.write(path, signal, 48000, subtype="PCM_24")
                np.testing.assert_allclose(read_mono_wav(path), signal, atol=2**-23)
                self.assertTrue(inspect_audio(path)["eligible"])

    def test_rejects_stereo_wrong_rate_nonfinite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            for signal, rate, subtype in ((np.zeros((20, 2)), 48000, "PCM_24"),
                                         (np.zeros(20), 24000, "PCM_24"),
                                         (np.array([np.nan]), 48000, "FLOAT")):
                sf.write(path, signal, rate, subtype=subtype)
                with self.assertRaises(ValueError):
                    read_mono_wav(path)
                self.assertFalse(inspect_audio(path)["eligible"])

    def test_spoken_and_sung_gtsinger_share_identity(self):
        a = identify("Spanish/ES-Bass-1/Vibrato/song/Control_Group/a.wav", "gtsinger")
        b = identify("Spanish/ES-Bass-1/Vibrato/song/Paired_Speech_Group/a.wav", "gtsinger")
        self.assertEqual(a["identity"], b["identity"])
        self.assertEqual((a["kind"], b["kind"]), ("singing", "speech"))

    def test_identity_and_song_exclusion_is_deterministic(self):
        rows = [{"identity": f"gtsinger:{index}", "corpus": "gtsinger", "kind": kind,
                 "song": "shared" if index < 6 else f"song-{index}",
                 "sha256": f"hash-{index}-{kind}", "eligible": True, "reasons": []}
                for index in range(10) for kind in ("speech", "singing")]
        a = split_records(rows, 42)
        b = split_records(list(reversed(rows)), 42)
        self.assertEqual({r["sha256"]: (r["split"], r["eligible"]) for r in a},
                         {r["sha256"]: (r["split"], r["eligible"]) for r in b})
        for field in ("identity", "song", "sha256"):
            owners = {}
            for row in a:
                if row["eligible"]:
                    self.assertEqual(owners.setdefault(row[field], row["split"]), row["split"])

    def test_insufficient_identities_fail_instead_of_fake_split(self):
        with self.assertRaises(ValueError):
            split_records([{"identity": "one", "corpus": "gtsinger"}], 42)

    def test_adding_singers_never_moves_existing_identities(self):
        rows = [{"identity": f"gtsinger:{i}", "corpus": "gtsinger"} for i in range(20)]
        before = identity_splits(rows[:3], 18)
        after = identity_splits(rows, 18)
        self.assertEqual(before, {key: after[key] for key in before})


@unittest.skipUnless(TRAINING_DEPS, "Optional training/audio dependencies")
class FeedbackPairTests(unittest.TestCase):
    @staticmethod
    def scalar(source, h, gain, delay, changed=None, change=None):
        mic = np.zeros(len(source))
        speaker = np.zeros(len(source))
        for n, value in enumerate(source):
            path = changed if changed is not None and n >= change else h
            mic[n] = value + sum(coefficient * speaker[n - k]
                                 for k, coefficient in enumerate(path) if n - k >= 0)
            if n >= delay:
                speaker[n] = gain * mic[n - delay]
                # For paths with h[0] != 0, current emitted audio is already
                # determined by delayed mic, so recompute the instantaneous term.
                mic[n] += path[0] * speaker[n]
        return mic, speaker

    def test_impulse_matches_analytic_geometric_echoes(self):
        source = np.zeros(20)
        source[0] = 1
        result = loop_pair(source, [0.5], 1, 3)
        expected = np.zeros(20)
        expected[::3] = 0.5 ** np.arange(7)
        np.testing.assert_allclose(result["input"], expected)
        np.testing.assert_array_equal(result["ideal_speaker"][3:], source[:-3])

    def test_fixed_and_changed_paths_match_independent_recurrence(self):
        source = np.random.default_rng(9).normal(0, 0.01, 120)
        h, alternate = np.array([0.1, -0.05, 0.03]), np.array([0.05, 0.03])
        for changed in (None, alternate):
            result = loop_pair(source, h, 0.8, 4, changed_path=changed, change_sample=61)
            mic, speaker = self.scalar(source, h, 0.8, 4, changed, 61)
            np.testing.assert_allclose(result["input"], mic, rtol=1e-6, atol=1e-8)
            np.testing.assert_allclose(result["speaker"], speaker, rtol=1e-6, atol=1e-8)

    def test_silence_and_no_feedback(self):
        source = np.arange(20) / 100
        result = loop_pair(source, np.zeros(3), 0.5, 2)
        np.testing.assert_allclose(result["input"], source)
        np.testing.assert_array_equal(result["speaker"], result["ideal_speaker"])
        result = loop_pair(np.zeros(20), [0.3], 0.5, 2)
        self.assertFalse(np.any(result["speaker"]))

    def test_future_source_cannot_affect_past_output(self):
        a = np.zeros(100)
        b = a.copy()
        b[60:] = 0.1
        first = loop_pair(a, [0.1, 0.2], 0.5, 3)
        second = loop_pair(b, [0.1, 0.2], 0.5, 3)
        np.testing.assert_array_equal(first["input"][:60], second["input"][:60])

    def test_path_seeds_are_disjoint_by_split(self):
        a, seed_a = path_for("train", 0, 42)
        b, seed_b = path_for("validation", 0, 42)
        self.assertNotEqual(seed_a, seed_b)
        self.assertFalse(np.array_equal(a, b))

    def test_final_test_cannot_be_used_to_prepare_training(self):
        with self.assertRaises(ValueError):
            prepare("unused", "unused", "unused", split="test")

    def test_preparation_preserves_sources_and_covers_both_kinds_and_scenarios(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = np.sin(np.arange(4800) * 0.03).astype(np.float32) * 0.01
            rows = []
            for kind in ("speech", "singing"):
                path = root / (kind + ".wav")
                sf.write(path, source, 48000, subtype="PCM_24")
                rows.append({"path": path.name, "sha256": sha256(path), "split": "train",
                             "eligible": True, "kind": kind, "identity": kind})
            manifest = root / "corpus.json"
            manifest.write_text(json.dumps({"schema_version": 2, "sample_rate": 48000,
                                            "seed": 7, "records": rows}))
            payload = prepare(manifest, root, root / "pairs", split="train", seconds=0.1)
            self.assertEqual(len(payload["examples"]), 8)
            for kind in ("speech", "singing"):
                self.assertEqual({r["scenario"] for r in payload["examples"] if r["kind"] == kind},
                                 {"fixed", "changed", "clean", "silence"})
            for row in rows:
                self.assertEqual(sha256(root / row["path"]), row["sha256"])
            for row in payload["examples"]:
                self.assertEqual(sha256(root / "pairs" / row["file"]), row["sha256"])
            with self.assertRaises(FileExistsError):
                prepare(manifest, root, root / "pairs", split="train", seconds=0.1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
from types import SimpleNamespace


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                        ("torch", "soundfile", "onnx", "onnxruntime")), "Optional training dependencies")
class TorchTrainingTests(unittest.TestCase):
    def test_training_and_resume_on_cpu(self):
        from afc_lab.doctor import smoke
        with tempfile.TemporaryDirectory() as directory:
            result = smoke(directory, "cpu")
            self.assertTrue(result["passed"])
            self.assertLessEqual(result["resume_max_parameter_error"], 1e-6)

    def test_gru_streaming_preserves_state(self):
        import torch
        from afc_lab.models import CausalSpectralGru
        torch.manual_seed(4)
        model = CausalSpectralGru(bins=9, hidden=12).eval()
        x = torch.randn(1, 12, 18)
        with torch.no_grad():
            whole, whole_state = model(x)
            pieces, state = [], None
            for frame in x.split(1, dim=1):
                y, state = model(frame, state)
                pieces.append(y)
        torch.testing.assert_close(whole, torch.cat(pieces, dim=1), atol=1e-6, rtol=1e-5)
        torch.testing.assert_close(whole_state, state, atol=1e-6, rtol=1e-5)

    def test_resume_rejects_different_experiment(self):
        import torch
        from afc_lab.checkpoint import save_checkpoint, load_checkpoint
        with tempfile.TemporaryDirectory() as directory:
            model = torch.nn.Linear(2, 2)
            optimizer = torch.optim.Adam(model.parameters())
            path = Path(directory) / "checkpoint.pt"
            save_checkpoint(path, model, optimizer, step=1, config={"seed": 1})
            with self.assertRaises(ValueError):
                load_checkpoint(path, model, optimizer, expected_config={"seed": 2})

    def test_pilot_epochs_resume_export_and_tamper_detection(self):
        import numpy as np
        import torch
        from afc_lab.corpus import sha256
        from afc_lab.pilot import run, Pairs
        from afc_lab.export_pilot import export
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for split in ("train", "validation"):
                folder = root / split
                folder.mkdir()
                rows = []
                for index, kind in enumerate(("speech", "singing")):
                    path = folder / f"{index}.npz"
                    x = np.sin(np.arange(1920) * (0.03 + index * 0.01)).astype(np.float32) * 0.05
                    np.savez(path, input=x, target=x)
                    rows.append({"file": path.name, "sha256": sha256(path), "kind": kind,
                                 "identity": f"{split}-{index}", "scenario": "clean",
                                 "source_sha256": f"{split}-{index}",
                                 "path_seed": index + (100 if split == "train" else 200)})
                (folder / "manifest.json").write_text(json.dumps({"split": split, "sample_rate": 48000,
                    "target": "source_before_forward_gain_and_delay", "examples": rows}))
            args = SimpleNamespace(train=root / "train", validation=root / "validation", output=root / "run",
                device="cpu", epochs=1, batch_size=2, hidden=8, steps_per_epoch=1, seed=13, resume=None)
            run(args)
            args.resume, args.epochs = root / "run/latest.pt", 2
            run(args)
            result = torch.load(root / "run/latest.pt", weights_only=True)
            self.assertEqual(result["step"], 2)
            exported = export(root / "run/latest.pt", root / "prototype.onnx")
            self.assertFalse(exported["engine_release"])
            self.assertLess(exported["maximum_streaming_error"], 1e-5)
            (root / "train/0.npz").write_bytes(b"corruption")
            with self.assertRaises(ValueError):
                Pairs(root / "train", "train")


if __name__ == "__main__":
    unittest.main()

"""Run the bounded infrastructure acceptance pipeline on original voice clips.

This does NOT approve the one-hour corpus, L3C reproduction, or use in live audio.
Run with the project's venv after bootstrap_training.py finishes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or root / "outputs/training" / ("smoke-" + stamp)).resolve()
    data = (args.data_root or root / "data/raw").resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use a new output directory; evidence is not overwritten")
    output.mkdir(parents=True, exist_ok=True)
    status = {"scope": "infrastructure_only_not_l3c_or_live_afc", "stages": [], "passed": False}
    report = output / "status.json"

    def write():
        report.write_text(json.dumps(status, indent=2), encoding="utf-8")

    def stage(name, module, *arguments):
        entry = {"name": name, "status": "running", "command": [module, *map(str, arguments)]}
        status["stages"].append(entry)
        write()
        print(f"\n{name}", flush=True)
        with (output / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, "-u", "-m", module, *map(str, arguments)],
                                    cwd=root, stdout=log, stderr=subprocess.STDOUT)
        entry["status"] = "passed" if result.returncode == 0 else "failed"
        entry["returncode"] = result.returncode
        write()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see {output / (name + '.log')}")
        print(f"{name}: passed", flush=True)

    stage("01_gpu", "afc_lab.doctor", "--smoke", "--output", output / "phase1")
    stage("02_samples", "afc_lab.fetch_samples", "--data-root", data)
    stage("02_vctk", "afc_lab.fetch_vctk_samples", "--data-root", data)
    stage("03_inventory", "afc_lab.corpus", "--data-root", data, "--output", output / "corpus.json")
    for split in ("train", "validation"):
        stage("04_pairs_" + split, "afc_lab.training_pairs", output / "corpus.json",
              "--data-root", data, "--output", output / ("pairs-" + split),
              "--split", split, "--limit", "24", "--seconds", "1")
    training = ["--train", output / "pairs-train", "--validation", output / "pairs-validation",
                "--output", output / "gru", "--batch-size", "2", "--steps-per-epoch", "4"]
    stage("05_train", "afc_lab.pilot", *training, "--epochs", "2")
    stage("06_resume", "afc_lab.pilot", *training, "--epochs", "4", "--resume", output / "gru/latest.pt")
    stage("07_export", "afc_lab.export_pilot", output / "gru/best.pt", output / "gru/prototype.onnx")
    status["passed"] = True
    status["quality_approved"] = False
    status["engine_release"] = False
    write()
    print(f"Infrastructure verified. Report: {report}")


if __name__ == "__main__":
    main()

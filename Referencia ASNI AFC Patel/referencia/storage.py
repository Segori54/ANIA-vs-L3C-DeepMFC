"""Versioned JSON and exact little-endian float32 exchange."""
import csv
import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "_" + uuid.uuid4().hex[:8]


def save_signal(path, values, rate):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.asarray(values, dtype="<f4")
    if a.ndim != 1:
        raise ValueError("Signal must be mono")
    a.tofile(path)
    return {"path": str(path.resolve()), "dtype": "<f4", "samples": len(a),
            "sample_rate": rate, "sha256": digest(path)}


def load_signal(spec):
    path = Path(spec["path"])
    if spec["dtype"] != "<f4" or path.stat().st_size != spec["samples"] * 4:
        raise ValueError("Invalid signal format/length")
    if digest(path) != spec["sha256"]:
        raise ValueError("Signal hash mismatch")
    return np.fromfile(path, dtype="<f4")


def csv_rows(path, rows):
    if not rows:
        raise ValueError("Cannot export empty table")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def save_model(path, model):
    write_json(path, model)
    target = Path(path).with_suffix(".csv")
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["k", "h", "delay_samples"])
        for k, value in enumerate(model["coefficients"]):
            writer.writerow([k, format(value, ".17g"), model["delaySamples"]])


def default_executable():
    candidates = [ROOT / "build/bin/Release/patel_compare.exe", ROOT / "build/bin/patel_compare",
                  ROOT / "build/bin/patel_compare.exe"]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("Compile comparador_cpp first; see README.md or pass --cpp")


class Bridge:
    def __init__(self, executable=None):
        self.executable = Path(executable).resolve() if executable else default_executable()

    def call(self, request, directory):
        directory = Path(directory)
        # Each logical operation has its own directory; never overwrite evidence.
        directory.mkdir(parents=True, exist_ok=False)
        req, response = directory / "request.json", directory / "response.json"
        write_json(req, {"schema_version": 1, **request})
        completed = subprocess.run([str(self.executable), str(req.resolve()), str(response.resolve())],
                                   capture_output=True, text=True, timeout=180)
        (directory / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f"C++ failed ({completed.returncode}): {completed.stderr}")
        result = read_json(response)
        build = result.get("build", {})
        source = ROOT.parent / "RealtimeFeedbackEngine/Source/Processors"
        if (build.get("estimator_cpp_sha256") != digest(source / "PatelEstimator.cpp") or
                build.get("estimator_h_sha256") != digest(source / "PatelEstimator.h")):
            raise RuntimeError("Comparator source fingerprint is stale/missing; rebuild comparador_cpp")
        return result

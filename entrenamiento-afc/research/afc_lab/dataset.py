from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np


def read_mono_wav(path: str | Path, expected_sample_rate: int = 48_000) -> np.ndarray:
    # libsndfile supports native PCM24 and FLAC without an intermediate PCM16 file.
    import soundfile as sf
    with sf.SoundFile(path) as stream:
        if stream.samplerate != expected_sample_rate:
            raise ValueError(f"{path}: expected {expected_sample_rate} Hz")
        if stream.channels != 1:
            raise ValueError(f"{path}: expected mono audio; select a channel explicitly")
        samples = stream.read(dtype="float32")
    if not np.isfinite(samples).all():
        raise ValueError(f"{path}: non-finite audio")
    return samples


def deterministic_group_split(
    groups: list[str], seed: int, ratios: tuple[float, float, float] = (0.8, 0.1, 0.1)
) -> dict[str, str]:
    if not np.isclose(sum(ratios), 1.0):
        raise ValueError("split ratios must sum to one")
    result: dict[str, str] = {}
    train_limit, validation_limit = ratios[0], ratios[0] + ratios[1]
    for group in sorted(set(groups)):
        digest = hashlib.sha256(f"{seed}:{group}".encode()).digest()
        fraction = int.from_bytes(digest[:8], "little") / float(2**64)
        result[group] = (
            "train" if fraction < train_limit
            else "validation" if fraction < validation_limit
            else "test"
        )
    return result


def write_dataset_manifest(
    records: list[dict[str, str]], destination: str | Path, seed: int
) -> dict[str, object]:
    required = {"path", "group", "kind"}
    if any(not required.issubset(record) for record in records):
        raise ValueError("each record requires path, group, and kind")
    assignments = deterministic_group_split([record["group"] for record in records], seed)
    manifest = {
        "schema_version": 1,
        "seed": seed,
        "records": [{**record, "split": assignments[record["group"]]} for record in records],
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

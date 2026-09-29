"""Causal 48 kHz feedback examples; no limiter that could hide instability."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.signal import lfilter, lfiltic
import soundfile as sf
from .signals import make_feedback_path
from .corpus import sha256


def loop_pair(source, path, gain, forward_delay, *, changed_path=None, change_sample=None):
    """mic[n]=source[n]+sum h[k]*speaker[n-k]; speaker[n]=gain*mic[n-D].

    Neural training target is source at the processor input; forward gain and
    delay are OUTSIDE the network. This is an explicit research convention,
    not a claim of exact L3C-DeepMFC reproduction.
    """
    source = np.asarray(source, dtype=np.float64)
    path = np.asarray(path, dtype=np.float64)
    if source.ndim != 1 or path.ndim != 1 or not source.size or not path.size:
        raise ValueError("Nonempty one-dimensional source/path required")
    if forward_delay < 1 or not np.isfinite(gain) or gain < 0:
        raise ValueError("Require causal forward delay and finite nonnegative gain")
    if not np.isfinite(source).all() or not np.isfinite(path).all():
        raise ValueError("Non-finite input")

    def denominator(h):
        a = np.zeros(forward_delay + len(h), dtype=np.float64)
        a[0] = 1
        a[forward_delay:] -= gain * h
        return a

    if changed_path is None:
        mic = lfilter([1.0], denominator(path), source)
    else:
        changed_path = np.asarray(changed_path, dtype=np.float64)
        if changed_path.ndim != 1 or not changed_path.size or not np.isfinite(changed_path).all():
            raise ValueError("Invalid changed path")
        if change_sample is None or not 0 < change_sample < source.size:
            raise ValueError("Path change must be inside the source")
        before = lfilter([1.0], denominator(path), source[:change_sample])
        after_a = denominator(changed_path)
        state = lfiltic([1.0], after_a, before[::-1][:len(after_a) - 1])
        after, _ = lfilter([1.0], after_a, source[change_sample:], zi=state)
        mic = np.concatenate((before, after))
    speaker = np.zeros_like(source)
    ideal_speaker = np.zeros_like(source)
    if forward_delay < len(source):
        speaker[forward_delay:] = gain * mic[:-forward_delay]
        ideal_speaker[forward_delay:] = gain * source[:-forward_delay]
    if (not np.isfinite(mic).all() or not np.isfinite(speaker).all()
            or np.max(np.abs(mic), initial=0) > np.finfo(np.float32).max
            or np.max(np.abs(speaker), initial=0) > np.finfo(np.float32).max):
        raise ValueError("Unstable/non-finite simulation; rejected, not limited")
    return {"input": mic.astype(np.float32), "target": source.astype(np.float32),
            "speaker": speaker.astype(np.float32), "ideal_speaker": ideal_speaker.astype(np.float32)}


def path_for(split, index, seed, length=1024):
    # No common seed/path between training and held-out material.
    digest = hashlib.sha256(f"{seed}:{split}:{index}".encode()).digest()
    path_seed = int.from_bytes(digest[:8], "little")
    rng = np.random.default_rng(path_seed)
    path = make_feedback_path(length, int(rng.integers(24, 240)), 0.012, rng)
    return path, path_seed


def prepare(manifest_path, root, output, *, split, limit=100, seconds=1.0):
    if split not in ("train", "validation"):
        raise ValueError("Final test/external recordings are reserved; use a separate frozen evaluation")
    manifest_path, root, output = Path(manifest_path), Path(root).resolve(), Path(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2 or manifest.get("sample_rate") != 48000:
        raise ValueError("Expected corpus schema 2 at 48 kHz")
    if limit < 1 or seconds < 0.1:
        raise ValueError("Invalid example count or segment duration")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use an empty output directory; runs are immutable")
    output.mkdir(parents=True, exist_ok=True)
    records = [r for r in manifest["records"] if r["split"] == split and r["eligible"]]
    # Alternate kinds, preserving an explicit shortage rather than duplicating identities.
    kinds = {kind: iter(r for r in records if r["kind"] == kind) for kind in ("speech", "singing")}
    examples = []
    count = round(seconds * 48000)
    current_records = {}
    for index in range(limit):
        kind = ("speech", "singing")[index % 2]
        # Exercise all four scenarios for each original before moving on.
        if index % 8 < 2:
            current_records[kind] = next(kinds[kind], None)
        row = current_records.get(kind)
        if row is None:
            if len(current_records) == 2 and all(value is None for value in current_records.values()):
                break
            continue
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Corpus path escapes data root")
        if sha256(path) != row["sha256"]:
            raise ValueError("Original audio changed since inventory")
        with sf.SoundFile(path) as stream:
            if stream.samplerate != 48000 or stream.channels != 1:
                raise ValueError("Original audio must be mono 48 kHz")
            source = stream.read(count, dtype="float32")
        if len(source) < count:
            source = np.pad(source, (0, count - len(source)))
        h, path_seed = path_for(split, index, manifest["seed"])
        changed, changed_seed = path_for(split, index + 1000000, manifest["seed"])
        # Alternate scenario schedule across kind to cover both voice types.
        scenario = ("fixed", "changed", "clean", "silence")[(index // 2) % 4]
        if scenario == "silence":
            source[:] = 0
        if scenario == "clean":
            h[:] = 0
        gain = 0.8 / max(float(np.sum(np.abs(h))), float(np.sum(np.abs(changed))), 0.8)
        pair = loop_pair(source, h, gain, 96,
                         changed_path=changed if scenario == "changed" else None,
                         change_sample=count // 2 if scenario == "changed" else None)
        if max(float(np.max(np.abs(pair[k]))) for k in ("input", "speaker")) >= 1:
            raise ValueError("Example exceeds full scale; adjust documented source level instead of clipping")
        filename = f"{index:06d}.npz"
        np.savez_compressed(output / filename, **pair, path=h,
                            changed_path=changed if scenario == "changed" else np.array([], dtype=np.float32))
        examples.append({"file": filename, "sha256": sha256(output / filename),
                         "kind": kind, "identity": row["identity"],
                         "song": row.get("song"), "source": row["path"], "scenario": scenario,
                         "source_sha256": row["sha256"], "path_seed": path_seed,
                         "changed_path_seed": changed_seed if scenario == "changed" else None,
                         "gain": gain, "forward_delay_samples": 96, "frames": count,
                         "change_sample": count // 2 if scenario == "changed" else None})
    payload = {"schema_version": 1, "sample_rate": 48000, "split": split,
               "purpose": "conservative_stable_pairs_not_closed_loop_training",
               "seed": manifest["seed"], "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
               "target": "source_before_forward_gain_and_delay", "examples": examples}
    (output / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not examples:
        raise ValueError("No examples; corpus lacks the requested split/kinds")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["train", "validation"], required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seconds", type=float, default=1.0)
    args = parser.parse_args()
    result = prepare(args.manifest, args.data_root, args.output, split=args.split, limit=args.limit, seconds=args.seconds)
    print(f"Prepared {len(result['examples'])} examples in {args.output}")


if __name__ == "__main__":
    main()

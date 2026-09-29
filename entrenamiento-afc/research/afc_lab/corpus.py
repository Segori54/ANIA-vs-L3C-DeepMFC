"""Audit original VCTK/GTSinger files and create portable, identity-disjoint manifests."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import numpy as np
import soundfile as sf
from .dataset import deterministic_group_split


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identify(relative, corpus):
    path = Path(relative)
    if corpus == "vctk":
        match = re.fullmatch(r"(p\d+)_\d+_mic1", path.stem)
        if not match:
            raise ValueError("VCTK pilot uses mic1 only, with original filenames")
        return {"identity": "vctk:" + match[1], "kind": "speech", "song": None,
                "language": "English", "technique": None}
    if corpus == "gtsinger":
        parts = path.parts
        # language / singer / technique / song / group / clip.wav
        if len(parts) != 6 or not re.fullmatch(r"[A-Z]{2}-[A-Za-z]+-\d+", parts[1]):
            raise ValueError("Expected original GTSinger language/singer/technique/song/group/file layout")
        if parts[4] not in {"Paired_Speech_Group", "Control_Group", "Breathy_Group", "Glissando_Group",
                            "Mixed_Voice_Group", "Falsetto_Group", "Pharyngeal_Group", "Vibrato_Group"}:
            raise ValueError("Unknown GTSinger recording group")
        return {"identity": "gtsinger:" + parts[1],
                "kind": "speech" if parts[4] == "Paired_Speech_Group" else "singing",
                "song": unicodedata.normalize("NFKC", parts[3]).casefold().strip(),
                "language": parts[0], "technique": parts[2]}
    raise ValueError("Unknown corpus")


def inspect_audio(path):
    info = sf.info(path)
    peak = 0.0
    power = 0.0
    near_full_scale = 0
    count = 0
    finite = True
    with sf.SoundFile(path) as stream:
        for block in stream.blocks(blocksize=65536, dtype="float32", always_2d=True):
            finite &= bool(np.isfinite(block).all())
            peak = max(peak, float(np.max(np.abs(block), initial=0)))
            power += float(np.sum(block.astype(np.float64) ** 2))
            near_full_scale += int(np.sum(np.abs(block) >= 0.999))
            count += block.size
    reasons = []
    if info.samplerate != 48000:
        reasons.append("sample_rate_not_48000")
    if info.channels != 1:
        reasons.append("not_mono")
    if not finite:
        reasons.append("non_finite")
    if count == 0:
        reasons.append("empty")
    if peak >= 1.0:
        reasons.append("full_scale_or_above")
    return {"sample_rate": info.samplerate, "channels": info.channels,
            "subtype": info.subtype, "frames": info.frames, "seconds": info.duration,
            "peak": peak if finite else None,
            "rms": float(np.sqrt(power / max(count, 1))) if finite else None,
            "near_full_scale_samples": near_full_scale,
            "eligible": not reasons, "reasons": reasons, "sha256": sha256(path)}


def identity_splits(records, seed):
    """Stable identity hash: adding recordings or people must not move old splits."""
    assignments = {}
    for corpus in sorted({r["corpus"] for r in records}):
        identities = sorted({r["identity"] for r in records if r["corpus"] == corpus})
        if len(identities) < 3:
            raise ValueError(f"{corpus}: at least 3 identities are needed; no valid train/val/test split")
        assignments.update(deterministic_group_split(identities, seed))
    return assignments


def split_records(records, seed):
    assignments = identity_splits(records, seed)
    result = [{**record, "split": assignments[record["identity"]]} for record in records]
    # Keep songs and exact duplicate recordings in only one split. Prefer held-out
    # material and exclude colliding development recordings (never move identities).
    priority = {"train": 0, "validation": 1, "test": 2}
    owners = {}
    for record in result:
        if not record["eligible"]:
            continue
        keys = [("hash", record["sha256"])]
        if record.get("song"):
            keys.append(("song", record["song"]))
        for key in keys:
            if key not in owners or priority[record["split"]] > priority[owners[key]]:
                owners[key] = record["split"]
    for record in result:
        keys = [("hash", record["sha256"])]
        if record.get("song"):
            keys.append(("song", record["song"]))
        if record["eligible"] and any(owners[key] != record["split"] for key in keys):
            record["eligible"] = False
            record["reasons"] = [*record["reasons"], "song_or_duplicate_cross_split"]
    return result


def select_pilot(records, seconds_per_kind):
    # Round-robin identities, deterministic ordering, full original clips.
    selected = []
    for split in ("train", "validation", "test"):
        budget = seconds_per_kind * {"train": 0.8, "validation": 0.1, "test": 0.1}[split]
        for kind in ("speech", "singing"):
            by_identity = defaultdict(list)
            for row in records:
                if row["eligible"] and row["split"] == split and row["kind"] == kind:
                    by_identity[row["identity"]].append(row)
            groups = [iter(sorted(rows, key=lambda r: hashlib.sha256(r["path"].encode()).digest()))
                      for _, rows in sorted(by_identity.items())]
            total = 0.0
            while groups and total < budget:
                remaining = []
                for group in groups:
                    row = next(group, None)
                    if row is not None:
                        selected.append(row)
                        total += row["seconds"]
                        remaining.append(group)
                    if total >= budget:
                        break
                groups = remaining
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True,
                        help="Contains vctk/ and/or gtsinger/ original directories")
    parser.add_argument("--output", type=Path, required=True)
    # 18 supplies all splits in the published six-clip smoke sample. Fixed before
    # training; do not tune this seed using model outcomes.
    parser.add_argument("--seed", type=int, default=18)
    parser.add_argument("--seconds-per-kind", type=float, default=3600)
    args = parser.parse_args()
    if args.seconds_per_kind <= 0:
        parser.error("seconds-per-kind must be positive")
    records, skipped = [], []
    for corpus in ("vctk", "gtsinger"):
        folder = args.data_root / corpus
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in (".wav", ".flac"):
                continue
            relative = path.relative_to(folder)
            try:
                identity = identify(relative, corpus)
                records.append({"path": path.relative_to(args.data_root).as_posix(),
                                "corpus": corpus, **identity, **inspect_audio(path)})
            except (ValueError, RuntimeError) as exc:
                skipped.append({"path": path.relative_to(args.data_root).as_posix(), "reason": str(exc)})
    if not records:
        raise SystemExit("No recognized original audio found; nothing was prepared")
    rows = split_records(records, args.seed)
    pilot = select_pilot(rows, args.seconds_per_kind)
    summary = {f"{split}/{kind}": round(sum(r["seconds"] for r in pilot
                if r["split"] == split and r["kind"] == kind), 2)
               for split in ("train", "validation", "test") for kind in ("speech", "singing")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    coverage = all(v > 0 for v in summary.values())
    duration_target_met = all(sum(r["seconds"] for r in pilot if r["kind"] == kind)
                              >= args.seconds_per_kind for kind in ("speech", "singing"))
    payload = {"schema_version": 2, "sample_rate": 48000, "seed": args.seed,
               "data_root_hint": str(args.data_root.resolve()),
               "scope": "pilot_not_final_corpus", "records": pilot,
               "inventory": rows, "skipped": skipped, "seconds": summary,
               "listening_review": "pending", "coverage_complete": coverage,
               "duration_target_met": duration_target_met,
               "requested_seconds_per_kind": args.seconds_per_kind, "complete": False}
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"manifest": str(args.output), "seconds": summary,
                      "coverage_complete": coverage, "duration_target_met": duration_target_met,
                      "listening_review": "pending"}, indent=2))
    if not coverage:
        raise SystemExit("Pilot incomplete: missing a kind/split after leakage exclusions")


if __name__ == "__main__":
    main()

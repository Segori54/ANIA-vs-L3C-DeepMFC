"""Minibatched, resumable pipeline pilot using the existing GRU (NOT L3C)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
from time import perf_counter
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from .checkpoint import load_checkpoint, save_checkpoint
from .models import CausalSpectralGru
from .corpus import sha256


class Pairs(Dataset):
    def __init__(self, folder, split):
        self.folder = Path(folder).resolve()
        content = (self.folder / "manifest.json").read_bytes()
        self.digest = hashlib.sha256(content).hexdigest()
        manifest = json.loads(content)
        if manifest.get("split") != split or manifest.get("sample_rate") != 48000:
            raise ValueError(f"Expected {split} pairs at 48 kHz")
        if manifest.get("target") != "source_before_forward_gain_and_delay":
            raise ValueError("Unexpected target convention")
        self.rows = manifest["examples"]
        if not self.rows or {r["kind"] for r in self.rows} != {"speech", "singing"}:
            raise ValueError("Both speech and singing are required")
        for row in self.rows:
            path = (self.folder / row["file"]).resolve()
            if not path.is_relative_to(self.folder):
                raise ValueError("Pair path escapes folder")
            if sha256(path) != row.get("sha256"):
                raise ValueError("Pair hash mismatch; regenerate pairs from verified originals")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        path = (self.folder / row["file"]).resolve()
        if not path.is_relative_to(self.folder):
            raise ValueError("Pair path escapes folder")
        with np.load(path, allow_pickle=False) as pair:
            x = np.array(pair["input"], dtype=np.float32)
            y = np.array(pair["target"], dtype=np.float32)
        if x.ndim != 1 or x.shape != y.shape or len(x) < 960:
            raise ValueError("Invalid pair shape")
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Non-finite pair")
        return torch.from_numpy(x), torch.from_numpy(y), row["kind"], row["scenario"]


def check_disjoint(train, validation):
    for field in ("identity", "song", "source_sha256", "path_seed", "changed_path_seed"):
        a = {r.get(field) for r in train.rows} - {None, ""}
        b = {r.get(field) for r in validation.rows} - {None, ""}
        if a & b:
            raise ValueError(f"Train/validation leakage in {field}")
    paths = lambda data: {r.get(key) for r in data.rows for key in ("path_seed", "changed_path_seed")} - {None}
    if paths(train) & paths(validation):
        raise ValueError("Train/validation feedback path overlap")


def spectrum(x):
    # Conservative prototype frontend: 20 ms window / 5 ms hop. NOT the
    # low-latency synthesis from L3C; not approved for PA/monitor integration.
    frames = x.unfold(-1, 960, 240)
    window = torch.hann_window(960, periodic=False, device=x.device)
    result = torch.fft.rfft(frames * window, n=1024)
    return torch.view_as_real(result).flatten(-2)


def evaluate(model, loader, device):
    sums = {}
    model.eval()
    with torch.no_grad():
        for x, y, kinds, scenarios in loader:
            x, y = spectrum(x.to(device)), spectrum(y.to(device))
            prediction, _ = model(x)
            model_error = (prediction - y).square().mean(dim=(1, 2))
            bypass_error = (x - y).square().mean(dim=(1, 2))
            if not torch.isfinite(model_error).all():
                raise RuntimeError("Non-finite validation output")
            for index, (kind, scenario) in enumerate(zip(kinds, scenarios)):
                for key in (kind, kind + "/" + scenario):
                    entry = sums.setdefault(key, {"count": 0, "model_mse": 0.0, "bypass_mse": 0.0})
                    entry["count"] += 1
                    entry["model_mse"] += float(model_error[index])
                    entry["bypass_mse"] += float(bypass_error[index])
    for row in sums.values():
        row["model_mse"] /= row["count"]
        row["bypass_mse"] /= row["count"]
    return sums


def run(args):
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; use --device cpu explicitly for debugging")
    if args.epochs < 1 or args.batch_size < 1 or args.hidden < 1 or args.steps_per_epoch < 0:
        raise ValueError("Invalid training limits")
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(2)
    device = torch.device(args.device)
    train, validation = Pairs(args.train, "train"), Pairs(args.validation, "validation")
    check_disjoint(train, validation)
    model = CausalSpectralGru(hidden=args.hidden).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    config = {"model": "causal_gru_pipeline_pilot_not_l3c", "hidden": args.hidden,
              "sample_rate": 48000, "frame": 960, "hop": 240, "fft": 1024,
              "seed": args.seed, "batch_size": args.batch_size, "steps_per_epoch": args.steps_per_epoch,
              "train_sha256": train.digest, "validation_sha256": validation.digest}
    output = Path(args.output)
    if output.exists() and any(output.iterdir()) and not args.resume:
        raise FileExistsError("Run exists; use --resume or a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    start_epoch, best = 0, float("inf")
    if args.resume:
        payload = load_checkpoint(args.resume, model, optimizer, expected_config=config)
        start_epoch = payload["step"]
        best = payload["extra"]["best"]
        history = output / "history.jsonl"
        if history.exists():
            entries = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
            if entries and entries[-1]["epoch"] != start_epoch:
                raise ValueError("History and checkpoint disagree; resume in a new output directory")
        else:
            # A new directory is a branch of the experiment; select its best
            # checkpoint from its own subsequent validation results.
            best = float("inf")
        if start_epoch >= args.epochs:
            raise ValueError("Requested total epochs must exceed the checkpoint epoch")
    (output / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    counts = {kind: sum(r["kind"] == kind for r in train.rows) for kind in ("speech", "singing")}
    weights = [1.0 / counts[r["kind"]] for r in train.rows]
    validation_loader = DataLoader(validation, batch_size=args.batch_size, shuffle=False, num_workers=0)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    for epoch in range(start_epoch, args.epochs):
        # Epoch-specific sampler seed makes epoch-boundary resume independent of
        # OS file order and dataloader prefetch. num_workers=0 supports both hosts.
        generator = torch.Generator().manual_seed(args.seed + epoch)
        samples = args.steps_per_epoch * args.batch_size if args.steps_per_epoch else len(train)
        sampler = WeightedRandomSampler(weights, samples, replacement=True, generator=generator)
        loader = DataLoader(train, batch_size=args.batch_size, sampler=sampler, num_workers=0)
        model.train()
        total, batches = 0.0, 0
        started = perf_counter()
        for x, y, _, _ in loader:
            x, y = spectrum(x.to(device)), spectrum(y.to(device))
            optimizer.zero_grad(set_to_none=True)
            prediction, _ = model(x)
            loss = (prediction - y).square().mean()
            if not torch.isfinite(loss):
                raise RuntimeError("Non-finite training loss")
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0, error_if_nonfinite=True)
            optimizer.step()
            total += float(loss.detach())
            batches += 1
        metrics = evaluate(model, validation_loader, device)
        score = (metrics["speech"]["model_mse"] + metrics["singing"]["model_mse"]) / 2
        improved = score < best
        best = min(best, score)
        report = {"epoch": epoch + 1, "train_mse": total / batches, "validation": metrics,
                  "seconds": perf_counter() - started,
                  "peak_vram_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else None}
        save_checkpoint(output / "latest.pt", model, optimizer, step=epoch + 1, config=config, extra={"best": best})
        if improved:
            save_checkpoint(output / "best.pt", model, optimizer, step=epoch + 1, config=config, extra={"best": best})
        with (output / "history.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(report) + "\n")
        print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--steps-per-epoch", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260929)
    run(parser.parse_args())


if __name__ == "__main__":
    main()

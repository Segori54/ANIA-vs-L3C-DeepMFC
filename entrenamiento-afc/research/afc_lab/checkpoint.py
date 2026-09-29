"""Portable, atomic checkpoints. Only load checkpoints produced by this project."""
from __future__ import annotations

import os
from pathlib import Path
import random
import torch


def save_checkpoint(path, model, optimizer, *, step, config, extra=None):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1, "step": step, "config": config,
        "model": model.state_dict(), "optimizer": optimizer.state_dict(),
        "torch_rng": torch.get_rng_state(), "python_rng": random.getstate(),
        "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
        "extra": extra or {},
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, destination)


def load_checkpoint(path, model, optimizer=None, *, expected_config=None, restore_rng=True):
    # Load on CPU: RNG state must remain a CPU ByteTensor, even for CUDA models.
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported checkpoint schema")
    if expected_config is not None and payload["config"] != expected_config:
        raise ValueError("Checkpoint configuration differs from this experiment")
    model.load_state_dict(payload["model"])
    if optimizer is not None:
        optimizer.load_state_dict(payload["optimizer"])
    if restore_rng:
        torch.set_rng_state(payload["torch_rng"])
        random.setstate(payload["python_rng"])
        if payload["cuda_rng"] and torch.cuda.is_available():
            if len(payload["cuda_rng"]) != torch.cuda.device_count():
                raise ValueError("GPU count changed; resume with explicit RNG reset")
            torch.cuda.set_rng_state_all(payload["cuda_rng"])
    return payload

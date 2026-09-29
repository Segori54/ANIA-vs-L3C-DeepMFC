from __future__ import annotations

from time import perf_counter_ns
from typing import Callable
import numpy as np


def benchmark_blocks(
    processor: Callable[[np.ndarray], np.ndarray], block_size: int,
    blocks: int = 2000, sample_rate: int = 48_000, seed: int = 0,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    durations = np.empty(blocks, dtype=np.float64)
    for index in range(blocks):
        block = rng.normal(0.0, 0.1, block_size).astype(np.float32)
        start = perf_counter_ns()
        processor(block)
        durations[index] = (perf_counter_ns() - start) / 1.0e6
    period_ms = block_size * 1000.0 / sample_rate
    return {
        "block_size": float(block_size),
        "period_ms": period_ms,
        "p50_ms": float(np.percentile(durations, 50)),
        "p95_ms": float(np.percentile(durations, 95)),
        "p99_ms": float(np.percentile(durations, 99)),
        "rtf": float(np.sum(durations) / (blocks * period_ms)),
        "p99_budget_fraction": float(np.percentile(durations, 99) / period_ms),
    }

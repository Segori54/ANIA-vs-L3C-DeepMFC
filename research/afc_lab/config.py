from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any
from itertools import product


@dataclass(frozen=True)
class PathConfig:
    length: int = 256
    direct_delay: int = 48
    decay: float = 0.025


@dataclass(frozen=True)
class PatelConfig:
    probe_duration_ms: int = 200
    probe_level_dbfs: float = -30.0
    filter_length: int = 256
    regularisation: float = 1.0e-6
    reactive: bool = True
    path_change_seconds: float | None = None


@dataclass(frozen=True)
class ExperimentConfig:
    sample_rate: int = 48_000
    duration_seconds: float = 5.0
    seed: int = 0
    block_sizes: tuple[int, ...] = (64, 128, 256)
    gain_margin_db: float = 3.0
    snr_db: float | None = None
    signal_kind: str = "voice_like"
    path: PathConfig = field(default_factory=PathConfig)
    patel: PatelConfig = field(default_factory=PatelConfig)
    output_dir: str = "outputs/run"

    def validate(self) -> None:
        if self.sample_rate != 48_000:
            raise ValueError("The thesis protocol is fixed at 48000 Hz")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if not self.block_sizes or any(value <= 0 for value in self.block_sizes):
            raise ValueError("block_sizes must contain positive integers")
        if self.path.length <= 0 or self.path.direct_delay < 1:
            raise ValueError("path length and direct delay must be positive")
        if self.path.direct_delay >= self.path.length:
            raise ValueError("direct_delay must be smaller than path length")
        if self.patel.filter_length <= 0:
            raise ValueError("filter_length must be positive")
        if self.patel.probe_duration_ms <= 0:
            raise ValueError("probe_duration_ms must be positive")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["block_sizes"] = list(self.block_sizes)
        return value


def _read_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "Configuration is not JSON-compatible YAML; install PyYAML for general YAML"
            ) from exc
        value = yaml.safe_load(text)
        if not isinstance(value, dict):
            raise ValueError("configuration root must be a mapping")
        return value


def load_config(path: str | Path) -> ExperimentConfig:
    raw = _read_mapping(Path(path))
    path_config = PathConfig(**raw.pop("path", {}))
    patel_config = PatelConfig(**raw.pop("patel", {}))
    if "block_sizes" in raw:
        raw["block_sizes"] = tuple(int(value) for value in raw["block_sizes"])
    config = ExperimentConfig(path=path_config, patel=patel_config, **raw)
    config.validate()
    return config


def load_batch(path: str | Path) -> list[ExperimentConfig]:
    raw = _read_mapping(Path(path))
    base = raw.get("base")
    grid = raw.get("grid")
    if not isinstance(base, dict) or not isinstance(grid, dict) or not grid:
        raise ValueError("batch config requires base and a non-empty grid")
    keys = list(grid)
    value_lists = [grid[key] for key in keys]
    if any(not isinstance(values, list) or not values for values in value_lists):
        raise ValueError("every grid entry must be a non-empty list")

    configurations: list[ExperimentConfig] = []
    for run_index, values in enumerate(product(*value_lists)):
        materialised = json.loads(json.dumps(base))
        for dotted_key, value in zip(keys, values):
            cursor = materialised
            parts = dotted_key.split(".")
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = value
        root = Path(str(materialised.get("output_dir", "outputs/batch")))
        materialised["output_dir"] = str(root / f"run-{run_index:04d}")
        path_config = PathConfig(**materialised.pop("path", {}))
        patel_config = PatelConfig(**materialised.pop("patel", {}))
        if "block_sizes" in materialised:
            materialised["block_sizes"] = tuple(materialised["block_sizes"])
        config = ExperimentConfig(path=path_config, patel=patel_config, **materialised)
        config.validate()
        configurations.append(config)
    return configurations

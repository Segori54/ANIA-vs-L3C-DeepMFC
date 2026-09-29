from __future__ import annotations

import json
from pathlib import Path
import wave
import numpy as np


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype("<i2")
    with wave.open(str(destination), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm.tobytes())


def write_json(path: str | Path, value: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_metric_svg(path: str | Path, rows: list[dict[str, float | str]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = 760, 360
    methods = [str(row["method"]) for row in rows]
    values = [float(row["si_sdr_db"]) for row in rows]
    lower = min(values + [0.0])
    upper = max(values + [1.0])
    span = max(upper - lower, 1.0)
    bars = []
    bar_width = 560 / max(len(values), 1)
    for index, (method, value) in enumerate(zip(methods, values)):
        normalized = (value - lower) / span
        bar_height = 240 * normalized
        x = 120 + index * bar_width
        y = 300 - bar_height
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width-18:.1f}" height="{bar_height:.1f}" fill="#3b82f6"/>')
        bars.append(f'<text x="{x + (bar_width-18)/2:.1f}" y="322" text-anchor="middle" font-size="12">{method}</text>')
        bars.append(f'<text x="{x + (bar_width-18)/2:.1f}" y="{max(y-8, 24):.1f}" text-anchor="middle" font-size="12">{value:.2f}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><text x="380" y="24" text-anchor="middle" font-size="18">SI-SDR por método</text>
<line x1="100" y1="300" x2="720" y2="300" stroke="#111"/><text x="24" y="180" transform="rotate(-90 24 180)" text-anchor="middle">SI-SDR (dB)</text>
{''.join(bars)}</svg>'''
    destination.write_text(svg, encoding="utf-8")

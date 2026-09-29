"""Create a local venv, install the training stack, and run the GPU gate.

Windows: python research/bootstrap_training.py
Linux:   python3 research/bootstrap_training.py
No global packages, OS packages, or GPU drivers are modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--torch-wheel", type=Path, help="Previously checksum-verified wheel for this OS/Python")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Reuse the already installed workspace environment without relocating it.
    shared = root.parent / ".venv"
    environment = shared if shared.exists() else root / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)

    def call(*arguments):
        subprocess.run([str(python), *map(str, arguments)], cwd=root, check=True)

    if args.torch_wheel:
        call("-m", "pip", "install", "--no-cache-dir", args.torch_wheel.resolve())
    else:
        call("-m", "pip", "install", "--no-cache-dir", "torch==2.10.0+cu128",
             "--index-url", "https://download.pytorch.org/whl/cu128")
    call("-m", "pip", "install", "--no-cache-dir", "-r", root / "research/requirements-training.txt",
         "-e", root / "research")
    call("-m", "pip", "check")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    call("-m", "afc_lab.doctor", "--smoke", "--output", root / "outputs/training" / ("phase1-" + stamp))


if __name__ == "__main__":
    main()

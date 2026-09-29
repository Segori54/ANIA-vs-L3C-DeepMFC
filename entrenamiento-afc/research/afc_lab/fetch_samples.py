"""Download six original GTSinger clips for pipeline checks, NOT the full pilot."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen


SAMPLES = [
    ("Spanish/ES-Bass-1/Breathy/A Gritos de Esperanza/Control_Group/0000.wav", "2f962d479233250f50b44c27838ac70eeee71d2be323aaad716aa8d19e0f15b4"),
    ("Spanish/ES-Bass-1/Breathy/A Gritos de Esperanza/Paired_Speech_Group/0000.wav", "a657d27f4d64c79651787174c73d06277df81c2a8e6526cc0956bfb53ac89b5a"),
    ("Spanish/ES-Soprano-1/Breathy/Ecos De Amor/Control_Group/0000.wav", "1c862804972dd5506f90bb0e6e942f5654b0a58f1ad8e1f52c2756a20e28bca6"),
    ("Spanish/ES-Soprano-1/Breathy/Ecos De Amor/Paired_Speech_Group/0000.wav", "3d42f4d251cfa50f9a2454989508d2c83bff00cf62605092918f4c4efc07d237"),
    ("English/EN-Alto-1/Breathy/all is found/Control_Group/0000.wav", "d1b5ffcb84064e16733a2aa69bff8cfbde33925f975f6fd79654a89031609a47"),
    ("English/EN-Alto-1/Breathy/all is found/Paired_Speech_Group/0000.wav", "cb89b7b4950dc671c69351db5348b86ff31384c75c564f09d35241ee5cb231e3"),
]


def fetch_samples(root):
    root = Path(root) / "gtsinger"
    base = "https://huggingface.co/datasets/GTSinger/GTSinger/resolve/main/"

    def one(item):
        relative, expected = item
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = base + quote(relative, safe="/")
        if destination.exists():
            data = destination.read_bytes()
        else:
            with urlopen(url, timeout=90) as response:
                data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"Original sample changed or corrupted: {relative}")
        if not destination.exists():
            temporary = destination.with_suffix(".partial")
            temporary.write_bytes(data)
            os.replace(temporary, destination)
        return {"path": relative, "url": url, "sha256": actual, "bytes": len(data)}

    root.mkdir(parents=True, exist_ok=True)
    with urlopen(base + "dataset_license.md", timeout=30) as response:
        (root / "dataset_license.md").write_bytes(response.read())
    with ThreadPoolExecutor(max_workers=3) as executor:
        records = list(executor.map(one, SAMPLES))
    payload = {"scope": "six_clip_pipeline_smoke_not_one_hour_pilot", "files": records}
    (root / "samples-provenance.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    print(json.dumps(fetch_samples(args.data_root), indent=2))


if __name__ == "__main__":
    main()

"""Resume large HTTPS downloads in verified byte ranges, then check SHA-256."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request


def fetch(url, destination, *, expected_sha256=None, chunk_bytes=8 * 1024 * 1024, workers=4):
    if not 1 <= workers <= 16 or chunk_bytes < 1:
        raise ValueError("Use 1–16 workers and a positive chunk size")
    if not url.startswith("https://"):
        raise ValueError("HTTPS source required")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        digest = file_hash(destination)
        if expected_sha256 and digest != expected_sha256:
            raise ValueError("Existing file checksum mismatch; original file preserved")
        if expected_sha256:
            return {"url": url, "sha256": digest, "bytes": destination.stat().st_size}
        raise FileExistsError("Existing download has no expected hash; verify before reuse")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=60) as response:
        content_range = response.headers.get("Content-Range", "")
        match = re.fullmatch(r"bytes 0-0/(\d+)", content_range)
        if response.status != 206 or not match:
            raise ValueError("Server does not support byte ranges")
        size = int(match[1])
        etag = response.headers.get("ETag")
    parts = destination.with_name(destination.name + ".parts")
    parts.mkdir(exist_ok=True)
    metadata = {"url": url, "size": size, "etag": etag, "chunk_bytes": chunk_bytes}
    meta_path = parts / "source.json"
    if meta_path.exists() and json.loads(meta_path.read_text()) != metadata:
        raise ValueError("Remote file changed; partial download preserved, refusing to mix versions")
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    def one(start):
        end = min(start + chunk_bytes, size) - 1
        target = parts / str(start)
        if target.exists() and target.stat().st_size == end - start + 1:
            return
        for attempt in range(4):
            try:
                headers = {"Range": f"bytes={start}-{end}"}
                if etag:
                    headers["If-Match"] = etag
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise ValueError("Unexpected byte range")
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise ValueError("Truncated range")
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(data)
                os.replace(temporary, target)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)

    offsets = range(0, size, chunk_bytes)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, _ in enumerate(executor.map(one, offsets), 1):
            if index % 16 == 0 or index == len(offsets):
                print(f"download {min(index * chunk_bytes, size) / size:.1%}", flush=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    digest = hashlib.sha256()
    with temporary.open("wb") as output:
        for offset in offsets:
            block = (parts / str(offset)).read_bytes()
            digest.update(block)
            output.write(block)
    value = digest.hexdigest()
    if expected_sha256 and value != expected_sha256:
        raise ValueError("SHA-256 mismatch; download was not promoted")
    os.replace(temporary, destination)
    record = {**metadata, "sha256": value}
    destination.with_suffix(destination.suffix + ".source.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    # Keep range files to permit auditing/resumption; no automatic deletion.
    return record


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(fetch(args.url, args.destination, expected_sha256=args.sha256, workers=args.workers), indent=2))


if __name__ == "__main__":
    main()

"""Extract a small VCTK sample using HTTPS ZIP ranges, preserving original FLACs.

Only selected original entries are retrieved; this is NOT a full archive download.
ZIP CRC is checked by zipfile; extracted SHA-256s and the archive ETag are recorded.
The full archive MD5 cannot be verified without downloading the full archive.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import time
from urllib.request import Request, urlopen
import zipfile
from .dataset import deterministic_group_split


URL = "https://datashare.ed.ac.uk/server/api/core/bitstreams/535f4286-e54c-4038-838c-a02285e32cb2/content"
ETAG = '"8a6ba2946b36fcbef0212cad601f4bfa"'
SIZE = 11747302977


class RangeZip(io.RawIOBase):
    def __init__(self, cache_folder):
        super().__init__()
        self.position = 0
        self.cache_start, self.cache = 0, b""
        self.bytes_downloaded = 0
        self.cache_folder = Path(cache_folder)
        self.cache_folder.mkdir(parents=True, exist_ok=True)

    def get_range(self, bounds):
        start, end = bounds
        path = self.cache_folder / f"{start}-{end}.bin"
        if path.exists() and path.stat().st_size == end - start + 1:
            return path.read_bytes()
        for attempt in range(3):
            try:
                # DSpace returns 416 with If-Match; check every response ETag.
                request = Request(URL, headers={"Range": f"bytes={start}-{end}"})
                with urlopen(request, timeout=45) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{SIZE}":
                        raise ValueError("Archive range/version mismatch")
                    if response.headers.get("ETag") != ETAG:
                        raise ValueError("Archive ETag changed")
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise ValueError("Truncated archive range")
                temporary = path.with_suffix(".partial")
                temporary.write_bytes(data)
                temporary.replace(path)
                self.bytes_downloaded += len(data)
                return data
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else self.position + offset if whence == 1 else SIZE + offset
        if position < 0:
            raise ValueError("Invalid ZIP offset")
        self.position = position
        return position

    def read(self, size=-1):
        if self.position >= SIZE or size == 0:
            return b""
        size = SIZE - self.position if size < 0 else min(size, SIZE - self.position)
        if not (self.cache_start <= self.position and self.position + size <= self.cache_start + len(self.cache)):
            start = self.position
            end = min(SIZE, start + max(size, 65536)) - 1
            chunk = 1024 * 1024
            ranges = [(offset, min(end, offset + chunk - 1)) for offset in range(start, end + 1, chunk)]
            with ThreadPoolExecutor(max_workers=4) as executor:
                data = b"".join(executor.map(self.get_range, ranges))
            self.cache_start, self.cache = start, data
        offset = self.position - self.cache_start
        result = self.cache[offset:offset + size]
        self.position += len(result)
        return result


def fetch_samples(root, clips_per_speaker=2):
    if not 1 <= clips_per_speaker <= 10:
        raise ValueError("This utility is limited to 1–10 clips per speaker")
    root = Path(root) / "vctk"
    root.mkdir(parents=True, exist_ok=True)
    records = []
    with RangeZip(root / ".range-cache" / ETAG.strip('"')) as remote, zipfile.ZipFile(remote) as archive:
        candidates = [name for name in archive.namelist()
                      if re.fullmatch(r"p\d+_\d+_mic1\.flac", PurePosixPath(name).name)]
        speakers = sorted({PurePosixPath(name).stem.split("_")[0] for name in candidates})
        splits = deterministic_group_split(["vctk:" + s for s in speakers], 18)
        selected = [next(s for s in speakers if splits["vctk:" + s] == split)
                    for split in ("train", "validation", "test")]
        names = []
        for speaker in selected:
            names.extend(sorted(n for n in candidates if PurePosixPath(n).name.startswith(speaker + "_"))[:clips_per_speaker])
        names.extend(n for n in archive.namelist() if PurePosixPath(n).name.lower() in ("readme.txt", "license.txt", "copying"))
        for name in names:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or any(":" in part for part in relative.parts):
                raise ValueError("Unsafe ZIP entry")
            destination = root.joinpath(*relative.parts)
            data = archive.read(name)  # zipfile verifies entry CRC before returning.
            digest = hashlib.sha256(data).hexdigest()
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise ValueError("Existing original differs; preserved")
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            records.append({"path": relative.as_posix(), "sha256": digest,
                            "zip_crc32": archive.getinfo(name).CRC, "bytes": len(data)})
            print(f"VCTK original: {relative.name}", flush=True)
        downloaded = remote.bytes_downloaded
    # Explicit archive-level license, independently available from Edinburgh.
    license_url = "https://datashare.ed.ac.uk/server/api/core/bitstreams/956a1688-0b59-428c-8a2f-10837433dde3/content"
    with urlopen(license_url, timeout=30) as response:
        license_data = response.read()
    if hashlib.md5(license_data).hexdigest() != "2946b37a07baeba80cea628909e28cae":
        raise ValueError("VCTK license differs from official metadata")
    (root / "license_text.txt").write_bytes(license_data)
    result = {"scope": "small_pipeline_sample_not_full_corpus", "url": URL, "archive_etag": ETAG,
              "full_archive_checksum_verified": False, "entry_crc_verified": True,
              "bytes_downloaded": downloaded, "speakers": selected, "files": records}
    (root / "samples-provenance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--clips-per-speaker", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(fetch_samples(args.data_root, args.clips_per_speaker), indent=2))


if __name__ == "__main__":
    main()

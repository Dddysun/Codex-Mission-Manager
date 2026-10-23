#!/usr/bin/env python3
"""Fetch one pinned official CPython archive; verify before extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists(): raise SystemExit("Choose an empty destination")
    lock = json.loads((ROOT / "packaging/python-runtime.lock.json").read_text())
    assert lock["url"].startswith("https://github.com/astral-sh/python-build-standalone/releases/download/")
    destination.mkdir(parents=True)
    archive = destination / "runtime.tar.gz"
    with urllib.request.urlopen(lock["url"], timeout=90) as source, archive.open("wb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk: break
            target.write(chunk)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["sha256"]:
        archive.unlink()
        raise SystemExit("Runtime checksum mismatch; not extracted")
    with tarfile.open(archive, "r:gz") as package:
        for item in package.getmembers():
            if item.isdev(): raise SystemExit("Unexpected device in archive")
            paths = [destination / item.name]
            if item.issym(): paths.append(destination / item.name / ".." / item.linkname)
            if item.islnk(): paths.append(destination / item.linkname)
            for path in paths:
                try: path.resolve().relative_to(destination)
                except ValueError: raise SystemExit("Archive path outside destination")
        if hasattr(tarfile, "data_filter"): package.extractall(destination, filter="data")
        else: package.extractall(destination)
    print(destination / "python")


if __name__ == "__main__": main()

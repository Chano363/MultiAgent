"""Restore a verified binary-parts-v1 archive without overwriting existing data.

Usage: python scripts/restore_binary_parts.py PATH/trajectory.npz.parts.json
"""
import argparse
import hashlib
import json
from pathlib import Path


def restore(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    if spec.get("format") != "binary-parts-v1":
        raise ValueError("Unsupported archive format")
    base = manifest_path.parent
    name = spec["original_file"]
    if Path(name).name != name:
        raise ValueError("Invalid original filename")
    target = base / name
    if target.exists():
        with target.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if target.stat().st_size == spec["size_bytes"] and digest == spec["sha256"]:
            return target
        raise FileExistsError("Existing file differs; refusing to overwrite")
    # Verify all parts and the full stream before creating the restored file.
    digest = hashlib.sha256()
    size = 0
    for item in spec["parts"]:
        if Path(item["file"]).name != item["file"]:
            raise ValueError("Invalid part filename")
        data = (base / item["file"]).read_bytes()
        if len(data) != item["size_bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Part integrity check failed")
        digest.update(data)
        size += len(data)
    if size != spec["size_bytes"] or digest.hexdigest() != spec["sha256"]:
        raise ValueError("Archive integrity check failed")
    with target.open("xb") as output:
        for item in spec["parts"]:
            output.write((base / item["file"]).read_bytes())
    with target.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != spec["sha256"]:
            raise ValueError("Restored file integrity check failed")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    print(restore(parser.parse_args().manifest))

# docksmith/engine/layer.py
import hashlib
import io
import json
import os
import tarfile
from typing import List, Tuple


def sha256_of_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def make_layer_tar(files: List[Tuple[str, str]]) -> bytes:
    """
    Build a tar archive from a list of (host_path, archive_name) tuples.

    Rules (critical for reproducibility):
    - Entries added in lexicographic order of archive_name
    - All timestamps zeroed
    - No extra metadata that varies between runs

    Returns raw tar bytes.
    """
    buf = io.BytesIO()

    # Sort by archive path — critical for digest reproducibility
    sorted_files = sorted(files, key=lambda x: x[1])

    with tarfile.open(fileobj=buf, mode="w:") as tar:
        for host_path, archive_name in sorted_files:
            info = tar.gettarinfo(host_path, arcname=archive_name)

            # Zero out all timestamps
            info.mtime = 0
            info.uid   = 0
            info.gid   = 0
            info.uname = ""
            info.gname = ""

            if info.isreg():
                with open(host_path, "rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)

    return buf.getvalue()


def make_layer_tar_from_rootfs(rootfs_before: str, rootfs_after: str) -> bytes:
    """
    Produce a delta tar: files present in rootfs_after that are
    new or different compared to rootfs_before.

    Used by RUN: we snapshot before, run the command, snapshot after,
    then diff to produce the layer.
    """
    # Snapshot after state: path -> sha256
    after_files = {}
    for dirpath, dirnames, filenames in os.walk(rootfs_after):
        # Include directories themselves
        rel_dir = os.path.relpath(dirpath, rootfs_after)
        if rel_dir != ".":
            after_files[rel_dir] = None  # directory marker

        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel  = os.path.relpath(full, rootfs_after)
            after_files[rel] = sha256_of_file(full)

    # Snapshot before state
    before_files = {}
    for dirpath, dirnames, filenames in os.walk(rootfs_before):
        rel_dir = os.path.relpath(dirpath, rootfs_before)
        if rel_dir != ".":
            before_files[rel_dir] = None

        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel  = os.path.relpath(full, rootfs_before)
            before_files[rel] = sha256_of_file(full)

    # Find new or changed files
    delta = []
    for rel, digest in after_files.items():
        if rel not in before_files or before_files[rel] != digest:
            if digest is None:
                # It's a directory — add it
                full_after = os.path.join(rootfs_after, rel)
                delta.append((full_after, rel))
            else:
                full_after = os.path.join(rootfs_after, rel)
                delta.append((full_after, rel))

    if not delta:
        # No changes — return empty tar
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:"):
            pass
        return buf.getvalue()

    return make_layer_tar(delta)


def store_layer(layer_bytes: bytes, layers_dir: str) -> Tuple[str, int]:
    """
    Write layer bytes to layers_dir named by digest.
    Returns (digest, size).
    """
    digest = sha256_of_bytes(layer_bytes)
    size   = len(layer_bytes)
    dest   = os.path.join(layers_dir, digest)

    if not os.path.exists(dest):
        with open(dest, "wb") as f:
            f.write(layer_bytes)

    return digest, size


def extract_layer(layer_path: str, target_dir: str) -> None:
    """
    Extract a layer tar into target_dir.
    Later layers overwrite earlier ones (union filesystem behaviour).
    """
    with tarfile.open(layer_path, "r:*") as tar:
        tar.extractall(path=target_dir)


def assemble_rootfs(layer_digests: List[str], layers_dir: str, target_dir: str) -> None:
    """
    Extract all layers in order into target_dir.
    This is the assembled container filesystem.
    """
    for digest in layer_digests:
        layer_path = os.path.join(layers_dir, digest)
        if not os.path.exists(layer_path):
            raise FileNotFoundError(f"Layer not found on disk: {digest}")
        extract_layer(layer_path, target_dir)


def hash_files_for_cache(file_paths: List[str]) -> str:
    """
    For COPY cache key: SHA-256 of each source file's bytes,
    concatenated in lexicographically sorted path order.
    """
    h = hashlib.sha256()
    for path in sorted(file_paths):
        with open(path, "rb") as f:
            h.update(f.read())
    return "sha256:" + h.hexdigest()

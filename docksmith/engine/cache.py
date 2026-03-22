# docksmith/engine/cache.py
import hashlib
import json
import os
from typing import Dict, List, Optional


def _sha256_str(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def compute_cache_key(
    prev_digest:      str,
    instruction_text: str,
    workdir:          str,
    env:              Dict[str, str],
    copy_files_hash:  Optional[str] = None,
) -> str:
    """
    Compute a deterministic cache key for a COPY or RUN instruction.

    prev_digest      : digest of the previous layer (or base manifest digest)
    instruction_text : full instruction string e.g. "RUN echo hello"
    workdir          : current WORKDIR value, "" if not set
    env              : dict of accumulated ENV values so far
    copy_files_hash  : (COPY only) hash of source file contents
    """
    # Serialize env in lexicographically sorted key order
    if env:
        env_str = "\n".join(f"{k}={v}" for k, v in sorted(env.items()))
    else:
        env_str = ""

    parts = [
        prev_digest,
        instruction_text,
        workdir,
        env_str,
    ]

    if copy_files_hash is not None:
        parts.append(copy_files_hash)

    combined = "\n".join(parts)
    return _sha256_str(combined)


def load_index(cache_dir: str) -> Dict[str, str]:
    """Load cache index from disk. Returns empty dict if not found."""
    index_path = os.path.join(cache_dir, "index.json")
    if not os.path.exists(index_path):
        return {}
    with open(index_path, "r") as f:
        return json.load(f)


def save_index(cache_dir: str, index: Dict[str, str]) -> None:
    """Save cache index to disk."""
    index_path = os.path.join(cache_dir, "index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


def cache_lookup(
    cache_dir:  str,
    layers_dir: str,
    cache_key:  str,
) -> Optional[str]:
    """
    Look up a cache key.
    Returns the layer digest if:
      - the key exists in the index, AND
      - the layer file actually exists on disk
    Returns None on any miss.
    """
    index = load_index(cache_dir)
    if cache_key not in index:
        return None

    digest = index[cache_key]
    layer_path = os.path.join(layers_dir, digest)
    if not os.path.exists(layer_path):
        return None

    return digest


def cache_store(
    cache_dir:  str,
    cache_key:  str,
    digest:     str,
) -> None:
    """Store a cache_key → layer_digest mapping."""
    index = load_index(cache_dir)
    index[cache_key] = digest
    save_index(cache_dir, index)

# docksmith/store/image.py
import hashlib
import json
import os
from typing import Optional
from docksmith.store.paths import images_dir


def compute_manifest_digest(manifest: dict) -> str:
    canonical        = dict(manifest)
    canonical["digest"] = ""
    serialized       = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def save_manifest(manifest: dict) -> str:
    fname = f"{manifest['name']}:{manifest['tag']}.json"
    path  = os.path.join(images_dir(), fname)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return path


def load_manifest(name: str, tag: str) -> Optional[dict]:
    fname = f"{name}:{tag}.json"
    path  = os.path.join(images_dir(), fname)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def delete_manifest(name: str, tag: str) -> bool:
    fname = f"{name}:{tag}.json"
    path  = os.path.join(images_dir(), fname)
    if not os.path.exists(path):
        return False
    os.unlink(path)
    return True

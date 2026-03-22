# docksmith/store/paths.py
import os

def root_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".docksmith")

def images_dir() -> str:
    return os.path.join(root_dir(), "images")

def layers_dir() -> str:
    return os.path.join(root_dir(), "layers")

def cache_dir() -> str:
    return os.path.join(root_dir(), "cache")

def init_dirs() -> None:
    """Create all state directories if they don't exist."""
    for d in [images_dir(), layers_dir(), cache_dir()]:
        os.makedirs(d, exist_ok=True)

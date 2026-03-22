import os

def root_dir() -> str:
    # Use SUDO_USER if running under sudo, so state always lives in the
    # real user's home, not /root/
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd
        home = pwd.getpwnam(sudo_user).pw_dir
    else:
        home = os.path.expanduser("~")
    return os.path.join(home, ".docksmith")

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

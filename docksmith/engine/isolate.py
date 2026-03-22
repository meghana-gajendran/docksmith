# docksmith/engine/isolate.py
import ctypes
import os
import subprocess
import sys
from typing import Dict, List, Optional

# Linux namespace flags
CLONE_NEWNS  = 0x00020000   # new mount namespace
CLONE_NEWPID = 0x20000000   # new PID namespace
CLONE_NEWUTS = 0x04000000   # new UTS (hostname) namespace

libc = ctypes.CDLL("libc.so.6", use_errno=True)


def _unshare(flags: int) -> None:
    """Call Linux unshare() syscall to create new namespaces."""
    ret = libc.unshare(flags)
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _child_setup(rootfs: str, workdir: str, env: Dict[str, str]) -> None:
    """
    This runs inside the child process before exec.
    Sets up isolation: namespaces + chroot.
    """
    try:
        # Create new mount and UTS namespaces
        _unshare(CLONE_NEWNS | CLONE_NEWUTS)

        # chroot into the assembled layer filesystem
        os.chroot(rootfs)

        # Set working directory (must exist inside rootfs)
        target_workdir = workdir if workdir else "/"
        try:
            os.chdir(target_workdir)
        except FileNotFoundError:
            os.chdir("/")

    except Exception as e:
        print(f"[isolate] setup error: {e}", file=sys.stderr)
        sys.exit(1)


def run_isolated(
    rootfs:  str,
    command: List[str],
    env:     Dict[str, str],
    workdir: str = "/",
) -> int:
    """
    Run a command isolated inside rootfs.

    - rootfs  : path to the assembled layer filesystem on the host
    - command : list of strings e.g. ["/bin/sh", "-c", "echo hello"]
    - env     : environment variables to inject
    - workdir : working directory inside the container

    Returns the exit code of the process.
    Requires root (sudo).
    """
    # Build environment list for the child
    child_env = {**env}

    # Ensure PATH is set if not already
    if "PATH" not in child_env:
        child_env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    proc = subprocess.Popen(
        command,
        env=child_env,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        preexec_fn=lambda: _child_setup(rootfs, workdir, child_env),
    )

    proc.wait()
    return proc.returncode


def run_isolated_capture(
    rootfs:  str,
    command: List[str],
    env:     Dict[str, str],
    workdir: str = "/",
) -> tuple:
    """
    Same as run_isolated but captures stdout/stderr.
    Used internally during RUN steps in build.
    Returns (returncode, stdout_bytes, stderr_bytes).
    """
    child_env = {**env}
    if "PATH" not in child_env:
        child_env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    proc = subprocess.Popen(
        command,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=lambda: _child_setup(rootfs, workdir, child_env),
    )

    stdout, stderr = proc.communicate()
    return proc.returncode, stdout, stderr

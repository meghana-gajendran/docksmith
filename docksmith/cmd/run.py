# docksmith/cmd/run.py
import click
import os
import shutil
import tempfile

from docksmith.engine.isolate import run_isolated
from docksmith.engine.layer import assemble_rootfs
from docksmith.store.image import load_manifest
from docksmith.store.paths import init_dirs, layers_dir


@click.command()
@click.argument("image")
@click.argument("cmd_args", nargs=-1)
@click.option("-e", "env_overrides", multiple=True, help="KEY=VALUE")
def run(image, cmd_args, env_overrides):
    """Run a container from an image."""
    init_dirs()

    # Parse name:tag
    if ":" in image:
        name, tag = image.split(":", 1)
    else:
        name, tag = image, "latest"

    # Load manifest
    manifest = load_manifest(name, tag)
    if manifest is None:
        click.echo(f"Error: image '{image}' not found.", err=True)
        raise SystemExit(1)

    cfg     = manifest.get("config", {})
    workdir = cfg.get("WorkingDir", "/") or "/"

    # Build env from image config
    env = {}
    for item in cfg.get("Env", []):
        if "=" in item:
            k, v = item.split("=", 1)
            env[k] = v

    # Apply -e overrides (take precedence)
    for override in env_overrides:
        if "=" in override:
            k, v = override.split("=", 1)
            env[k] = v
        else:
            click.echo(f"Warning: ignoring malformed -e value: {override}", err=True)

    # Determine command
    if cmd_args:
        command = list(cmd_args)
    elif cfg.get("Cmd"):
        command = cfg["Cmd"]
    else:
        click.echo(
            f"Error: no CMD defined in image '{image}' and no command given.",
            err=True,
        )
        raise SystemExit(1)

    # Assemble rootfs
    rootfs_tmp = tempfile.mkdtemp(prefix="docksmith_rootfs_")
    try:
        layer_digests = [l["digest"] for l in manifest["layers"]]
        assemble_rootfs(layer_digests, layers_dir(), rootfs_tmp)

        # Create workdir inside rootfs if needed
        if workdir and workdir != "/":
            wd_path = os.path.join(rootfs_tmp, workdir.lstrip("/"))
            os.makedirs(wd_path, exist_ok=True)

        # Run
        rc = run_isolated(
            rootfs  = rootfs_tmp,
            command = command,
            env     = env,
            workdir = workdir,
        )

        raise SystemExit(rc)

    finally:
        shutil.rmtree(rootfs_tmp, ignore_errors=True)

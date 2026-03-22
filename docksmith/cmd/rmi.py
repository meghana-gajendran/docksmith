# docksmith/cmd/rmi.py
import click
import os

from docksmith.store.image import delete_manifest, load_manifest
from docksmith.store.paths import init_dirs, layers_dir


@click.command()
@click.argument("image")
def rmi(image):
    """Remove an image and its layer files."""
    init_dirs()

    if ":" in image:
        name, tag = image.split(":", 1)
    else:
        name, tag = image, "latest"

    # Load manifest first to get layer digests
    manifest = load_manifest(name, tag)
    if manifest is None:
        click.echo(f"Error: image '{image}' not found.", err=True)
        raise SystemExit(1)

    # Delete each layer file
    ldir = layers_dir()
    for layer in manifest.get("layers", []):
        digest     = layer["digest"]
        layer_path = os.path.join(ldir, digest)
        if os.path.exists(layer_path):
            os.unlink(layer_path)
            click.echo(f"Deleted layer {digest[:19]}...")
        else:
            click.echo(f"Layer already missing: {digest[:19]}...")

    # Delete manifest
    delete_manifest(name, tag)
    click.echo(f"Removed image {name}:{tag}")

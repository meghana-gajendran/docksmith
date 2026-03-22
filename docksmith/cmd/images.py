# docksmith/cmd/images.py
import click
import json
import os
import glob
from docksmith.store.paths import images_dir


@click.command()
def images():
    """List all images in the local store."""
    img_dir = images_dir()
    pattern = os.path.join(img_dir, "*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        click.echo("No images found.")
        return

    # Print header
    click.echo(f"{'NAME':<20} {'TAG':<15} {'ID':<15} {'CREATED'}")
    click.echo("-" * 70)

    for fpath in files:
        with open(fpath) as f:
            m = json.load(f)
        name    = m.get("name", "?")
        tag     = m.get("tag", "?")
        digest  = m.get("digest", "")
        created = m.get("created", "?")
        short_id = digest.replace("sha256:", "")[:12]
        click.echo(f"{name:<20} {tag:<15} {short_id:<15} {created}")

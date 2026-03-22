import click

@click.command(name="import")
@click.argument("tarfile")
def import_image(tarfile):
    """Import a base image from a Docker-saved tar file."""
    click.echo(f"[import] tarfile={tarfile}")

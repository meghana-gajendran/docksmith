# main.py
import click
from docksmith.cmd.build import build
from docksmith.cmd.images import images
from docksmith.cmd.run import run
from docksmith.cmd.rmi import rmi
from docksmith.cmd.import_image import import_image

@click.group()
def cli():
    """Docksmith — a simplified Docker-like build and runtime system."""
    pass

cli.add_command(build)
cli.add_command(images)
cli.add_command(run)
cli.add_command(rmi)
cli.add_command(import_image)

if __name__ == "__main__":
    cli()

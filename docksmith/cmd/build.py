# docksmith/cmd/build.py
import click
import os
from docksmith.engine.builder import build as run_build


@click.command()
@click.option("-t", "tag", required=True, help="Name and tag e.g. myapp:latest")
@click.option("--no-cache", "no_cache", is_flag=True, default=False)
@click.argument("context", default=".")
def build(tag, no_cache, context):
    """Build an image from a Docksmithfile."""
    context = os.path.abspath(context)
    run_build(context_dir=context, name_tag=tag, no_cache=no_cache)

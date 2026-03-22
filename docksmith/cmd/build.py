import click

@click.command()
@click.option("-t", "tag", required=True, help="Name and tag e.g. myapp:latest")
@click.option("--no-cache", is_flag=True, default=False)
@click.argument("context", default=".")
def build(tag, no_cache, context):
    """Build an image from a Docksmithfile."""
    click.echo(f"[build] tag={tag} context={context} no_cache={no_cache}")

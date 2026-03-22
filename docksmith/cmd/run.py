import click

@click.command()
@click.argument("image")
@click.argument("cmd_args", nargs=-1)
@click.option("-e", "env_overrides", multiple=True, help="KEY=VALUE")
def run(image, cmd_args, env_overrides):
    """Run a container from an image."""
    click.echo(f"[run] image={image} cmd={cmd_args} env={env_overrides}")

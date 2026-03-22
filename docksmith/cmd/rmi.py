import click

@click.command()
@click.argument("image")
def rmi(image):
    """Remove an image and its layers."""
    click.echo(f"[rmi] image={image}")

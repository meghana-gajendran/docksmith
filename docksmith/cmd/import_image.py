# docksmith/cmd/import_image.py
import click
import tarfile
import json
import hashlib
import os
import shutil
import tempfile
from docksmith.store.paths import init_dirs, layers_dir, images_dir


def sha256_of_file(path: str) -> str:
    """Compute sha256 digest of a file's raw bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_manifest_digest(manifest: dict) -> str:
    """Compute digest with digest field set to empty string."""
    canonical = dict(manifest)
    canonical["digest"] = ""
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return sha256_of_bytes(serialized)


@click.command(name="import")
@click.argument("tarpath")
def import_image(tarpath):
    """Import a base image from a Docker-saved tar file."""

    init_dirs()

    tarpath = os.path.expanduser(tarpath)
    if not os.path.exists(tarpath):
        click.echo(f"Error: file not found: {tarpath}", err=True)
        raise SystemExit(1)

    click.echo(f"Importing {tarpath} ...")

    with tarfile.open(tarpath, "r") as outer:

        # --- Read manifest.json ---
        manifest_bytes = outer.extractfile("manifest.json").read()
        manifests = json.loads(manifest_bytes)
        if not manifests:
            click.echo("Error: empty manifest.json", err=True)
            raise SystemExit(1)
        m = manifests[0]

        repo_tags = m.get("RepoTags", [])
        if not repo_tags:
            click.echo("Error: no RepoTags in manifest", err=True)
            raise SystemExit(1)

        # Parse name and tag from e.g. "alpine:3.18"
        full_tag = repo_tags[0]
        if ":" in full_tag:
            # strip docker registry prefix if present e.g. docker.io/library/alpine:3.18
            short = full_tag.split("/")[-1]
            name, tag = short.split(":", 1)
        else:
            name, tag = full_tag, "latest"

        click.echo(f"  Name: {name}  Tag: {tag}")

        # --- Read config blob ---
        config_path = m["Config"]
        config_bytes = outer.extractfile(config_path).read()
        config_data = json.loads(config_bytes)

        img_config = config_data.get("config", {})
        env_list   = img_config.get("Env", [])
        cmd_list   = img_config.get("Cmd", [])
        workdir    = img_config.get("WorkingDir", "/")
        created    = config_data.get("created", "")

        # --- Process each layer ---
        layer_entries = []
        for layer_path in m["Layers"]:
            click.echo(f"  Processing layer: {layer_path}")

            # Extract layer tar to a temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tar") as tmp:
                tmp_path = tmp.name
                layer_bytes = outer.extractfile(layer_path).read()
                tmp.write(layer_bytes)

            # Compute digest from raw bytes
            digest = sha256_of_bytes(layer_bytes)
            size   = len(layer_bytes)

            # Copy to ~/.docksmith/layers/<digest>
            dest = os.path.join(layers_dir(), digest)
            if os.path.exists(dest):
                click.echo(f"    Layer {digest[:19]}... already exists, skipping.")
            else:
                shutil.move(tmp_path, dest)
                click.echo(f"    Stored layer {digest[:19]}... ({size} bytes)")

            # Find createdBy from history (skip empty_layer entries)
            history = config_data.get("history", [])
            non_empty = [h for h in history if not h.get("empty_layer", False)]
            idx = len(layer_entries)
            created_by = non_empty[idx]["created_by"] if idx < len(non_empty) else layer_path

            layer_entries.append({
                "digest":    digest,
                "size":      size,
                "createdBy": created_by,
            })

            # Clean up temp if still around
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # --- Build Docksmith manifest ---
        manifest = {
            "name":    name,
            "tag":     tag,
            "digest":  "",
            "created": created,
            "config": {
                "Env":        env_list,
                "Cmd":        cmd_list,
                "WorkingDir": workdir,
            },
            "layers": layer_entries,
        }

        # Compute and set digest
        manifest["digest"] = compute_manifest_digest(manifest)

        # Write manifest to ~/.docksmith/images/<name>:<tag>.json
        manifest_filename = f"{name}:{tag}.json"
        manifest_path = os.path.join(images_dir(), manifest_filename)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        click.echo(f"\n✓ Imported {name}:{tag}")
        click.echo(f"  Digest:  {manifest['digest']}")
        click.echo(f"  Layers:  {len(layer_entries)}")
        click.echo(f"  Written: {manifest_path}")

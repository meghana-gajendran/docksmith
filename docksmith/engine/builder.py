# docksmith/engine/builder.py
import copy
import glob
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from docksmith.engine.cache import (
    cache_lookup, cache_store, compute_cache_key
)
from docksmith.engine.isolate import run_isolated
from docksmith.engine.layer import (
    assemble_rootfs, hash_files_for_cache, make_layer_tar,
    make_layer_tar_from_rootfs, sha256_of_bytes, store_layer
)
from docksmith.engine.parser import Instruction, parse
from docksmith.store.image import compute_manifest_digest, load_manifest, save_manifest
from docksmith.store.paths import cache_dir, images_dir, init_dirs, layers_dir


def _parse_name_tag(name_tag: str):
    if ":" in name_tag:
        name, tag = name_tag.split(":", 1)
    else:
        name, tag = name_tag, "latest"
    return name, tag


def _resolve_copy_sources(args: str, context_dir: str):
    parts = args.split()
    if len(parts) < 2:
        raise ValueError(f"COPY requires at least src and dest, got: {args}")

    dest    = parts[-1]
    srcs    = parts[:-1]

    files = []
    for pattern in srcs:
        full_pattern = os.path.join(context_dir, pattern)
        matched = glob.glob(full_pattern, recursive=True)
        if not matched:
            raise FileNotFoundError(f"COPY: no files matched '{pattern}'")
        for m in matched:
            if os.path.isfile(m):
                files.append(m)
            elif os.path.isdir(m):
                for root, dirs, fnames in os.walk(m):
                    for fname in fnames:
                        files.append(os.path.join(root, fname))

    if not files:
        raise FileNotFoundError(f"COPY: no source files found for: {srcs}")

    return sorted(files), dest


def _make_copy_layer(files: List[str], dest: str, context_dir: str) -> bytes:
    entries = []
    for f in files:
        rel = os.path.relpath(f, context_dir)
        archive_name = os.path.join(dest.lstrip("/"), rel)
        entries.append((f, archive_name))
    return make_layer_tar(entries)


def _env_dict_to_list(env: Dict[str, str]) -> List[str]:
    return [f"{k}={v}" for k, v in sorted(env.items())]


def build(context_dir: str, name_tag: str, no_cache: bool = False):
    init_dirs()

    name, tag = _parse_name_tag(name_tag)
    docksmithfile = os.path.join(context_dir, "Docksmithfile")

    if not os.path.exists(docksmithfile):
        print(f"Error: no Docksmithfile found in {context_dir}")
        raise SystemExit(1)

    instructions = parse(docksmithfile)
    total_steps  = len(instructions)
    build_start  = time.time()

    layer_entries   = []
    env_state       = {}
    workdir_state   = ""
    cmd_state       = []
    prev_digest     = None
    cascade_miss    = False
    original_created = None

    for step_idx, instr in enumerate(instructions, start=1):
        step_label = f"Step {step_idx}/{total_steps} : {instr.op} {instr.args}"

        if instr.op == "FROM":
            print(step_label)
            base_name, base_tag = _parse_name_tag(instr.args)
            manifest = load_manifest(base_name, base_tag)
            if manifest is None:
                print(f"Error: base image '{instr.args}' not found in local store.")
                print(f"Run: python main.py import <tarfile>")
                raise SystemExit(1)

            layer_entries = list(manifest["layers"])

            base_cfg     = manifest.get("config", {})
            env_list     = base_cfg.get("Env", [])
            workdir_state = base_cfg.get("WorkingDir", "/") or "/"
            cmd_state    = base_cfg.get("Cmd", [])

            for item in env_list:
                if "=" in item:
                    k, v = item.split("=", 1)
                    env_state[k] = v

            prev_digest = manifest["digest"]
            original_created = manifest.get("created")
            continue

        if instr.op == "WORKDIR":
            print(step_label)
            workdir_state = instr.args
            continue

        if instr.op == "ENV":
            print(step_label)
            if "=" in instr.args:
                k, v = instr.args.split("=", 1)
                env_state[k.strip()] = v.strip()
            continue

        if instr.op == "CMD":
            print(step_label)
            cmd_state = json.loads(instr.args)
            continue

        step_start = time.time()

        if instr.op == "COPY":
            files, dest = _resolve_copy_sources(instr.args, context_dir)
            files_hash  = hash_files_for_cache(files)
            cache_key   = compute_cache_key(
                prev_digest=prev_digest,
                instruction_text=f"{instr.op} {instr.args}",
                workdir=workdir_state,
                env=env_state,
                copy_files_hash=files_hash,
            )
        else:
            cache_key = compute_cache_key(
                prev_digest=prev_digest,
                instruction_text=f"{instr.op} {instr.args}",
                workdir=workdir_state,
                env=env_state,
            )

        hit_digest = None
        if not no_cache and not cascade_miss:
            hit_digest = cache_lookup(cache_dir(), layers_dir(), cache_key)

        if hit_digest:
            elapsed = time.time() - step_start
            print(f"{step_label} [CACHE HIT] {elapsed:.2f}s")
            digest = hit_digest
            layer_size = os.path.getsize(os.path.join(layers_dir(), digest))

        else:
            cascade_miss = True

            if instr.op == "COPY":
                layer_bytes = _make_copy_layer(files, dest, context_dir)
                digest, layer_size = store_layer(layer_bytes, layers_dir())

            else:  # RUN (FIXED)
                rootfs_tmp = tempfile.mkdtemp(prefix="docksmith_run_")
                try:
                    if workdir_state and workdir_state != "/":
                        wd_in_rootfs = os.path.join(
                            rootfs_tmp, workdir_state.lstrip("/")
                        )
                        os.makedirs(wd_in_rootfs, exist_ok=True)

                    all_digests = [l["digest"] for l in layer_entries]
                    assemble_rootfs(all_digests, layers_dir(), rootfs_tmp)

                    def snapshot(rootfs):
                        state = {}
                        for dirpath, dirs, fnames in os.walk(rootfs):
                            for fname in fnames:
                                full = os.path.join(dirpath, fname)
                                rel  = os.path.relpath(full, rootfs)
                                try:
                                    st = os.stat(full)
                                    state[rel] = (st.st_size, st.st_mtime)
                                except OSError:
                                    pass
                        return state

                    before_state = snapshot(rootfs_tmp)

                    cmd = ["/bin/sh", "-c", instr.args]
                    rc  = run_isolated(
                        rootfs=rootfs_tmp,
                        command=cmd,
                        env=env_state,
                        workdir=workdir_state or "/",
                    )

                    if rc != 0:
                        print(f"Error: RUN failed with exit code {rc}")
                        raise SystemExit(rc)

                    after_state = snapshot(rootfs_tmp)
                    changed = []
                    for rel, info in after_state.items():
                        if rel not in before_state or before_state[rel] != info:
                            full = os.path.join(rootfs_tmp, rel)
                            changed.append((full, rel))

                    if changed:
                        layer_bytes = make_layer_tar(changed)
                    else:
                        import io, tarfile
                        buf = io.BytesIO()
                        with tarfile.open(fileobj=buf, mode="w:"):
                            pass
                        layer_bytes = buf.getvalue()

                    digest, layer_size = store_layer(layer_bytes, layers_dir())

                finally:
                    shutil.rmtree(rootfs_tmp, ignore_errors=True)

            if not no_cache:
                cache_store(cache_dir(), cache_key, digest)

            elapsed = time.time() - step_start
            print(f"{step_label} [CACHE MISS] {elapsed:.2f}s")

        prev_digest = digest
        layer_entries.append({
            "digest": digest,
            "size": layer_size,
            "createdBy": f"{instr.op} {instr.args}",
        })

    total_elapsed = time.time() - build_start

    created = original_created if not cascade_miss and original_created \
              else datetime.now(timezone.utc).isoformat()

    manifest = {
        "name": name,
        "tag": tag,
        "digest": "",
        "created": created,
        "config": {
            "Env": _env_dict_to_list(env_state),
            "Cmd": cmd_state,
            "WorkingDir": workdir_state,
        },
        "layers": layer_entries,
    }

    manifest["digest"] = compute_manifest_digest(manifest)
    save_manifest(manifest)

    short_digest = manifest["digest"].replace("sha256:", "")[:12]
    print(f"\nSuccessfully built sha256:{short_digest} {name}:{tag} ({total_elapsed:.2f}s)")

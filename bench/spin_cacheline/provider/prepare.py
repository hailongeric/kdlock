#!/usr/bin/env python3
"""Prepare a private provider source tree; never edit the production checkout.

The checked overlay only adds benchmark observations. Keeping it explicit makes
the variant reviewable without maintaining another copy of the lock protocol.
Run preparation/build/tests in the recovery guest, like the rest of this bench.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = HERE.parent / ".build/provider"
KIND = "spin_cacheline private provider"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def production_files(root):
    """Copy build inputs only, excluding objects, editor files and Kbuild output."""
    return sorted(path.relative_to(root) for directory in ("include", "kernel_module")
                  for path in (root / directory).rglob("*")
                  if path.is_file() and
                  not any(p.startswith(".") for p in path.relative_to(root).parts) and
                  (path.suffix in (".c", ".inc", ".h", ".S", ".def") or path.name == "Makefile") and
                  not path.name.endswith(".mod.c"))


def prepare(output=BUILD, root=ROOT):
    output, root = Path(output), Path(root)
    # Refuse an arbitrary existing directory. A failed preparation remains
    # marked as ours, so the next explicit build can replace its partial files.
    marker = output / "manifest.json"
    if output.exists():
        if (output.is_symlink() or not marker.is_file() or
                json.loads(marker.read_text()).get("kind") != KIND):
            raise RuntimeError(f"refusing to replace an unowned build directory: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    marker.write_text(json.dumps(dict(kind=KIND, complete=False)) + "\n")
    files = production_files(root)
    base = {str(p): digest(root / p) for p in files}
    overlay = {p.name: digest(p) for p in
               (HERE / "observation.patch", HERE / "kd_bench.c", HERE / "kd_bench.h")}
    for relative in files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    shutil.copyfile(HERE / "kd_bench.c", output / "kernel_module/kd_bench.c")
    shutil.copyfile(HERE / "kd_bench.h", output / "include/kd_bench.h")
    # No fuzzy matching or reverse application: an incompatible project update
    # must fail here, before compiling or loading an unreviewed instrumentation.
    result = subprocess.run(["patch", "--batch", "--forward", "--fuzz=0",
                             "--no-backup-if-mismatch", "-p1", "-i",
                             str(HERE / "observation.patch")], cwd=output,
                            text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("provider observation overlay failed:\n" + result.stdout + result.stderr)
    if base != {str(p): digest(root / p) for p in files}:
        raise RuntimeError("production inputs changed during provider preparation")
    manifest = dict(kind=KIND, complete=True, production=base, observation=overlay,
                    prepared={str(p): digest(output / p) for p in production_files(output)},
                    patch_output=result.stdout)
    marker.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    manifest = prepare()
    print(manifest["patch_output"], end="")
    print(f"Private provider prepared at {BUILD}; production files unchanged.")

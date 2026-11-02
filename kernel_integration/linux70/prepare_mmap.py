#!/usr/bin/env python3
"""Prepare a Linux 7 mmap wrapper overlay; leave the input tree/config untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(ROOT):
        raise ValueError("a new output directory outside source and project is required")
    manifest = json.loads((HERE / "mmap-base-sha256.json").read_text())
    for name, expected in (manifest["files"] | manifest["native_bodies"]).items():
        if digest(source / name) != expected:
            raise ValueError("Ubuntu 7.0.0-38.38 input differs: " + name)
    patch = HERE / "mmap-lock.patch"
    paths = re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(), re.M)
    if len(paths) != len(manifest["files"]) or set(paths) != set(manifest["files"]):
        raise ValueError("patch exceeds the reviewed wrapper scope")
    output.mkdir(parents=True)
    tree = output / "overlay"
    result = dict(passed=False, source_package=manifest["source_package"],
                  source=str(source), overlay=str(tree), kernel_built=False,
                  installed=False, booted=False, live_mm_tests=0,
                  wrapper_policy="reserved-deferred-read-v2",
                  wrapper_input_files=len(manifest["files"]),
                  native_bpf_when_disabled=True,
                  config_symbol=manifest["config_symbol"], config_modified=False,
                  patch_sha256=digest(patch),
                  base_manifest_sha256=digest(HERE / "mmap-base-sha256.json"),
                  native_body_sha256=manifest["native_bodies"])
    try:
        for name in manifest["files"]:
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        completed = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
            cwd=tree, text=True, capture_output=True, timeout=60, check=True)
        (output / "patch.log").write_text(completed.stdout + completed.stderr)
        # The clobber entry must belong to the protected caller's frame, not
        # an outlined acquisition wrapper which returns before its body starts.
        # These are lock API declarations only; their native bodies stay exact.
        header = tree / 'include/linux/mmap_lock.h'
        text = header.read_text()
        inline_declarations = (
            'static inline void mmap_write_lock(',
            'static inline void mmap_write_lock_nested(',
            'static inline int __must_check mmap_write_lock_killable(',
        )
        for declaration in inline_declarations:
            if text.count(declaration) != 1:
                raise ValueError('writer wrapper declaration changed: ' + declaration)
            text = text.replace(declaration, declaration.replace('inline', '__always_inline', 1))
        header.write_text(text)
        result['capture_inline_declarations'] = list(inline_declarations)
        generator = ROOT / "kernel_integration/mmap_lock/prepare.py"
        # Only the shared source generator is reused; the retired 6.1 entry
        # point, archive reconstruction and kernel configuration are not run.
        inputs, generated = runpy.run_path(str(generator))["generated_sources"](tree)
        inputs[str(generator.relative_to(ROOT))] = digest(generator)
        inputs[str(Path(__file__).relative_to(ROOT))] = digest(Path(__file__))
        outputs = {name: digest(tree / name) for name in manifest["files"]}
        outputs.update(generated)
        for name, expected in (manifest["files"] | manifest["native_bodies"]).items():
            if digest(source / name) != expected:
                raise ValueError("input changed during preparation: " + name)
        result.update(passed=True, inputs=inputs, outputs=outputs,
                      source_unchanged=True, generated_sources=len(generated))
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        (output / "prepare.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="authenticated, unmodified Ubuntu source")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not os.uname().release.startswith("7.0."):
        raise SystemExit("run preparation only in the designated Linux 7 guest")
    result = prepare(args.source, args.output)
    print(json.dumps({name: result[name] for name in
                      ("passed", "overlay", "generated_sources", "config_modified")}))


if __name__ == "__main__":
    main()

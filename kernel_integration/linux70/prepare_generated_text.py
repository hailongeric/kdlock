#!/usr/bin/env python3
"""Prepare the optional ITS inventory producer; leave source/config untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PACKAGE = "linux=7.0.0-38.38"
KIND = "its-page-inventory-v1"
BASE_SHA256 = "aea30078622661afabd2e4ab28873c34b2b14d4fe6a8a88b7e374f9ef784dcdb"
PATCH_SHA256 = "58a4dfaa50314c4f2904744b88c602d6af91fd2313fed0c0cf48f3d994b5c15c"
LOOKUP_WORK_UNITS = 4096
PATCH_PATHS = frozenset(("arch/x86/kernel/alternative.c", "kernel/module/main.c"))
HEADER = "include/linux/kd_generated_text.h"
OUTPUTS = PATCH_PATHS | {HEADER}
INPUTS = frozenset(("include/kd_generated_text.h",
    "kernel_integration/linux70/prepare_generated_text.py",
    "kernel_integration/linux70/generated_text.patch",
    "kernel_integration/linux70/generated-text-base-sha256.json"))


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(receipt):
    require(receipt.get("schema") == 1 and receipt.get("kind") == KIND and
            receipt.get("abi") == 1 and receipt.get("passed") is True and
            receipt.get("lookup_work_units") == LOOKUP_WORK_UNITS and
            receipt.get("source_unchanged") is True and
            receipt.get("config_modified") is False and
            receipt.get("source_package") == PACKAGE,
            "generated-text preparation did not pass")
    require(all(receipt.get(name) is False for name in ("kernel_built", "installed", "booted")),
            "generated-text preparation claims a later stage")
    require(set(receipt.get("inputs", {})) == INPUTS and
            set(receipt.get("outputs", {})) == OUTPUTS and
            set(receipt.get("source_files", {})) == PATCH_PATHS,
            "generated-text pathname scope differs")
    for mapping in (receipt["inputs"], receipt["outputs"], receipt["source_files"]):
        require(all(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value)
                    for value in mapping.values()), "invalid generated-text hash")
    require(receipt["outputs"][HEADER] == receipt["inputs"]["include/kd_generated_text.h"],
            "generated-text header copy differs")
    require(receipt["inputs"]["kernel_integration/linux70/generated-text-base-sha256.json"] ==
            BASE_SHA256, "generated-text base identity differs")
    require(receipt["inputs"]["kernel_integration/linux70/generated_text.patch"] == PATCH_SHA256,
            "generated-text patch identity differs")
    base_path = HERE / "generated-text-base-sha256.json"
    require(digest(base_path) == BASE_SHA256 and
            receipt["source_files"] == json.loads(base_path.read_text())["files"],
            "generated-text pristine identity differs")


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    require(not output.exists() and not output.is_relative_to(source) and
            not output.is_relative_to(ROOT), "new output outside source/project required")
    base_path = HERE / "generated-text-base-sha256.json"
    require(digest(base_path) == BASE_SHA256, "generated-text base identity differs")
    base = json.loads(base_path.read_text())
    require(base["source_package"] == PACKAGE and set(base["files"]) == PATCH_PATHS and
            base["new_files"] == [HEADER], "generated-text base scope differs")
    for name, expected in base["files"].items():
        path = source / name
        require(path.resolve().is_relative_to(source) and not path.is_symlink() and
                digest(path) == expected, "generated-text pristine input differs: " + name)
    require(not (source / HEADER).exists(), "generated-text header already exists")
    patch = HERE / "generated_text.patch"
    require(digest(patch) == PATCH_SHA256, "generated-text patch identity differs")
    paths = re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(), re.M)
    require(len(paths) == len(PATCH_PATHS) and set(paths) == PATCH_PATHS,
            "generated-text patch scope differs")
    inputs = {name: digest(ROOT / name) for name in sorted(INPUTS)}
    output.mkdir(parents=True)
    tree = output / "overlay"
    result = dict(schema=1, kind=KIND, abi=1, passed=False, source_package=PACKAGE,
                  lookup_work_units=LOOKUP_WORK_UNITS,
                  source=str(source), overlay=str(tree), config_modified=False,
                  kernel_built=False, installed=False, booted=False,
                  inputs=inputs, source_files=base["files"])
    try:
        for name in PATCH_PATHS:
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        proc = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
                              cwd=tree, capture_output=True, text=True, timeout=60)
        (output / "patch.log").write_text(proc.stdout + proc.stderr)
        require(proc.returncode == 0, "generated-text patch failed")
        target = tree / HEADER
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "include/kd_generated_text.h", target)
        for name, expected in base["files"].items():
            require(digest(source / name) == expected, "generated-text source changed: " + name)
        for name, expected in inputs.items():
            require(digest(ROOT / name) == expected, "generated-text project input changed: " + name)
        result.update(passed=True, source_unchanged=True,
                      outputs={name: digest(tree / name) for name in sorted(OUTPUTS)})
        validate(result)
    except BaseException as error:
        result["passed"] = False
        result["error"] = repr(error)
        raise
    finally:
        (output / "prepare.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release.startswith("7.0."),
            "designated Linux 7 VM only")
    result = prepare(args.source, args.output)
    print(json.dumps({name: result[name] for name in ("passed", "overlay", "abi")}))


if __name__ == "__main__":
    main()

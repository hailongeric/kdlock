#!/usr/bin/env python3
"""Prepare the exact Linux 7 file-table/pipe lock overlay; never build/install."""
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
SHARED = ("kd_config.h", "kd_spin_type.h", "kd_mutex_types.h")
SELECTED = {
    "fs/file.c": ("set_close_on_exec",),
    "fs/pipe.c": ("pipe_ioctl", "pipe_fcntl"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_text(text, name):
    """Exact reviewed functions; balance tokens while ignoring comments/strings."""
    match = re.search(r"(?m)^[^;{}\n]*\b" + re.escape(name) + r"\s*\(", text)
    if not match:
        raise ValueError("missing function " + name)
    start = text.index("{", match.start())
    tokens = re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]',
                         text[start:], re.S)
    depth = 0
    for token in tokens:
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if not depth:
                return text[match.start():start + token.end()]
    raise ValueError("unterminated function " + name)


def native_body(text):
    """Invert only the reviewed lock-call substitutions, preserving all bodies."""
    replacements = {
        "KD_API_FILES_LOCK(files)": "spin_lock(&files->file_lock)",
        "KD_API_FILES_UNLOCK(files)": "spin_unlock(&files->file_lock)",
        "KD_API_PIPE_LOCK(pipe, 1, 2)": "mutex_lock(&pipe->mutex)",
        "KD_API_PIPE_LOCK(pipe, cmd == F_GETPIPE_SZ, 3)": "mutex_lock(&pipe->mutex)",
        "KD_API_PIPE_UNLOCK(pipe)": "mutex_unlock(&pipe->mutex)",
        "kd_api_pipe_lock(&pipe->mutex)": "mutex_lock(&pipe->mutex)",
        "kd_api_pipe_unlock(&pipe->mutex)": "mutex_unlock(&pipe->mutex)",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return text


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(ROOT):
        raise ValueError("a new output outside the source and project is required")
    manifest = json.loads((HERE / "base-sha256.json").read_text())
    for name, expected in manifest["files"].items():
        if digest(source / name) != expected:
            raise ValueError("authenticated Linux 7 source differs: " + name)
    patch = HERE / "lock-binding.patch"
    paths = re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(), re.M)
    if len(paths) != len(manifest["files"]) or set(paths) != set(manifest["files"]):
        raise ValueError("patch exceeds reviewed binding scope")
    output.mkdir(parents=True)
    tree = output / "overlay"
    result = dict(schema=1, passed=False, source=str(source), overlay=str(tree),
                  source_package=manifest["source_package"],
                  config_symbol=manifest["config_symbol"], config_modified=False,
                  kernel_built=False, installed=False, booted=False,
                  runtime_tests=0, patch_sha256=digest(patch),
                  manifest_sha256=digest(HERE / "base-sha256.json"))
    try:
        for name in manifest["files"]:
            dest = tree / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, dest)
        command = ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)]
        proc = subprocess.run(command, cwd=tree, text=True, capture_output=True,
                              timeout=60)
        (output / "patch.log").write_text(proc.stdout + proc.stderr)
        result["patch_command"] = command
        if proc.returncode:
            raise RuntimeError("exact overlay patch failed")
        inputs = {str(Path(__file__).relative_to(ROOT)): digest(Path(__file__))}
        for file in sorted((HERE / "overlay").rglob("*")):
            if not file.is_file():
                continue
            relative = file.relative_to(HERE / "overlay")
            # C and assembly cannot share the same Kbuild object basename.
            if relative.as_posix() == "kernel/locking/kd_api/bridge.S":
                relative = Path("kernel/locking/kd_api/entry.S")
            dest = tree / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, dest)
            inputs[str(file.relative_to(ROOT))] = digest(file)
        for name in SHARED:
            src = ROOT / "include" / name
            dest = tree / "include/linux/kd_api" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            inputs[str(src.relative_to(ROOT))] = digest(src)
        control = ROOT / "include/kd_api_control.h"
        shutil.copyfile(control, tree / "include/linux/kd_api_control.h")
        inputs[str(control.relative_to(ROOT))] = digest(control)
        bodies = {}
        for name, functions in SELECTED.items():
            for function in functions:
                before = function_text((source / name).read_text(), function)
                after = native_body(function_text((tree / name).read_text(), function))
                if before != after:
                    raise ValueError("native body changed beyond lock calls: " + function)
                bodies[f"{name}:{function}"] = hashlib.sha256(before.encode()).hexdigest()
        for name, expected in manifest["files"].items():
            if digest(source / name) != expected:
                raise ValueError("source changed during preparation: " + name)
        result.update(passed=True, source_unchanged=True, inputs=inputs,
                      native_body_sha256=bodies,
                      outputs={str(p.relative_to(tree)): digest(p)
                               for p in sorted(tree.rglob("*")) if p.is_file()})
    except BaseException as error:
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
    if os.geteuid() != 0 or not os.uname().release.startswith("7.0."):
        raise SystemExit("preparation runs only in the designated Linux 7 VM")
    result = prepare(args.source, args.output)
    print(json.dumps({key: result[key] for key in
                      ("passed", "overlay", "config_modified", "kernel_built")}))


if __name__ == "__main__":
    main()

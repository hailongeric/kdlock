#!/usr/bin/env python3
"""Exact Linux 7.0 source integration, with externally pinned inputs.

Source inspection/preparation only; this script invokes no compiler, make,
package manager, Git mutation, VM control or source cleanup. Run only after the
controller established an idle isolated candidate source/build pair. An idle
flag is a caller assertion, not an activity/recovery check.

inspect prints scoped source/config/package SHA256 fingerprints without edits.
plan requires those externally retained fingerprints and prints the exact diff.
apply additionally requires protected baseline paths and a fresh receipt directory;
it writes exact before/after backups and a journal before atomic file replacement.
There is no fuzz, duplicate installation, automatic rollback or partial resume.
An interrupted application must be reviewed from its retained receipt; never run
again over unknown partial changes. verify checks an earlier complete receipt.

The source fingerprint covers Makefile plus the FIVE edited kernel files, not
an authenticated whole-kernel provenance proof. Identity labels name the caller's
separately established source package/revision and frozen kdlock snapshot. The
package fingerprint covers its actual Kconfig/Kbuild and C/header/assembly inputs.
No config value is changed. The actual vendor source must match each exact
literal context below; old KD changes outside those contexts are preserved.
"""

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid


FORMAT = "kdlock.exact-target-integration.v1"
EDITED = (
    "include/linux/sched.h", "kernel/fork.c", "kernel/exit.c",
    "init/Kconfig", "kernel/Makefile",
)
SOURCE_INPUTS = ("Makefile",) + EDITED
# Explicit normal paths confirmed by the controller; never mutate these inputs.
NORMAL_INPUTS = (
    Path("/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source"),
    Path("/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build"),
)

# Literal upstream-v7.0 contexts, additionally bound to caller-pinned WHOLE files.
# copy_process calls dup_task_struct after usage/stack refs are initialized.
# bad_fork_free is before the kernel drops that unpublished child's stack.
# do_exit hook precedes kthread_do_exit and all task teardown.
EDITS = {
    "include/linux/sched.h": (
        (b"struct task_struct {\n#ifdef CONFIG_THREAD_INFO_IN_TASK\n",
         b"struct kd_task_root_context;\n\nstruct task_struct {\n#ifdef CONFIG_THREAD_INFO_IN_TASK\n"),
        (b"\trandomized_struct_fields_start\n",
         b"\trandomized_struct_fields_start\n\n"
         b"\t/* Own native-root/core and task-owned auxiliary-control backing. */\n"
         b"\tstruct kd_task_root_context\t*kd_root_context;\n"),
    ),
    "kernel/fork.c": (
        (b"#include <linux/sched/task_stack.h>\n",
         b"#include <linux/sched/task_stack.h>\n"
         b"#ifdef CONFIG_KDLOCK_REBUILD\n#include \"kdlock/kernel/lifecycle.h\"\n#endif\n"),
        (b"\tretval = -ENOMEM;\n\tp = dup_task_struct(current, node);\n\tif (!p)\n\t\tgoto fork_out;\n",
         b"\tretval = -ENOMEM;\n\tp = dup_task_struct(current, node);\n\tif (!p)\n\t\tgoto fork_out;\n"
         b"#ifdef CONFIG_KDLOCK_REBUILD\n"
         b"\tretval = kd_task_lifecycle_prepare_unpublished(p);\n"
         b"\tif (retval)\n\t\tgoto bad_fork_free;\n#endif\n"),
        (b"bad_fork_free:\n\tWRITE_ONCE(p->__state, TASK_DEAD);\n",
         b"bad_fork_free:\n#ifdef CONFIG_KDLOCK_REBUILD\n"
         b"\t/* Unpublished child holds end before the kernel drops its stack. */\n"
         b"\tBUG_ON(kd_task_lifecycle_abort_unpublished(p));\n#endif\n"
         b"\tWRITE_ONCE(p->__state, TASK_DEAD);\n"),
    ),
    "kernel/exit.c": (
        (b"#include <linux/sched/task_stack.h>\n",
         b"#include <linux/sched/task_stack.h>\n"
         b"#ifdef CONFIG_KDLOCK_REBUILD\n#include \"kdlock/kernel/lifecycle.h\"\n#endif\n"),
        (b"\tWARN_ON(irqs_disabled());\n\tWARN_ON(tsk->plug);\n\n\tkthread = tsk_is_kthread(tsk);\n",
         b"\tWARN_ON(irqs_disabled());\n\tWARN_ON(tsk->plug);\n\n"
         b"#ifdef CONFIG_KDLOCK_REBUILD\n"
         b"\t/* Refuse freeing live source/owner state; perform no source unlock. */\n"
         b"\tBUG_ON(kd_task_lifecycle_exit_current());\n#endif\n\n"
         b"\tkthread = tsk_is_kthread(tsk);\n"),
    ),
    "init/Kconfig": (
        (b"endmenu\t\t# General setup\n",
         b"source \"kernel/kdlock/Kconfig\"\n\nendmenu\t\t# General setup\n"),
    ),
    "kernel/Makefile": (
        (b"obj-y += locking/\n",
         b"obj-y += locking/\nobj-$(CONFIG_KDLOCK_REBUILD) += kdlock/\n"),
    ),
}
MARKERS = {
    "include/linux/sched.h": (b"kd_root_context",),
    "kernel/fork.c": (b"kd_task_lifecycle_", b"CONFIG_KDLOCK_REBUILD"),
    "kernel/exit.c": (b"kd_task_lifecycle_", b"CONFIG_KDLOCK_REBUILD"),
    "init/Kconfig": (b"kernel/kdlock/Kconfig", b"KDLOCK_REBUILD"),
    "kernel/Makefile": (b"CONFIG_KDLOCK_REBUILD", b"kdlock/"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def absolute(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("paths must be explicit absolute paths without '..'")
    if path != path.resolve(strict=False):
        raise ValueError("symlink or noncanonical path component: " + str(path))
    return path


def within(path, parent):
    return path == parent or parent in path.parents


def regular(path):
    # Hardlinks are deliberately allowed. Replacement never writes their inode.
    if path.is_symlink():
        raise ValueError("symlink input: " + str(path))
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or path != path.resolve(strict=True):
        raise ValueError("nonregular/noncanonical input: " + str(path))
    return path.read_bytes(), info


def fingerprint(identity, hashes):
    return sha(canonical({"format": FORMAT, "identity": identity, "files": hashes}))


def package_inputs(package):
    required = ("Kconfig", "Kbuild", "kernel/lifecycle.c", "kernel/lifecycle.h")
    for name in required:
        regular(package / name)
    names = {"Kconfig", "Kbuild"}
    for folder in ("kernel", "include"):
        base = package / folder
        if not base.is_dir() or base.is_symlink():
            raise ValueError("missing/noncanonical package folder: " + str(base))
        for path in base.rglob("*"):
            if path.is_symlink():
                raise ValueError("symlink package input: " + str(path))
            if path.suffix in (".c", ".h", ".S", ".inc", ".lds"):
                names.add(path.relative_to(package).as_posix())
    return {name: sha(regular(package / name)[0]) for name in sorted(names)}


def inspect_inputs(args):
    tree, build, package = absolute(args.tree), absolute(args.build), absolute(args.package)
    if not tree.is_dir() or not build.is_dir() or not package.is_dir():
        raise ValueError("source, separate build and package must already exist")
    if within(tree, build) or within(build, tree):
        raise ValueError("kernel source and build must be separate nonnested directories")
    raw, infos = {}, {}
    for name in SOURCE_INPUTS:
        raw[name], infos[name] = regular(tree / name)
    make_lines = raw["Makefile"].splitlines()
    if b"VERSION = 7" not in make_lines or b"PATCHLEVEL = 0" not in make_lines:
        raise ValueError("selected source must be Linux 7.0.x")
    config, _ = regular(build / ".config")
    values = config.splitlines()
    if b"CONFIG_X86_64=y" not in values or b"CONFIG_PREEMPT_RT=y" in values:
        raise ValueError("configuration must select x86_64 without PREEMPT_RT")
    source_hashes = {name: sha(raw[name]) for name in SOURCE_INPUTS}
    package_hashes = package_inputs(package)
    pins = {
        "source_identity": args.source_identity,
        "package_identity": args.package_identity,
        "source_fingerprint": fingerprint(args.source_identity, source_hashes),
        "config_sha256": sha(config),
        "package_fingerprint": fingerprint(args.package_identity, package_hashes),
        "source_files": source_hashes,
        "package_files": package_hashes,
    }
    return tree, build, package, raw, infos, pins


def validate_pins(args, pins):
    for name in ("source_fingerprint", "config_sha256", "package_fingerprint"):
        expected = getattr(args, name)
        if expected is None or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("supply an externally retained lowercase SHA256 for --" + name.replace("_", "-"))
        if expected != pins[name]:
            raise ValueError("pinned " + name + " differs; no edit is authorized")


def construct(raw):
    result = {}
    for name in EDITED:
        original = raw[name]
        if not original.endswith(b"\n") or b"\r" in original:
            raise ValueError("unexpected newline convention: " + name)
        if any(marker in original for marker in MARKERS[name]):
            raise ValueError("existing/partial new integration requires review, not reapplication: " + name)
        updated = original
        for before, after in EDITS[name]:
            if updated.count(before) != 1:
                raise ValueError("exact unique source context absent/ambiguous: " + name + ": " + repr(before))
            updated = updated.replace(before, after, 1)
        result[name] = updated
    return result


def patch_bytes(raw, updated):
    chunks = []
    for name in EDITED:
        chunks.extend(difflib.unified_diff(
            raw[name].decode("utf-8").splitlines(keepends=True),
            updated[name].decode("utf-8").splitlines(keepends=True),
            fromfile="a/" + name, tofile="b/" + name,
        ))
    return "".join(chunks).encode("utf-8")


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_file(path, data, mode=0o600):
    # Set mode on the NEW inode at creation, never chmod/chown a shared source.
    previous = os.umask(0)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    finally:
        os.umask(previous)
    try:
        position = 0
        while position < len(data):
            amount = os.write(descriptor, data[position:])
            if amount <= 0:
                raise OSError("write made no progress: " + str(path))
            position += amount
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def journal(path, event):
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        data = canonical(event) + b"\n"
        position = 0
        while position < len(data):
            amount = os.write(descriptor, data[position:])
            if amount <= 0:
                raise OSError("journal write made no progress")
            position += amount
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def apply(args, tree, build, package, raw, infos, pins, updated, patch):
    if not args.idle_confirmed:
        raise ValueError("--idle-confirmed requires the controller's actual prior idle/recovery check")
    if not args.protected_tree:
        raise ValueError("supply every protected normal/frozen --protected-tree path")
    protected = list(NORMAL_INPUTS) + [absolute(value) for value in args.protected_tree]
    if any(within(tree, path) or within(path, tree) or within(build, path) or within(path, build)
           for path in protected):
        raise ValueError("refusing a protected normal/frozen source or build tree")
    if package != tree / "kernel/kdlock":
        raise ValueError("apply requires the pinned package already copied at source/kernel/kdlock")
    receipt = absolute(args.receipt_dir) if args.receipt_dir else None
    if receipt is None or within(receipt, tree) or any(within(receipt, path) for path in protected):
        raise ValueError("fresh receipt directory must be outside source and protected trees")
    if not receipt.parent.is_dir():
        raise ValueError("receipt parent must already exist")
    receipt.mkdir(mode=0o700, exist_ok=False)
    manifest = {
        "format": FORMAT, "tree": str(tree), "build": str(build), "package": str(package),
        "pins": pins, "after": {name: sha(updated[name]) for name in EDITED},
        "installer_sha256": sha(Path(__file__).read_bytes()),
        "mode": {name: stat.S_IMODE(infos[name].st_mode) for name in EDITED},
        "protected_trees": [str(path) for path in protected],
        "idle_is_caller_assertion": True,
    }
    for label, blobs in (("before", raw), ("after", updated)):
        for name, data in blobs.items():
            path = receipt / label / name
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            create_file(path, data)
            fsync_directory(path.parent)
    create_file(receipt / "integration.patch", patch)
    create_file(receipt / "manifest.json", canonical(manifest) + b"\n")
    create_file(receipt / "journal.jsonl", canonical({"phase": "PREPARED"}) + b"\n")
    # Persist every nested backup-directory entry before touching any target.
    for folder in sorted((p for p in receipt.rglob("*") if p.is_dir()),
                         key=lambda p: len(p.parts), reverse=True):
        fsync_directory(folder)
    fsync_directory(receipt)
    fsync_directory(receipt.parent)
    staged = {}
    try:
        # Preflight all inputs again after backing up, before replacing any file.
        _, _, _, latest, _, latest_pins = inspect_inputs(args)
        validate_pins(args, latest_pins)
        if latest != raw:
            raise ValueError("source changed during preparation; refusing replacement")
        for name in EDITED:
            target = tree / name
            temporary = target.parent / (".kdlock-apply-" + uuid.uuid4().hex)
            create_file(temporary, updated[name], stat.S_IMODE(infos[name].st_mode))
            staged[name] = temporary
        journal(receipt / "journal.jsonl", {"phase": "STAGED", "files": {k: str(v) for k, v in staged.items()}})
        for name in EDITED:
            target = tree / name
            if regular(target)[0] != raw[name]:
                raise ValueError("source changed before exact replacement: " + name)
            os.replace(staged[name], target)
            fsync_directory(target.parent)
            journal(receipt / "journal.jsonl", {"phase": "REPLACED", "file": name, "sha256": sha(updated[name])})
        journal(receipt / "journal.jsonl", {"phase": "COMMITTED"})
    except BaseException as error:
        journal(receipt / "journal.jsonl", {"phase": "INCOMPLETE", "error": str(error)})
        raise
    print(str(receipt))


def verify(args, tree, build, package, raw, _infos, pins):
    if not args.receipt_dir:
        raise ValueError("verify needs the exact complete --receipt-dir")
    receipt = absolute(args.receipt_dir)
    manifest = json.loads(regular(receipt / "manifest.json")[0])
    events = [json.loads(line) for line in regular(receipt / "journal.jsonl")[0].splitlines()]
    if (manifest.get("format") != FORMAT or manifest.get("tree") != str(tree)
            or manifest.get("build") != str(build) or manifest.get("package") != str(package)
            or not events or events[-1].get("phase") != "COMMITTED"):
        raise ValueError("receipt does not identify a complete exact application")
    expected = manifest["pins"]
    validate_pins(args, expected)
    if (fingerprint(expected["source_identity"], expected["source_files"])
            != expected["source_fingerprint"]):
        raise ValueError("receipt source map differs from its externally pinned fingerprint")
    if (pins["source_identity"] != expected["source_identity"]
            or pins["package_identity"] != expected["package_identity"]):
        raise ValueError("receipt identity labels differ from the supplied identities")
    if (pins["config_sha256"] != expected["config_sha256"]
            or pins["package_fingerprint"] != expected["package_fingerprint"]):
        raise ValueError("configuration or package changed since application")
    before = {}
    for name in SOURCE_INPUTS:
        before[name] = regular(receipt / "before" / name)[0]
        if sha(before[name]) != expected["source_files"][name]:
            raise ValueError("backup differs from pinned original source: " + name)
    reconstructed = construct(before)
    if manifest["after"] != {name: sha(reconstructed[name]) for name in EDITED}:
        raise ValueError("receipt after-map differs from the exact supported edits")
    for name in SOURCE_INPUTS:
        wanted = reconstructed.get(name, before[name])
        if raw[name] != wanted:
            raise ValueError("applied source differs from exact retained integration: " + name)
    print("Exact applied source/config/package bytes match the complete receipt; no build evidence.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "plan", "apply", "verify"))
    for name in ("tree", "build", "package", "source-identity", "package-identity"):
        parser.add_argument("--" + name, required=True)
    for name in ("source-fingerprint", "config-sha256", "package-fingerprint"):
        parser.add_argument("--" + name)
    parser.add_argument("--receipt-dir")
    parser.add_argument("--protected-tree", action="append")
    parser.add_argument("--idle-confirmed", action="store_true")
    args = parser.parse_args()
    if not args.source_identity or not args.package_identity:
        raise ValueError("exact externally established identity labels are required")
    tree, build, package, raw, infos, pins = inspect_inputs(args)
    if args.mode == "inspect":
        print(json.dumps(pins, sort_keys=True, indent=2))
    elif args.mode == "verify":
        verify(args, tree, build, package, raw, infos, pins)
    else:
        validate_pins(args, pins)
        updated = construct(raw)
        patch = patch_bytes(raw, updated)
        if args.mode == "plan":
            sys.stdout.buffer.write(patch)
        else:
            apply(args, tree, build, package, raw, infos, pins, updated, patch)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)

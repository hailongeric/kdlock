#!/usr/bin/env python3
"""Snapshot tracked source on 380G10 and synchronize the new host and idle VM.

No builds, tests, benchmark execution or project-file deletion occur here.
"""
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import socket
import stat
import subprocess
import sys
import tempfile


SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               "-o", "StrictHostKeyChecking=yes"]


def run(command, timeout, **kwargs):
    return subprocess.run(command, check=True, timeout=timeout, **kwargs)


def git(source, *arguments):
    return run(["git", "-C", str(source), *arguments], 30,
               stdout=subprocess.PIPE).stdout


def load_guest_code(helper):
    """Read the maintained guest program without importing/writing bytecode."""
    for node in ast.parse(helper.read_text()).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "REMOTE_CODE"
                for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Maintained sync_source.py lacks its guest program")


def safe_relative(relative):
    path = PurePosixPath(relative)
    if (not relative or path.is_absolute() or str(path) != relative or
            ".." in path.parts or any(ord(char) < 32 for char in relative)):
        raise ValueError("Unsafe tracked path: " + repr(relative))
    if any(part.startswith(".") for part in path.parts) and relative not in (
            ".gitattributes", ".gitignore"):
        raise ValueError("Private or Git metadata path is outside source sync: " + relative)
    if "__pycache__" in path.parts:
        raise ValueError("Python cache cannot be source input: " + relative)
    return path


def excluded_evidence(path):
    return path.parts[0] == "results" and "raw" in path.parts[1:]


def snapshot(source, destination):
    paths = sorted(set(os.fsdecode(path) for path in
                       git(source, "ls-files", "--cached", "-z").split(b"\0") if path))
    manifest, omitted, excluded = {}, [], []
    size = 0
    for relative in paths:
        path = safe_relative(relative)
        if excluded_evidence(path):
            excluded.append(relative)
            continue
        original = source
        try:
            for part in path.parts:
                original /= part
                mode = original.lstat().st_mode
                if stat.S_ISLNK(mode):
                    raise ValueError("Tracked path contains a symlink: " + relative)
        except FileNotFoundError:
            omitted.append(relative)
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("Tracked source is not a regular file: " + relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Recheck the final component when opening; never follow a substituted link.
        fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as incoming, target.open("xb") as outgoing:
            before = os.fstat(incoming.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 256 * 1024 * 1024:
                raise ValueError("Tracked input is not a regular source file below 256 MiB: " + relative)
            digest = hashlib.sha256()
            copied = 0
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(block)
                digest.update(block)
                copied += len(block)
            after = os.fstat(incoming.fileno())
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if copied != before.st_size or any(getattr(before, key) != getattr(after, key)
                                                for key in fields):
                raise ValueError("Source changed while snapshotting; rerun: " + relative)
            os.fchmod(outgoing.fileno(), before.st_mode & 0o777)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        manifest[relative] = digest.hexdigest()
        size += copied
    if not manifest:
        raise ValueError("No regular tracked source files were selected")
    return manifest, omitted, excluded, size


def guest_inspect(args, helper, manifest):
    guest_command = "PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote(load_guest_code(helper))
    physical_command = shlex.join([args.scripts + "/vm_ssh.sh", guest_command])
    request = {"operation": "inspect", "manifest": manifest}
    result = run(["ssh", *SSH_OPTIONS, args.host, physical_command], args.timeout,
                 input=(json.dumps(request, sort_keys=True) + "\n").encode(),
                 stdout=subprocess.PIPE)
    response = json.loads(result.stdout)
    if (response.get("root") != "/root/host_fs/kdlock" or
            response.get("fstype") != "ext4" or response.get("idle") is not True or
            set(response.get("hashes", {})) != set(manifest)):
        raise RuntimeError("Guest did not confirm idle ext4 source and every requested path")
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--host", default="eric@10.176.26.71", help="physical benchmark host SSH target")
    parser.add_argument("--mirror", default="/home/eric/vm/vm-shared/kdlock")
    parser.add_argument("--scripts", default="/home/eric/vm/qemu-scripts")
    parser.add_argument("--timeout", type=int, default=600, help="seconds allowed per SSH/rsync step")
    parser.add_argument("--dry-run", action="store_true", help="inspect differences without modifying remote files")
    args = parser.parse_args()
    if args.timeout <= 0 or not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+", args.host):
        raise ValueError("Use a positive timeout and an SSH target of user@hostname")
    for remote_path in (args.mirror, args.scripts):
        if (not re.fullmatch(r"/[A-Za-z0-9_./-]+", remote_path) or
                ".." in PurePosixPath(remote_path).parts):
            raise ValueError("Remote paths must be safe absolute directory paths")
    source = args.source.resolve(strict=True)
    if Path(os.fsdecode(git(source, "rev-parse", "--show-toplevel")).strip()).resolve() != source:
        raise ValueError("--source must name the Git checkout root")
    helper = Path(__file__).resolve().with_name("sync_source.py")
    # Serialize this source host's sync processes; the guest helper separately locks writes.
    lock_path = Path(tempfile.gettempdir()) / ("kdlock-source-to-vm-" + args.host + ".lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another source-host synchronization is active") from None
        with tempfile.TemporaryDirectory(prefix="kdlock-source-snapshot-") as temporary:
            stage = Path(temporary)
            tree = stage / "source"
            tree.mkdir()
            manifest, omitted, excluded, size = snapshot(source, tree)
            metadata = {
                "source_host": socket.gethostname(), "source_path": str(source),
                "target_host": args.host, "files": len(manifest), "transfer_bytes": size,
                "git_head": git(source, "rev-parse", "HEAD").decode().strip(),
                "git_status": git(source, "status", "--short").decode(),
                "snapshot_utc": datetime.now(timezone.utc).isoformat(),
                "snapshot_policy": "Regular tracked current bytes copied into a private local snapshot; hashes describe transferred bytes.",
                "omitted_missing_tracked_paths": omitted, "excluded_raw_evidence": excluded,
            }
            for name, value in (("source-sha256.json", manifest), ("source-state.json", metadata)):
                (stage / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            files = stage / "files.list"
            files.write_bytes(b"".join(os.fsencode(path) + b"\0" for path in manifest))
            print(f"Snapshot: {len(manifest)} tracked files, {size:,} bytes; dry-run={args.dry_run}", flush=True)
            for relative in omitted:
                print("Omitted missing tracked path; remote file is retained: " + relative, flush=True)
            for relative in excluded:
                print("Excluded raw evidence: " + relative, flush=True)
            before = guest_inspect(args, helper, manifest)
            changed = sorted(path for path in manifest if before["hashes"][path] != manifest[path])
            print(json.dumps({"guest_changed_files": len(changed), "changed": changed}, sort_keys=True), flush=True)
            transfer = ["rsync", "-a", "--no-owner", "--no-group", "-e",
                        shlex.join(["ssh", *SSH_OPTIONS])]
            mirror_transfer = [*transfer, "--from0", "--files-from=" + str(files)]
            if args.dry_run:
                mirror_transfer += ["--dry-run", "--itemize-changes"]
            run([*mirror_transfer, str(tree) + "/", args.host + ":" + args.mirror + "/"], args.timeout)
            if args.dry_run:
                print("Dry run complete; no remote project files or manifests were written.")
                return 0
            # Deploy helper bytes from the same snapshot when tracked; otherwise use this
            # command's reviewed companion for initial setup, never a changing source stream.
            snapshot_helper = tree / "tools/vm/sync_source.py"
            if not snapshot_helper.is_file():
                snapshot_helper = stage / "sync_source.py"
                snapshot_helper.write_bytes(helper.read_bytes())
                snapshot_helper.chmod(0o755)
            run([*transfer, str(snapshot_helper), str(stage / "source-sha256.json"),
                 str(stage / "source-state.json"), args.host + ":" + args.scripts + "/"], args.timeout)
            command = shlex.join([args.scripts + "/sync_source.py", "--source", args.mirror,
                                  "--manifest", args.scripts + "/source-sha256.json",
                                  "--ssh", args.scripts + "/vm_ssh.sh", "--timeout", str(args.timeout)])
            run(["ssh", *SSH_OPTIONS, args.host, command], args.timeout)
            print("Synchronization complete; subsequent builds, tests and benchmarks run in the new VM.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("STOP: " + str(error), file=sys.stderr)
        raise SystemExit(1)

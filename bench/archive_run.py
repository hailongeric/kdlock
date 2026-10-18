#!/usr/bin/env python3
"""Preserve a completed evidence tree in grouped tar.gz files in an idle guest.

Explicit groups select top-level paths; every other path is metadata. Files,
directories and symlinks are retained without following symlinks. Nothing is
deleted or unloaded. Failed captures remain incomplete and must be retained;
retry only into another new sibling output directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tarfile
import time


ROOT = Path(__file__).resolve().parents[1]
RELEASE = "6.1.159-kdclobber2"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    # Do not replace the last complete JSON receipt with a truncated prefix.
    temporary = path.with_name("." + path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def inventory(base):
    rows = {}

    def walk_error(error):
        raise error

    for directory, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
        for name in sorted([*dirs, *files]):
            path = Path(directory) / name
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or
                    stat.S_ISLNK(info.st_mode), "unsupported special evidence path: " + str(path))
            rows[str(path.relative_to(base))] = dict(
                mode=info.st_mode, bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                ctime_ns=info.st_ctime_ns, inode=info.st_ino, device=info.st_dev,
                uid=info.st_uid, gid=info.st_gid, links=info.st_nlink,
                link=os.readlink(path) if stat.S_ISLNK(info.st_mode) else None)
    return rows


def groups_for(base, assignments):
    groups, owners = {}, {}
    available = {path.name: path for path in base.iterdir()}
    for assignment in assignments:
        group, separator, name = assignment.partition("=")
        require(separator and re.fullmatch(r"[a-z][a-z0-9_-]*", group) and
                group != "metadata", "group must be NAME=TOP_LEVEL_PATH; metadata is reserved")
        require(name in available and Path(name).name == name and name not in owners,
                "group path is missing, nested or already assigned: " + name)
        owners[name] = group
        groups.setdefault(group, []).append(available[name])
    groups["metadata"] = [path for name, path in sorted(available.items()) if name not in owners]
    return {name: sorted(paths) for name, paths in groups.items()}


def idle(base, common_idle):
    common_idle()
    # Extend the shared spin predicate to other maintained providers/payloads.
    for module in Path("/sys/module").iterdir():
        require(module.name not in {"real_api", "rwlock_bench", "rwlock_test", "rwsem_probe"}
                and not module.name.startswith(("kd_", "tclock_", "tc_", "jit_")),
                "project module remains loaded: " + module.name)
    for comm in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            name = comm.read_text().strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(name not in {"rb_worker", "kd_rwsem_probe", "kd_rwsem_cancel", "kd-cancel"}
                and not name.startswith(("kd-local/", "kd_mtask_", "kd_irq_api/", "kd_guard/")),
                "project task remains active: " + str(comm) + ": " + name)

    # Replay can write evidence after all kernel work drains. Inspect actual
    # descriptors, not command-line substrings or programs in archived source.
    # This also rejects redirecting this archiver's own output into base.
    for descriptor in Path("/proc").glob("[0-9]*/fd/[0-9]*"):
        try:
            target = os.readlink(descriptor)
            if not target.startswith("/"):
                continue
            target = target.removesuffix(" (deleted)")
            if not Path(target).is_relative_to(base):
                continue
            fdinfo = descriptor.parent.parent / "fdinfo" / descriptor.name
            flags = next(line.split()[1] for line in fdinfo.read_text().splitlines()
                         if line.startswith("flags:"))
        except (FileNotFoundError, ProcessLookupError):
            continue
        require((int(flags, 8) & os.O_ACCMODE) == os.O_RDONLY,
                "evidence still open for writing: " + str(descriptor) + " -> " + target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--health", type=Path, required=True,
                        help="completed idle health JSON inside base, with current boot_id")
    parser.add_argument("--group", action="append", required=True, metavar="NAME=PATH",
                        help="assign one top-level path; repeat for each selected group/root")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release == RELEASE and
            str(ROOT).startswith("/root/") and (ROOT / "bench/spin_cacheline/bench_runtime.py").is_file(),
            "run from the maintained checkout in the intended recovery guest")
    require(60 <= args.timeout_seconds <= 7200, "timeout must be 60..7200 seconds")
    base = args.base.resolve(strict=True)
    require(not args.output.is_symlink(), "output must not be a symbolic link")
    out = args.output.resolve()
    health_path = args.health.resolve(strict=True)
    require(base.is_dir() and not base.is_relative_to(ROOT), "base must be external evidence")
    require(out.parent == base.parent and out != base and not out.exists() and not out.is_symlink(),
            "output must be a new sibling directory")
    require(health_path.is_relative_to(base) and health_path.is_file(),
            "health receipt must be retained inside base")
    health = json.loads(health_path.read_text())
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(health.get("idle") is True and health.get("boot_id") == boot_id,
            "health receipt must confirm idle on the current guest boot")
    for key in ("new_faults_in_retained_dmesg", "per_session_kernel_faults"):
        require(not health.get(key, []), "health receipt reports faults: " + key)
    if "no_linux_mutex_imports" in health:
        require(health["no_linux_mutex_imports"] is True, "health receipt reports native mutex imports")

    # Only maintained idle code is imported, never an evidence snapshot. Do
    # not generate bytecode or alter frozen benchmark inputs during capture.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "bench/spin_cacheline"))
    from bench_runtime import idle as common_idle

    out.mkdir()
    receipt = dict(schema=1, completed=False, guest_base=str(base), archive_prefix=base.name,
                   boot_id=boot_id, kernel_release=os.uname().release,
                   health_path=str(health_path.relative_to(base)), health_sha256=sha256(health_path),
                   script_sha256=sha256(Path(__file__)),
                   idle_source_sha256=sha256(ROOT / "bench/spin_cacheline/bench_runtime.py"),
                   started_ns=time.time_ns(), groups=[],
                   scope="Complete evidence preservation; no deletion, module action, test or timing")
    save(out / "archives.json", receipt)

    def interrupted(signum, frame):
        raise TimeoutError("archive interrupted by signal " + str(signum))

    old = {number: signal.signal(number, interrupted)
           for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM)}
    signal.alarm(args.timeout_seconds)
    try:
        idle(base, common_idle)
        before = inventory(base)
        require(before, "empty evidence base")
        groups = groups_for(base, args.group)
        require({path.name for paths in groups.values() for path in paths} ==
                {name for name in before if "/" not in name},
                "top-level inputs changed while grouping")
        health_mtime = health_path.stat().st_mtime_ns
        require(all(row["mtime_ns"] <= health_mtime for name, row in before.items()
                    if name.endswith(".command.json")), "command receipt is newer than final health")
        save(out / "input-inventory.json", before)
        (out / "archive_run.py").write_bytes(Path(__file__).read_bytes())
        for name, paths in groups.items():
            if not paths:
                continue
            idle(base, common_idle)
            target = out / (name + ".tar.gz")
            print("ARCHIVE " + name, flush=True)
            with target.open("xb") as stream:
                with tarfile.open(fileobj=stream, mode="w:gz", compresslevel=6,
                                  dereference=False, format=tarfile.PAX_FORMAT) as archive:
                    for path in paths:
                        archive.add(path, arcname=str(Path(base.name) / path.name), recursive=True)
                stream.flush()
                os.fsync(stream.fileno())
            row = dict(group=name, file=target.name, path=str(target), bytes=target.stat().st_size,
                       sha256=sha256(target), roots=[str(Path(base.name) / path.name) for path in paths])
            receipt["groups"].append(row)
            save(out / "archives.json", receipt)
            print(json.dumps(row, sort_keys=True), flush=True)
        require(inventory(base) == before, "input paths/metadata changed; retain incomplete capture")
        require(sha256(health_path) == receipt["health_sha256"], "health changed during capture")
        require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == boot_id,
                "guest boot changed during capture")
        idle(base, common_idle)
        receipt.update(completed=True, guest_idle=True, finished_ns=time.time_ns(),
                       input_inventory_sha256=sha256(out / "input-inventory.json"))
        save(out / "archives.json", receipt)
    except BaseException as error:
        receipt.update(completed=False, error=repr(error), finished_ns=time.time_ns())
        save(out / "archives.json", receipt)
        raise
    finally:
        signal.alarm(0)
        for number, handler in old.items():
            signal.signal(number, handler)
    print("All evidence preserved; unchanged inventory and final guest idle confirmed", flush=True)


if __name__ == "__main__":
    main()

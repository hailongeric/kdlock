#!/usr/bin/env python3
"""Delete only the explicitly approved historical scope2/3/4 objects.

Run on the guest from stdin. Receipts are JSON lines on stdout; no report files
are written on the guest. Symlinks inside an approved directory are unlinked,
never followed. Existing boot/module namespaces and all evidence are excluded.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

BASE = "/mnt/kdlock-builds2"
BOOT = "9336b735-78f0-4f9c-9d9e-f04677f8d6bc"
RELEASE = "7.0.0-38-kdrebuild5"
ROWS = [
    ("kdlock-reader-scope4-9f9fb90e-20261101.manifest.json", 1298432),
    ("kdlock-reader-scope4-9f9fb90e-20261101.tar.gz", 119001088),
    ("kdlock-reader-scope4-aeec5053-20261101.manifest.json", 1298432),
    ("kdlock-reader-scope4-aeec5053-20261101.tar.gz", 118173696),
    ("kdlock-scope2-recipe-f4ae82cf", 328269824),
    ("kdlock-scope2-recipe-f4ae82cf-20261031.tar.gz", 118411264),
    ("kdlock-scope2-recipe-f4ae82cf.manifest.json", 1277952),
    ("kdlock-scope3-api-prepare-7814c61a-20261031", 471040),
    ("kdlock-scope3-mmap-prepare-7814c61a-20261031", 491520),
    ("kdlock-scope3-modules-stage-7814c61a-20261031", 696442880),
    ("kdlock-scope3-recipe-7814c61a", 328368128),
    ("kdlock-scope4-api-prepare-9f9fb90e-20261101", 471040),
    ("kdlock-scope4-mmap-prepare-9f9fb90e-20261101", 495616),
    ("kdlock-scope4-modules-stage-9f9fb90e-20261101", 696442880),
    ("kdlock-scope4-recipe-9f9fb90e", 333729792),
    ("kdlock-scope4-recipe-aeec5053", 333647872),
    ("kdlock-writer-queue-scope3-7814c61a-20261031.manifest.json", 1277952),
    ("kdlock-writer-queue-scope3-7814c61a-20261031.tar.gz", 118415360),
    ("kdscope2-api-prepare", 471040),
    ("kdscope2-install-stage-20261031", 696446976),
    ("kdscope2-mmap-prepare", 491520),
    ("kdscope2-root-install-work-20261031", 273641472),
    ("linux-7.0.0-38-kdscope2", 14486286336),
    ("linux-7.0.0-38-kdscope3", 14486945792),
    ("linux-7.0.0-38-kdscope4", 35047698432),
]
TARGETS = [BASE + "/" + name for name, _ in ROWS]
PROTECTED = [
    BASE + "/linux-7.0.0-38-kdscope5",
    BASE + "/kdlock-main-build-c6becf81-01a1bc4f",
    BASE + "/kdlock-main-build-c6becf81-01a1bc4f/source",
    BASE + "/kdlock-main-build-c6becf81-01a1bc4f/build",
    BASE + "/kdlock-main-build-c6becf81-01a1bc4f/receipts",
    BASE + "/kdlock-evidence",
    "/mnt/kdlock-builds/linux-7.0.0-38-kdlock1",
    "/mnt/kdlock-builds/linux-7.0.0-38-kdmm1",
    "/mnt/kdlock-builds/linux-6.1.159-kdclobber2",
    "/mnt/kdlock-builds/ubuntu-7.0.0-38-source",
    "/mnt/kdlock-builds/kdlock-evidence",
    "/mnt/kdlock-builds/kdlock-retained",
    "/mnt/kdlock-builds/kdlock-main-work",
    "/mnt/kdlock-builds/kdlock-main-work/kernel5-fixtures-68a2e5ed-rw-01",
    "/mnt/kdlock-builds/kdlock-main-work/kernel5-fixtures-e990fde3-rw-01",
    "/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027",
    "/boot", "/lib/modules", "/root/kdlock-kernel-baselines",
    "/etc/default/grub", "/etc/grub.d", "/boot/grub/grub.cfg",
    "/boot/grub/grubenv",
]


def emit(kind, **fields):
    print(json.dumps(dict(kind=kind, utc=datetime.datetime.now(
        datetime.timezone.utc).isoformat(), **fields), sort_keys=True), flush=True)


def read(path):
    with open(path) as stream:
        return stream.read()


def metadata(path):
    st = os.lstat(path)
    row = dict(device=st.st_dev, inode=st.st_ino, mode=st.st_mode,
               uid=st.st_uid, gid=st.st_gid, size=st.st_size,
               allocated=st.st_blocks * 512, nlink=st.st_nlink,
               mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns)
    if stat.S_ISLNK(st.st_mode):
        row["link"] = os.readlink(path)
    return row


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def filesystem(path):
    st = os.statvfs(path)
    return dict(block_size=st.f_frsize, total=st.f_blocks * st.f_frsize,
                free=st.f_bfree * st.f_frsize,
                available=st.f_bavail * st.f_frsize,
                inodes=st.f_files, free_inodes=st.f_ffree)


def mount_rows():
    rows = []
    for line in read("/proc/self/mountinfo").splitlines():
        words = line.split()
        sep = words.index("-")
        point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), words[4])
        rows.append(dict(point=point, device=words[2], filesystem=words[sep+1],
                         source=words[sep+2], options=words[5]))
    return rows


def under(path, root):
    return path == root or path.startswith(root + "/")


def process_references():
    references, busy, errors = [], [], []
    pids = sorted(int(name) for name in os.listdir("/proc") if name.isdigit())
    fd_count = 0
    for pid in pids:
        prefix = "/proc/" + str(pid)
        try:
            comm = read(prefix + "/comm").strip()
            with open(prefix + "/cmdline", "rb") as stream:
                command = stream.read().replace(b"\0", b" ").decode(errors="replace")
            if comm.startswith(("kd-fixture/", "kd-scene/")):
                busy.append(dict(pid=pid, comm=comm, reason="fixture_worker"))
            executable = command.split(" ", 1)[0].rsplit("/", 1)[-1]
            if executable in {"make", "gcc", "gcc-15", "cc1", "clang", "ld", "ld.bfd", "as", "objtool"}:
                busy.append(dict(pid=pid, comm=comm, command=command[:1600]))
            for target in TARGETS:
                if target in command:
                    references.append(dict(pid=pid, kind="cmdline", target=target))
            for leaf in ["cwd", "exe"]:
                try:
                    path = os.readlink(prefix + "/" + leaf).removesuffix(" (deleted)")
                except FileNotFoundError:
                    continue
                for target in TARGETS:
                    if under(path, target):
                        references.append(dict(pid=pid, kind=leaf, path=path, target=target))
            for fd in os.listdir(prefix + "/fd"):
                fd_count += 1
                try:
                    path = os.readlink(prefix + "/fd/" + fd).removesuffix(" (deleted)")
                except FileNotFoundError:
                    continue
                for target in TARGETS:
                    if under(path, target):
                        references.append(dict(pid=pid, kind="fd", fd=fd, path=path, target=target))
            for line in read(prefix + "/maps").splitlines():
                words = line.split(None, 5)
                if len(words) == 6:
                    path = words[5].removesuffix(" (deleted)")
                    for target in TARGETS:
                        if under(path, target):
                            references.append(dict(pid=pid, kind="maps", path=path, target=target))
        except (FileNotFoundError, ProcessLookupError):
            if os.path.exists(prefix):
                errors.append(dict(pid=pid, error="incomplete live process inspection"))
        except (PermissionError, OSError) as error:
            errors.append(dict(pid=pid, error=repr(error)))
    return dict(processes=len(pids), file_descriptors=fd_count,
                references=references, busy=busy, errors=errors)


def runtime_state():
    return dict(boot=read("/proc/sys/kernel/random/boot_id").strip(),
                release=os.uname().release, taint=read("/proc/sys/kernel/tainted").strip(),
                fixtures=[line for line in read("/proc/modules").splitlines()
                          if "runtime_fixture" in line],
                devices=[name for name in sorted(os.listdir("/dev"))
                         if name.startswith("kd_") and "fixture" in name])


def protected_snapshot():
    rows = {}
    for path in PROTECTED:
        rows[path] = metadata(path)
        if stat.S_ISREG(rows[path]["mode"]):
            rows[path]["sha256"] = file_hash(path)
    # Every installed boot file and module-namespace entry remains outside the
    # approved batch. Content hashes cover boot files; module namespace/link
    # metadata and selected source/config identities cover the retained roots.
    for name in sorted(os.listdir("/boot")):
        path = "/boot/" + name
        rows[path] = metadata(path)
        if stat.S_ISREG(rows[path]["mode"]):
            rows[path]["sha256"] = file_hash(path)
    for name in sorted(os.listdir("/lib/modules")):
        path = "/lib/modules/" + name
        rows[path] = metadata(path)
        if stat.S_ISDIR(rows[path]["mode"]):
            for leaf in ["build", "source", "modules.dep", "modules.alias"]:
                item = path + "/" + leaf
                if os.path.lexists(item):
                    rows[item] = metadata(item)
                    if stat.S_ISREG(rows[item]["mode"]):
                        rows[item]["sha256"] = file_hash(item)
    for root in [BASE + "/linux-7.0.0-38-kdscope5", BASE + "/kdlock-main-build-c6becf81-01a1bc4f"]:
        for rel in ["build/.config", "build/include/config/kernel.release", "composition.json",
                    "source/include/linux/mmap_lock.h", "source/mm/mmap.c", "source/mm/memory.c"]:
            path = root + "/" + rel
            if os.path.isfile(path):
                rows[path] = metadata(path)
                rows[path]["sha256"] = file_hash(path)
    return rows


def main():
    os.nice(19)
    subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True,
                   stdout=subprocess.DEVNULL)
    assert os.geteuid() == 0 and len(TARGETS) == len(set(TARGETS)) == 25
    assert shutil.rmtree.avoids_symlink_attacks
    assert os.path.realpath(BASE) == BASE
    mounts = mount_rows()
    state_before = runtime_state()
    emit("identity_before", hostname=read("/etc/hostname").strip(),
         state=state_before, mounts=mounts)
    assert state_before["boot"] == BOOT and state_before["release"] == RELEASE
    assert state_before["taint"] == "12288"
    assert not state_before["fixtures"] and not state_before["devices"]
    selected_mount = [row for row in mounts if row["point"] == BASE]
    assert len(selected_mount) == 1 and selected_mount[0]["source"] == "/dev/sdc"
    assert selected_mount[0]["filesystem"] == "ext4"
    before_fs = filesystem(BASE)
    protected_before = protected_snapshot()
    emit("protected_before", records=protected_before)
    scan = process_references()
    emit("process_recheck_before", **scan)
    if scan["errors"] or scan["busy"]:
        raise RuntimeError("process inspection incomplete or build/worker activity present")
    blocked = {row["target"] for row in scan["references"]}
    preflight = {}
    for target, (_, approved_allocated) in zip(TARGETS, ROWS):
        reasons = []
        if os.path.dirname(target) != BASE or os.path.realpath(target) != target:
            reasons.append("noncanonical or symlink target")
        if any(under(row["point"], target) for row in mounts):
            reasons.append("target or descendant is a mountpoint")
        if any(under(target, p) or under(p, target) for p in PROTECTED):
            reasons.append("protected path overlap")
        try:
            item = metadata(target)
            if not (stat.S_ISDIR(item["mode"]) or stat.S_ISREG(item["mode"])):
                reasons.append("target is not a regular file or directory")
            if item["device"] != os.stat(BASE).st_dev:
                reasons.append("different filesystem")
        except OSError as error:
            item = None
            reasons.append(repr(error))
        if target in blocked:
            reasons.append("active process reference")
        preflight[target] = dict(lstat=item, reasons=reasons,
                                 approved_allocated=approved_allocated)
    # du defaults to no symlink following. All targets have passed canonical and
    # mount checks before any contents are measured or removed.
    allowed = [p for p in TARGETS if not preflight[p]["reasons"]]
    if allowed:
        measured = subprocess.run(["du", "-x", "-s", "-B1", "--", *allowed],
                                  text=True, capture_output=True, check=True, timeout=120)
        for line in measured.stdout.splitlines():
            size, path = line.split("\t", 1)
            preflight[path]["allocated_before"] = int(size)
            if int(size) != preflight[path]["approved_allocated"]:
                preflight[path]["reasons"].append("allocation differs from approved inventory")
    emit("preflight", filesystem=before_fs, targets=preflight)
    outcomes = []
    for target in TARGETS:
        item = preflight[target]
        if item["reasons"]:
            outcome = dict(path=target, status="BLOCKED", reasons=item["reasons"])
        else:
            # No task is permitted to mutate these frozen paths during this
            # window. Recheck the exact top-level identity immediately before
            # removing it; rmtree's fd traversal does not follow child symlinks.
            if metadata(target) != item["lstat"]:
                outcome = dict(path=target, status="BLOCKED", reasons=["identity changed after preflight"])
            else:
                emit("delete_begin", path=target, lstat=item["lstat"],
                     allocated_before=item["allocated_before"])
                try:
                    if stat.S_ISDIR(item["lstat"]["mode"]):
                        shutil.rmtree(target)
                    else:
                        os.unlink(target)
                    outcome = dict(path=target, status="ABSENT" if not os.path.lexists(target) else "STILL_PRESENT",
                                   allocated_before=item["allocated_before"],
                                   lstat_after=metadata(target) if os.path.lexists(target) else None)
                except OSError as error:
                    outcome = dict(path=target, status="ERROR", error=repr(error),
                                   present=os.path.lexists(target))
        outcomes.append(outcome)
        emit("target_outcome", **outcome)
        if outcome["status"] in ["ERROR", "STILL_PRESENT"]:
            break
    protected_after = protected_snapshot()
    changes = [p for p in sorted(set(protected_before) | set(protected_after))
               if protected_before.get(p) != protected_after.get(p)]
    emit("protected_after", records=protected_after, changes=changes)
    scan_after = process_references()
    emit("process_recheck_after", **scan_after)
    after_fs = filesystem(BASE)
    links = {}
    for number in [2, 3, 4]:
        root = "/lib/modules/7.0.0-38-kdscope" + str(number)
        for leaf in ["build", "source"]:
            path = root + "/" + leaf
            if os.path.islink(path):
                links[path] = dict(target=os.readlink(path), resolves=os.path.exists(path))
    emit("final", status="COMPLETE" if len(outcomes) == 25 and all(
         row["status"] == "ABSENT" for row in outcomes) and not changes else "INCOMPLETE",
         requested=25, absent=sum(row["status"] == "ABSENT" for row in outcomes),
         outcomes=outcomes, state_after=runtime_state(), filesystem_before=before_fs,
         filesystem_after=after_fs, guest_free_increase=after_fs["free"]-before_fs["free"],
         guest_available_increase=after_fs["available"]-before_fs["available"],
         protected_changes=changes, remaining_old_links=links,
         no_host_reclamation_claim=True)
    return 0 if len(outcomes) == 25 and all(row["status"] == "ABSENT" for row in outcomes) and not changes else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        emit("stopped", error=repr(error))
        raise

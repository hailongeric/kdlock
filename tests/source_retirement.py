"""Source controls embedded in the two-frame complex test, not a smoke suite.

Callers remain paused for busy(); finish() requires every caller and translator
to have exited. The external quiescence boundary is not a hook-reader barrier.
"""

import argparse
import errno
import fcntl
import hashlib
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

from elftools.elf.elffile import ELFFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "disassem"))
import device_session as source
from native_only_protocol import NATIVE_ONLY, entries

ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate, message):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(message)


def child_handle(out):
    child = json.loads((out / "child.json").read_text())
    assert child["mutex_stack_bytes"] == 256
    handle = os.pidfd_open(child["pid"])
    try:
        assert not select.select([handle], [], [], 0)[0], "orphan already exited"
        assert os.readlink(f"/proc/{child['pid']}/fd/{child['fd']}") == source.DEVICE
    except BaseException:
        os.close(handle)
        raise
    return handle


def orphan_writer(fd, out):
    # compile_entry resolves the script relative to its normal mode-2 workspace.
    # Only its script is substituted; the real parent inherits one open file
    # description through fork/exec and Python validates that exact device.
    out.mkdir()
    workspace = out / "daemon"
    (workspace / "0x1234/42").mkdir(parents=True)
    (out / "disassem").mkdir()
    (out / "disassem/disassem.py").symlink_to(ROOT / "tests/source_session_child.py")
    handle = None
    with (out / "child.log").open("w") as log:
        parent = subprocess.Popen(
            [str(out.parent / "source-session-driver")],
            cwd=workspace,
            env={**os.environ, "KD_SESSION_PROBE": str(out)},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for(lambda: (out / "child.json").exists(), "compiler child not ready")
            handle = child_handle(out)
            leased = source.info(fd)
            assert leased["writers"] == 1 and parent.poll() is None, leased
            parent.terminate()
            assert parent.wait(timeout=3) == -15
            assert not select.select([handle], [], [], 0)[0], "child exited with parent"
            assert source.info(fd) == leased
            return leased
        except BaseException:
            (out / "release").touch()
            raise
        finally:
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=3)
            if handle is not None:
                os.close(handle)


def release_writer(out):
    if not out.exists():
        return
    # No signal is sent to an orphan identified only by a recorded PID. The
    # release file is private to this run; pidfd observes exit without PID reuse.
    (out / "release").touch()
    if not (out / "child.json").exists():
        return
    child = json.loads((out / "child.json").read_text())
    try:
        handle = os.pidfd_open(child["pid"])
    except ProcessLookupError:
        return
    try:
        assert select.select([handle], [], [], 3)[0], "writer failed to drain"
    finally:
        os.close(handle)


def writer_refused():
    try:
        fd = os.open(source.DEVICE, os.O_RDWR | os.O_CLOEXEC)
    except OSError as error:
        assert error.errno == errno.ESHUTDOWN, error
    else:
        os.close(fd)
        raise AssertionError("new writer admitted after closing")


def busy(fd, out):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        log = subprocess.check_output(["dmesg"], text=True, timeout=2)
        if all(f"kd_parallel arrive: lane={lane} " in log for lane in (0, 1)):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("two native arrivals were not observed")
    before = source.info(fd)
    assert before == {"state": source.OPEN, "modules": 1, "frames": 2, "writers": 0}, (
        before
    )
    leased = orphan_writer(fd, out / "writer")
    assert leased == dict(before, writers=1), leased
    try:
        fcntl.ioctl(fd, source.RETIRE)
    except OSError as error:
        assert error.errno == errno.EBUSY, error
    else:
        raise AssertionError("retired with two live frames")
    after = source.info(fd)
    assert after == dict(leased, state=source.DRAINING), after
    writer_refused()
    # Let the surviving child inspect text only after retirement closed admission.
    # Both native frames remain held until this controller returns to the shell.
    published = json.loads((out / "published.json").read_text())
    symbols = [line.split() for line in Path("/proc/kallsyms").read_text().splitlines()]
    (address,) = [
        int(row[0], 16)
        for row in symbols
        if row[2:] == ["kd_parallel_native", "[klock_module]"]
    ]
    inspection = out / "writer/inspect.json"
    inspection.with_suffix(".tmp").write_text(
        json.dumps({"address": address, "entry": published[0]["entry"]})
    )
    inspection.with_suffix(".tmp").replace(inspection)
    wait_for(
        lambda: (out / "writer/inspected.json").exists(), "orphan inspection failed"
    )
    inspected = json.loads((out / "writer/inspected.json").read_text())
    assert inspected["info"] == after and inspected["bytes"] == 16, inspected
    assert (
        inspected["mutex_stack_bytes"] == inspected["queried_mutex_stack_bytes"] == 256
    )
    assert source.info(fd) == after
    return {"before": before, "leased": leased, "busy": after, "inspected": inspected}


def finish(fd, out):
    before = source.info(fd)
    assert before == {
        "state": source.DRAINING,
        "modules": 1,
        "frames": 0,
        "writers": 1,
    }, before
    # Once real frames have drained, the orphan writer alone must block retire.
    handle = child_handle(out / "writer")
    try:
        try:
            fcntl.ioctl(fd, source.RETIRE)
        except OSError as error:
            assert error.errno == errno.EBUSY, error
        else:
            raise AssertionError("retired before orphan writer closed")
        assert source.info(fd) == before
    finally:
        os.close(handle)
        release_writer(out / "writer")
    wait_for(lambda: source.info(fd)["writers"] == 0, "writer description remains live")
    closed = json.loads((out / "writer/closed.json").read_text())
    assert closed["closed"]
    drained = source.info(fd)
    assert drained == dict(before, writers=0), drained
    # Workload FDs, compiler parent and child are now gone. Refusal observes the
    # source pin, not a test client's open device; never force either exit.
    unload = subprocess.run(
        ["rmmod", "klock_module"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert unload.returncode != 0 and "in use" in unload.stderr, unload
    assert Path("/sys/module/klock_module").exists()
    old = entries()
    assert old
    fcntl.ioctl(fd, source.RETIRE)
    after = source.info(fd)
    assert after == {
        "state": source.RETIRED,
        "modules": 0,
        "frames": 0,
        "writers": 0,
    }, after
    retired = entries()
    assert [(e.rip, e.code, e.tgid) for e in retired] == [
        (e.rip, e.code, e.tgid) for e in old
    ]
    assert all(e.status == NATIVE_ONLY for e in retired), retired
    # This readonly description still pins the same retired provider. Its
    # implementation contract is stable without admitting another writer.
    assert source.query_mutex_stack_bytes(fd) == 256
    writer_refused()
    return {
        "writer_only": before,
        "drained": drained,
        "retired": after,
        "entries": len(old),
        "unload_refusal": unload.stderr,
    }


def registry_snapshot():
    return [
        {"entry": e.rip, "code": e.code, "tgid": e.tgid, "status": e.status}
        for e in entries()
    ]


def source_symbols():
    names = {
        "kd_parallel_cs0",
        "kd_parallel_cs1",
        "kd_parallel_native",
        "parallel_lanes",
    }
    symbols = {
        row[2]: int(row[0], 16)
        for line in Path("/proc/kallsyms").read_text().splitlines()
        if len(row := line.split()) == 4
        and row[3] == "[klock_module]"
        and row[2] in names
    }
    assert set(symbols) == names and all(symbols.values()), symbols
    return symbols


def lock_return_sites(symbols, published):
    # Validate the old JIT keys against actual ELF CALL relocations, not only
    # a function's range. Reload uses the same module bytes and runtime bases;
    # each completed native record must therefore pass the same outer-lock RIP.
    sites = {}
    with (ROOT / "workload_modules/lock_scenarios/klock_module.ko").open("rb") as stream:
        elf = ELFFile(stream)
        symtab = elf.get_section_by_name(".symtab")
        for name in ("kd_parallel_cs0", "kd_parallel_cs1"):
            (symbol,) = symtab.get_symbol_by_name(name)
            calls = []
            for section in elf.iter_sections():
                if (
                    section["sh_type"] != "SHT_RELA"
                    or section["sh_info"] != symbol["st_shndx"]
                ):
                    continue
                linked = elf.get_section(section["sh_link"])
                for relocation in section.iter_relocations():
                    offset = relocation["r_offset"] - symbol["st_value"]
                    if (
                        0 <= offset < symbol["st_size"]
                        and linked.get_symbol(relocation["r_info_sym"]).name
                        == "mutex_lock"
                    ):
                        assert relocation["r_info_type"] in (2, 4), relocation.entry
                        calls.append(symbols[name] + offset + 4)
            assert len(calls) == 2, (name, calls)
            sites[str(min(calls))] = name
    assert set(map(int, sites)) == {p["entry"] for p in published}, sites
    return sites


def reload_marker(phase):
    fd = os.open("/dev/kmsg", os.O_WRONLY | os.O_CLOEXEC)
    try:
        os.write(fd, f"<6>kd_source reload: phase={phase}\n".encode())
    finally:
        os.close(fd)


def reload_source(fd, out):
    state = source.info(fd)
    assert state == {
        "state": source.RETIRED,
        "modules": 0,
        "frames": 0,
        "writers": 0,
    }, state
    old = registry_snapshot()
    assert old and all(e["status"] == NATIVE_ONLY for e in old)
    first = int(
        Path("/sys/module/klock_module/parameters/mutex_parallel_first").read_text()
    )
    before = source_symbols()
    sites = lock_return_sites(before, json.loads((out / "published.json").read_text()))
    module = ROOT / "workload_modules/lock_scenarios/klock_module.ko"
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    # All old callers/frames/writers have drained. Keep kdlock and its retired
    # registry loaded, so unloading the provider cannot erase a stale-entry bug.
    subprocess.run(["rmmod", "klock_module"], check=True, timeout=10)
    reload_marker("begin")
    subprocess.run(
        [
            "insmod",
            str(module),
            "mutex_parallel=1",
            "mutex_parallel_retired=1",
            f"mutex_parallel_first={first}",
        ],
        check=True,
        timeout=10,
    )
    after = source_symbols()
    assert after == before, ("source address reuse not observed", before, after)
    assert hashlib.sha256(module.read_bytes()).hexdigest() == digest
    assert registry_snapshot() == old and source.info(fd) == state
    writer_refused()
    return {
        "before": before,
        "after": after,
        "sites": sites,
        "module_sha256": digest,
        "state": state,
        "registry": old,
        "first": first,
    }


def reloaded(fd, path):
    evidence = json.loads(path.read_text())
    assert source_symbols() == evidence["after"]
    assert registry_snapshot() == evidence["registry"]
    assert source.info(fd) == evidence["state"]
    # The identical eight roles have returned; module exit emits six complete
    # native records. The oracle validates them and real native queue pressure.
    subprocess.run(["rmmod", "klock_module"], check=True, timeout=10)
    reload_marker("end")
    assert registry_snapshot() == evidence["registry"]
    writer_refused()
    evidence["completed"] = True
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=("busy", "finish", "release", "reload", "reloaded")
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.phase == "release":
        release_writer(args.output / "writer")
        return
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        operations = {"busy": busy, "finish": finish, "reload": reload_source}
        result = (
            reloaded(fd, args.output)
            if args.phase == "reloaded"
            else operations[args.phase](fd, args.output.parent)
        )
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()

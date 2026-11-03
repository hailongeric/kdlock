#!/usr/bin/env python3
"""Guest-only reached-instruction execution fixture and normal provider build.

The fixture links the exact production engine source into its own module.
It checks resident execution independently of capture/cache integration; it
does not enable MM delegation or produce a throughput measurement.
"""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "bench/spin_cacheline"))
sys.path.insert(0, str(ROOT / "bench/mmap_fault"))
import bench_runtime as rt
import kernel_identity
import mm_platform
from provider.prepare import prepare as prepare_provider

MODULE = "kd_reached_test"
PASS = re.compile(r"KD_REACHED_TEST result=PASS cases=([0-9]+) "
                  r"executor_pid=([0-9]+) origin_pid=([0-9]+) "
                  r"source_fetches=([0-9]+) checks=([0-9]+) "
                  r"failure_line=([0-9]+) executor_stack=([0-9a-f]+)")


def idle():
    runpy.run_path(str(ROOT / "bench/archive_run.py"))["idle"](ROOT, rt.idle)
    rt.require(not Path("/sys/module", MODULE).exists(), "existing reached fixture")
    for path in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            name = path.read_text().strip()
        except FileNotFoundError:
            continue
        rt.require(name != "kd_reached_test", "existing reached fixture task")


def sources(root):
    result = {}
    for directory in ("include", "kernel_module", "tests/kernel/reached_path",
                      "bench/spin_cacheline", "bench/mmap_fault", "bench/basic",
                      "kernel_baseline", "kernel_integration/linux70"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (not path.is_file() or path.name.endswith(".mod.c") or
                    any(part.startswith(".") or part == "__pycache__"
                        for part in relative.parts)):
                continue
            if (path.suffix in (".c", ".h", ".inc", ".S", ".py", ".def",
                                ".json", ".patch", ".md") or
                    path.name in ("Makefile", "requirements.txt", "guest.config")):
                result[str(relative)] = rt.digest(path)
    name = "bench/archive_run.py"
    result[name] = rt.digest(root / name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith("/root/"),
               "run in the designated development guest")
    rt.require(os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1" and
               bool(os.environ.get("KDLOCK_SNAPSHOT_TAG")),
               "confirmed recovery snapshot required")
    rt.require(sys.executable == mm_platform.PYTHON and
               shutil.which("python3") == mm_platform.PYTHON,
               "pinned translation Python required")
    provenance = mm_platform.source_identity(ROOT)
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT),
               "new output outside the frozen source required")
    output_volume = out.parent
    while not output_volume.exists():
        output_volume = output_volume.parent
    rt.require(shutil.disk_usage(ROOT).free >= 2 * 1024**3 and
               shutil.disk_usage(output_volume).free >= 4 * 1024**3,
               "source and output filesystems lack focused-build headroom")
    idle()
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, actual_mm=False,
                  capture_integration=False, provider_loaded=False,
                  source_provenance=provenance,
                  snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"])
    messages = ""
    fd = None

    def logs():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                data = os.read(fd, 1 << 20)
            except BlockingIOError:
                break
            if not data:
                break
            messages += data.decode(errors="replace") + "\n"
        (out / "kernel.log").write_text(messages)

    def check_log():
        logs()
        rt.require(not rt.FAULT.search(messages),
                   "kernel execution failure; retain the current module state")

    try:
        result["kernel_identity"] = kernel_identity.capture(args, out, rt.command)
        rt.write_json(out / "environment.json", dict(
            source_provenance=provenance, kernel_identity=result["kernel_identity"],
            python=sys.executable, argv=sys.argv,
            boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            cmdline=Path("/proc/cmdline").read_text(),
            snapshot_tag=result["snapshot_tag"]))
        hashes = sources(ROOT)
        source, build = out / "source", out / "build"
        for relative in hashes:
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        rt.write_json(out / "source-sha256.json", hashes)
        rt.require(sources(ROOT) == sources(source) == hashes, "source copy changed")
        prepare_provider(build / "provider", source)
        provider = build / "provider/kernel_module/kdlock_km.ko"
        rt.command(["make", "-C", provider.parent, f"KDIR={args.kernel_source}",
                    "W=1", "KDLOCK_SELFTEST=0", "KDLOCK_NUMA=1",
                    "KDLOCK_SPIN_BATCH=1024", "KDLOCK_MUTEX_BATCH=1024",
                    "KDLOCK_MUTEX_NUMA_BOUNDARY=1024", "UBSAN_SANITIZE=n"],
                   out / "build-provider.log", timeout=300)
        result["provider_build_passed"] = True
        fixture = source / f"tests/kernel/reached_path/payload/{MODULE}.ko"
        rt.command(["make", "-C", fixture.parent, f"KDIR={args.kernel_source}",
                    f"KDLOCK_INCLUDE={source / 'include'}",
                    f"KDLOCK_REACHED_SOURCE={source / 'kernel_module/kd_reached.c'}"],
                   out / "build-fixture.log", timeout=180)
        binaries = {str(path): rt.digest(path) for path in (provider, fixture)}
        rt.write_json(out / "binary-sha256.json", binaries)
        rt.command(["objdump", "-dr", fixture], out / "fixture-disassembly.txt")

        def verify():
            rt.require(sources(ROOT) == sources(source) == hashes,
                       "frozen implementation or fixture source changed")
            rt.require(all(rt.digest(Path(path)) == digest
                           for path, digest in binaries.items()), "frozen binary changed")
            rt.require(mm_platform.source_identity(ROOT) == provenance,
                       "committed source identity changed")

        verify()
        idle()
        fd = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(["insmod", fixture], out / "load-fixture.log", timeout=45)
        check_log()
        rows = PASS.findall(messages)
        rt.require(len(rows) == 1, "missing or repeated reached fixture completion")
        cases, executor, origin, fetches, checks, failure_line = map(int, rows[0][:6])
        executor_stack = int(rows[0][6], 16)
        rt.require(cases > 0 and executor > 0 and origin > 0 and
                   executor != origin and fetches > 0 and checks >= cases and
                   failure_line == 0 and executor_stack != 0,
                   "reached fixture lacks other-task execution or source-byte fetches")
        result["fixture"] = dict(cases=cases, executor_pid=executor,
                                 origin_pid=origin, source_fetches=fetches,
                                 checks=checks, failure_line=failure_line,
                                 executor_stack=executor_stack)
        verify()
        rt.command(["rmmod", MODULE], out / "unload-fixture.log")
        check_log()
        idle()
        result.update(passed=True, drained=True)
    except (rt.Failure, OSError, ValueError, KeyError, ImportError) as error:
        result.update(error=str(error), error_type=type(error).__name__)
        raise
    finally:
        logs()
        if fd is not None:
            os.close(fd)
        rt.write_json(out / "result.json", result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

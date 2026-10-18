#!/usr/bin/env python3
"""Guest-only conditional address-guard exit, original-task resume and sticky ban."""
import argparse
import ctypes
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "bench/spin_cacheline"))
import bench_runtime as rt
from bench_session import Session
import kernel_identity
from provider.prepare import prepare as prepare_provider
from native_only_protocol import entries

DEVICE = "/dev/kd_jit_address_guard_test"
WORKER_COMM = "kg_worker"
RUNNER = "tests/kernel/spin/address_guard"
PAYLOAD = "workload_modules/jit_address_guard"
MODULE = "jit_address_guard_test"
CAP_VERSIONS, CAP_BIT, IMAGE_REQUIREMENT = (7, 8, 9), 6, 2
SUCCESS_MESSAGE = "PASS: cold branch delegated; aliasing load resumed on original task; exact effects/values; permanent native-only state; final drain"
RUN, SNAPSHOT, PREPARE, HOT = 0xC0204501, 0x80504502, 0x4503, 0x4504
PARAMETERS = Path("/sys/module/kdlock_km/parameters")
FIELDS = ("prefix", "suffix", "hot_taken", "lock_address", "entry", "marker",
          "failures", "active", "hot", "idle")


def image_registry():
    # Capability v7 keeps the 64-byte record and gives the former padding
    # its published requirement bits and immutable generation identifier.
    names = ("status", "pid", "tgid", "lock_kind", "entry", "code", "jump_from",
             "target", "entry_abi", "requirements", "generation")
    return [dict(zip(names, struct.unpack("=4i4Q2IQ", bytes(entry)))) for entry in entries()]


def snapshot():
    buffer = bytearray(80)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return dict(zip(FIELDS, struct.unpack("=10Q", buffer)))


def worker(arguments):
    cpu, iterations, index, start_ns = map(int, arguments)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(15, ctypes.c_char_p(WORKER_COMM.encode()), 0, 0, 0):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    comm = Path("/proc/self/comm").read_text().strip()
    rt.require(comm == WORKER_COMM, "worker task name differs from provider eligibility")
    os.sched_setaffinity(0, {cpu})
    buffer = bytearray(struct.pack("=4I2Q", iterations, index, 0, 0, 0, 0))
    with open(DEVICE, "rb", buffering=0) as device:
        while time.monotonic_ns() < start_ns:
            time.sleep(.001)
        fcntl.ioctl(device, RUN, buffer, True)
    returned, returned_index, reserved0, reserved1, completed, errors = struct.unpack("=4I2Q", buffer)
    print(json.dumps(dict(cpu=cpu, comm=comm, iterations=returned, worker=returned_index,
                         reserved=[reserved0, reserved1], completed=completed, errors=errors)))


def sources(root):
    hashes = {}
    for directory in ("include", "kernel_module", "daemon", "disassem", "kernel_baseline",
                      "bench/spin_cacheline", "bench/tclock_compare/allocator_guard",
                      "tests/protocols", "tests/kernel/spin/address_guard", RUNNER, PAYLOAD):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (not path.is_file() or any(p.startswith(".") or p in ("__pycache__", "results")
                                          for p in relative.parts) or path.name.endswith(".mod.c")):
                continue
            if (path.suffix in (".c", ".h", ".inc", ".S", ".def", ".py", ".json", ".patch", ".md") or
                    path.name in ("Makefile", "requirements.txt", "guest.config")):
                hashes[str(relative)] = rt.digest(path)
    return hashes


def idle():
    rt.idle()
    for name in ("jit_address_guard_test", "jit_string_service_test", MODULE, "rwsem_probe", "rwlock_bench", "rwlock_test", "real_api",
                 "tc_allocator_guard", "tclock_backend_km", "tclock_mutex_backend_km",
                 "tclock_rwlock_backend_km"):
        rt.require(not Path("/sys/module", name).exists(), "existing module: " + name)
    for path in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            rt.require(path.read_text().strip() != WORKER_COMM, "existing marker worker: " + str(path))
        except FileNotFoundError:
            continue


class EscapeSession(Session):
    def __init__(self, out, spec, binaries, verify):
        super().__init__(out, spec, workload_module=binaries["workload"])
        self.binaries, self.verify = binaries, verify
        self.daemon_binary = binaries["daemon"]
        self.translation_source = out / "source"

    def counts(self, label):
        row = snapshot()
        rt.write_json(self.path / (label + ".counts.json"), row)
        rt.require(row["active"] == 0 and row["idle"] == 1,
                   "workload or spin lock still active: " + str(row), "UNDRAINED")
        rt.require(row["failures"] == 0 and row["prefix"] == row["suffix"],
                   "exclusion/effect/continuation failure: " + str(row), "DATA_ERROR")
        return row

    def counters(self):
        return {key: int((PARAMETERS / key).read_text())
                for key in ("bench_jit_bodies", "bench_jit_completions", "address_guard_count")}

    def registry(self, label, expected):
        rows = image_registry()
        rt.write_json(self.path / (label + ".registry.json"), rows)
        rt.require(len(rows) == 1 and rows[0]["entry"] == self.record["layout"]["entry"] and
                   rows[0]["lock_kind"] == 1 and rows[0]["entry_abi"] == 1 and
                   rows[0]["status"] == expected,
                   f"unexpected registry at {label}: {rows}", "DATA_ERROR")
        return rows

    def prepare(self):
        self.verify()
        self.run(["insmod", self.binaries["guard"]], "load-allocator-guard.log")
        self.run(["rmmod", "tc_allocator_guard"], "unload-allocator-guard.log")
        self.run(["insmod", self.binaries["provider"], "bench_quiet=1",
                  "bench_complete_probe=1", "jit_timing=0",
                  f"target_process={WORKER_COMM}"], "load-provider.log")
        self.loaded_kd = True
        caps = bytearray(16)
        with open("/dev/kd_dev", "rb", buffering=0) as device:
            fcntl.ioctl(device, 0x80104B73, caps, True)
        version, features, stack_bytes, module_bytes = struct.unpack("=4I", caps)
        self.record["capabilities"] = dict(version=version, features=features,
                                           mutex_stack_bytes=stack_bytes, percpu_module_bytes=module_bytes)
        self.save()
        rt.require(version in CAP_VERSIONS and features & (1 << CAP_BIT),
                   "required checked-spin capability missing")
        self.run(["insmod", self.workload_module], "load-workload.log")
        self.loaded_source = True
        layout = self.counts("initial")
        rt.require(layout["prefix"] == layout["suffix"] == layout["hot_taken"] == layout["hot"] == 0,
                   "nonzero initial workload state")
        rt.require(layout["lock_address"] and layout["entry"] and layout["marker"], "missing source labels")
        self.record.update(layout=layout, entry_range=[layout["entry"], layout["entry"] + 1],
                           caller_abi="clobber", entry_abi=1)
        (PARAMETERS / "bench_lock_addr").write_text(str(layout["lock_address"]))
        with open(DEVICE, "rb", buffering=0) as device:
            fcntl.ioctl(device, PREPARE)
        self.start_daemon()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.faults()
            rows = rt.registry()
            rt.require(self.daemon.poll() is None, "daemon exited during translation")
            rt.require(len(rows) == 1 and rows[0]["entry"] == layout["entry"] and
                       rows[0]["status"] in (-1, 0), f"cold branch rejected: {rows}")
            if rows[0]["status"] == 0 and not rt.children(self.daemon.pid):
                self.record["publication"] = self.publication()
                self.record["image_registry"] = self.registry("initial", 0)
                rt.require(self.record["image_registry"][0]["requirements"] == IMAGE_REQUIREMENT and
                           self.record["image_registry"][0]["generation"] > 0,
                           "marker image lacks the required native-exit contract")
                self.record["initial_parameters"] = rt.parameters()
                rt.require(self.record["initial_parameters"]["target_process"] == WORKER_COMM,
                           "provider worker eligibility name differs")
                self.save()
                return
            time.sleep(.1)
        raise rt.Failure("TIMEOUT", "cold branch failed to publish", unsafe=True)

    def phase(self, name, iterations, hot):
        self.verify()
        before = self.counts(name + "-before")
        rt.require(before["hot"] == hot, "incorrect phase flag")
        counts_before = self.counters()
        result = dict(name=name, iterations=iterations, hot=hot, before=before,
                      counters_before=counts_before, registry_before=image_registry(), complete=False)
        self.record.setdefault("phases", []).append(result)
        self.save()
        start_ns = time.monotonic_ns() + 1000000000
        processes, logs = [], []
        try:
            for index, cpu in enumerate(self.record["cpus"]):
                log = (self.path / f"{name}-worker-{index}.json").open("w")
                logs.append(log)
                argv = [sys.executable, self.translation_source / RUNNER / "run.py",
                        "--worker", str(cpu), str(iterations), str(index), str(start_ns)]
                processes.append(subprocess.Popen(list(map(str, argv)), stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True))
        except OSError as error:
            for log in logs:
                log.close()
            rt.write_json(self.path / (name + "-callers.json"), [dict(pid=p.pid, argv=p.args) for p in processes])
            raise rt.Failure("CALLER_START_FAILED", f"retain caller PIDs {[p.pid for p in processes]}",
                             unsafe=True) from error
        rt.write_json(self.path / (name + "-callers.json"), [dict(pid=p.pid, argv=p.args) for p in processes])
        deadline = time.monotonic() + self.record["phase_timeout"]
        try:
            for process in processes:
                process.wait(timeout=max(.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise rt.Failure("TIMEOUT", f"retain caller PIDs {[p.pid for p in processes]}", unsafe=True) from error
        finally:
            for log in logs:
                log.close()
        self.faults()
        result["returncodes"] = [p.returncode for p in processes]
        self.save()
        rt.require(all(p.returncode == 0 for p in processes), "worker process failed", "DATA_ERROR")
        workers = [json.loads((self.path / f"{name}-worker-{i}.json").read_text())
                   for i in range(len(processes))]
        after, counts_after = self.counts(name + "-after"), self.counters()
        delta = {key: counts_after[key] - counts_before[key] for key in counts_before}
        result.update(workers=workers, after=after, counters_after=counts_after, jit_delta=delta,
                      registry_after=image_registry())
        self.save()
        for index, worker_result in enumerate(workers):
            rt.require(worker_result == dict(cpu=self.record["cpus"][index], comm=WORKER_COMM, iterations=iterations,
                       worker=index, reserved=[0, 0], completed=iterations, errors=0),
                       f"worker {index} progress/context/value failure: {worker_result}", "DATA_ERROR")
        operations = iterations * len(workers)
        rt.require(after["prefix"] - before["prefix"] == operations and
                   after["suffix"] - before["suffix"] == operations and
                   after["hot_taken"] - before["hot_taken"] == hot * operations,
                   "prefix/suffix/native branch duplicated or omitted", "DATA_ERROR")
        rt.require(0 <= delta["bench_jit_completions"] <= delta["bench_jit_bodies"] <= operations,
                   "invalid execution counters", "DATA_ERROR")
        rt.require(0 <= delta["address_guard_count"] <= operations and
                   (hot or delta["address_guard_count"] == 0),
                   "invalid or unexpected address-guard exit count", "DATA_ERROR")
        state = rt.status()
        result["source_after"] = state
        rt.require(state["state"] == 0 and state["frames"] == 0,
                   "phase did not drain its execution frames", "UNDRAINED")
        result["complete"] = True
        self.save()
        self.verify()
        print(json.dumps(dict(name=name, operations=operations, jit_delta=delta)), flush=True)
        return result

    def measure(self):
        self.record["execution_status"] = "MEASURING"
        self.phase("cold-warmup", self.record["warmup_iterations"], 0)
        cold = self.phase("cold-delegated", self.record["iterations"], 0)
        rt.require(cold["jit_delta"]["bench_jit_bodies"] == cold["jit_delta"]["bench_jit_completions"] > 0,
                   "cold branch lacks completed delegated bodies", "NO_JIT")
        self.registry("cold", 0)
        rt.require(self.publication() == self.record["publication"], "cold image changed")
        with open(DEVICE, "rb", buffering=0) as device:
            fcntl.ioctl(device, HOT)
        hot = self.phase("hot-escape", self.record["iterations"], 1)
        rt.require(hot["jit_delta"]["address_guard_count"] > 0,
                   "hot branch did not execute a validated address guard", "DATA_ERROR")
        self.registry("hot", -3)
        self.faults()
        pattern = re.compile(r"reason=ADDRESS_GUARD\s+entry=(0x[0-9a-f]+)\s+rip=(0x[0-9a-f]+)\s+"
                             r"generation=(\d+)\s+waiter_pid=(\d+)\s+action=native_suffix_and_disable", re.I)
        events = [dict(entry=int(m[1], 16), rip=int(m[2], 16), generation=int(m[3]), waiter_pid=int(m[4]))
                  for m in pattern.finditer(self.messages)]
        self.record["escape_events"] = events
        self.save()
        pids = {row["pid"] for row in json.loads((self.path / "hot-escape-callers.json").read_text())}
        rt.require(events and len(events) <= hot["jit_delta"]["address_guard_count"] and
                   all(event["entry"] == self.record["layout"]["entry"] and
                   event["rip"] == self.record["layout"]["marker"] and
                   event["generation"] == self.record["image_registry"][0]["generation"] and
                   event["waiter_pid"] in pids for event in events),
                   "missing or mismatched address-guard event", "DATA_ERROR")
        post = self.phase("post-ban", self.record["iterations"], 1)
        rt.require(all(value == 0 for value in post["jit_delta"].values()),
                   "delegation resumed after terminal rejection", "DATA_ERROR")
        self.registry("post-ban", -3)
        self.record.update(jit_status="COLD_JIT_THEN_NATIVE_ONLY", accepted=True,
                           final_parameters=rt.parameters())
        self.verify()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cpus", type=rt.cpu_list, default=list(range(16)))
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--warmup-iterations", type=int, default=100000)
    parser.add_argument("--phase-timeout", type=int, default=120)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith("/root/") and
               os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1" and os.environ.get("KDLOCK_SNAPSHOT_TAG"),
               "verified recovery guest and recorded snapshot tag required")
    rt.require(4 <= len(args.cpus) <= 60 and len(set(args.cpus)) == len(args.cpus) and
               set(args.cpus) <= os.sched_getaffinity(0), "select 4..60 distinct available worker CPUs")
    rt.require(0 < args.iterations <= 10000000 and 0 < args.warmup_iterations <= 10000000 and
               1 <= args.phase_timeout <= 600, "invalid iteration/timeout bounds")
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), "new output outside source required")
    idle()
    out.mkdir(parents=True)
    try:
        identity = kernel_identity.capture(args, out, rt.command)
        packages = {p: importlib.metadata.version(p) for p in ("miasm", "future", "pyparsing", "pyelftools")}
        rt.require(packages == dict(miasm="0.1.5", future="1.0.0", pyparsing="2.4.7", pyelftools="0.27"),
                   "translation dependency versions differ")
        rt.write_json(out / "environment.json", dict(kernel_identity=identity, packages=packages,
            topology=rt.capture_topology(args.cpus), argv=sys.argv, python=sys.executable,
            snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"], boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            cmdline=Path("/proc/cmdline").read_text(), uname=list(os.uname())))
        source, build = out / "source", out / "build"
        hashes = sources(ROOT)
        for relative in hashes:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        rt.write_json(out / "source-sha256.json", hashes)
        rt.require(sources(ROOT) == sources(source) == hashes, "source snapshot changed")
        # The prepared provider is a private, recorded observation overlay.
        # Production sources and their instruction policy remain unmodified.
        prepare_provider(build / "provider", source)
        provider = build / "provider/kernel_module/kdlock_km.ko"
        rt.command(["make", "-C", provider.parent, f"KDIR={args.kernel_source}", "W=1",
                    "KDLOCK_SELFTEST=0", "KDLOCK_NUMA=1", "KDLOCK_SPIN_BATCH=1024", "UBSAN_SANITIZE=n"],
                   out / "build-provider.log", timeout=180)
        guard_dir = build / "guard"
        shutil.copytree(source / "bench/tclock_compare/allocator_guard", guard_dir)
        rt.command(["make", "-C", guard_dir, f"KDIR={args.kernel_source}"], out / "build-guard.log", timeout=180)
        workload = source / PAYLOAD / (MODULE + ".ko")
        rt.command(["make", "-C", workload.parent, f"KDIR={args.kernel_source}",
                    f"KDLOCK_INCLUDE={source / 'include'}",
                    f"KBUILD_EXTRA_SYMBOLS={provider.parent / 'Module.symvers'}"], out / "build-workload.log", timeout=180)
        rt.command(["make", "-C", source / "daemon", "CFLAGS=-O2 -Wall -Wextra -Werror"],
                   out / "build-daemon.log", timeout=120)
        binaries = dict(provider=provider, workload=workload, daemon=source / "daemon/daemon",
                        guard=guard_dir / "tc_allocator_guard.ko")
        binary_hashes = {str(path): rt.digest(path) for path in binaries.values()}
        rt.write_json(out / "binary-sha256.json", binary_hashes)
        # Capture exact generated C/.inc/assembly inputs as well as production.
        prepared_hashes = {str(p.relative_to(build / "provider")): rt.digest(p)
                           for p in (build / "provider").rglob("*") if p.is_file() and
                           (p.suffix in (".c", ".h", ".inc", ".S", ".def") or p.name == "Makefile")
                           and not p.name.endswith(".mod.c")}
        rt.write_json(out / "prepared-source-sha256.json", prepared_hashes)

        def verify():
            rt.require(sources(ROOT) == hashes and sources(source) == hashes,
                       "live or frozen source changed")
            rt.require(all(rt.digest(Path(path)) == value for path, value in binary_hashes.items()),
                       "frozen binary changed")
            rt.require(all(rt.digest(build / "provider" / path) == value
                           for path, value in prepared_hashes.items()), "prepared provider input changed")

        verify()
        idle()
        spec = dict(name="session", arm="kdlock", lock_kind="spin", delegate=True,
                    cpus=args.cpus, iterations=args.iterations, warmup_iterations=args.warmup_iterations,
                    phase_timeout=args.phase_timeout, kernel_identity=identity)
        session = EscapeSession(out, spec, binaries, verify)
        session.execute()
        verify()
        idle()
        rt.write_json(out / "result.json", dict(passed=True, drained=True, phases=session.record["phases"],
            escape_events=session.record["escape_events"], kernel_identity=identity,
            snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]))
        print(SUCCESS_MESSAGE)
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, ImportError) as error:
        rt.write_json(out / "failure.json", dict(error=str(error), status=getattr(error, "status", "FAILED"),
                                               unsafe=getattr(error, "unsafe", False)))
        print(f"STOP: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

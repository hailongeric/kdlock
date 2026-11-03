#!/usr/bin/env python3
"""Guest rwlock correctness test with native, KD-native and KD-JIT controls.

Use a verified recovery snapshot and freshly built, frozen inputs. A timeout
leaves modules/callers in place for diagnosis; it never implies safe drain.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "bench/spin_cacheline"))
from bench_runtime import Failure, command, cpu_list, digest, idle, registry, require
from bench_session import Session
import kernel_identity

RUN = 0xC0205201
SNAPSHOT = 0x80685202
PREPARE = 0x5203
DEVICE = "/dev/kd_rwlock_test"


def snapshot():
    buffer = bytearray(104)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    row = struct.unpack("=10Q6I", buffer)
    return dict(values=list(row[:8]), gate_address=row[8], entry=row[9],
                failures=row[10], max_readers=row[11], active=row[12],
                cnts=row[13], gate=row[14])


def worker(arguments):
    cpu, iterations, every, index, start_ns = map(int, arguments)
    os.sched_setaffinity(0, {cpu})
    buffer = bytearray(struct.pack("=4I2Q", iterations, every, index, 0, 0, 0))
    with open(DEVICE, "rb", buffering=0) as device:
        while time.monotonic_ns() < start_ns:
            time.sleep(0.001)
        fcntl.ioctl(device, RUN, buffer, True)
    _, _, _, _, reads, writes = struct.unpack("=4I2Q", buffer)
    print(json.dumps(dict(cpu=cpu, reads=reads, writes=writes)))


class RWSession(Session):
    def counts(self, label):
        row = snapshot()
        (self.path / f"{label}.counts.json").write_text(json.dumps(row, indent=2) + "\n")
        require(not any(row[key] for key in ("failures", "active", "cnts", "gate")),
                f"rwlock invariants/drain failed: {row}", "DATA_ERROR")
        return row

    def prepare(self):
        if self.record["arm"] == "kdlock":
            guard = ROOT / "bench/tclock_compare/allocator_guard/tc_allocator_guard.ko"
            self.run(["insmod", guard], "allocator-load.log")
            self.run(["rmmod", "tc_allocator_guard"], "allocator-unload.log")
            provider = Path(self.record["provider"])
            self.run(["insmod", provider, "bench_quiet=1", "jit_timing=0",
                      "spin_entry_ratio_limit=0",
                      "spin_delegate=" + str(int(self.record["delegate"]))], "load-kd.log")
            self.loaded_kd = True
        self.run(["insmod", self.workload_module], "load-workload.log")
        self.loaded_source = True
        first = self.counts("initial")
        require(first["values"] == [0] * 8, "nonzero initial data")
        if not self.loaded_kd:
            require(first["entry"] == 0, "expected native workload")
            return
        require(first["entry"] and first["gate_address"], "expected KD workload")
        Path("/sys/module/kdlock_km/parameters/bench_lock_addr").write_text(str(first["gate_address"]))
        self.record.update(entry_range=[first["entry"], first["entry"] + 1], caller_abi="clobber", entry_abi=3)
        with open(DEVICE, "rb", buffering=0) as device:
            fcntl.ioctl(device, PREPARE)
        self.start_daemon()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.faults()
            rows = registry()
            require(len(rows) == 1 and rows[0]["entry"] == first["entry"], "unexpected registry")
            require(rows[0]["status"] in (-1, 0), f"translation refused/failed: {rows}")
            require(self.daemon.poll() is None, "daemon exited during translation")
            if rows[0]["status"] == 0:
                self.record["publication"] = self.publication()
                return
            time.sleep(0.1)
        raise Failure("TIMEOUT", "translation did not publish", unsafe=True)

    def phase(self, name, every, *, cpus=None, iterations=None, require_jit=False):
        cpus = self.record["cpus"] if cpus is None else cpus
        iterations = iterations or self.record["iterations"]
        before = self.counts(name + "-before")
        counter = Path("/sys/module/kdlock_km/parameters/bench_jit_bodies")
        jit_before = int(counter.read_text()) if self.loaded_kd else 0
        processes, logs = [], []
        start_ns = time.monotonic_ns() + 1000000000
        try:
            for index, cpu in enumerate(cpus):
                log = (self.path / f"{name}-worker-{index}.json").open("w")
                logs.append(log)
                argv = [sys.executable, str(Path(__file__).resolve()), "--worker", str(cpu),
                        str(iterations), str(every), str(index), str(start_ns)]
                processes.append(subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                                  start_new_session=True))
        except OSError as error:
            for log in logs:
                log.close()
            raise Failure("CALLER_START_FAILED", f"retained caller PIDs {[p.pid for p in processes]}",
                          unsafe=True) from error
        (self.path / f"{name}-callers.json").write_text(json.dumps([
            dict(pid=p.pid, argv=p.args) for p in processes], indent=2) + "\n")
        deadline = time.monotonic() + 90
        try:
            for process in processes:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise Failure("TIMEOUT", f"rwlock callers still live; PIDs {[p.pid for p in processes]}",
                          unsafe=True) from error
        finally:
            for log in logs:
                log.close()
        self.faults()
        require(all(p.returncode == 0 for p in processes), "worker failed", "DATA_ERROR")
        workers = [json.loads((self.path / f"{name}-worker-{i}.json").read_text())
                   for i in range(len(cpus))]
        for i, result in enumerate(workers):
            first = (-i) % every if every else iterations
            writes = 1 + (iterations - 1 - first) // every if first < iterations else 0
            require(result == dict(cpu=cpus[i], reads=iterations - writes, writes=writes),
                    f"worker {i} lost progress: {result}", "DATA_ERROR")
        after = self.counts(name + "-after")
        writes = sum(row["writes"] for row in workers)
        require(after["values"] == [v + writes for v in before["values"]],
                "lost or duplicate writer effects", "DATA_ERROR")
        jit = int(counter.read_text()) - jit_before if self.loaded_kd else 0
        require(0 <= jit <= writes, "invalid returned-body count", "DATA_ERROR")
        if not every or not self.record["delegate"]:
            require(jit == 0, "native/readers-only control executed JIT", "DATA_ERROR")
        if require_jit and self.loaded_kd and self.record["delegate"]:
            require(jit > 0, "contended writers executed no JIT bodies", "NO_JIT")
        if not every and len(cpus) > 1:
            require(after["max_readers"] > 1, "readers did not overlap", "DATA_ERROR")
        result = dict(name=name, write_every=every, iterations=iterations,
                      workers=workers, jit_bodies=jit, max_readers=after["max_readers"])
        self.record.setdefault("phases", []).append(result)
        self.save()
        print(json.dumps(result), flush=True)

    def measure(self):
        self.phase("single-writer", 1, cpus=self.record["cpus"][:1], iterations=1000)
        self.phase("concurrent-readers", 0)
        self.phase("writer-warmup", 1, iterations=100000)
        self.phase("writers", 1, require_jit=True)
        self.phase("mixed-half", 2, require_jit=True)
        self.phase("mixed-read-heavy", 8)
        if self.loaded_kd:
            require(self.publication() == self.record["publication"], "publication changed")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("native", "kdlock"), default="kdlock")
    parser.add_argument("--delegate", choices=("on", "off"), default="on")
    parser.add_argument("--cpus", type=cpu_list, default=list(range(16)))
    parser.add_argument("--iterations", type=int, default=50000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workload", type=Path, default=ROOT / "tests/kernel/rwlock/fixture/rwlock_test.ko")
    parser.add_argument("--provider", type=Path, default=ROOT / "bench/spin_cacheline/.build/provider/kernel_module/kdlock_km.ko")
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    args.output = args.output.resolve()
    require(os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1",
            "confirm an actual recovery snapshot before setting KDLOCK_RECOVERY_CONFIRMED=1")
    require(4 <= len(args.cpus) <= 40 and set(args.cpus) <= os.sched_getaffinity(0),
            "select 4..40 distinct available CPUs for contended JIT acceptance")
    require(0 < args.iterations <= 10000000, "iterations outside 1..10000000")
    idle()
    require(not Path("/sys/module/rwlock_test").exists(), "rwlock workload already loaded")
    args.output.mkdir(parents=True, exist_ok=False)
    identity = kernel_identity.capture(args, args.output, command)
    boot = Path("/proc/cmdline").read_text()
    command(["dmesg"], args.output / "preflight-kernel.log")
    # The boot printk may have rotated out. The operations preflight verifies
    # native dispatch independently; do not infer a policy change from log loss.
    require("nopvspin" in boot.split(), "guest is missing the native-qspinlock boot argument")
    (args.output / "boot.txt").write_text(boot)
    inputs = [ROOT / "include/kd_rwlock.h", ROOT / "tests/kernel/rwlock/fixture/module.c",
              ROOT / "tests/kernel/rwlock/fixture/api.h", ROOT / "tests/kernel/rwlock/fixture/Makefile",
              Path(__file__).resolve()]
    (args.output / "inputs.json").write_text(json.dumps({str(p): digest(p) for p in inputs}, indent=2) + "\n")
    # Preserve the translator/header inputs used by this daemon session.
    for directory in ("include", "disassem"):
        shutil.copytree(ROOT / directory, args.output / "source" / directory,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    spec = dict(name="session", arm=args.backend, delegate=args.delegate == "on" and args.backend == "kdlock",
                cpus=args.cpus, iterations=args.iterations, provider=str(args.provider.resolve()),
                workload_sha256=digest(args.workload), kernel=os.uname().release,
                kernel_identity=identity,
                provider_sha256=digest(args.provider) if args.backend == "kdlock" else None)
    session = RWSession(args.output, spec, workload_module=args.workload.resolve())
    try:
        session.execute()
    finally:
        session.save()
    print("PASS rwlock: data, per-worker progress, exclusion, reader overlap and final drain", flush=True)


if __name__ == "__main__":
    main()

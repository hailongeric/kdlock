#!/usr/bin/env python3
"""Guest-only public mutex -> spin failed-CAS owner transfer and exact drain."""
import argparse
import ctypes
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
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
sys.path.insert(0, str(ROOT / "bench/tclock_compare"))
from mutex_api_audit import audit_public_entries

DEVICE = "/dev/kd_mutex_mixed_transfer"
MODULE = "kd_mutex_mixed_transfer"
COMM = ("kmx_worker", "kmx_spin", "kmx_worker", "kmx_worker", "kmx_thief")
GATE, SPIN, COMBINER, WAITER, THIEF = range(5)
PARAMETERS = Path("/sys/module/kdlock_km/parameters")
RUN, SNAPSHOT = 0xC0184D01, 0x81284D02
PREPARE, RELEASE, DRAIN, WARMUP, ARM = 0x4D03, 0x4D04, 0x4D05, 0xC0184D06, 0x4D07
PREHOLDER_RELEASE = 0x4D08
REQUIRED_ELIGIBILITY = (1 << GATE) | (1 << COMBINER) | (1 << WAITER)
FIELDS = ("a", "b", "entry", "spin_call", "active", "failures", "started", "ready",
          "done", "release_gate", "owner", "gate", "tail", "b_word", "prefix", "suffix",
          "combiner_bodies", "owner_before", "owner_after", "combiner_owner", "samples",
          "steal_attempts", "steals", "prefix_observed", "thief_done", "c_task", "w_task",
          "warm_ops", "armed", "warm_eligible", "entry_checked", "entry_eligible",
          "preholder_release", "preholder_done", "g_task", "t_task", "waiters")


def control(command):
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, command)


def snapshot():
    buffer = bytearray(296)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return dict(zip(FIELDS, struct.unpack("=36Qq", buffer)))


def publish(path, value):
    temporary = path.with_suffix(".tmp")
    rt.write_json(temporary, value)
    temporary.replace(path)


def wait_worker_start(go):
    # Pending userspace workers may leave a failed setup; this never interrupts
    # an ioctl already executing in the kernel or supplies evidence of drain.
    abort = go.parent / "abort-starts.json"
    deadline = time.monotonic() + 360
    while not go.exists():
        rt.require(not abort.exists(), "setup aborted before ioctl", "SETUP_ABORTED")
        rt.require(time.monotonic() < deadline, "worker start barrier expired", "TIMEOUT")
        time.sleep(.001)
    rt.require(not abort.exists(), "setup aborted before ioctl", "SETUP_ABORTED")


def worker(arguments):
    role, cpu, iterations = map(int, arguments[:3])
    warm = arguments[3] == "warm"
    receipt, go = map(Path, arguments[4:])
    rt.require(0 <= role < 5 and arguments[3] in ("warm", "test"), "invalid worker role")
    comm = "kmx_worker" if warm else COMM[role]
    libc = ctypes.CDLL(None, use_errno=True)
    rt.require(libc.prctl(15, ctypes.c_char_p(comm.encode()), 0, 0, 0) == 0,
               "failed to set worker comm")
    os.sched_setaffinity(0, {cpu})
    rt.require(os.sched_getaffinity(0) == {cpu} and Path("/proc/self/comm").read_text().strip() == comm,
               "worker affinity/comm differs")
    buffer = bytearray(struct.pack("=2I2Q", role, iterations, 0, 0))
    with open(DEVICE, "rb", buffering=0) as device:
        publish(receipt, dict(pid=os.getpid(), role=role, cpu=cpu, comm=comm))
        # Test workers import and bind before up to four bounded warm rounds.
        wait_worker_start(go)
        fcntl.ioctl(device, WARMUP if warm else RUN, buffer, True)
    returned_role, requested, returned, errors = struct.unpack("=2I2Q", buffer)
    print(json.dumps(dict(pid=os.getpid(), role=returned_role, cpu=cpu, comm=comm,
                         iterations=requested, returned=returned, errors=errors)))


def sources(root):
    hashes = {}
    for directory in ("include", "kernel_module", "daemon", "disassem", "kernel_baseline",
                      "kernel_integration/linux70", "bench/spin_cacheline",
                      "bench/tclock_compare/allocator_guard", "tests/protocols",
                      "tests/kernel/mutex/mixed_transfer"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (not path.is_file() or any(p.startswith(".") or p in ("__pycache__", "results")
                                          for p in relative.parts) or path.name.endswith(".mod.c")):
                continue
            if (path.suffix in (".c", ".h", ".inc", ".S", ".def", ".py", ".json", ".patch", ".md") or
                    path.name in ("Makefile", "requirements.txt", "guest.config")):
                hashes[str(relative)] = rt.digest(path)
    audit = "bench/tclock_compare/mutex_api_audit.py"
    hashes[audit] = rt.digest(root / audit)
    return hashes


def idle():
    rt.idle()
    for name in (MODULE, "jit_continuation_test", "rwsem_probe", "rwlock_bench", "rwlock_test", "real_api",
                 "tc_allocator_guard", "tclock_backend_km", "tclock_mutex_backend_km",
                 "tclock_rwlock_backend_km", "kd_mutex_local_probe", "kd_spin_irq_api_test"):
        rt.require(not Path("/sys/module", name).exists(), "existing module: " + name)
    for path in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            rt.require(path.read_text().strip() not in COMM, "existing mixed worker: " + str(path))
        except FileNotFoundError:
            pass


def trace_records(messages, prefix):
    result = []
    for line in messages.splitlines():
        if prefix in line:
            fields = line.split(prefix, 1)[1].strip().split()
            rt.require(all(field.count("=") == 1 for field in fields), "malformed trace: " + line,
                       "DATA_ERROR")
            row = dict(field.split("=") for field in fields)
            rt.require(len(row) == len(fields), "duplicate trace field: " + line, "DATA_ERROR")
            result.append(row)
    return result


def observe_hotlock(provider_root):
    """Expose the existing cached query only in this frozen diagnostic build."""
    path = provider_root / "kernel_module/kd_hotlock.c"
    text = path.read_text()
    anchor = ("bool kd_hotlock_query_mutex(unsigned long address) { "
              "return kd_hotlock_access(address, 1, false, false); }")
    export = "EXPORT_SYMBOL_GPL(kd_hotlock_query_mutex);"
    rt.require(text.count(anchor) == 1 and export not in text,
               "hotlock query observation overlay anchor differs")
    record = dict(path="kernel_module/kd_hotlock.c", before=rt.digest(path),
                  change=export, semantics="existing cached query; no heat/count/clock update")
    path.write_text(text.replace(anchor, anchor + "\n" + export))
    record["after"] = rt.digest(path)
    return record


class MixedSession(Session):
    def __init__(self, out, spec, binaries, verify):
        super().__init__(out, spec, workload_module=binaries["workload"])
        self.binaries, self.verify = binaries, verify
        self.daemon_binary = binaries["daemon"]
        self.translation_source = out / "source"
        self.callers, self.logs = [], []

    def counts(self, label):
        row = snapshot()
        rt.write_json(self.path / (label + ".counts.json"), row)
        rt.require(row["active"] == row["owner"] == row["gate"] == row["tail"] ==
                   row["b_word"] == row["waiters"] == 0,
                   "caller/lock records have not drained: " + str(row), "UNDRAINED")
        rt.require(row["failures"] == 0, "payload observation failure: " + str(row), "DATA_ERROR")
        if self.record.get("callers_joined"):
            control(DRAIN)
        return row

    def counters(self):
        return {name: int((PARAMETERS / name).read_text())
                for name in ("bench_jit_bodies", "bench_jit_completions")}

    def prepare(self):
        self.verify()
        self.run(["insmod", self.binaries["guard"]], "load-guard.log")
        self.run(["rmmod", "tc_allocator_guard"], "unload-guard.log")
        self.run(["insmod", self.binaries["provider"], "bench_quiet=1", "bench_complete_probe=1",
                  "jit_timing=0", "target_process=kmx_worker"], "load-provider.log")
        self.loaded_kd = True
        self.run(["insmod", self.workload_module], "load-payload.log")
        self.loaded_source = True
        layout = self.counts("initial")
        rt.require(layout["a"] and layout["b"] and layout["entry"] and layout["spin_call"],
                   "missing physical/control identity")
        self.record.update(layout=layout, entry_range=[layout["entry"], layout["entry"] + 1],
                           caller_abi="clobber")
        (PARAMETERS / "bench_lock_addr").write_text(str(layout["a"]))
        control(PREPARE)
        self.start_daemon()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.faults()
            rows = rt.registry()
            rt.require(self.daemon.poll() is None, "daemon exited while preparing")
            rt.require(len(rows) == 1 and rows[0]["entry"] == layout["entry"] and
                       rows[0]["status"] in (-1, 0), "unexpected prepared entry: " + str(rows))
            if rows[0]["status"] == 0 and not rt.children(self.daemon.pid):
                self.record["publication"] = self.publication()
                self.record["parameters"] = rt.parameters()
                self.save()
                return
            time.sleep(.1)
        raise rt.Failure("TIMEOUT", "prepared mutex image did not publish", unsafe=True)

    def launch(self, role, warm=False, round_number=0):
        prefix = f"warm-{round_number}" if warm else "test"
        name = prefix + "-" + str(role)
        receipt = self.path / (name + "-ready.json")
        go = self.path / (prefix + "-go.json" if warm else name + "-go.json")
        log = (self.path / (name + ".json")).open("w")
        self.logs.append(log)
        argv = [sys.executable, self.translation_source / "tests/kernel/mutex/mixed_transfer/run.py",
                "--worker", role, self.record["cpus"][role],
                self.record["warmup_iterations"] if warm else 1,
                "warm" if warm else "test", receipt, go]
        process = subprocess.Popen(list(map(str, argv)), stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        row = dict(pid=process.pid, role=role, cpu=self.record["cpus"][role], warm=warm,
                   warm_round=round_number if warm else None,
                   argv=list(map(str, argv)), receipt=str(receipt), output=name + ".json")
        self.callers.append((process, row))
        self.record["callers"] = [row for _, row in self.callers]
        self.save()
        return process, row

    def wait_state(self, label, predicate, processes, timeout=3):
        deadline = time.monotonic() + timeout
        row, observed_ns = None, None
        try:
            while time.monotonic() < deadline:
                self.faults()
                row = snapshot()
                observed_ns = time.monotonic_ns()
                rt.require(not row["failures"], "payload failed during " + label, "DATA_ERROR")
                if predicate(row):
                    rt.write_json(self.path / (label + ".counts.json"), row)
                    return row
                rt.require(all(process.poll() is None for process, _ in processes),
                           "worker exited before " + label, "DATA_ERROR")
                time.sleep(.002)
            raise rt.Failure("TIMEOUT", "retain workers: " + label, unsafe=True)
        except Exception as error:
            # Preserve the exact last observation, even on payload failure or
            # caller exit. A timeout snapshot is evidence, never a drain proof.
            failure = dict(label=label, error=str(error), last_snapshot=row,
                           observed_ns=observed_ns,
                           callers=[dict(metadata, returncode=process.poll())
                                    for process, metadata in processes])
            rt.write_json(self.path / (label + ".failed.json"), failure)
            self.record["failed_wait"] = failure
            self.save()
            raise

    def join(self, processes, timeout):
        deadline = time.monotonic() + timeout
        for process, _ in processes:
            process.wait(timeout=max(.01, deadline - time.monotonic()))
        rows = []
        for process, metadata in processes:
            rt.require(process.returncode == 0, "worker returned failure: " + str(metadata), "DATA_ERROR")
            row = json.loads((self.path / metadata["output"]).read_text())
            wanted = self.record["warmup_iterations"] if metadata["warm"] else 1
            comm = "kmx_worker" if metadata["warm"] else COMM[metadata["role"]]
            rt.require(row == dict(pid=process.pid, role=metadata["role"], cpu=metadata["cpu"],
                                   comm=comm, iterations=wanted, returned=wanted, errors=0),
                       "worker effects/context differ: " + str(row), "DATA_ERROR")
            rows.append(row)
        return rows

    def wait_receipts(self, processes, label):
        deadline = time.monotonic() + 10
        while not all(Path(row["receipt"]).exists() for _, row in processes):
            rt.require(time.monotonic() < deadline and all(p.poll() is None for p, _ in processes),
                       label + " readiness failed", "TIMEOUT")
            time.sleep(.005)

    def warm(self):
        self.record["warm_rounds"] = []
        for round_number in range(1, self.record["warmup_rounds"] + 1):
            warm = [self.launch(role, True, round_number) for role in range(5)]
            self.wait_receipts(warm, "warmup")
            publish(self.path / f"warm-{round_number}-go.json", dict(start=True))
            workers = self.join(warm, 60)
            before = self.counts(f"warm-{round_number}-drain")
            rt.require(before["warm_ops"] == round_number * 5 * self.record["warmup_iterations"] and
                       not before["prefix"] and not before["suffix"] and not before["started"],
                       "warmup count/probe isolation differs", "DATA_ERROR")
            self.record["warm_rounds"].append(dict(workers=workers, after=before))
            self.save()
            # A global JIT witness cannot establish CPU-local admission for G,
            # C or W. These cached queries ran at each affine worker's return.
            if before["warm_eligible"] & REQUIRED_ELIGIBILITY == REQUIRED_ELIGIBILITY:
                return before
        raise rt.Failure("DATA_ERROR", "real warmup did not make G/C/W eligible: " + str(before))

    def measure(self):
        self.verify()
        # Complete imports and affinity binding before the real warmup. No
        # holder is started until all required CPU-local queries report hot.
        probe = [self.launch(role) for role in (GATE, SPIN, THIEF, COMBINER, WAITER)]
        self.wait_receipts(probe, "test")
        self.warm()
        counters_before = self.counters()
        rt.require(counters_before["bench_jit_bodies"] > 0,
                   "real warmup did not demonstrate delegation; no forced heat fallback", "DATA_ERROR")
        control(ARM)
        # T holds A locally; G claims ACQUIRING without publishing a node. Once
        # T releases, G owns HELD. Only then can C and W publish queue nodes.
        publish(self.path / f"test-{THIEF}-go.json", dict(start=True))
        self.wait_state("preholder-held", lambda row: row["ready"] & (1 << THIEF) and
                        row["owner"] == row["t_task"] != 0 and row["gate"] == 0, probe)
        publish(self.path / f"test-{GATE}-go.json", dict(start=True))
        self.wait_state("gate-acquiring", lambda row: row["ready"] & (1 << GATE) and
                        row["owner"] == row["t_task"] != 0 and row["gate"] == 2 and
                        row["entry_eligible"] & (1 << GATE), probe)
        control(PREHOLDER_RELEASE)
        self.wait_state("gate-held", lambda row: row["owner"] == row["g_task"] != 0 and
                        row["gate"] == 1 and row["preholder_done"], probe)
        publish(self.path / f"test-{SPIN}-go.json", dict(start=True))
        self.wait_state("spin-held", lambda row: row["ready"] & (1 << SPIN) and row["b_word"], probe)
        publish(self.path / f"test-{COMBINER}-go.json", dict(start=True))
        first = self.wait_state("combiner-queued", lambda row: row["waiters"] == 1 and row["tail"] and
                                row["entry_eligible"] & (1 << COMBINER), probe)
        publish(self.path / f"test-{WAITER}-go.json", dict(start=True))
        self.wait_state("waiter-queued", lambda row: row["waiters"] == 2 and
                        row["tail"] != first["tail"] and row["ready"] == 31 and
                        row["entry_checked"] == row["entry_eligible"] == REQUIRED_ELIGIBILITY, probe)
        control(RELEASE)
        self.record["workers"] = self.join(probe, 15)
        self.record["callers_joined"] = True
        self.faults()
        after = self.counts("transfer-drain")
        delta = {key: self.counters()[key] - counters_before[key] for key in counters_before}
        rt.require(delta == dict(bench_jit_bodies=1, bench_jit_completions=0),
                   "expected one partial delegated W body: " + str(delta), "DATA_ERROR")
        rt.require(after["prefix"] == after["suffix"] == after["combiner_bodies"] == 1 and
                   after["owner_before"] == after["combiner_owner"] == after["c_task"] != 0 and
                   after["owner_after"] == after["w_task"] != after["c_task"] and
                   after["samples"] >= 2 and after["steal_attempts"] >= 10000 and
                   after["steals"] == 0 and after["done"] == after["ready"] == after["started"] == 31 and
                   after["prefix_observed"] == after["thief_done"] == 1,
                   "owner/effect/no-gap/reacquisition observations differ: " + str(after), "DATA_ERROR")
        pids = {row["role"]: row["pid"] for row in self.record["workers"]}
        layout = self.record["layout"]
        transfers = trace_records(self.messages, "kd_mutex transfer: ")
        rt.require(transfers == [dict(outer=f"{layout['a']:x}", executor=str(pids[COMBINER]),
                                    owner=str(pids[WAITER]), target=f"{layout['spin_call']:x}", pending="1")],
                   "missing/extraneous actual owner exchange: " + str(transfers), "DATA_ERROR")
        begins = trace_records(self.messages, "kd_native begin: ")
        rt.require(len(begins) == 1 and begins[0]["task"] == str(pids[WAITER]) and
                   int(begins[0]["outer"], 16) == layout["a"] and
                   int(begins[0]["entry"], 16) == layout["entry"] and
                   int(begins[0]["ip"], 16) == layout["spin_call"] and
                   int(begins[0]["cpu"]) == self.record["cpus"][COMBINER] and
                   int(begins[0]["sp"], 16) != 0 and begins[0]["held"] == begins[0]["remaining"] == "1" and
                   begins[0]["mutex"] == "1" and begins[0]["outer_released"] == "0",
                   "native resume did not preserve the pending B CALL: " + str(begins), "DATA_ERROR")
        rt.require(trace_records(self.messages, "kd_native ack: ") ==
                   [dict(task=str(pids[WAITER]), lock=f"{layout['a']:x}", mutex="1", last_spin="0")] and
                   trace_records(self.messages, "kd_native complete: ") ==
                   [dict(task=str(pids[WAITER]), outer=f"{layout['a']:x}", mutex="1")],
                   "physical unlock/retirement ACK differs", "DATA_ERROR")
        publication_after = self.publication()
        rt.require(publication_after == self.record["publication"], "immutable image changed", "DATA_ERROR")
        self.record.update(after=after, jit_delta=delta, owner_transfers=transfers,
                           native_begin=begins, publication_after=publication_after)
        self.verify()
        self.save()

    def execute(self):
        # A timeout or failed observation never authorizes killing ioctl users,
        # source retirement, module unload, or forced cleanup.
        try:
            self.prepare()
            self.measure()
            self.cleanup()
            stats = trace_records(self.messages, "kd_native stats: ")
            rt.require(stats == [dict(started="1", completed="1", unlocks="1")],
                       "final exact native counters differ: " + str(stats), "DATA_ERROR")
            self.record.update(execution_status="OK", native_stats=stats)
        except Exception as error:
            publish(self.path / "abort-starts.json", dict(error=str(error),
                    meaning="unstarted userspace barriers only; active ioctls untouched"))
            self.record.update(execution_status=getattr(error, "status", "RUN_FAILED"), error=str(error),
                               unsafe=True, retained_modules=[name for name in (MODULE, "kdlock_km")
                                                             if Path("/sys/module", name).exists()])
            raise
        finally:
            self.record["finished_ns"] = time.monotonic_ns()
            self.save()
            for log in self.logs:
                log.close()
            os.close(self.kmsg)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cpus", type=rt.cpu_list, default=rt.cpu_list("0-4"),
                        help="five distinct CPUs: delegation holder G, B holder, C, W, predecessor/thief T")
    parser.add_argument("--warmup-iterations", type=int, default=50000)
    parser.add_argument("--warmup-rounds", type=int, default=4,
                        help="maximum real warmup rounds before refusing cold G/C/W CPUs (1..4)")
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith("/root/") and
               os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1" and os.environ.get("KDLOCK_SNAPSHOT_TAG"),
               "verified recovery guest and recorded snapshot required")
    rt.require(len(args.cpus) == len(set(args.cpus)) == 5 and set(args.cpus) <= os.sched_getaffinity(0),
               "select five distinct available CPUs")
    rt.require(5000 <= args.warmup_iterations <= 200000, "warmup iterations out of range")
    rt.require(1 <= args.warmup_rounds <= 4, "warmup rounds out of range")
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
            snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"], uname=list(os.uname()),
            boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip()))
        source, build = out / "source", out / "build"
        hashes = sources(ROOT)
        for relative in hashes:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        rt.write_json(out / "source-sha256.json", hashes)
        rt.require(sources(ROOT) == sources(source) == hashes, "source changed while freezing")
        prepare_provider(build / "provider", source)
        # Preserve cold protocol evidence without logging every warmup body.
        # These exact replacements change only the existing diagnostic sink.
        native = build / "provider/kernel_module/execution/native.inc"
        text = native.read_text()
        trace_overlay = dict(before=rt.digest(native), sites=[])
        for prefix in ("kd_native begin:", "kd_native ack:", "kd_native complete:"):
            old = 'KD_PR_ROUTINE("' + prefix
            rt.require(text.count(old) == 1, "native trace overlay anchor differs: " + prefix)
            text = text.replace(old, 'pr_info("' + prefix)
            trace_overlay["sites"].append(prefix)
        native.write_text(text)
        trace_overlay["after"] = rt.digest(native)
        rt.write_json(out / "native-trace-overlay.json", trace_overlay)
        rt.write_json(out / "hotlock-query-overlay.json", observe_hotlock(build / "provider"))
        provider = build / "provider/kernel_module/kdlock_km.ko"
        rt.command(["make", "-C", provider.parent, f"KDIR={args.kernel_source}", "W=1",
                    "KDLOCK_SELFTEST=0", "KDLOCK_NUMA=1", "UBSAN_SANITIZE=n"],
                   out / "build-provider.log", timeout=180)
        guard = build / "guard"
        shutil.copytree(source / "bench/tclock_compare/allocator_guard", guard)
        rt.command(["make", "-C", guard, f"KDIR={args.kernel_source}"], out / "build-guard.log", timeout=180)
        payload = source / "tests/kernel/mutex/mixed_transfer/payload/kd_mutex_mixed_transfer.ko"
        rt.command(["make", "-C", payload.parent, f"KDIR={args.kernel_source}",
                    f"KDLOCK_INCLUDE={source / 'include'}", f"KBUILD_EXTRA_SYMBOLS={provider.parent / 'Module.symvers'}"],
                   out / "build-payload.log", timeout=180)
        imports = set(rt.command(["nm", "-u", payload], out / "payload-imports.txt").split())
        rt.require({"kd_mutex_direct_lock_clobber_v1", "kd_mutex_direct_unlock_clobber_v1",
                    "kd_spin_lock_clobber_v1", "kd_spin_unlock_clobber_v1",
                    "kd_hotlock_query_mutex"} <= imports and
                   "kd_spin_lock_pinned_clobber_v1" not in imports,
                   "public control shells differ")
        rt.write_json(out / "public-entry-audit.json",
                      audit_public_entries(payload, {"mixed_transfer_entry": "protected_body"}))
        rt.command(["objdump", "-dr", payload], out / "payload-disassembly.txt")
        rt.command(["make", "-C", source / "daemon", "CFLAGS=-O2 -Wall -Wextra -Werror"],
                   out / "build-daemon.log", timeout=120)
        binaries = dict(provider=provider, workload=payload, daemon=source / "daemon/daemon",
                        guard=guard / "tc_allocator_guard.ko")
        binary_hashes = {str(p): rt.digest(p) for p in binaries.values()}
        prepared = {str(p.relative_to(build / "provider")): rt.digest(p)
                    for p in (build / "provider").rglob("*") if p.is_file() and
                    (p.suffix in (".c", ".h", ".inc", ".S", ".def") or p.name == "Makefile") and
                    not p.name.endswith(".mod.c")}
        rt.write_json(out / "binary-sha256.json", binary_hashes)
        rt.write_json(out / "prepared-source-sha256.json", prepared)

        def verify():
            rt.require(sources(ROOT) == sources(source) == hashes, "live or frozen source changed")
            rt.require(all(rt.digest(Path(p)) == h for p, h in binary_hashes.items()), "binary changed")
            rt.require(all(rt.digest(build / "provider" / p) == h for p, h in prepared.items()),
                       "prepared provider changed")

        verify()
        idle()
        session = MixedSession(out, dict(name="session", arm="kdlock", lock_kind="mutex", entry_abi=2,
            delegate=True, cpus=args.cpus, warmup_iterations=args.warmup_iterations,
            warmup_rounds=args.warmup_rounds,
            kernel_identity=identity, snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]), binaries, verify)
        session.execute()
        verify()
        idle()
        rt.write_json(out / "result.json", dict(passed=True, drained=True, after=session.record["after"],
            jit_delta=session.record["jit_delta"], native_stats=session.record["native_stats"],
            source_retirement=session.record["retired"], kernel_identity=identity,
            snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]))
        print("PASS: actual failed CAS; C -> W physical owner; no thief acquisition; exact suffix, ACK, C reacquisition and drain")
        return 0
    except Exception as error:
        rt.write_json(out / "failure.json", dict(error=str(error), status=getattr(error, "status", "RUN_FAILED"),
                                               cleanup="not attempted on failure"))
        print(f"FAIL: {error}; retain workers and modules", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

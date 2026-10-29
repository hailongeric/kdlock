#!/usr/bin/env python3
"""Guest-only reached Native CALL and repeated per-path delegation."""
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "bench/spin_cacheline"))
import bench_runtime as rt
from bench_session import Session
import kernel_identity
from provider.prepare import prepare as prepare_provider
from native_only_protocol import entries
sys.path.insert(0, str(ROOT / "bench/tclock_compare"))
from mutex_api_audit import audit_public_entries

DEVICE = "/dev/kd_jit_native_call_test"
WORKER_COMM = "kn_worker"
RUN, SNAPSHOT, PREPARE, HOT, COLD = 0xC0204E01, 0x80584E02, 0x4E03, 0x4E04, 0x4E05
PARAMETERS = Path("/sys/module/kdlock_km/parameters")
FIELDS = ("prefix", "suffix", "taken", "lock_address", "entry", "call_site", "native_target",
          "failures", "active", "hot", "idle")

def publish_barrier(path, value):
    temporary = path.with_suffix(".tmp")
    rt.write_json(temporary, value)
    temporary.replace(path)

def image_registry():
    # Capability v6 keeps the 64-byte record and gives the former padding
    # its published requirement bits and immutable generation identifier.
    names = ("status", "pid", "tgid", "lock_kind", "entry", "code", "jump_from",
             "target", "entry_abi", "requirements", "generation")
    return [dict(zip(names, struct.unpack("=4i4Q2IQ", bytes(entry)))) for entry in entries()]

def snapshot():
    buffer = bytearray(88)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return dict(zip(FIELDS, struct.unpack("=11Q", buffer)))

def worker(arguments):
    cpu, iterations, index = map(int, arguments[:3])
    barrier = Path(arguments[3])
    role = arguments[4]
    rt.require(role == "writer", "invalid worker role")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(15, ctypes.c_char_p(WORKER_COMM.encode()), 0, 0, 0):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    comm = Path("/proc/self/comm").read_text().strip()
    rt.require(comm == WORKER_COMM, "worker task name differs from provider eligibility")
    os.sched_setaffinity(0, {cpu})
    rt.require(os.sched_getaffinity(0) == {cpu}, "worker affinity differs")
    buffer = bytearray(struct.pack("=4I2Q", iterations, index, 0, 0, 0, 0))
    with open(DEVICE, "rb", buffering=0) as device:
        publish_barrier(barrier / f"ready-{index}.json",
                        dict(pid=os.getpid(), cpu=cpu, role=role, comm=comm))
        deadline = time.monotonic() + 30
        while not (barrier / "go.json").exists():
            rt.require(time.monotonic() < deadline, "worker start barrier expired", "TIMEOUT")
            time.sleep(.001)
        start_ns = json.loads((barrier / "go.json").read_text())["start_ns"]
        while time.monotonic_ns() < start_ns:
            time.sleep(.001)
        fcntl.ioctl(device, RUN, buffer, True)
    returned, returned_index, reserved0, reserved1, completed, errors = struct.unpack("=4I2Q", buffer)
    print(json.dumps(dict(cpu=cpu, comm=comm, role=role, iterations=returned, worker=returned_index,
                         reserved=[reserved0, reserved1], completed=completed, errors=errors)))

def sources(root):
    hashes = {}
    for directory in ("include", "kernel_module", "daemon", "disassem", "kernel_baseline", "kernel_integration",
                      "bench/spin_cacheline", "bench/tclock_compare/allocator_guard",
                      "tests/protocols", "tests/kernel/jit_native_call"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (not path.is_file() or any(p.startswith(".") or p in ("__pycache__", "results")
                                          for p in relative.parts) or path.name.endswith(".mod.c")):
                continue
            if (path.suffix in (".c", ".h", ".inc", ".S", ".def", ".py", ".json", ".patch", ".md") or
                    path.name in ("Makefile", "requirements.txt", "guest.config")):
                hashes[str(relative)] = rt.digest(path)
    audit_path = "bench/tclock_compare/mutex_api_audit.py"
    hashes[audit_path] = rt.digest(root / audit_path)
    return hashes

def idle():
    rt.idle()
    for name in ("jit_native_call_test", "jit_escape_test", "rwsem_probe", "rwlock_bench", "rwlock_test", "real_api",
                 "tc_allocator_guard", "tclock_backend_km", "tclock_mutex_backend_km",
                 "tclock_rwlock_backend_km"):
        rt.require(not Path("/sys/module", name).exists(), "existing module: " + name)
    for path in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            rt.require(path.read_text().strip() != WORKER_COMM, "existing Native CALL worker: " + str(path))
        except FileNotFoundError:
            continue

def observe_provider(provider_root, record):
    """Private cold-path count after the real pending-CALL validator succeeds."""
    import difflib
    path = provider_root / "kernel_module/execution/wrapper_entry.inc"
    before = path.read_text()
    declaration = "static int kd_jit_pending_call_native(struct kd_exec_frame *frame,"
    counter = r'''static atomic64_t kd_native_call_probe_count = ATOMIC64_INIT(0);
static int kd_native_call_probe_get(char *buffer, const struct kernel_param *kp)
{
    (void)kp;
    return scnprintf(buffer, PAGE_SIZE, "%lld\n", (long long)atomic64_read(&kd_native_call_probe_count));
}
static const struct kernel_param_ops kd_native_call_probe_ops = {.get = kd_native_call_probe_get};
module_param_cb(native_call_probe_count, &kd_native_call_probe_ops, NULL, 0444);

'''
    point = "\tkd_exec_frame_save_continuation(frame, regs);\n\tpr_warn_ratelimited("
    replacement = ("\tkd_exec_frame_save_continuation(frame, regs);\n"
        "\tif (!strcmp(reason, \"NATIVE_CALL_TERMINAL\") || !strcmp(reason, \"INDIRECT_CALL_NATIVE\"))\n"
        "\t\tatomic64_inc(&kd_native_call_probe_count);\n\tpr_warn_ratelimited(")
    rt.require(before.count(declaration) == before.count(point) == 1,
               "Native CALL observation anchors differ")
    after = before.replace(declaration, counter + declaration).replace(point, replacement)
    path.write_text(after)
    patches = list(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                   fromfile="a/kernel_module/execution/wrapper_entry.inc",
                   tofile="b/kernel_module/execution/wrapper_entry.inc"))
    # Expose existing exact rendezvous counters without adding a decision or
    # suppressing any owner, frame or ACK check. Read only after callers join.
    path = provider_root / "kernel_module/kd_exec.c"
    before = path.read_text()
    anchor = "static atomic64_t kd_native_unlocks;"
    observation = r'''static int kd_native_call_relay_get(char *buffer, const struct kernel_param *kp)
{
    (void)kp;
    return scnprintf(buffer, PAGE_SIZE, "%lld %lld %lld\n",
        (long long)atomic64_read(&kd_native_started),
        (long long)atomic64_read(&kd_native_completed),
        (long long)atomic64_read(&kd_native_unlocks));
}
static const struct kernel_param_ops kd_native_call_relay_ops = {.get = kd_native_call_relay_get};
module_param_cb(native_call_relay, &kd_native_call_relay_ops, NULL, 0444);
'''
    rt.require(before.count(anchor) == 1, "Native relay observation anchor differs")
    after = before.replace(anchor, anchor + "\n" + observation)
    path.write_text(after)
    patches.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                   fromfile="a/kernel_module/kd_exec.c", tofile="b/kernel_module/kd_exec.c"))
    record.write_text("".join(patches))


def audit_call(disassembly, mode):
    match = re.search(r"(?m)^([0-9a-f]+) <jit_native_call_site>:\n([^\n]+)(?:\n([^\n]+))?", disassembly)
    rt.require(match is not None, "missing exact Native CALL label")
    instruction = re.fullmatch(r"\s*([0-9a-f]+):\s*((?:[0-9a-f]{2}\s+)+)\s*call\s+(.+)", match[2])
    rt.require(instruction is not None and int(instruction[1], 16) == int(match[1], 16),
               "named site is not the actual CALL instruction")
    raw = bytes.fromhex(instruction[2])
    rt.require(mode in ("direct", "indirect") and raw, "invalid CALL audit mode/bytes")
    if mode == "direct":
        rt.require(len(raw) == 5 and raw[0] == 0xe8 and
                   re.search(r"R_X86_64_(?:PLT32|PC32)\s+_raw_spin_trylock-0x4\s*$", match[3] or ""),
                   "direct CALL lacks exact Native target relocation")
    else:
        offset = int(0x40 <= raw[0] <= 0x4f)
        rt.require(len(raw) == offset + 2 and raw[offset] == 0xff and
                   raw[offset + 1] >> 6 == 3 and (raw[offset + 1] >> 3) & 7 == 2,
                   "fresh indirect CALL is not canonical register FF /2")
    return dict(mode=mode, object_offset=int(match[1], 16), length=len(raw), bytes=raw.hex())


def validate_phase(phase, hot):
    delta = phase["jit_delta"]
    rt.require(delta["native_escape_count"] == 0, "CALL probe reached an instruction marker", "DATA_ERROR")
    rt.require(all(delta[key] == delta["native_call_probe_count"] for key in
                   ("native_started", "native_completed", "native_unlocks")),
               "native begin/physical unlock/completion ACK totals differ", "DATA_ERROR")
    if hot:
        rt.require(delta["bench_jit_bodies"] == delta["native_call_probe_count"] > 0 and
                   delta["bench_jit_completions"] == 0,
                   "taken branch lacks exact validated CALL/native-suffix counts", "DATA_ERROR")
    else:
        rt.require(delta["bench_jit_bodies"] == delta["bench_jit_completions"] > 0 and
                   delta["native_call_probe_count"] == 0,
                   "cold branch lacks returned JIT bodies", "NO_JIT")


class NativeCallSession(Session):
    def __init__(self, out, spec, binaries, verify):
        super().__init__(out, spec, workload_module=binaries["workload"])
        self.binaries, self.verify = binaries, verify
        self.daemon_binary = binaries["daemon"]
        self.translation_source = out / "source"

    def counts(self, label):
        row = snapshot()
        rt.write_json(self.path / (label + ".counts.json"), row)
        rt.require(row["active"] == 0 and row["idle"] == 1,
                   "workload or lock still active: " + str(row), "UNDRAINED")
        rt.require(row["failures"] == 0 and row["prefix"] == row["suffix"],
                   "exclusion/effect/continuation failure: " + str(row), "DATA_ERROR")
        return row

    def registry(self, label, expected):
        rows = image_registry()
        rt.write_json(self.path / (label + ".registry.json"), rows)
        rt.require(len(rows) == 1 and rows[0]["entry"] == self.record["layout"]["entry"] and
                   rows[0]["lock_kind"] == self.record["registry_kind"] and
                   rows[0]["entry_abi"] == self.record["entry_abi"] and
                   rows[0]["status"] == expected,
                   f"unexpected registry at {label}: {rows}", "DATA_ERROR")
        return rows

    def counters(self):
        result = {key: int((PARAMETERS / key).read_text()) for key in
                  ("bench_jit_bodies", "bench_jit_completions", "native_call_probe_count", "native_escape_count")}
        relay = list(map(int, (PARAMETERS / "native_call_relay").read_text().split()))
        rt.require(len(relay) == 3 and all(value >= 0 for value in relay), "invalid native relay counters")
        result.update(zip(("native_started", "native_completed", "native_unlocks"), relay))
        return result

    def prepare(self):
        self.verify()
        self.run(["insmod", self.binaries["guard"]], "load-allocator-guard.log")
        self.run(["rmmod", "tc_allocator_guard"], "unload-allocator-guard.log")
        self.run(["insmod", self.binaries["provider"], "bench_quiet=1", "bench_complete_probe=1",
                  "jit_timing=0", f"target_process={WORKER_COMM}"], "load-provider.log")
        self.loaded_kd = True
        caps = bytearray(16)
        with open("/dev/kd_dev", "rb", buffering=0) as device:
            fcntl.ioctl(device, 0x80104B73, caps, True)
        version, features, stack_bytes, module_bytes = struct.unpack("=4I", caps)
        self.record["capabilities"] = dict(version=version, features=features,
            mutex_stack_bytes=stack_bytes, percpu_module_bytes=module_bytes)
        self.save()
        rt.require(version in (12, 13) and features & (1 << 12),
                   "Native CALL continuation capability missing from reviewed v12/v13 provider")
        self.run(["insmod", self.workload_module], "load-workload.log")
        self.loaded_source = True
        layout = self.counts("initial")
        rt.require(layout["prefix"] == layout["suffix"] == layout["taken"] == layout["hot"] == 0,
                   "nonzero initial workload")
        rt.require(all(value == 0 for value in self.counters().values()), "nonzero initial provider counters")
        rt.require(all(layout[key] for key in ("lock_address", "entry", "call_site", "native_target")),
                   "missing actual source/CALL identity")
        self.record.update(layout=layout, entry_range=[layout["entry"], layout["entry"] + 1], caller_abi="clobber")
        (PARAMETERS / "bench_lock_addr").write_text(str(layout["lock_address"]))
        with open(DEVICE, "rb", buffering=0) as device:
            fcntl.ioctl(device, PREPARE)
        self.start_daemon()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.faults()
            rows = rt.registry()
            rt.require(self.daemon.poll() is None, "daemon exited during translation")
            rt.require(len(rows) == 1 and rows[0]["entry"] == layout["entry"] and rows[0]["status"] in (-1, 0),
                       "Native CALL entry rejected: " + str(rows))
            if rows[0]["status"] == 0 and not rt.children(self.daemon.pid):
                self.record["publication"] = self.publication()
                self.record["image_registry"] = self.registry("initial", 0)
                rt.require(self.record["image_registry"][0]["requirements"] == 0 and
                           self.record["image_registry"][0]["generation"] > 0,
                           "CALL image must be immutable without an instruction-marker requirement")
                self.record["initial_parameters"] = rt.parameters()
                self.save()
                return
            time.sleep(.1)
        raise rt.Failure("TIMEOUT", "Native CALL entry did not publish", unsafe=True)

    def phase(self, name, iterations, hot):
        self.verify()
        before = self.counts(name + "-before")
        rt.require(before["hot"] == hot, "incorrect phase flag")
        counts_before = self.counters()
        result = dict(name=name, iterations=iterations, hot=hot, before=before,
                      counters_before=counts_before, registry_before=image_registry(), complete=False)
        self.record.setdefault("phases", []).append(result)
        self.save()
        barrier = self.path / (name + "-barrier")
        barrier.mkdir()
        requested = [self.record["reader_iterations"] if role == "reader" else iterations
                     for role in self.record["worker_roles"]]
        processes, logs = [], []
        joined = False
        failure_stage = "CALLER_START_FAILED"

        def callers():
            return [dict(pid=p.pid, argv=p.args, role=self.record["worker_roles"][i],
                         cpu=self.record["cpus"][i]) for i, p in enumerate(processes)]

        try:
            for index, cpu in enumerate(self.record["cpus"]):
                log = (self.path / f"{name}-worker-{index}.json").open("w")
                logs.append(log)
                argv = [sys.executable, self.translation_source / "tests/kernel/jit_native_call/run.py",
                        "--worker", str(cpu), str(requested[index]), str(index), str(barrier),
                        self.record["worker_roles"][index]]
                processes.append(subprocess.Popen(list(map(str, argv)), stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True))
                # Keep identities in memory even if publishing a receipt fails.
                # Session.execute saves this record on the failure path.
                result["callers"] = callers()
            rt.write_json(self.path / (name + "-callers.json"), callers())
            failure_stage = "CALLER_CONTROL_FAILED"
            deadline = time.monotonic() + self.record["phase_timeout"]
            ready_deadline = min(deadline, time.monotonic() + 20)
            while not all((barrier / f"ready-{i}.json").exists() for i in range(len(processes))):
                if time.monotonic() >= ready_deadline or any(p.poll() is not None for p in processes):
                    raise rt.Failure("TIMEOUT", "retain callers: start readiness barrier failed",
                                     unsafe=True)
                time.sleep(.01)
            ready = [json.loads((barrier / f"ready-{i}.json").read_text())
                     for i in range(len(processes))]
            if not all(row == dict(pid=processes[i].pid, cpu=self.record["cpus"][i],
                                   role=self.record["worker_roles"][i], comm=WORKER_COMM)
                       for i, row in enumerate(ready)):
                raise rt.Failure("DATA_ERROR", "retain callers: worker readiness identity differs",
                                 unsafe=True)
            result["ready"] = ready
            publish_barrier(barrier / "go.json", dict(start_ns=time.monotonic_ns() + 100000000))
            for process in processes:
                process.wait(timeout=max(.01, deadline - time.monotonic()))
            joined = True
        except Exception as error:
            # Until every caller joins, even barrier/receipt I/O or JSON errors
            # leave live device users possible. A zero payload active count
            # before GO does not prove those users drained.
            if isinstance(error, rt.Failure):
                error.unsafe = True
                raise
            status = "TIMEOUT" if isinstance(error, subprocess.TimeoutExpired) else failure_stage
            raise rt.Failure(status, f"retain caller PIDs {[p.pid for p in processes]}: {error}",
                             unsafe=True) from error
        finally:
            for log in logs:
                try:
                    log.close()
                except OSError as error:
                    raise rt.Failure("CALLER_LOG_FAILED", str(error), unsafe=not joined) from error
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
            rt.require(worker_result == dict(cpu=self.record["cpus"][index], comm=WORKER_COMM, iterations=requested[index],
                       role=self.record["worker_roles"][index], worker=index,
                       reserved=[0, 0], completed=requested[index], errors=0),
                       f"worker {index} progress/context failure: {worker_result}", "DATA_ERROR")
        operations = iterations * self.record["worker_roles"].count("writer")
        read_operations = self.record["reader_iterations"] * self.record["worker_roles"].count("reader")
        result.update(write_operations=operations, read_operations=read_operations)
        rt.require(after["prefix"] - before["prefix"] == operations and
                   after["suffix"] - before["suffix"] == operations and
                   after["taken"] - before["taken"] == hot * operations,
                   "prefix/suffix/native branch duplicated or omitted", "DATA_ERROR")
        rt.require(0 <= delta["bench_jit_completions"] <= delta["bench_jit_bodies"] <= operations,
                   "invalid execution counters", "DATA_ERROR")
        rt.require(0 <= delta["native_call_probe_count"] <= operations and
                   (hot or delta["native_call_probe_count"] == 0),
                   "invalid or unexpected Native CALL count", "DATA_ERROR")
        rt.require(delta["native_escape_count"] == 0, "instruction marker substituted for CALL", "DATA_ERROR")
        state = rt.status()
        result["source_after"] = state
        rt.require(state["state"] == 0 and state["frames"] == 0,
                   "phase did not drain its execution frames", "UNDRAINED")
        result["complete"] = True
        self.save()
        self.verify()
        print(json.dumps(dict(name=name, write_operations=operations,
                              read_operations=read_operations, jit_delta=delta)), flush=True)
        return result

    def cleanup(self):
        super().cleanup()
        rows = re.findall(r"kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)", self.messages)
        total = sum(phase.get("jit_delta", {}).get("native_call_probe_count", 0)
                    for phase in self.record.get("phases", []))
        rt.require(rows == [(str(total), str(total), str(total))],
                   "final native counters do not match joined CALL continuations", "DATA_ERROR")
        self.record["native_totals"] = dict(started=total, completed=total, unlocks=total)

    def measure(self):
        self.record["execution_status"] = "MEASURING"
        self.phase("cold-warmup", self.record["warmup_iterations"], 0)
        taken = []
        for name, hot in (("cold-delegated", 0), ("taken-native", 1), ("cold-after-native", 0), ("taken-repeat", 1)):
            with open(DEVICE, "rb", buffering=0) as device:
                fcntl.ioctl(device, HOT if hot else COLD)
            phase = self.phase(name, self.record["iterations"], hot)
            validate_phase(phase, hot)
            if hot: taken.append(phase)
            rt.require(self.registry(name, 0) == self.record["image_registry"] and
                       self.publication() == self.record["publication"],
                       "CALL changed the ready image/registry identity", "DATA_ERROR")
        self.faults()
        pattern = re.compile(r"reason=(NATIVE_CALL_TERMINAL|INDIRECT_CALL_NATIVE)\s+entry=(0x[0-9a-f]+)\s+"
                             r"ip=(0x[0-9a-f]+)\s+sp=(0x[0-9a-f]+)\s+return=(0x[0-9a-f]+)\s+"
                             r"lock=(0x[0-9a-f]+)\s+task=(\d+)\s+hostcall=(\d+)", re.I)
        events = [dict(reason=m[1], entry=int(m[2], 16), target=int(m[3], 16), sp=int(m[4], 16),
                       return_ip=int(m[5], 16), lock=int(m[6], 16), task=int(m[7]), hostcall=int(m[8]))
                  for m in pattern.finditer(self.messages)]
        pids = {caller["pid"] for phase in taken for caller in phase["callers"]}
        layout = self.record["layout"]
        expected_reason = "INDIRECT_CALL_NATIVE" if self.record["call_mode"] == "indirect" else "NATIVE_CALL_TERMINAL"
        rt.require(events and len(events) <= sum(p["jit_delta"]["native_call_probe_count"] for p in taken) and
                   all(event["reason"] == expected_reason and event["entry"] == layout["entry"] and
                       event["target"] == layout["native_target"] and event["lock"] == layout["lock_address"] and
                       event["return_ip"] == layout["call_site"] + self.record["call_audit"]["length"] and
                       event["task"] in pids and event["sp"] and event["hostcall"] == 0 for event in events),
                   "missing/mismatched exact Native CALL event", "DATA_ERROR")
        self.record.update(call_events=events, accepted=True,
            jit_status="COLD_JIT_TAKEN_NATIVE_COLD_JIT_TAKEN_NATIVE", final_parameters=rt.parameters())
        self.verify()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cpus", type=rt.cpu_list, default=list(range(16)))
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--warmup-iterations", type=int, default=200000)
    parser.add_argument("--phase-timeout", type=int, default=180)
    parser.add_argument("--call-mode", choices=("direct", "indirect"), required=True)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith("/root/") and
               os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1" and os.environ.get("KDLOCK_SNAPSHOT_TAG"),
               "verified recovery guest and recorded snapshot tag required")
    rt.require(4 <= len(args.cpus) <= 60 and len(set(args.cpus)) == len(args.cpus) and
               set(args.cpus) <= os.sched_getaffinity(0), "select 4..60 distinct available worker CPUs")
    rt.require(0 < args.iterations <= 1000000 and 0 < args.warmup_iterations <= 1000000 and
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
        prepare_provider(build / "provider", source)
        observe_provider(build / "provider", out / "native-call-observation.patch")
        provider = build / "provider/kernel_module/kdlock_km.ko"
        rt.command(["make", "-C", provider.parent, f"KDIR={args.kernel_source}", "W=1",
                    "KDLOCK_SELFTEST=0", "KDLOCK_NUMA=1", "KDLOCK_SPIN_BATCH=1024", "UBSAN_SANITIZE=n"],
                   out / "build-provider.log", timeout=180)
        guard_dir = build / "guard"
        shutil.copytree(source / "bench/tclock_compare/allocator_guard", guard_dir)
        rt.command(["make", "-C", guard_dir, f"KDIR={args.kernel_source}"], out / "build-guard.log", timeout=180)
        workload = source / "tests/kernel/jit_native_call/payload/jit_native_call_test.ko"
        rt.command(["make", "-C", workload.parent, f"KDIR={args.kernel_source}",
                    f"KDLOCK_INCLUDE={source / 'include'}", f"NATIVE_CALL_MODE={args.call_mode}",
                    f"KBUILD_EXTRA_SYMBOLS={provider.parent / 'Module.symvers'}"], out / "build-workload.log", timeout=180)
        mode = rt.command(["modinfo", "-F", "kd_native_call_mode", workload], out / "call-mode.txt").strip()
        rt.require(mode == args.call_mode, "compiled CALL mode differs")
        imports = set(rt.command(["nm", "-u", workload], out / "workload-imports.txt").split())
        rt.require({"_raw_spin_trylock", "kd_mutex_direct_lock_clobber_v1",
                    "kd_mutex_direct_unlock_clobber_v1", "kd_mutex_prepare"} <= imports and
                   not imports & {"kd_spin_lock_clobber_v1", "kd_mutex_outer_contended_clobber_v1",
                                  "kd_mutex_api_lock", "kd_mutex_api_unlock"},
                   "Native target or public mutex call shell differs")
        disassembly = rt.command(["objdump", "-dr", "--insn-width=16", workload], out / "workload-disassembly.txt")
        call_audit = audit_call(disassembly, args.call_mode)
        rt.write_json(out / "call-site-audit.json", call_audit)
        rt.write_json(out / "public-entry-audit.json",
                      audit_public_entries(workload, {"jit_native_call_entry": "native_call_body"}))
        rt.command(["make", "-C", source / "daemon", "CFLAGS=-O2 -Wall -Wextra -Werror"],
                   out / "build-daemon.log", timeout=120)
        binaries = dict(provider=provider, workload=workload, daemon=source / "daemon/daemon",
                        guard=guard_dir / "tc_allocator_guard.ko")
        binary_hashes = {str(path): rt.digest(path) for path in binaries.values()}
        rt.write_json(out / "binary-sha256.json", binary_hashes)
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
        spec = dict(name="session", arm="kdlock", lock_kind="mutex", delegate=True, registry_kind=2,
                    entry_abi=2, image_requirements=0, call_mode=args.call_mode, call_audit=call_audit,
                    caller_shell="mutex_public_direct", cookie_storage="provider_acquisition_ledger",
                    worker_roles=["writer"] * len(args.cpus), reader_iterations=0,
                    cpus=args.cpus, iterations=args.iterations, warmup_iterations=args.warmup_iterations,
                    phase_timeout=args.phase_timeout, kernel_identity=identity)
        session = NativeCallSession(out, spec, binaries, verify)
        session.execute()
        verify()
        idle()
        rt.write_json(out / "result.json", dict(passed=True, drained=True, phases=session.record["phases"],
            call_mode=args.call_mode, entry_abi=2, image_requirements=0,
            call_audit=call_audit, call_events=session.record["call_events"],
            native_totals=session.record["native_totals"], retired=session.record["retired"],
            kernel_identity=identity, snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]))
        print("PASS: cold JIT, reached Native CALL, cold JIT, repeated Native CALL; exact effects and full drain")
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, ImportError) as error:
        rt.write_json(out / "failure.json", dict(error=str(error), status=getattr(error, "status", "FAILED"),
                                               unsafe=getattr(error, "unsafe", False)))
        print(f"STOP: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Guest-only public mutex -> spin owner handoff or queued role swap and exact drain."""
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
RUN, SNAPSHOT = 0xC0184D01, 0x81804D02
PREPARE, RELEASE, DRAIN, WARMUP, ARM = 0x4D03, 0x4D04, 0x4D05, 0xC0184D06, 0x4D07
PREHOLDER_RELEASE = 0x4D08
REQUIRED_ELIGIBILITY = (1 << GATE) | (1 << COMBINER) | (1 << WAITER)
PROTOCOLS = ("owner-handoff", "role-swap")
CASES = ("simple", "c-native", "c-early-spin", "w-early-spin", "w-early-mutex")
FIELDS = ("a", "b", "entry", "spin_call", "active", "failures", "started", "ready",
          "done", "release_gate", "owner", "gate", "tail", "b_word", "prefix", "suffix",
          "combiner_bodies", "owner_before", "owner_after", "combiner_owner", "samples",
          "steal_attempts", "steals", "prefix_observed", "thief_done", "c_task", "w_task",
          "warm_ops", "armed", "warm_eligible", "entry_checked", "entry_eligible",
          "preholder_release", "preholder_done", "g_task", "t_task",
          "protocol", "test_case", "native_marker", "m", "m_owner", "c_native_task",
          "c_native_owner", "c_native_flags", "c_native_visits", "early_unlocked",
          "early_inner_held", "waiters")


def control(command):
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, command)


def snapshot():
    buffer = bytearray(384)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return dict(zip(FIELDS, struct.unpack("=47Qq", buffer)))


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
    for name in (MODULE, "jit_escape_test", "rwsem_probe", "rwlock_bench", "rwlock_test", "real_api",
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


def observe_outer_release(provider_root):
    """Keep the existing cold release observation when bench_quiet is enabled."""
    relative = "kernel_module/mutex/combiner.inc"
    path = provider_root / relative
    original = path.read_text()
    prefix = "kd_mutex outer release:"
    old, new = 'KD_PR_ROUTINE("' + prefix, 'pr_info("' + prefix
    rt.require(original.count(old) == 1 and new not in original,
               "outer-release trace overlay anchor differs")
    receipt = dict(path=relative, before=rt.digest(path), sites=[prefix],
                   semantics="diagnostic sink only; release ordering and ownership unchanged")
    path.write_text(original.replace(old, new, 1))
    receipt["after"] = rt.digest(path)
    return receipt


def validate_result(record, after, delta, messages):
    """Require effects and returned execution evidence, not an exchange offer alone."""
    protocol, case = record["protocol"], record["case"]
    swapped = protocol == "role-swap"
    early_waiter = case in ("w-early-spin", "w-early-mutex")
    expected_delta = dict(bench_jit_bodies=2 if swapped and not early_waiter else 1,
                          bench_jit_completions=int(swapped and case in ("simple", "c-early-spin")))
    rt.require(delta == expected_delta, "returned JIT evidence differs: " + str(delta), "DATA_ERROR")
    wanted_owner = after["w_task"] if swapped and not early_waiter else after["c_task"]
    rt.require(after["prefix"] == after["suffix"] == after["combiner_bodies"] == 1 and
               after["owner_before"] == after["c_task"] != 0 and
               after["combiner_owner"] == wanted_owner and
               after["owner_after"] == after["w_task"] != after["c_task"] and
               after["samples"] >= 2 and after["steal_attempts"] >= 10000 and
               after["steals"] == 0 and after["done"] == after["ready"] == after["started"] == 31 and
               after["prefix_observed"] == after["thief_done"] == 1,
               "owner/effect/no-gap observations differ: " + str(after), "DATA_ERROR")
    rt.require(after["protocol"] == PROTOCOLS.index(protocol) and
               after["test_case"] == CASES.index(case), "payload mode differs", "DATA_ERROR")
    early = case in ("c-early-spin", "w-early-spin", "w-early-mutex")
    rt.require(after["early_unlocked"] == after["early_inner_held"] == int(early),
               "early A release did not preserve the inner lock", "DATA_ERROR")
    pids = {row["role"]: row["pid"] for row in record["workers"]}
    layout = record["layout"]
    transfers = trace_records(messages, "kd_mutex transfer: ")
    exchanges = trace_records(messages, "kd_mutex role exchange: ")
    if swapped:
        rt.require(not transfers and len(exchanges) == 1 and
                   set(exchanges[0]) == {"outer", "executor", "owner", "queued", "head"} and
                   exchanges[0]["outer"] == f"{layout['a']:x}" and
                   exchanges[0]["executor"] == str(pids[COMBINER]) and
                   exchanges[0]["owner"] == str(pids[WAITER]) and
                   int(exchanges[0]["queued"], 16) and int(exchanges[0]["head"], 16),
                   "queued exchange offer differs: " + str(exchanges), "DATA_ERROR")
    else:
        rt.require(not exchanges and transfers == [dict(outer=f"{layout['a']:x}",
                   executor=str(pids[COMBINER]), owner=str(pids[WAITER]),
                   target=f"{layout['spin_call']:x}", pending="1")],
                   "physical owner handoff differs: " + str(transfers), "DATA_ERROR")
    native = not swapped or case == "c-native"
    native_role, executor = (COMBINER, WAITER) if swapped else (WAITER, COMBINER)
    native_ip = layout["native_marker"] if swapped else layout["spin_call"]
    begins = trace_records(messages, "kd_native begin: ")
    acks = trace_records(messages, "kd_native ack: ")
    completions = trace_records(messages, "kd_native complete: ")
    if native:
        rt.require(len(begins) == 1 and begins[0]["task"] == str(pids[native_role]) and
                   int(begins[0]["outer"], 16) == layout["a"] and
                   int(begins[0]["entry"], 16) == layout["entry"] and
                   int(begins[0]["ip"], 16) == native_ip and
                   int(begins[0]["cpu"]) == record["cpus"][executor] and
                   int(begins[0]["sp"], 16) and begins[0]["held"] == begins[0]["remaining"] == "1" and
                   begins[0]["mutex"] == "1" and begins[0]["outer_released"] == "0",
                   "native continuation identity differs: " + str(begins), "DATA_ERROR")
        rt.require(acks == [dict(task=str(pids[native_role]), lock=f"{layout['a']:x}",
                                mutex="1", last_spin="0")] and
                   completions == [dict(task=str(pids[native_role]), outer=f"{layout['a']:x}", mutex="1")],
                   "physical unlock/retirement ACK differs", "DATA_ERROR")
    else:
        rt.require(not begins and not acks and not completions,
                   "unexpected native relay in custody path", "DATA_ERROR")
    expected_native = (after["c_task"], after["w_task"], 0x95, 1) if case == "c-native" else (0, 0, 0, 0)
    rt.require(tuple(after[key] for key in ("c_native_task", "c_native_owner", "c_native_flags",
                                          "c_native_visits")) == expected_native,
               "C instruction escape task/owner/flags/effects differ", "DATA_ERROR")
    outer = trace_records(messages, "kd_mutex outer release: ")
    expected_outer = [dict(task=str(pids[COMBINER]), owner=str(pids[WAITER]),
                           owner_task=f"{after['w_task']:x}", outer=f"{layout['a']:x}",
                           next_task="0", remaining="1")] if case == "c-early-spin" else []
    rt.require(outer == expected_outer, "after-body early release differs: " + str(outer), "DATA_ERROR")
    return dict(owner_transfers=transfers, role_exchanges=exchanges, native_begin=begins,
                native_acks=acks, native_completions=completions, outer_releases=outer,
                expected_native_stats=dict(started=str(int(native)), completed=str(int(native)),
                                           unlocks=str(int(native))))


def validate_native_publication(record, after, messages, escape_delta):
    """Only C's verified instruction escape may change NORMAL to NATIVE_ONLY."""
    before = record["publication"]
    entry = before["entry"]
    rt.require(record["protocol"] == "role-swap" and record["case"] == "c-native" and
               entry["status"] == 0 and entry["entry_abi"] == 2 and
               entry["requirements"] & 1 and entry["generation"] > 0 and
               "loaded_image" not in before,
               "unexpected native-publication contract", "DATA_ERROR")
    expected = dict(before, entry=dict(entry, status=-3))
    rt.require(after == expected,
               "native-only transition changed image identity, bytes or source state", "DATA_ERROR")
    pids = {row["role"]: row["pid"] for row in record["workers"]}
    events = trace_records(messages, "reason=NATIVE_ESCAPE ")
    rt.require(escape_delta == 1 and events == [dict(entry=f"0x{entry['entry']:x}",
               rip=f"0x{record['layout']['native_marker']:x}", generation=str(entry["generation"]),
               waiter_pid=str(pids[COMBINER]), action="native_suffix_and_disable")],
               "native-only status lacks the exact C instruction escape", "DATA_ERROR")
    return events


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
                   row["b_word"] == row["m_owner"] == row["waiters"] == 0,
                   "caller/lock records have not drained: " + str(row), "UNDRAINED")
        rt.require(row["failures"] == 0, "payload observation failure: " + str(row), "DATA_ERROR")
        if self.record.get("callers_joined"):
            control(DRAIN)
        return row

    def counters(self):
        return {name: int((PARAMETERS / name).read_text())
                for name in ("bench_jit_bodies", "bench_jit_completions")}

    def native_escape_count(self):
        return int((PARAMETERS / "native_escape_count").read_text())

    def publication_after(self, escape_delta):
        if self.record["protocol"] != "role-swap" or self.record["case"] != "c-native":
            rt.require(escape_delta == 0 and not trace_records(self.messages, "reason=NATIVE_ESCAPE "),
                       "unexpected instruction escape", "DATA_ERROR")
            return self.publication()
        # kd_jit_native_escape disables this exact entry without replacing its
        # immutable image. Keep the full prior identity; only status may differ.
        before = self.record["publication"]
        rows, source = rt.registry(), rt.status()
        rt.write_json(self.path / "post-native.registry.json", rows)
        rt.require(len(rows) == 1 and set(before["images"]) == {"jit.bin", "jit.S", "bin.txt"},
                   "native-only image/registry extent differs", "DATA_ERROR")
        entry = before["entry"]
        folder = self.path / "workspace/daemon" / hex(entry["entry"]) / str(entry["tgid"]) / "asm"
        after = dict(entry=rows[0], source=source,
                     images={name: rt.digest(folder / name) for name in before["images"]})
        events = validate_native_publication(self.record, after, self.messages, escape_delta)
        self.record["escape_events"] = events
        return after

    def prepare(self):
        self.verify()
        self.run(["insmod", self.binaries["guard"]], "load-guard.log")
        self.run(["rmmod", "tc_allocator_guard"], "unload-guard.log")
        self.run(["insmod", self.binaries["provider"], "bench_quiet=1", "bench_complete_probe=1",
                  "jit_timing=0", "target_process=kmx_worker"], "load-provider.log")
        self.loaded_kd = True
        self.run(["insmod", self.workload_module,
                  f"protocol={PROTOCOLS.index(self.record['protocol'])}",
                  f"test_case={CASES.index(self.record['case'])}"], "load-payload.log")
        self.loaded_source = True
        layout = self.counts("initial")
        rt.require(layout["a"] and layout["b"] and layout["entry"] and layout["spin_call"],
                   "missing physical/control identity")
        rt.require(layout["m"] and layout["native_marker"] and
                   layout["protocol"] == PROTOCOLS.index(self.record["protocol"]) and
                   layout["test_case"] == CASES.index(self.record["case"]),
                   "payload case/control identity differs")
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
        escape_before = self.native_escape_count()
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
        # Save the joined observations even if a protocol-specific assertion
        # fails. Joined callers alone do not authorize skipping exact drain.
        escape_delta = self.native_escape_count() - escape_before
        self.record.update(after=after, jit_delta=delta, native_escape_delta=escape_delta)
        self.save()
        observations = validate_result(self.record, after, delta, self.messages)
        publication_after = self.publication_after(escape_delta)
        if self.record["case"] != "c-native":
            rt.require(publication_after == self.record["publication"], "immutable image changed", "DATA_ERROR")
        self.record.update(observations, publication_after=publication_after)
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
            rt.require(stats == [self.record["expected_native_stats"]],
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
    parser.add_argument("--protocol", choices=PROTOCOLS, default="owner-handoff",
                        help="explicit runtime expectation; role-swap requires its source candidate")
    parser.add_argument("--case", choices=CASES, default="simple",
                        help="one bounded scenario; non-simple cases require role-swap")
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
    rt.require(args.protocol == "role-swap" or args.case == "simple",
               "non-simple cases require --protocol role-swap")
    if args.protocol == "role-swap":
        rt.require("kd_mutex role exchange:" in (ROOT / "kernel_module/mutex/combiner.inc").read_text(),
                   "role-swap runtime is absent; integrate its reviewed candidate before this probe")
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
        rt.write_json(out / "outer-release-trace-overlay.json",
                      observe_outer_release(build / "provider"))
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
            warmup_rounds=args.warmup_rounds, protocol=args.protocol, case=args.case,
            kernel_identity=identity, snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]), binaries, verify)
        session.execute()
        verify()
        idle()
        rt.write_json(out / "result.json", dict(passed=True, drained=True, protocol=args.protocol,
            case=args.case, after=session.record["after"],
            jit_delta=session.record["jit_delta"], native_stats=session.record["native_stats"],
            source_retirement=session.record["retired"], kernel_identity=identity,
            snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]))
        print(f"PASS: {args.protocol}/{args.case}; failed CAS, exact owner/body/ACK evidence and drain")
        return 0
    except Exception as error:
        rt.write_json(out / "failure.json", dict(error=str(error), status=getattr(error, "status", "RUN_FAILED"),
                                               cleanup="not attempted on failure"))
        print(f"FAIL: {error}; retain workers and modules", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

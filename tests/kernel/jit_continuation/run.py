#!/usr/bin/env python3
"""Guest-only JIT continuation and repeated per-path delegation."""
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

DEVICE = "/dev/kd_jit_continuation_test"
WORKER_COMM = "kc_worker"
RUN, SNAPSHOT, PREPARE, HOT = 0xC0204501, 0x80504502, 0x4503, 0x4504
READ = 0xC0204505
COLD = 0x4506
ORIGIN_SNAPSHOT = 0x80404507
ORIGIN_COUNTERS = ("origin_instruction_count", "origin_reentry_count", "origin_suffix_count")
PARAMETERS = Path("/sys/module/kdlock_km/parameters")
FIELDS = ("prefix", "suffix", "hot_taken", "lock_address", "entry", "marker",
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
    buffer = bytearray(80)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return dict(zip(FIELDS, struct.unpack("=10Q", buffer)))


def origin_snapshot():
    buffer = bytearray(64)
    with open(DEVICE, "rb", buffering=0) as device:
        fcntl.ioctl(device, ORIGIN_SNAPSHOT, buffer, True)
    values = struct.unpack("=8Q", buffer)
    return dict(effects=list(values[:4]), instructions=list(values[4:]))


def validate_execution(delta, hot, service, instructions=1, force_suffix=False):
    """Exact returned-root versus committed-service/reentry conservation."""
    entered, completed = delta["bench_jit_bodies"], delta["bench_jit_completions"]
    native = delta["native_escape_count"]
    origin = [delta.get(name, 0) for name in ORIGIN_COUNTERS]
    rt.require(entered > 0, "phase lacks actual JIT entries", "NO_JIT")
    if not hot:
        rt.require(entered == completed and native == 0 and origin == [0, 0, 0],
                   "cold path did not return through JIT without instruction service", "DATA_ERROR")
    elif service:
        expected = [entered, 0, entered] if force_suffix else [instructions*entered, instructions*entered, 0]
        rt.require(native == 0 and completed == (0 if force_suffix else entered) and origin == expected,
                   "committed waiter instruction/reentry/suffix conservation differs", "DATA_ERROR")
    else:
        rt.require(entered == native and completed == 0 and origin == [0, 0, 0],
                   "native-only marker did not resume the original suffix", "DATA_ERROR")


def configure_worker(cpu):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(15, ctypes.c_char_p(WORKER_COMM.encode()), 0, 0, 0):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    comm = Path("/proc/self/comm").read_text().strip()
    rt.require(comm == WORKER_COMM, "worker task name differs from provider eligibility")
    os.sched_setaffinity(0, {cpu})
    rt.require(os.sched_getaffinity(0) == {cpu}, "worker affinity differs")


def worker(arguments):
    cpu, iterations, index = map(int, arguments[:3])
    barrier = Path(arguments[3])
    role = arguments[4]
    rt.require(role in ("writer", "reader"), "invalid worker role")
    configure_worker(cpu)
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
        fcntl.ioctl(device, READ if role == "reader" else RUN, buffer, True)
    returned, returned_index, reserved0, reserved1, completed, errors = struct.unpack("=4I2Q", buffer)
    print(json.dumps(dict(cpu=cpu, comm=comm, role=role, iterations=returned, worker=returned_index,
                         reserved=[reserved0, reserved1], completed=completed, errors=errors)))


def sources(root):
    hashes = {}
    for directory in ("include", "kernel_module", "daemon", "disassem", "kernel_baseline", "kernel_integration/linux70",
                      "bench/spin_cacheline", "bench/tclock_compare/allocator_guard",
                      "tests/protocols", "tests/kernel/jit_continuation"):
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
    for name in ("jit_continuation_test", "rwsem_probe", "rwlock_bench", "rwlock_test", "real_api",
                 "tc_allocator_guard", "tclock_backend_km", "tclock_mutex_backend_km",
                 "tclock_rwlock_backend_km"):
        rt.require(not Path("/sys/module", name).exists(), "existing module: " + name)
    for path in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            rt.require(path.read_text().strip() != WORKER_COMM, "existing marker worker: " + str(path))
        except FileNotFoundError:
            continue


class ContinuationSession(Session):
    def __init__(self, out, spec, binaries, verify):
        super().__init__(out, spec, workload_module=binaries["workload"])
        self.binaries, self.verify = binaries, verify
        self.daemon_binary = binaries["daemon"]
        self.translation_source = out / "source"

    def counts(self, label):
        row = snapshot()
        if self.record.get("origin_instructions"):
            row["origin"] = origin_snapshot()
        rt.write_json(self.path / (label + ".counts.json"), row)
        rt.require(row["active"] == 0 and row["idle"] == 1,
                   "workload or lock still active: " + str(row), "UNDRAINED")
        rt.require(row["failures"] == 0 and row["prefix"] == row["suffix"],
                   "exclusion/effect/continuation failure: " + str(row), "DATA_ERROR")
        return row

    def counters(self):
        names = ("bench_jit_bodies", "bench_jit_completions", "native_escape_count")
        if self.record.get("origin_capable"):
            names += ORIGIN_COUNTERS
        return {key: int((PARAMETERS / key).read_text()) for key in names}

    def registry(self, label, expected):
        rows = image_registry()
        rt.write_json(self.path / (label + ".registry.json"), rows)
        rt.require(len(rows) == 1 and rows[0]["entry"] == self.record["layout"]["entry"] and
                   rows[0]["lock_kind"] == self.record["registry_kind"] and
                   rows[0]["entry_abi"] == self.record["entry_abi"] and
                   rows[0]["status"] == expected,
                   f"unexpected registry at {label}: {rows}", "DATA_ERROR")
        return rows

    def prepare(self):
        self.verify()
        self.run(["insmod", self.binaries["guard"]], "load-allocator-guard.log")
        self.run(["rmmod", "tc_allocator_guard"], "unload-allocator-guard.log")
        self.run(["insmod", self.binaries["provider"], "bench_quiet=1",
                  "bench_complete_probe=1", "jit_timing=0",
                  f"hotlock_stats={int(self.record['hotlock_stats'])}",
                  f"target_process={WORKER_COMM}"], "load-provider.log")
        self.loaded_kd = True
        caps = bytearray(16)
        with open("/dev/kd_dev", "rb", buffering=0) as device:
            fcntl.ioctl(device, 0x80104B73, caps, True)
        version, features, stack_bytes, module_bytes = struct.unpack("=4I", caps)
        self.record["capabilities"] = dict(version=version, features=features,
                                           mutex_stack_bytes=stack_bytes, percpu_module_bytes=module_bytes)
        self.save()
        rt.require(version in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17) and features & (1 << 5),
                   "native-escape capability v6+/bit5 missing")
        self.record["origin_capable"] = version >= 13 and bool(features & (1 << 13))
        self.record["origin_service"] = (self.record["origin_capable"] and
            self.record["entry_abi"] == 2 and not self.record["mixed_spin"])
        if (self.record["origin_capable"] and self.record["entry_abi"] == 2 and
                self.record.get("mode", "continuation") == "continuation"):
            self.record["image_requirements"] |= 64
        rt.require(not self.record.get("origin_instructions") or self.record["origin_service"],
                   "four-instruction probe requires v13/bit13 sole-outer mutex service")
        if self.record["origin_capable"]:
            rt.require((PARAMETERS/"origin_instruction_force_suffix").read_text().strip() == "N",
                       "forced suffix diagnostic unexpectedly enabled at load")
        if self.record["lock_kind"] in ("spin", "rwlock"):
            rt.require(version in (12, 13, 14, 15, 16, 17) and features & (1 << 11),
                       "ordinary spin/rwlock root escape requires v12/bit11 plus bit5")
        self.run(["insmod", self.workload_module], "load-workload.log")
        self.loaded_source = True
        layout = self.counts("initial")
        rt.require(layout["prefix"] == layout["suffix"] == layout["hot_taken"] == layout["hot"] == 0,
                   "nonzero initial workload state")
        rt.require(layout["lock_address"] and layout["entry"] and layout["marker"], "missing source labels")
        if self.record.get("origin_instructions"):
            rt.require(layout["origin"]["effects"] == [0]*4 and
                       len(set(layout["origin"]["instructions"])) == 4 and
                       layout["origin"]["instructions"][0] == layout["marker"],
                       "instruction labels or initial effects differ")
        self.record.update(layout=layout, entry_range=[layout["entry"], layout["entry"] + 1],
                           caller_abi="clobber")
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
                rt.require(self.record["image_registry"][0]["requirements"] ==
                           self.record["image_requirements"] and
                           self.record["image_registry"][0]["generation"] > 0,
                           "marker image lacks the required native-exit contract")
                if self.record.get("origin_instructions"):
                    images = list((self.path/"workspace").rglob("jit.bin"))
                    rt.require(len(images) == 1, "exactly one immutable instruction image required")
                    data = images[0].read_bytes()
                    rt.require(len(data) >= 16 and data[-16:-8] == b"KDOS0001",
                               "original-task instruction footer missing")
                    offset, count = struct.unpack_from("<2I", data, len(data)-8)
                    rt.require(count == 4 and offset+count*32 == len(data)-16,
                               "exact four-site image metadata required")
                    sites = [struct.unpack_from("<QQIBBH8s", data, offset+index*32) for index in range(count)]
                    expected = dict(zip(layout["origin"]["instructions"],
                                        ((1,b"\x0f\x31"), (2,b"\x0f\x01\xf9"),
                                         (3,b"\x0f\xa2"), (2,b"\x0f\x01\xf9"))))
                    rt.require({row[0] for row in sites} == set(expected) and
                               all(next_ip == ip+length and kind == expected[ip][0] and
                                   opcode == expected[ip][1].ljust(8,b"\0") and
                                   length == len(expected[ip][1]) and reserved == 0 and code < offset
                                   for ip,next_ip,code,kind,length,reserved,opcode in sites),
                               "immutable instruction/successor metadata differs")
                    self.record["origin_sites"] = [dict(ip=row[0], next_ip=row[1], code_offset=row[2],
                        kind=row[3], length=row[4], opcode=row[6].hex()) for row in sites]
                self.record["initial_parameters"] = rt.parameters()
                rt.require(self.record["initial_parameters"]["target_process"] == WORKER_COMM,
                           "provider worker eligibility name differs")
                self.save()
                return
            time.sleep(.1)
        raise rt.Failure("TIMEOUT", "cold branch failed to publish", unsafe=True)

    def phase(self, name, iterations, hot, force_suffix=False):
        self.verify()
        before = self.counts(name + "-before")
        rt.require(before["hot"] == hot, "incorrect phase flag")
        counts_before = self.counters()
        result = dict(name=name, iterations=iterations, hot=hot, force_suffix=force_suffix, before=before,
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
                argv = [sys.executable, self.translation_source / "tests/kernel/jit_continuation/run.py",
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
                       f"worker {index} progress/context/flags failure: {worker_result}", "DATA_ERROR")
        operations = iterations * self.record["worker_roles"].count("writer")
        read_operations = self.record["reader_iterations"] * self.record["worker_roles"].count("reader")
        result.update(write_operations=operations, read_operations=read_operations)
        rt.require(after["prefix"] - before["prefix"] == operations and
                   after["suffix"] - before["suffix"] == operations and
                   after["hot_taken"] - before["hot_taken"] == hot * operations,
                   "prefix/suffix/native branch duplicated or omitted", "DATA_ERROR")
        if self.record.get("origin_instructions"):
            rt.require(before["origin"]["instructions"] == after["origin"]["instructions"] ==
                       self.record["layout"]["origin"]["instructions"] and
                       [end-start for start,end in zip(before["origin"]["effects"],after["origin"]["effects"])] ==
                       [hot*operations]*4, "instruction effects duplicated, lost or labels changed", "DATA_ERROR")
        if self.record.get("origin_capable"):
            rt.require(all(0 <= delta[key] <= operations*(4 if self.record.get("origin_instructions") else 1)
                           for key in ORIGIN_COUNTERS), "instruction counters out of bounds", "DATA_ERROR")
        rt.require(0 <= delta["bench_jit_completions"] <= delta["bench_jit_bodies"] <= operations,
                   "invalid execution counters", "DATA_ERROR")
        rt.require(0 <= delta["native_escape_count"] <= operations and
                   (hot or delta["native_escape_count"] == 0),
                   "invalid or unexpected instruction escape count", "DATA_ERROR")
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

    def measure(self):
        self.record["execution_status"] = "MEASURING"
        self.phase("cold-warmup", self.record["warmup_iterations"], 0)
        taken = []
        phases = [("cold-delegated", 0, False), ("hot-escape", 1, False),
                  ("cold-after-escape", 0, False), ("hot-repeat", 1, False)]
        if self.record.get("origin_instructions"):
            phases += [("hot-forced-post-instruction-suffix", 1, True),
                       ("cold-after-forced-suffix", 0, False)]
        for name, hot, force_suffix in phases:
            # phase() returns only after every caller joins and the source
            # frames drain. The payload also requires exclusive idle control.
            with open(DEVICE, "rb", buffering=0) as device:
                fcntl.ioctl(device, HOT if hot else COLD)
            if self.record.get("origin_capable"):
                (PARAMETERS/"origin_instruction_force_suffix").write_text(str(int(force_suffix))+"\n")
                rt.require((PARAMETERS/"origin_instruction_force_suffix").read_text().strip() ==
                           ("Y" if force_suffix else "N"), "forced suffix diagnostic readback differs")
            phase = self.phase(name, self.record["iterations"], hot, force_suffix)
            delta = phase["jit_delta"]
            validate_execution(delta, hot, self.record["origin_service"],
                               4 if self.record.get("origin_instructions") else 1, force_suffix)
            phase["execution_contract"] = ("returned_jit" if not hot else
                "post_instruction_native_suffix" if force_suffix else
                "waiter_instruction_and_same_image_reentry" if self.record["origin_service"] else
                "before_instruction_native_suffix")
            phase["execution_validated"] = True
            self.save()
            if hot and not self.record["origin_service"]:
                taken.append(phase)
            rows = self.registry(name, 0)
            rt.require(rows == self.record["image_registry"] and
                       self.publication() == self.record["publication"],
                       f"{name} changed the immutable image or registry identity", "DATA_ERROR")
        self.faults()
        pattern = re.compile(r"reason=NATIVE_ESCAPE\s+entry=(0x[0-9a-f]+)\s+rip=(0x[0-9a-f]+)\s+"
                             r"generation=(\d+)\s+waiter_pid=(\d+)\s+action=native_suffix_keep_eligible", re.I)
        events = [dict(entry=int(m[1], 16), rip=int(m[2], 16), generation=int(m[3]), waiter_pid=int(m[4]))
                  for m in pattern.finditer(self.messages)]
        self.record["escape_events"] = events
        self.save()
        pids = {row["pid"] for phase in taken
                for row in json.loads((self.path / (phase["name"] + "-callers.json")).read_text())
                if row["role"] == "writer"}
        # Logs are rate limited; counters prove a reached marker in EACH taken
        # phase. Every retained log must still name one exact eligible caller.
        if taken:
            rt.require(events and len(events) <= sum(p["jit_delta"]["native_escape_count"] for p in taken) and
                       all(event["entry"] == self.record["layout"]["entry"] and
                       event["rip"] == self.record["layout"]["marker"] and
                       event["generation"] == self.record["image_registry"][0]["generation"] and
                       event["waiter_pid"] in pids for event in events),
                       "missing or mismatched native-escape event", "DATA_ERROR")
        else:
            rt.require(not events, "service-only phases unexpectedly used a before-instruction suffix")
        self.record.update(jit_status=("COLD_JIT_WAITER_INSTRUCTION_JIT_REENTRY_REPEAT"
            if self.record["origin_service"] else "COLD_JIT_TAKEN_NATIVE_COLD_JIT_TAKEN_NATIVE"), accepted=True,
                           final_parameters=rt.parameters())
        self.verify()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--killable-worker":
        from killable_mode import worker as killable_worker
        killable_worker(sys.argv[2:], configure_worker)
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("continuation", "killable", "helper"), default="continuation")
    parser.add_argument("--cpus", type=rt.cpu_list, default=list(range(16)))
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--warmup-iterations", type=int, default=100000)
    parser.add_argument("--phase-timeout", type=int, default=120)
    parser.add_argument("--family", choices=("mutex", "spin", "rwlock", "rwsem"), default="mutex")
    parser.add_argument("--reader-count", type=int,
                        help="rwlock/rwsem: dedicate the last N selected CPUs to readers (default 1)")
    parser.add_argument("--reader-iterations", type=int, default=10000000,
                        help="shared operations per reader and phase; hot writers require a pending reader")
    parser.add_argument("--mutex-api", choices=("outer", "public"), default="outer")
    parser.add_argument("--mixed-spin", action="store_true",
                        help="mutex: hold an exact nested spin ticket across native escape")
    parser.add_argument("--origin-instructions", action="store_true",
                        help="sole-outer mutex: four original-task instructions, JIT reentry and forced suffix")
    parser.add_argument("--hotlock-stats", action="store_true",
                        help="retain final heat observations for diagnosis; admission is unchanged")
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith("/root/") and
               os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1" and os.environ.get("KDLOCK_SNAPSHOT_TAG"),
               "verified recovery guest and recorded snapshot tag required")
    rt.require(4 <= len(args.cpus) <= 60 and len(set(args.cpus)) == len(args.cpus) and
               set(args.cpus) <= os.sched_getaffinity(0), "select 4..60 distinct available worker CPUs")
    rt.require(args.mode not in ("killable", "helper") or
               (args.family == "rwsem" and not args.origin_instructions and not args.mixed_spin),
               "killable/helper modes require rwsem without instruction or mixed-spin variants")
    shared = args.family in ("rwlock", "rwsem") and args.mode not in ("killable", "helper")
    reader_count = args.reader_count if args.reader_count is not None else int(shared)
    rt.require((shared and 1 <= reader_count <= len(args.cpus) - 4) or
               (not shared and reader_count == 0),
               "rwlock/rwsem need at least one reader and four writers; other families have no readers")
    rt.require(args.family == "mutex" or args.mutex_api == "outer",
               "--mutex-api public requires --family mutex")
    rt.require(not args.mixed_spin or args.family == "mutex",
               "--mixed-spin requires --family mutex")
    rt.require(not args.origin_instructions or (args.family == "mutex" and not args.mixed_spin),
               "--origin-instructions requires a mutex without nested spin")
    rt.require(0 < args.reader_iterations <= 10000000, "reader iterations out of bounds")
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
        workload = source / "tests/kernel/jit_continuation/payload/jit_continuation_test.ko"
        rt.command(["make", "-C", workload.parent, f"KDIR={args.kernel_source}",
                    f"KDLOCK_INCLUDE={source / 'include'}",
                    f"JIT_CONTINUATION_FAMILY={args.family}",
                    f"JIT_CONTINUATION_MODE={args.mode}",
                    f"JIT_CONTINUATION_MUTEX_API={args.mutex_api}",
                    f"JIT_CONTINUATION_MIXED_SPIN={int(args.mixed_spin)}",
                    f"JIT_CONTINUATION_ORIGIN_INSTRUCTIONS={int(args.origin_instructions)}",
                    f"KBUILD_EXTRA_SYMBOLS={provider.parent / 'Module.symvers'}"], out / "build-workload.log", timeout=180)
        compiled_api = rt.command(["modinfo", "-F", "kd_mutex_api", workload],
                                  out / "mutex-api.txt").strip()
        rt.require(compiled_api == (args.mutex_api if args.family == "mutex" else "not_applicable"),
                   "compiled mutex API differs")
        compiled_family = rt.command(["modinfo", "-F", "kd_continuation_family", workload],
                                     out / "family.txt").strip()
        rt.require(compiled_family == args.family, "compiled continuation family differs")
        compiled_mode = rt.command(["modinfo", "-F", "kd_continuation_mode", workload],
                                  out / "mode.txt").strip()
        rt.require(compiled_mode == args.mode, "compiled continuation mode differs")
        compiled_origin = rt.command(["modinfo", "-F", "kd_origin_instructions", workload],
                                     out / "origin-instructions.txt").strip()
        rt.require(compiled_origin == ("4" if args.origin_instructions else "0"),
                   "compiled original-task instruction variant differs")
        imported = rt.command(["nm", "-u", workload], out / "workload-imports.txt")
        if args.mixed_spin:
            rt.require({"kd_spin_lock_clobber_v1", "kd_spin_unlock_clobber_v1"} <= set(imported.split()),
                       "mixed payload lacks ordinary nested spin controls")
        rt.command(["objdump", "-dr", workload], out / "workload-disassembly.txt")
        if args.family in ("spin", "rwlock"):
            names = set(imported.split())
            acquire = ("kd_spin_lock_pinned_clobber_v1" if args.family == "spin"
                       else "kd_rwlock_lock_pinned_clobber_v1")
            opposite = ("kd_rwlock_lock_pinned_clobber_v1" if args.family == "spin"
                        else "kd_spin_lock_pinned_clobber_v1")
            rt.require({acquire, "kd_spin_unlock_clobber_v1", "kd_spin_prepare"} <= names and
                       opposite not in names and
                       (args.family != "rwlock" or "kd_rwlock_fast_write_unlock" in names) and
                       not any(name.startswith(("kd_mutex_", "mutex", "__mutex")) for name in names),
                       "spin/rwlock marker caller imports another lock family")
        elif args.family == "rwsem" and args.mode in ("killable", "helper"):
            names = set(imported.split())
            rt.require({"kd_rwsem_down_write_killable_clobber_v1", "kd_rwsem_up_write_clobber_v1",
                        "kd_down_write_killable", "kd_rwsem_prepare"} <= names,
                       "killable payload lacks integer root or conventional nested controls")
            rt.write_json(out / "public-entry-audit.json", audit_public_entries(workload,
                {"jit_continuation_entry": "killable_body"},
                lock_symbol="kd_rwsem_down_write_killable_clobber_v1",
                unlock_symbol="kd_rwsem_up_write_clobber_v1", integer_result=True))
        elif args.family == "rwsem":
            names = set(imported.split())
            rt.require({"kd_rwsem_down_write_clobber_v1", "kd_rwsem_write_release",
                        "kd_down_read", "kd_up_read", "kd_rwsem_is_idle",
                        "kd_mutex_direct_unlock_clobber_v1", "kd_rwsem_prepare"} <= names and
                       not names & {"kd_mutex_direct_lock_clobber_v1", "kd_mutex_api_lock",
                                    "kd_mutex_api_unlock", "kd_mutex_lock_clobber_v1",
                                    "kd_mutex_unlock_clobber_v1",
                                    "kd_spin_lock_pinned_clobber_v1",
                                    "kd_rwlock_lock_pinned_clobber_v1"} and
                       not any(re.fullmatch(
                           r"(?:mutex\w*|__mutex\w*|down_(?:read|write)\w*|up_(?:read|write)|"
                           r"rwsem\w*|__rwsem\w*|osq_lock|osq_unlock)", name) for name in names),
                       "rwsem marker caller lacks the public prepared API or uses another lock shell")
            rt.write_json(out / "public-entry-audit.json",
                          audit_public_entries(workload, {"jit_continuation_entry": "continuation_body"},
                              lock_symbol="kd_rwsem_down_write_clobber_v1"))
        elif args.mutex_api == "public":
            names = set(imported.split())
            rt.require({"kd_mutex_direct_lock_clobber_v1", "kd_mutex_direct_unlock_clobber_v1"} <= names and
                       not names & {"kd_mutex_outer_contended_clobber_v1", "kd_mutex_local_unlock",
                                    "kd_mutex_api_lock", "kd_mutex_api_unlock",
                                    "kd_mutex_lock_clobber_v1", "kd_mutex_unlock_clobber_v1"} and
                       not any(re.fullmatch(r"(?:mutex\w*|__mutex\w*|atomic_dec_and_mutex_lock|osq_lock|osq_unlock)",
                                            name) for name in names),
                       "public marker caller imports another call shell")
            rt.write_json(out / "public-entry-audit.json",
                          audit_public_entries(workload, {"jit_continuation_entry": "continuation_body"}))
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
        if args.mode in ("killable", "helper"):
            shell, cookie = "rwsem_killable_clobber", "canonical_retained_request"
        elif args.family == "mutex":
            shell = "mutex_public_direct" if args.mutex_api == "public" else "mutex_outer_cookie"
            cookie = "provider_acquisition_ledger" if args.mutex_api == "public" else "outer_acquisition_local"
        elif args.family == "rwsem":
            shell, cookie = "rwsem_outer_cookie", "outer_acquisition_local"
        else:
            shell, cookie = args.family + "_direct", "provider_cpu_heat"
        spec = dict(name="session", arm="kdlock", lock_kind=args.family, delegate=True, mode=args.mode,
                    registry_kind=2 if args.family in ("mutex", "rwsem") else 1,
                    entry_abi={"mutex": 2, "spin": 1, "rwlock": 3, "rwsem": 2}[args.family],
                    image_requirements=(8064 if args.mode == "helper" else 384 if args.mode == "killable" else
                                        1 if args.family in ("mutex", "rwsem") else 33),
                    mutex_api=args.mutex_api if args.family == "mutex" else "not_applicable",
                    mixed_spin=args.mixed_spin,
                    origin_instructions=args.origin_instructions,
                    caller_shell=shell, cookie_storage=cookie, hotlock_stats=args.hotlock_stats,
                    worker_roles=["writer"] * (len(args.cpus) - reader_count) + ["reader"] * reader_count,
                    reader_iterations=args.reader_iterations,
                    cpus=args.cpus, iterations=args.iterations, warmup_iterations=args.warmup_iterations,
                    phase_timeout=args.phase_timeout, kernel_identity=identity)
        selected_session = ContinuationSession
        if args.mode == "killable":
            from killable_mode import session_class
            selected_session = session_class(ContinuationSession)
        elif args.mode == "helper":
            from helper_mode import session_class
            selected_session = session_class(ContinuationSession)
        session = selected_session(out, spec, binaries, verify)
        session.execute()
        verify()
        idle()
        rt.write_json(out / "result.json", dict(passed=True, drained=True, phases=session.record["phases"],
            family=args.family, mode=args.mode, entry_abi=session.record["entry_abi"],
            image_requirements=session.record["image_requirements"],
            worker_roles=session.record["worker_roles"],
            mixed_spin=session.record["mixed_spin"],
            origin_instructions=session.record["origin_instructions"],
            origin_service=session.record["origin_service"],
            capabilities=session.record["capabilities"],
            mutex_api=session.record["mutex_api"], caller_shell=session.record["caller_shell"],
            cookie_storage=session.record["cookie_storage"],
            escape_events=session.record["escape_events"], kernel_identity=identity,
            snapshot_tag=os.environ["KDLOCK_SNAPSHOT_TAG"]))
        if args.mode == "killable":
            print("PASS: actual other-task killable roots, queued/draining cancellation and nested parent effects")
            return 0
        if args.mode == "helper":
            print("PASS: identity and mapped original-task primitives return to the same executor/image without replay")
            return 0
        print("PASS: cold paths and reached original-task instructions retain exact effects and tested flags; "
              + ("same-image JIT reentry verified; " if session.record["origin_service"] else "native suffix verified; ")
              + "image remains eligible; final drain")
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, ImportError) as error:
        rt.write_json(out / "failure.json", dict(error=str(error), status=getattr(error, "status", "FAILED"),
                                               unsafe=getattr(error, "unsafe", False)))
        print(f"STOP: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

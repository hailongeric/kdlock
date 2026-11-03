#!/usr/bin/env python3
"""Shared benchmark validation, placement, evidence and guest lifecycle helpers.

These checks serve the current direct runner and offline evidence readers.
No workload starts on import; failure/timeout never implies caller drain.
"""
import argparse
import ctypes
import fcntl
import hashlib
import itertools
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from summarize import write_json

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench/spin_cacheline"
WORKLOAD = ROOT / "workload_modules/spin_cacheline"
sys.path.insert(0, str(ROOT / "tests/protocols"))
sys.path.insert(0, str(ROOT / "disassem"))
from native_only_protocol import entries
from cpu_placement import capture_topology
from device_session import info, RETIRE

FAULT = re.compile(r"BUG:|\bWARNING:|kernel panic|double fault|soft lockup|"
                   r"hard LOCKUP|unable to handle|general protection fault|"
                   r"Oops:|\[ERROR\]|\[KD_JIT\]\[ERROR\]|invariant_failures=[1-9]", re.I)
PROVIDER = HERE / ".build/provider/kernel_module/kdlock_km.ko"
BINARIES = (str(PROVIDER.relative_to(ROOT)), str((WORKLOAD / "spin_cacheline.ko").relative_to(ROOT)),
            "bench/spin_cacheline/client", "daemon/daemon")


class Failure(RuntimeError):
    def __init__(self, status, message, unsafe=False):
        super().__init__(message)
        self.status, self.unsafe = status, unsafe


def require(ok, message, status="PREPARATION_FAILED"):
    if not ok:
        raise Failure(status, message)


def image_capacity():
    """Use the same bounded image capacity as the compiled daemon/provider."""
    header = (ROOT / "include/exe_info.h").read_text(encoding="ascii")
    match = re.search(
        r"(?m)^#define KD_CODE_BLOCK_SIZE \(([0-9]+)UL \* ([0-9]+)\)$", header)
    require(match is not None, "unrecognized shared image capacity", "DATA_ERROR")
    capacity = int(match[1]) * int(match[2])
    require(capacity > 0, "invalid shared image capacity", "DATA_ERROR")
    return capacity


def cpu_list(text):
    result = []
    for piece in text.split(","):
        match = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", piece)
        if not match:
            raise argparse.ArgumentTypeError("use CPUs such as 0-23 or 0,2,4,6")
        start, end = int(match[1]), int(match[2] or match[1])
        if not 0 <= start <= end < 1024:
            raise argparse.ArgumentTypeError("invalid CPU range")
        result.extend(range(start, end + 1))
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("duplicate CPU")
    return result


def make_plan(lines, threads, iterations, repeats, cpus):
    """Keep each native/kdlock pair adjacent, alternating order between pairs."""
    require(repeats > 0 and repeats % 2 == 0, "--repeats must be a positive even number")
    require(0 < iterations <= 100000000, "--iterations must be in 1..100000000")
    require(0 < max(threads) <= len(cpus), "not enough distinct CPUs for the threads")
    result = []
    for n, t in itertools.product(dict.fromkeys(lines), dict.fromkeys(threads)):
        for repeat in range(repeats):
            order = ("native", "kdlock") if repeat % 2 == 0 else ("kdlock", "native")
            for arm in order:
                result.append(dict(name=f"c{n:02d}-t{t:02d}-r{repeat:02d}-{arm}",
                                   cachelines=n, threads=t, iterations=iterations,
                                   repeat=repeat, arm=arm, cpus=cpus[:t]))
    return result


def annotate_topology(plan, topology):
    # The 24-worker point exceeds one node in the current guest. Retain the
    # real per-worker placement instead of treating every point as single-node.
    nodes = dict(zip(topology["role_cpus"], topology["role_nodes"]))
    for spec in plan:
        spec["cpu_nodes"] = [nodes[cpu] for cpu in spec["cpus"]]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, path, *, timeout=30, cwd=ROOT, env=None):
    """Timeout leaves the process/session intact for diagnosis; never unload then.

    A process stuck in a kernel ioctl cannot be assumed drained after a signal.
    Every caller records the PID/command so recovery can inspect it explicitly.
    """
    with path.open("w") as log:
        p = subprocess.Popen(list(map(str, args)), cwd=cwd, env=env, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
        write_json(path.with_suffix(path.suffix + ".command.json"),
                   dict(argv=list(map(str, args)), cwd=str(cwd), pid=p.pid,
                        timeout_seconds=timeout, started_ns=time.monotonic_ns()))
        try:
            result = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise Failure("TIMEOUT", f"PID {p.pid} timed out: {args}; no cleanup attempted",
                          unsafe=True) from error
    require(result == 0, f"command exited {result}: {args}; see {path}")
    return path.read_text()


def source_state():
    """Freeze implementation fragments as inputs, alongside their parent files."""
    sources = {}
    # Freeze both the unmodified production inputs and the exact prepared
    # provider sources. Do not accidentally hash editor files or Kbuild output.
    for directory in ("bench/spin_cacheline", "workload_modules/spin_cacheline",
                      "workload_modules/mutex_cacheline",
                      "include", "kernel_module", "daemon",
                      "disassem", "kernel_baseline", "kernel_integration/linux70",
                      "kernel_integration/real_api",
                      "kernel_baseline/experiments/spin_static",
                      "kernel_baseline/experiments/spin_clobber",
                      "bench/spin_cacheline/.build/provider"):
        for path in (ROOT / directory).rglob("*"):
            if (path.is_file() and "__pycache__" not in path.parts and
                not any(part.startswith((".", "0x"))
                        for part in path.relative_to(ROOT / directory).parts) and
                (path.suffix in (".c", ".inc", ".h", ".py", ".S", ".md", ".patch", ".def", ".json") or
                 path.name in ("Makefile", "requirements.txt", "guest.config")) and
                not path.name.endswith(".mod.c")):
                sources[str(path.relative_to(ROOT))] = digest(path)
    for name in ("tests/protocols/native_only_protocol.py", "tests/protocols/cpu_placement.py"):
        sources[name] = digest(ROOT / name)
    return sources


def idle():
    """Reject known workload/module leftovers; this is not a global hook drain."""
    for name in ("kdlock_km", "spin_cacheline", "mutex_cacheline", "klock_module", "kd_depth_source",
                 "kd_dispatch_floor"):
        require(not Path(f"/sys/module/{name}").exists(), f"existing module: {name}")
    for task in Path("/proc").glob("[0-9]*/task/[0-9]*/comm"):
        try:
            comm = task.read_text().strip()
        except FileNotFoundError:
            continue
        require(comm not in ("sc_worker", "klock_test", "kd_test", "daemon"),
                f"existing task: {task}: {comm}")


def status():
    """Read the source-session ledger without creating a translation writer."""
    fd = os.open("/dev/kd_dev", os.O_RDONLY | os.O_CLOEXEC)
    try:
        return info(fd)
    finally:
        os.close(fd)


def parameters():
    return {p.name: p.read_text().strip()
            for p in Path("/sys/module/kdlock_km/parameters").iterdir()}


def registry():
    require(ctypes.sizeof(__import__("native_only_protocol").Entry) == 64,
            "unexpected registry ABI")
    return [dict(entry=e.rip, code=e.code, status=e.status, pid=e.pid,
                 tgid=e.tgid, lock_kind=e.lock_kind, entry_abi=e.entry_abi,
                 requirements=e.requirements, generation=e.generation) for e in entries()]


def children(pid):
    path = Path(f"/proc/{pid}/task/{pid}/children")
    return path.read_text().split() if path.exists() else []


def validate_measurement(m, spec, iterations):
    """Recompute client aggregation and check every active/inactive data line."""
    if spec.get('duration_ms', 0):
        return validate_timed_measurement(m, spec)
    require(m["schema"] == 1 and m["complete"] is True and m["data_ok"] is True,
            "client reported an incomplete/incorrect workload", "DATA_ERROR")
    n, t = spec["cachelines"], spec["threads"]
    require((m["cachelines"], m["threads"], m["iterations"]) == (n, t, iterations),
            "client workload differs", "DATA_ERROR")
    ws = m["workers"]
    require(len(ws) == t and [w["cpu"] for w in ws] == spec["cpus"] and
            all(w["observed_cpu"] == w["cpu"] and w["error"] == 0 and
                w["completed"] == iterations and w["cpu_ns"] > 0 for w in ws),
            "worker affinity/completion differs", "DATA_ERROR")
    require(m["completed"] == sum(w["completed"] for w in ws) == t * iterations and
            m["worker_cpu_ns"] == sum(w["cpu_ns"] for w in ws) and
            m["finished_ns"] == max(w["finished_ns"] for w in ws) and
            m["wall_ns"] == m["finished_ns"] - m["started_ns"] > 0,
            "incorrect client aggregation", "DATA_ERROR")
    validate_payload(m, spec)


def validate_payload(m, spec):
    """Both measurement modes require the same exact business-data oracle."""
    n = spec["cachelines"]
    require(len(m["before"]) == len(m["after"]) == 16,
            "invalid snapshot shape", "DATA_ERROR")
    workload = spec.get('workload', 'cacheline')
    require(workload in ('cacheline', 'rcuht'), 'unsupported workload', 'DATA_ERROR')
    require(m.get('workload', 'cacheline') == workload, 'workload differs', 'DATA_ERROR')
    if workload == 'rcuht':
        before, after = m['before'], m['after']
        require(n == 0 and m.get('hash_integrity_ok') is True and
                all(a >= b for a, b in zip(after, before)) and
                after[0] - before[0] == m['completed'] and
                before[0] == sum(before[1:4]) and after[0] == sum(after[1:4]) and
                not any(before[4:] + after[4:]),
                'hash outcome/integrity mismatch', 'DATA_ERROR')
    else:
        require(all(after - before == (m["completed"] if i < n else 0)
                    for i, (before, after) in enumerate(zip(m["before"], m["after"]))),
                "payload counter delta mismatch", "DATA_ERROR")


def validate_timed_measurement(m, spec):
    """Keep final data exact while deriving peak only from sampled progress."""
    from peak import analyze_peak

    require(m['schema'] == 2 and m['measurement_mode'] == 'duration' and
            m['complete'] is True and m['data_ok'] is True,
            'client reported an incomplete/incorrect timed workload', 'DATA_ERROR')
    require(spec.get('workload', 'cacheline') == m['workload'] and
            m['workload'] in ('cacheline', 'rcuht') and
            spec.get('scenario', 'plain') == 'plain' and
            (m['cachelines'], m['threads'], m['iterations']) ==
            (spec['cachelines'], spec['threads'], 0),
            'timed client workload differs', 'DATA_ERROR')
    ws = m['workers']
    require(len(ws) == spec['threads'] and [w['cpu'] for w in ws] == spec['cpus'] and
            all(w['observed_cpu'] == w['cpu'] and w['error'] == 0 and
                type(w['completed']) is int and w['completed'] > 0 and
                w['cpu_ns'] > 0 for w in ws),
            'timed worker affinity/completion differs', 'DATA_ERROR')
    require(m['completed'] == sum(w['completed'] for w in ws) and
            m['worker_cpu_ns'] == sum(w['cpu_ns'] for w in ws) and
            m['finished_ns'] == max(w['finished_ns'] for w in ws) and
            m['wall_ns'] == m['finished_ns'] - m['started_ns'] > 0,
            'incorrect timed client aggregation', 'DATA_ERROR')
    validate_payload(m, spec)
    try:
        return analyze_peak(m, spec)
    except (ValueError, KeyError, TypeError) as error:
        raise Failure('DATA_ERROR', str(error)) from error


def classify_bodies(before, after, completed):
    require(0 <= before <= after and 0 <= after - before <= completed,
            "invalid measured JIT body delta", "DATA_ERROR")
    count = after - before
    return dict(jit_bodies=count, jit_share=count / completed,
                jit_status="JIT" if count else "NO_JIT")

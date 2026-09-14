"""Opt-in, same-guest native-with-hooks/JIT measurements of ordinary mode 2/5.

This reuses the workload and evidence runner, not the JIT-dependent SELFTEST
roles. Two arms cannot supply the missing native-delegation comparator. The
internal arm commands require the recovery guest just like the public runner.
"""

import argparse
import hashlib
import itertools
import json
import math
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import regression
from regression_evidence import write_json
from verify_evidence import require, unique_object, verify_run

ROOT = regression.ROOT
PREFIX = "KD_BENCH_METRICS "
TRANSLATION_PREFIX = "KD_TRANSLATION_METRICS "
PREPARATION = {"warmup": (1, 1, 1, 1), "promotion": (1, 12000, 10, 1)}
BODY = re.compile(r"JIT body witness: entry=([0-9a-f]+) lock=([0-9a-f]+) body=1\b")
BINARIES = (
    "kernel_module/kdlock_km.ko",
    "klock_module/klock_module.ko",
    "daemon/daemon",
    "bench/klock_test",
)


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def unsigned(value):
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError("expected an unsigned decimal integer")
    return int(value)


def cpu_list(value):
    """Canonicalize explicit CPU sets without silently dropping duplicates."""
    cpus = []
    for part in value.split(","):
        match = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", part)
        if not match:
            raise argparse.ArgumentTypeError("invalid CPU list")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 0 <= first <= last < 4096:
            raise argparse.ArgumentTypeError("invalid CPU range")
        cpus.extend(range(first, last + 1))
    if len(cpus) != len(set(cpus)):
        raise argparse.ArgumentTypeError("duplicate CPU")
    return sorted(cpus)


def validate_trial(trial):
    require(set(trial) == {"mode", "threads", "loops", "workload", "runs", "cpus"},
            "invalid trial fields")
    require(all(type(trial[k]) is int for k in trial if k != "cpus"),
            "noninteger workload parameter")
    require(trial["mode"] in (2, 5), "only ordinary service modes are comparable")
    require(2 <= trial["threads"] <= 4096 and trial["loops"] > 0 and trial["runs"] > 0,
            "positive loops/runs and at least two contending threads required")
    require(0 <= trial["workload"] < 2**64, "workload exceeds the ioctl ABI")
    require(trial["threads"] * trial["runs"] <= 2**20, "measurement sample limit")
    require(12001 + trial["threads"] * trial["runs"] * trial["loops"] <= 10000000,
            "work exceeds the existing full-state oracle limit")
    cpus = trial["cpus"]
    require(isinstance(cpus, list) and cpus and
            all(type(cpu) is int and 0 <= cpu < 4096 for cpu in cpus) and
            cpus == sorted(set(cpus)), "invalid canonical CPU set")
    return trial


def guest_only():
    require(ROOT == Path("/root/host_fs/kdlock") and os.geteuid() == 0,
            "execution requires root in the documented guest checkout")
    require(os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1",
            "confirm the recovery snapshot before live execution")


def metrics(text, parameters, mode):
    """Reject partial samples before exposing any paired performance result."""
    lines = [line[len(PREFIX):] for line in text.splitlines() if line.startswith(PREFIX)]
    require(len(lines) == 1, "missing/duplicate benchmark record")
    value = json.loads(lines[0], object_pairs_hook=unique_object)
    threads, loops, work, runs = parameters
    expected = {"schema": 1, "complete": True, "threads": threads, "mode": mode,
                "role_base": 0, "loops_per_ioctl": loops, "workload": work,
                "ioctls_per_thread": runs, "requested_ioctls": threads * runs,
                "completed_ioctls": threads * runs}
    require(all(type(value.get(k)) is type(v) and value[k] == v
                for k, v in expected.items()), "benchmark parameters/counts differ")
    require(value["workers"] == [dict(id=i, completed=runs, error=0)
                                 for i in range(threads)], "incomplete worker records")
    require(all(type(field) is int for worker in value["workers"]
                for field in worker.values()), "invalid worker field types")
    for key in ("wall_ns", "worker_cpu_ns", "ioctl_p50_ns", "ioctl_p99_ns"):
        require(type(value[key]) is int and value[key] > 0, f"invalid {key}")
    require(value["ioctl_p50_ns"] <= value["ioctl_p99_ns"] <= value["wall_ns"],
            "invalid latency ordering")
    rate = value["ioctls_per_second"]
    require(type(rate) in (int, float) and math.isfinite(rate) and
            math.isclose(rate, threads * runs * 1e9 / value["wall_ns"],
                         rel_tol=1e-6, abs_tol=1e-6), "invalid throughput")
    return value


def parameters(trial, phase):
    return PREPARATION[phase] if phase in PREPARATION else tuple(
        trial[k] for k in ("threads", "loops", "workload", "runs"))


def hashes(paths):
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def console_state():
    """Keep serial filtering visible; never tune global printk for a fast arm."""
    return {"printk": Path("/proc/sys/kernel/printk").read_text().strip(),
            "ignore_loglevel": Path("/sys/module/printk/parameters/ignore_loglevel")
            .read_text().strip(), "consoles": Path("/proc/consoles").read_text()}


def initialize(out):
    """Capture the actual loaded experiment selection before any CS executes."""
    trial = validate_trial(json.loads(os.environ["KD_BENCH_TRIAL"]))
    arm = os.environ["KD_BENCH_ARM"]
    require(arm in ("native", "jit"), "invalid arm")
    params = {module: {p.name: p.read_text().strip() for p in sorted(
        Path(f"/sys/module/{module}/parameters").iterdir())}
        for module in ("kdlock_km", "klock_module")}
    require(params["kdlock_km"]["target_process"] ==
            ("klock_test" if arm == "jit" else "kd_unused"), "wrong selector")
    require(params["kdlock_km"]["mutex_jit"] == "1", "mutex_jit must remain enabled")
    # The immutable module setting, not a requested environment value, defines
    # which accounting contract every invocation in this session must satisfy.
    timing = os.environ.get("KD_BENCH_JIT_TIMING", "0")
    require(timing in ("0", "1") and params["kdlock_km"].get("jit_timing") ==
            ("Y" if timing == "1" else "N"), "JIT timing selection was not applied")
    require(params["klock_module"]["mode5_call_quota"] == "N", "ordinary service only")
    symbol = "global_lock" if trial["mode"] == 2 else "global_mutex"
    locks = [parts[0] for line in Path("/proc/kallsyms").read_text().splitlines()
             if len(parts := line.split()) == 4 and
             parts[2:] == [symbol, "[klock_module]"]]
    require(len(locks) == 1 and int(locks[0], 16), "ambiguous/hidden physical lock")
    require(set(trial["cpus"]) <= os.sched_getaffinity(0), "CPUs outside allowed set")
    write_json(out / "initial.json", {
        "schema": 1, "arm": arm, "trial": trial, "parameters": params,
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "release": os.uname().release, "lock": int(locks[0], 16),
        "binaries": hashes(ROOT / path for path in BINARIES),
        "console": console_state(),
        "started_ns": time.monotonic_ns(),
    })


def run_phase(out, phase):
    """Pin the launcher; unmodified pthread workers inherit this allowed set.

    This observes an affinity mask, not each worker's residency or an exclusive
    CPU reservation. Keep controller/launch time separate from the C envelope.
    """
    initial = read_json(out / "initial.json")
    trial = initial["trial"]
    values = parameters(trial, phase)
    os.sched_setaffinity(0, trial["cpus"])
    observed = sorted(os.sched_getaffinity(0))
    require(observed == trial["cpus"], "requested affinity was not applied")
    command = [str(ROOT / "bench/klock_test"), *map(str, values), str(trial["mode"])]
    record = {"command": command, "requested_cpus": trial["cpus"],
              "inherited_cpus": observed, "console_before": console_state(),
              "started_ns": time.monotonic_ns()}
    write_json(out / f"{phase}.json", record)
    require(record["console_before"] == initial["console"], "console changed before phase")
    env = regression.child_environment()
    env.update(KD_TEST_METRICS="1", KD_TEST_COMM="klock_test")
    with (out / f"{phase}.log").open("w") as log:
        result = subprocess.run(["timeout", "--kill-after=5s", "120s", *command],
                                env=env, stdout=log, stderr=subprocess.STDOUT)
    record.update(exit=result.returncode, finished_ns=time.monotonic_ns())
    record["console_after"] = console_state()
    write_json(out / f"{phase}.json", record)
    require(record["console_after"] == initial["console"], "console changed during phase")
    require(result.returncode == 0, f"{phase} failed: {result.returncode}")
    record["metrics"] = metrics((out / f"{phase}.log").read_text(), values, trial["mode"])
    write_json(out / f"{phase}.json", record)


def publication(out, phase):
    """Use the existing registry observer, after translators/workers drain.

    Stable before/after images constrain this experiment only. They do not add
    immutable JIT generations or certify arbitrary concurrent recompilation.
    """
    from mutex_signal_protocol import wait_ready
    from native_only_protocol import entries

    initial = read_json(out / "initial.json")
    state = json.loads(subprocess.check_output(
        [sys.executable, str(ROOT / "disassem/device_session.py"), "status"],
        text=True, timeout=10))
    require(state["state"] == 0 and state["frames"] == state["writers"] == 0,
            "source session has active frames/writers or is retired")
    artifacts = sorted((ROOT / "daemon").glob("0x*/*/asm"))
    if initial["arm"] == "jit":
        require(len(artifacts) == 1 and len(entries()) == 1, "expected one ordinary entry")
        ready = wait_ready(artifacts[0], lock_kind=1 if initial["trial"]["mode"] == 2 else 2)
        images = hashes(artifacts[0] / name for name in ("jit.S", "jit.bin", "bin.txt"))
    else:
        require(not artifacts and not entries(), "native reference has JIT entries/images")
        ready, images = None, {}
    write_json(out / f"published-{phase}.json", {
        "entry": ready, "images": images, "source": state,
        "console": console_state(),
        "observed_ns": time.monotonic_ns(),
    })


def stats(text, tag, separator=": "):
    rows = re.findall(re.escape(tag + separator) + r"([^\n]+)", text)
    require(len(rows) == 1, f"missing/duplicate {tag}")
    return {key: int(value) for key, value in re.findall(r"(\w+)=([0-9]+)", rows[0])}


def validate_body_phase(before, after, publication_before, publication_after, lock, arm):
    """A prior phase's body or a replaced image cannot certify this payload."""
    require(after.startswith(before), "kernel snapshot lost or replaced its prefix")
    first, last = publication_before["entry"], publication_after["entry"]
    require(publication_before["images"] == publication_after["images"],
            "generated images changed during measurement")
    body = BODY.findall(after[len(before):])
    if arm == "native":
        require(first is None and last is None and not BODY.search(after),
                "native reference executed JIT")
        require("install JIT chunk:" not in after, "native reference installed JIT")
    else:
        require(first is not None and last is not None and first["status"] == 0,
                "JIT entry was not NORMAL")
        require({k: v for k, v in first.items() if k != "observed_ns"} ==
                {k: v for k, v in last.items() if k != "observed_ns"},
                "JIT registration changed during measurement")
        require(body and all(int(entry, 16) == int(first["entry"], 16) and
                             int(address, 16) == lock for entry, address in body),
                "measured JIT lacks matching returned bodies")
        require("install JIT chunk:" not in after[len(before):],
                "JIT recompiled during measurement")
    return len(body)


def preparation_costs(initial, phases, publications, text, body_count, finished):
    """Join real child accounting to the prepared entry, not readiness latency.

    Compilation may overlap promotion; its duration must not be added to the
    preparation envelope. wait4 RSS is a per-process high-water maximum, not
    concurrent tree memory. The payload still includes queue/services/oracles.
    """
    start = initial["started_ns"]
    console = initial["console"]
    require(all(type(value) is int and value >= 0 for value in (start, finished)),
            "invalid arm clock")
    previous = start
    process_times = {}
    for name in (*PREPARATION, "measure"):
        phase = phases[name]
        left, right = phase["started_ns"], phase["finished_ns"]
        require(type(left) is int and type(right) is int and
                previous <= left < right <= finished, "phase clocks overlap or regress")
        require(phase["console_before"] == phase["console_after"] == console,
                "console changed across phases")
        process_times[name] = right - left
        require(0 < phase["metrics"]["wall_ns"] <= right - left,
                "worker envelope exceeds process observation")
        previous = right
    before, after = publications
    require(before["console"] == after["console"] == console, "publication console changed")
    require(all(type(p["observed_ns"]) is int for p in publications) and
            phases["promotion"]["finished_ns"] <= before["observed_ns"] <=
            phases["measure"]["started_ns"] < phases["measure"]["finished_ns"] <=
            after["observed_ns"] <= finished, "publication outside measured boundary")

    records = [json.loads(line[len(TRANSLATION_PREFIX):], object_pairs_hook=unique_object)
               for line in text.splitlines() if line.startswith(TRANSLATION_PREFIX)]
    require(len(records) <= 1000, "too many translation attempts")
    require(bool(records) == (initial["arm"] == "jit"), "missing/unexpected translator metrics")
    counters = ("wall_ns", "user_ns", "system_ns", "maxrss_kib", "minor_faults",
                "major_faults", "voluntary_cs", "involuntary_cs")
    previous = start
    for record in records:
        integer_fields = ("schema", "pid", "tgid", "lock_kind", "child", "started_ns",
                          "finished_ns", "status", "result", *counters)
        require(set(record) == set(integer_fields) | {"entry"} and
                all(type(record[k]) is int and record[k] >= 0 for k in integer_fields),
                "invalid translator fields")
        require(record["schema"] == 1 and record["status"] == record["result"] == 0,
                "translator failed/refused during the ordinary comparison")
        entry = before["entry"]
        require(record["pid"] == entry["pid"] and record["tgid"] == entry["tgid"] and
                type(record["entry"]) is str and
                re.fullmatch(r"0x[0-9a-f]+", record["entry"]) and
                int(record["entry"], 16) == int(entry["entry"], 16) and
                record["lock_kind"] == (1 if initial["trial"]["mode"] == 2 else 2),
                "translation belongs to a different published entry")
        require(record["child"] > 0 and record["maxrss_kib"] > 0 and
                previous <= record["started_ns"] < record["finished_ns"] <=
                before["observed_ns"] and record["wall_ns"] ==
                record["finished_ns"] - record["started_ns"], "invalid translation interval")
        previous = record["finished_ns"]
    measured_cs = math.prod(initial["trial"][k] for k in ("threads", "loops", "runs"))
    require(0 <= body_count <= measured_cs, "JIT bodies exceed measured critical sections")
    translated = {key: sum(record[key] for record in records)
                  for key in counters if key != "maxrss_kib"}
    translated.update(attempts=len(records), records=records,
                      maxrss_kib=max((r["maxrss_kib"] for r in records), default=None))
    return {"schema": 1, "preparation_elapsed_ns": before["observed_ns"] - start,
            "phase_process_ns": process_times, "translation": translated,
            "measured_cs": measured_cs, "measured_jit_share": body_count / measured_cs,
            "measure_process_outside_workers_ns": process_times["measure"] -
            phases["measure"]["metrics"]["wall_ns"]}


def jit_boundary_costs(initial, text, bodies):
    """Validate unload totals against ordinary mode 2/5's actual exit protocol.

    Timings cover the whole loaded session, including preparation. Dispatch is
    inclusive; subtraction is valid here only because these CSs have no nested
    JIT/control recursion. Neither aggregate elapsed intervals nor their means
    are CPU time, pure instructions or complete native-suffix cost. Queue rows
    stop at physical acquisition/first executed dispatch, exclude body time and
    overlap other requests, so they are not subtracted from dispatch totals.
    """
    enabled = initial["parameters"]["kdlock_km"].get("jit_timing", "N")
    require(enabled in ("Y", "N"), "invalid loaded JIT timing setting")
    rows = re.findall(r"kd_jit timing: ([^\n]*)", text)
    if enabled == "N":
        require(not rows, "disabled session unexpectedly reported JIT timings")
        return None
    require(initial["trial"]["mode"] in (2, 5) and initial["arm"] in ("native", "jit"),
            "boundary subtraction requires an ordinary service comparison")
    require(type(bodies) is int and 0 <= bodies <= 10000000, "invalid body count")
    require(initial["arm"] != "native" or bodies == 0, "native timing has JIT bodies")
    # Every admitted ordinary queue request either becomes the native owner or
    # executes JIT. Join the new counters to existing independent slowpath stats;
    # don't accept a nonzero timer alone as evidence of complete accounting.
    queued = 0
    if initial["arm"] == "jit":
        if initial["trial"]["mode"] == 2:
            queue = stats(text, f"kd_spin lock stats: lock={initial['lock']:x}", " ")
            require(queue.get("waiters") == 0, "spin queue did not drain")
        else:
            queue = stats(text, "kd_mutex stats")
        queued = queue.get("slowpath")
        operations = 12001 + math.prod(initial["trial"][k] for k in ("threads", "loops", "runs"))
        require(type(queued) is int and bodies <= queued <= operations,
                "invalid ordinary queue/slowpath count")
    # Ordinary services return to JIT, not native-owner waits. Native references
    # bypass both kdlock queues. Old archived reports remain readable, but new
    # enabled captures must contain all ten rows and match the right backend.
    # Handoff contains owner wait; both are zero for these returning services.
    expected = dict(
        dispatch=bodies,
        wrapper=3 * bodies,
        hostcall=2 * bodies,
        control=bodies,
        native_spin_wait=0,
        native_mutex_wait=0,
        spin_queue=queued if initial["trial"]["mode"] == 2 else 0,
        mutex_queue=queued if initial["trial"]["mode"] == 5 else 0,
        native_spin_handoff=0,
        native_mutex_handoff=0,
    )
    require(len(rows) == len(expected), "missing/duplicate JIT timing rows")
    phases = {}
    for row in rows:
        match = re.fullmatch(r"phase=(\w+) samples=([0-9]+) ns=([0-9]+) invalid=0", row)
        require(match is not None, "malformed/invalid JIT timing row")
        name, samples, ns = match[1], int(match[2]), int(match[3])
        require(name in expected and name not in phases, "unknown/duplicate JIT phase")
        require(samples == expected[name] and ns <= 2**63 - 1,
                "timing counts disagree with wrapper/service/control returns or queue stats")
        require(samples > 0 or ns == 0, "empty timing phase has elapsed time")
        phases[name] = dict(samples=samples, ns=ns, mean_ns=ns / samples if samples else None)
    inner = sum(phases[name]["ns"] for name in ("wrapper", "hostcall", "control"))
    require(phases["dispatch"]["ns"] >= inner, "non-nested boundaries exceed dispatch")
    return {"schema": 1, "scope": "loaded session including preparation; ordinary mode 2/5",
            "phases": phases, "dispatch_residual_ns": phases["dispatch"]["ns"] - inner}


def finish_arm(out):
    """Join measurements to the existing kernel's full replay/service oracle."""
    initial = read_json(out / "initial.json")
    trial, arm = initial["trial"], initial["arm"]
    phases = {name: read_json(out / f"{name}.json")
              for name in (*PREPARATION, "measure")}
    for name, record in phases.items():
        require(record["exit"] == 0 and record["inherited_cpus"] == trial["cpus"],
                "failed phase or differing affinity")
        require(record["metrics"] == metrics((out / f"{name}.log").read_text(),
                parameters(trial, name), trial["mode"]), "phase metrics disagree")
    before, after, final = ((out / name).read_text()
                            for name in ("before.dmesg", "after.dmesg", "final.log"))
    require(final.startswith(after) and not regression.FAULTS.search(final),
            "kernel fault or incomplete final log")
    publications = [read_json(out / f"published-{name}.json") for name in ("before", "after")]
    body_count = validate_body_phase(before, after, *publications, initial["lock"], arm)
    operations = 12001 + trial["threads"] * trial["loops"] * trial["runs"]
    integrity = stats(final, "kd_cs integrity")
    require(integrity == dict(operations=operations, active_states=1, failures=0),
            "full complex-state oracle failed")
    require(re.findall(r"module unloaded, final counter: ([0-9]+)", final) ==
            [str(operations)], "completed operation count differs")
    require(re.findall(fr"mode{trial['mode']} api observations: ([0-9]+)", final) ==
            [str(operations)], "clock results were not consumed exactly once")
    if trial["mode"] == 5:
        require(re.findall(r"mode5 api calls: ([0-9]+)", final) == [str(operations)],
                "ordinary mode 5 clock CALL count differs")
    scalar = stats(final, "kd_scalar service: mode=" + str(trial["mode"]), " ")
    require(scalar == dict(calls=operations, failures=0), "scalar result oracle failed")
    hostcalls = stats(final, "kd_hostcall stats")
    all_bodies = len(BODY.findall(final))
    require(hostcalls == dict(exits=all_bodies * 2, executed=all_bodies * 2,
                             resumed=all_bodies * 2, rejected=0, failed=0, limit=0),
            "two services did not return into every JIT body")
    if arm == "native":
        require(all_bodies == 0, "native session executed JIT outside measurement")
    require(stats(final, "kd_native stats") == dict(started=0, completed=0, unlocks=0),
            "ordinary comparison unexpectedly used native continuation")
    comparable = {key: initial[key] for key in ("trial", "boot", "release", "binaries")}
    comparable["console"] = initial["console"]
    comparable["parameters"] = {
        module: {k: v for k, v in values.items() if k != "target_process"}
        for module, values in initial["parameters"].items()}
    finished = time.monotonic_ns()
    daemon_log = out / "daemon.log"
    costs = preparation_costs(initial, phases, publications,
        daemon_log.read_text() if daemon_log.exists() else "", body_count, finished)
    boundaries = jit_boundary_costs(initial, final, all_bodies)
    if boundaries is not None:
        costs["jit_boundaries"] = boundaries
    require(console_state() == initial["console"], "console changed before final accounting")
    report = {"schema": 1, "arm": arm, "comparable": comparable,
              "initial": initial, "phases": phases, "operations": operations,
              "measured_bodies": body_count, "all_bodies": all_bodies,
              "hostcalls": hostcalls, "costs": costs, "finished_ns": finished}
    write_json(out / "arm.json", report)
    print(json.dumps({"arm": arm, "mode": trial["mode"], "operations": operations,
                      "measured_bodies": body_count, "complete": True}), flush=True)


def pair_results(first, second):
    """Pair identical inputs only; keep ratios per repeat, never pool modes."""
    require({first["arm"], second["arm"]} == {"native", "jit"}, "missing paired arm")
    require(first["comparable"] == second["comparable"], "paired inputs differ")
    require(first["operations"] == second["operations"], "paired states differ")
    require(first["finished_ns"] < second["initial"]["started_ns"],
            "arm sessions overlap or order changed")
    native, jit = (first, second) if first["arm"] == "native" else (second, first)
    require(native["all_bodies"] == native["measured_bodies"] == 0 and
            jit["all_bodies"] >= jit["measured_bodies"] > 0,
            "pair lacks distinct native and measured-JIT evidence")
    n, j = (r["phases"]["measure"]["metrics"] for r in (native, jit))
    report = {"trial": first["comparable"]["trial"], "order": [first["arm"], second["arm"]],
            "native": n, "jit": j, "jit_measured_bodies": jit["measured_bodies"],
            "instrumented_throughput_ratio_jit_over_native":
                j["ioctls_per_second"] / n["ioctls_per_second"]}
    # Historical pairs remain readable without inventing unavailable telemetry.
    # New and old accounting must not be mixed into a single comparable pair.
    require(("costs" in native) == ("costs" in jit), "paired accounting versions differ")
    if "costs" in native:
        report["costs"] = {"native": native["costs"], "jit": jit["costs"]}
        report["console"] = first["comparable"]["console"]
    return report


def summarize(out):
    """Read archived arm reports only after the existing byte/outcome verifier.

    A failed/incomplete pair is retained, not retried, averaged or silently
    removed. This summary is not an independent authentication of its logs.
    """
    verified = verify_run(out)
    selection = read_json(out / "selection.json")
    arms = {}
    for case in verified["cases"]:
        if not case["recorded_accepted"]:
            continue
        with tarfile.open(out / case["name"] / "protocol.tar.gz", "r:gz") as archive:
            members = [m for m in archive.getmembers() if m.name.endswith("/arm.json")]
            require(len(members) == 1 and members[0].isfile() and members[0].size < 2**20,
                    "missing/oversized arm report")
            arm = json.loads(archive.extractfile(members[0]).read(),
                             object_pairs_hook=unique_object)
            selected = next(item for item in selection if item["name"] == case["name"])
            require(arm["arm"] == selected["env"]["KD_BENCH_ARM"] and
                    arm["comparable"]["trial"] ==
                    json.loads(selected["env"]["KD_BENCH_TRIAL"]),
                    "arm report differs from selected command/environment")
            require(arm["initial"]["parameters"]["kdlock_km"].get("jit_timing", "N") ==
                    ("Y" if selected["env"].get("KD_BENCH_JIT_TIMING", "0") == "1" else "N"),
                    "loaded timing setting differs from selected experiment")
            arms[case["name"]] = arm
    pairs, missing = [], []
    require(len(selection) % 2 == 0, "odd comparison selection")
    for offset in range(0, len(selection), 2):
        names = [item["name"] for item in selection[offset:offset + 2]]
        if all(name in arms for name in names):
            pairs.append(dict(cases=names, **pair_results(*(arms[name] for name in names))))
        else:
            missing.append(names)
    report = {"schema": 1, "scope": "instrumented native-with-hooks/JIT; no third arm",
              "complete": verified["all_recorded_accepted"] and not missing,
              "pairs": pairs, "incomplete_pairs": missing}
    write_json(out / "comparison.json", report)
    return report


def make_cases(trials, repeats, jit_timing=False):
    """Balance native/JIT ordering without retrying a missing-JIT result."""
    require(type(jit_timing) is bool, "JIT timing selection must be boolean")
    require(repeats >= 2 and repeats <= 100 and repeats % 2 == 0,
            "repeats must be even and between 2 and 100 for balanced order")
    require(0 < len(trials) * repeats <= 128, "select at most 128 pairs explicitly")
    result = []
    for index, trial in enumerate(trials):
        validate_trial(trial)
        for repeat in range(repeats):
            order = ("native", "jit") if repeat % 2 == 0 else ("jit", "native")
            for arm in order:
                env = {"KD_BENCH_TRIAL": json.dumps(trial, sort_keys=True), "KD_BENCH_ARM": arm}
                if jit_timing:
                    env["KD_BENCH_JIT_TIMING"] = "1"
                result.append(regression.Case(
                    f"pair-{index:03d}-repeat-{repeat:02d}-{arm}", "benchmark_arm.sh",
                    env=env))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", type=int, nargs="+", choices=(2, 5), required=True)
    parser.add_argument("--threads", type=unsigned, nargs="+", default=[8])
    parser.add_argument("--workload", type=unsigned, nargs="+", default=[100000])
    parser.add_argument("--loops", type=unsigned, default=16)
    parser.add_argument("--runs", type=unsigned, default=2)
    parser.add_argument("--cpus", type=cpu_list, required=True)
    parser.add_argument("--repeats", type=unsigned, default=2)
    parser.add_argument(
        "--jit-timing",
        action="store_true",
        help="collect inclusive kernel JIT boundary timings for both arms",
    )
    parser.add_argument("--timeout", type=unsigned, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    trials = [dict(mode=mode, threads=threads, workload=workload, loops=args.loops,
                   runs=args.runs, cpus=args.cpus)
              for mode, threads, workload in itertools.product(
                  dict.fromkeys(args.mode), dict.fromkeys(args.threads),
                  dict.fromkeys(args.workload))]
    cases = make_cases(trials, args.repeats, args.jit_timing)
    require(args.timeout > 0, "positive case timeout required")
    if args.dry_run:
        for case in cases:
            print(f"{case.name}: {case.display()}")
        return 0
    guest_only()
    regression.check_idle()
    require(set(args.cpus) <= os.sched_getaffinity(0), "CPUs outside allowed set")
    require(args.output is not None, "choose a new --output outside the checkout")
    out = args.output.resolve()
    require(not out.is_relative_to(ROOT), "evidence must be outside source checkout")
    out.mkdir(parents=True, exist_ok=False)
    status = regression.run(cases, out, args.timeout)
    report = summarize(out)
    print(f"Paired evidence: {out / 'comparison.json'}; complete={report['complete']}")
    return status or int(not report["complete"])


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "arm":
            guest_only()
            _, _, action, directory = sys.argv
            out = Path(directory)
            if action == "init":
                initialize(out)
            elif action in (*PREPARATION, "measure"):
                run_phase(out, action)
            elif action in ("before", "after"):
                publication(out, action)
            elif action == "finish":
                finish_arm(out)
            else:
                raise RuntimeError("unknown internal arm command")
        else:
            raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError, TypeError,
            AssertionError, subprocess.SubprocessError) as error:
        raise SystemExit(f"FAIL: {error}; retain evidence, do not retry automatically") from error

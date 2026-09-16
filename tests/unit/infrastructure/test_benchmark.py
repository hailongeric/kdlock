"""Verify the actual ioctl driver's measurement protocol, not kernel execution."""

import argparse
import copy
import json
import math
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PREFIX = "KD_BENCH_METRICS "
sys.path.insert(0, str(ROOT / "tests"))
import paired_benchmark as paired


def check_pair_protocol():
    """Exercise comparison boundaries without adding another live smoke case.

    Synthetic phase logs can validate the observer, not certify actual JIT or
    state transitions. The recovery-guest experiment supplies those separately.
    """
    checks = 0

    def rejects(function, *args):
        nonlocal checks
        try:
            function(*args)
        except (RuntimeError, argparse.ArgumentTypeError):
            checks += 1
        else:
            raise AssertionError("invalid paired evidence was accepted")

    trial = dict(mode=2, threads=3, loops=2, workload=10, runs=3, cpus=[0, 1])
    cases = paired.make_cases([trial, dict(trial, mode=5)], 2)
    assert [case.env["KD_BENCH_ARM"] for case in cases] == [
        "native", "jit", "jit", "native"] * 2
    assert len({case.name for case in cases}) == 8
    assert all(case.script == "tools/benchmark_arm.sh" for case in cases)
    assert paired.cpu_list("2-3,0") == [0, 2, 3]
    assert len(paired.regression.CASES) == 80
    checks += 1
    assert all("KD_BENCH_JIT_TIMING" not in case.env for case in cases)
    timed_cases = paired.make_cases([trial], 2, True)
    assert all(case.env["KD_BENCH_JIT_TIMING"] == "1" for case in timed_cases)
    with patch.dict(os.environ, {"KD_BENCH_JIT_TIMING": "1"}):
        assert "KD_BENCH_JIT_TIMING" not in paired.regression.child_environment(cases[0])
        assert paired.regression.child_environment(timed_cases[0])["KD_BENCH_JIT_TIMING"] == "1"
    checks += 3
    rejects(paired.make_cases, [trial], 2, "1")
    for cpus in ("", "0,0", "2-0", "4096", "0,x", "0-2,1"):
        rejects(paired.cpu_list, cpus)
    for key, value in (("mode", 4), ("threads", 1), ("loops", 0), ("workload", -1),
                       ("runs", 2**20), ("loops", 10000000), ("cpus", [1, 0])):
        rejects(paired.validate_trial, dict(trial, **{key: value}))
    for repeats in (0, 1, 3, 102):
        rejects(paired.make_cases, [trial], repeats)

    def record(values):
        threads, loops, work, runs = values
        return dict(schema=1, complete=True, threads=threads, mode=2, role_base=0,
                    loops_per_ioctl=loops, workload=work, ioctls_per_thread=runs,
                    requested_ioctls=threads * runs, completed_ioctls=threads * runs,
                    wall_ns=1000, worker_cpu_ns=100, ioctl_p50_ns=100,
                    ioctl_p99_ns=1000, ioctls_per_second=threads * runs * 1e6,
                    workers=[dict(id=i, completed=runs, error=0) for i in range(threads)])

    values = paired.parameters(trial, "measure")
    value = record(values)
    assert paired.metrics(PREFIX + json.dumps(value), values, 2) == value
    checks += 1
    for key, bad in (("complete", False), ("mode", 5), ("role_base", 1),
                     ("completed_ioctls", 0), ("wall_ns", None),
                     ("ioctls_per_second", float("nan")), ("ioctl_p99_ns", 1001)):
        rejects(paired.metrics, PREFIX + json.dumps(dict(value, **{key: bad})), values, 2)
    rejects(paired.metrics, "\n".join([PREFIX + json.dumps(value)] * 2), values, 2)

    ready = dict(entry=dict(entry="0xabc", status=0, code="0xdef", tgid=10,
                           pid=0, observed_ns=1), images={"jit.bin": "fixed"})
    native_ready = dict(entry=None, images={})
    before = "[1] preparation complete\n"
    after = before + "[2] JIT body witness: entry=abc lock=123 body=1\n"
    assert paired.validate_body_phase(before, after, ready, ready, 0x123, "jit") == 1
    assert paired.validate_body_phase(before, before, native_ready, native_ready,
                                      0x123, "native") == 0
    checks += 2
    rejects(paired.validate_body_phase, before, after[len(before):], ready, ready, 0x123, "jit")
    rejects(paired.validate_body_phase, after, after, ready, ready, 0x123, "jit")
    rejects(paired.validate_body_phase, before, after, ready, ready, 0x456, "jit")
    rejects(paired.validate_body_phase, before, after, native_ready, native_ready, 0x123, "native")
    for field, replacement in (("images", {"jit.bin": "replaced"}),
                               ("entry", dict(ready["entry"], status=-1)),
                               ("entry", dict(ready["entry"], tgid=11))):
        rejects(paired.validate_body_phase, before, after, ready,
                dict(ready, **{field: replacement}), 0x123, "jit")

    # Run the complete arm summarizer against normal log shapes, including the
    # mode-labelled scalar service, then mutate an oracle, not just timings.
    with tempfile.TemporaryDirectory(prefix="kdlock-pair-unit-") as directory:
        out = Path(directory)
        console = dict(printk="4\t4\t1\t7", ignore_loglevel="N", consoles="ttyS0\n")
        ready.update(console=console, observed_ns=7000)
        ready_after = dict(ready, observed_ns=11000)
        initial = dict(schema=1, arm="jit", trial=trial, lock=0x123, boot="same",
                       release="6.1.159", binaries={"module": "same"}, started_ns=0,
                       console=console,
                       parameters={"kdlock_km": {"target_process": "klock_test",
                                                 "mutex_jit": "1"}})
        paired.write_json(out / "initial.json", initial)
        for index, name in enumerate((*paired.PREPARATION, "measure")):
            data = record(paired.parameters(trial, name))
            (out / f"{name}.log").write_text(PREFIX + json.dumps(data) + "\n")
            paired.write_json(out / f"{name}.json", dict(exit=0, inherited_cpus=[0, 1],
                metrics=data, started_ns=1000 + index * 3500,
                finished_ns=3000 + index * 3500, console_before=console,
                console_after=console))
        paired.write_json(out / "published-before.json", ready)
        paired.write_json(out / "published-after.json", ready_after)
        (out / "before.dmesg").write_text(before)
        (out / "after.dmesg").write_text(after)
        operations = 12019
        final = after + (
            f"[3] kd_cs integrity: operations={operations} active_states=1 failures=0\n"
            f"[4] module unloaded, final counter: {operations}\n"
            f"[5] mode2 api observations: {operations}\n"
            f"[6] kd_scalar service: mode=2 calls={operations} failures=0\n"
            "[7] kd_hostcall stats: exits=2 executed=2 resumed=2 rejected=0 failed=0 limit=0\n"
            "[8] kd_native stats: started=0 completed=0 unlocks=0\n"
            "[8] kd_spin lock stats: lock=123 slowpath=2 waiters=0\n")
        (out / "final.log").write_text(final)
        compilation = dict(schema=1, pid=0, tgid=10, entry="0xabc", lock_kind=1,
            child=42, started_ns=4500, finished_ns=5500, wall_ns=1000, user_ns=100,
            system_ns=10, maxrss_kib=512, minor_faults=5, major_faults=0,
            voluntary_cs=1, involuntary_cs=2, status=0, result=0)
        (out / "daemon.log").write_text(paired.TRANSLATION_PREFIX + json.dumps(compilation))
        with patch.object(paired, "console_state", return_value=console), \
             patch.object(paired.time, "monotonic_ns", return_value=12000):
            paired.finish_arm(out)
        first = paired.read_json(out / "arm.json")
        assert first["costs"] == dict(schema=1, preparation_elapsed_ns=7000,
            phase_process_ns=dict(warmup=2000, promotion=2000, measure=2000),
            translation=dict(attempts=1, records=[compilation], wall_ns=1000,
                user_ns=100, system_ns=10, maxrss_kib=512, minor_faults=5,
                major_faults=0, voluntary_cs=1, involuntary_cs=2),
            measured_cs=18, measured_jit_share=1/18, measure_process_outside_workers_ns=1000)
        checks += 1

        # The optional kernel intervals must join actual session body counts,
        # not mere image publication or a caller's requested measurement flag.
        timed_initial = copy.deepcopy(initial)
        timed_initial["parameters"]["kdlock_km"]["jit_timing"] = "Y"
        timing_rows = [
            "[9] kd_jit timing: phase=dispatch samples=1 ns=100 invalid=0\n",
            "[9] kd_jit timing: phase=wrapper samples=3 ns=30 invalid=0\n",
            "[9] kd_jit timing: phase=hostcall samples=2 ns=20 invalid=0\n",
            "[9] kd_jit timing: phase=control samples=1 ns=10 invalid=0\n",
            "[9] kd_jit timing: phase=native_spin_wait samples=0 ns=0 invalid=0\n",
            "[9] kd_jit timing: phase=native_mutex_wait samples=0 ns=0 invalid=0\n",
            "[9] kd_jit timing: phase=spin_queue samples=2 ns=60 invalid=0\n",
            "[9] kd_jit timing: phase=mutex_queue samples=0 ns=0 invalid=0\n",
            "[9] kd_jit timing: phase=native_spin_handoff samples=0 ns=0 invalid=0\n",
            "[9] kd_jit timing: phase=native_mutex_handoff samples=0 ns=0 invalid=0\n",
        ]
        timings = "".join(timing_rows)
        boundaries = paired.jit_boundary_costs(timed_initial, final + timings, 1)
        assert boundaries["dispatch_residual_ns"] == 40
        assert boundaries["phases"]["wrapper"] == dict(samples=3, ns=30, mean_ns=10)
        assert boundaries["phases"]["spin_queue"] == dict(samples=2, ns=60, mean_ns=30)
        assert paired.jit_boundary_costs(initial, final, 1) is None
        checks += 3
        rejects(paired.jit_boundary_costs, initial, final + timings, 1)
        for bad in ("", "".join(timing_rows[:3]), "".join(timing_rows[:4]),
                    "".join(timing_rows[:5]), "".join(timing_rows[:6]),
                    "".join(timing_rows[:7]), timings + timing_rows[0],
                    "".join(timing_rows[:8]), "".join(timing_rows[:9]),
                    timings.replace("native_mutex_handoff", "native_spin_handoff"),
                    timings.replace("phase=native_spin_handoff samples=0", "phase=native_spin_handoff samples=1"),
                    timings.replace("native_mutex_wait", "native_spin_wait"),
                    timings.replace("samples=0 ns=0", "samples=1 ns=10", 1),
                    timings.replace("samples=0 ns=0", "samples=0 ns=1", 1),
                    timings.replace("phase=control", "phase=wrapper"),
                    timings.replace("phase=control", "phase=queue"),
                    timings.replace("phase=spin_queue samples=2", "phase=spin_queue samples=1"),
                    timings.replace("phase=mutex_queue samples=0", "phase=mutex_queue samples=1"),
                    timings.replace("samples=3", "samples=2"),
                    timings.replace("samples=2", "samples=1"),
                    timings.replace("ns=100", "ns=59"),
                    timings.replace("ns=100", f"ns={2**63}"),
                    timings.replace("ns=100", "ns=-1"),
                    timings.replace("invalid=0", "invalid=1"),
                    timings.replace("invalid=0", "invalid=0 extra=1")):
            rejects(paired.jit_boundary_costs, timed_initial, final + bad, 1)
        rejects(paired.jit_boundary_costs, dict(timed_initial, trial=dict(trial, mode=4)),
                timings, 1)
        # The same service path on mutex uses its own queue counter. Queue ns
        # may exceed dispatch ns because waiting requests overlap in time.
        mutex_initial = dict(timed_initial, trial=dict(trial, mode=5))
        mutex_log = "kd_mutex stats: slowpath=2\n" + timings.replace(
            "phase=spin_queue", "phase=swapped").replace(
            "phase=mutex_queue", "phase=spin_queue").replace(
            "phase=swapped", "phase=mutex_queue").replace("ns=60", "ns=600")
        mutex_cost = paired.jit_boundary_costs(mutex_initial, mutex_log, 1)
        assert mutex_cost["phases"]["mutex_queue"]["ns"] == 600
        assert mutex_cost["dispatch_residual_ns"] == 40
        checks += 1
        rejects(paired.jit_boundary_costs, timed_initial,
                (final + timings).replace("slowpath=2", "slowpath=3"), 1)
        rejects(paired.jit_boundary_costs, timed_initial,
                (final + timings).replace("waiters=0", "waiters=1"), 1)
        zero_timings = "".join(
            f"kd_jit timing: phase={name} samples=0 ns=0 invalid=0\n"
            for name in ("dispatch", "wrapper", "hostcall", "control",
                         "native_spin_wait", "native_mutex_wait", "spin_queue", "mutex_queue",
                         "native_spin_handoff", "native_mutex_handoff"))
        empty = paired.jit_boundary_costs(dict(timed_initial, arm="native"), zero_timings, 0)
        assert all(p["samples"] == p["ns"] == 0 and p["mean_ns"] is None
                   for p in empty["phases"].values())
        checks += 1
        rejects(paired.jit_boundary_costs, dict(timed_initial, arm="native"), timings, 1)
        rejects(paired.jit_boundary_costs, dict(timed_initial, arm="native"),
                zero_timings.replace("ns=0", "ns=1"), 0)
        paired.write_json(out / "initial.json", timed_initial)
        (out / "final.log").write_text(final + timings)
        with patch.object(paired, "console_state", return_value=console), \
             patch.object(paired.time, "monotonic_ns", return_value=12000):
            paired.finish_arm(out)
            assert paired.read_json(out / "arm.json")["costs"]["jit_boundaries"] == boundaries
            (out / "final.log").write_text(final)
            rejects(paired.finish_arm, out)
        checks += 1
        paired.write_json(out / "initial.json", initial)

        def cost_record(data):
            return paired.preparation_costs(initial, first["phases"],
                [ready, ready_after], paired.TRANSLATION_PREFIX + json.dumps(data), 1, 12000)

        for key, bad in (("pid", 1), ("tgid", 11), ("entry", "0xdef"),
                         ("lock_kind", 2), ("started_ns", -1), ("finished_ns", 9000),
                         ("wall_ns", 999), ("schema", 2), ("status", 256),
                         ("result", -1), ("user_ns", True), ("maxrss_kib", 0)):
            rejects(cost_record, dict(compilation, **{key: bad}))
        rejects(paired.preparation_costs, initial, first["phases"], [ready, ready_after],
                "", 1, 12000)
        duplicated = "\n".join([paired.TRANSLATION_PREFIX + json.dumps(compilation)] * 2)
        rejects(paired.preparation_costs, initial, first["phases"], [ready, ready_after],
                duplicated, 1, 12000)
        for key, bad in (("started_ns", 5000), ("finished_ns", 8000),
                         ("console_after", dict(console, ignore_loglevel="Y"))):
            phases = copy.deepcopy(first["phases"])
            phases["measure"][key] = bad
            rejects(paired.preparation_costs, initial, phases, [ready, ready_after],
                    paired.TRANSLATION_PREFIX + json.dumps(compilation), 1, 12000)

        second = copy.deepcopy(first)
        second.update(arm="native", measured_bodies=0, all_bodies=0)
        second["initial"]["arm"] = "native"
        second["initial"]["started_ns"] = first["finished_ns"] + 1
        for phase in second["phases"].values():
            phase["started_ns"] += 12000
            phase["finished_ns"] += 12000
        second["finished_ns"] = 24000
        native_publications = [dict(p, entry=None, images={}, observed_ns=p["observed_ns"] + 12000)
                               for p in (ready, ready_after)]
        second["costs"] = paired.preparation_costs(second["initial"], second["phases"],
                                                  native_publications, "", 0, 24000)
        assert second["costs"]["translation"]["attempts"] == 0
        assert second["costs"]["translation"]["maxrss_kib"] is None
        assert second["costs"]["measured_jit_share"] == 0
        result = paired.pair_results(first, second)
        assert result["order"] == ["jit", "native"]
        assert result["instrumented_throughput_ratio_jit_over_native"] == 1
        checks += 2
        for key, replacement in (("boot", "changed"), ("binaries", {"module": "new"}),
                                 ("trial", dict(trial, cpus=[2, 3])),
                                 ("console", dict(console, printk="7 4 1 7"))):
            changed = copy.deepcopy(second)
            changed["comparable"][key] = replacement
            rejects(paired.pair_results, first, changed)
        rejects(paired.pair_results, first, first)
        changed = copy.deepcopy(second)
        changed["initial"]["started_ns"] = 0
        rejects(paired.pair_results, first, changed)
        changed = copy.deepcopy(second)
        changed["all_bodies"] = 1
        rejects(paired.pair_results, first, changed)
        changed = copy.deepcopy(second)
        del changed["costs"]
        rejects(paired.pair_results, first, changed)
        legacy = copy.deepcopy(first)
        del legacy["costs"]
        del legacy["comparable"]["console"]
        del changed["comparable"]["console"]
        assert "costs" not in paired.pair_results(legacy, changed)
        checks += 1
        (out / "final.log").write_text(final.replace("resumed=2", "resumed=1"))
        rejects(paired.finish_arm, out)

        # The byte verifier has its own production tests. Here its boundary is
        # substituted to check pairing/partial-run bookkeeping, not authenticity.
        selection = []
        recorded = []
        for name, arm in (("first", first), ("second", second)):
            selection.append(dict(name=name, env={"KD_BENCH_ARM": arm["arm"],
                                                  "KD_BENCH_TRIAL": json.dumps(trial)}))
            recorded.append(dict(name=name, recorded_accepted=True))
            directory = out / name
            directory.mkdir()
            paired.write_json(out / "arm.json", arm)
            with tarfile.open(directory / "protocol.tar.gz", "w:gz") as archive:
                archive.add(out / "arm.json", arcname="kdlock-arm/arm.json")
        paired.write_json(out / "selection.json", selection)
        verification = dict(cases=recorded, all_recorded_accepted=True)
        with patch.object(paired, "verify_run", return_value=verification):
            summary = paired.summarize(out)
            assert summary["complete"] and len(summary["pairs"]) == 1
            selection[0]["env"]["KD_BENCH_JIT_TIMING"] = "1"
            paired.write_json(out / "selection.json", selection)
            rejects(paired.summarize, out)
            del selection[0]["env"]["KD_BENCH_JIT_TIMING"]
            paired.write_json(out / "selection.json", selection)
            verification["all_recorded_accepted"] = False
            recorded[1]["recorded_accepted"] = False
            summary = paired.summarize(out)
            assert not summary["complete"] and not summary["pairs"]
            assert summary["incomplete_pairs"] == [["first", "second"]]
            recorded.pop()
            assert not paired.summarize(out)["complete"]
            checks += 3
            selection[0]["env"]["KD_BENCH_ARM"] = "native"
            paired.write_json(out / "selection.json", selection)
            rejects(paired.summarize, out)
    print(f"[PASS] paired measurement observer ({checks} checks; no kernel execution)")


def main():
    checks = 0
    with tempfile.TemporaryDirectory(prefix="kdlock-benchmark-") as directory:
        binary = Path(directory) / "benchmark_fixture"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
               str(ROOT / "tests/unit/infrastructure/benchmark_fixture.c"), "-o", str(binary)],
            check=True, timeout=30,
        )

        def run(args=None, *, status=0, record=True, **options):
            nonlocal checks
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("KD_", "BENCH_"))}
            env.update(KD_TEST_METRICS="1", KD_TEST_COMM="klock_test")
            env.update(options)
            result = subprocess.run(
                [str(binary), *(args or ["3", "2", "10", "3", "4", "8"])],
                env=env, capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == status, (result.stdout, result.stderr)
            lines = [line[len(PREFIX):] for line in result.stdout.splitlines()
                     if line.startswith(PREFIX)]
            assert len(lines) == int(record), result.stdout
            checks += 1
            return (json.loads(lines[0]) if lines else None), result

        value, output = run()
        assert value == {
            "schema": 1, "complete": True, "threads": 3, "mode": 4,
            "role_base": 8, "loops_per_ioctl": 2, "workload": 10,
            "ioctls_per_thread": 3, "requested_ioctls": 9, "completed_ioctls": 9,
            "wall_ns": 13500, "worker_cpu_ns": 1500,
            "ioctls_per_second": 666666.666667,
            "ioctl_p50_ns": 2100, "ioctl_p99_ns": 3200,
            "workers": [{"id": i, "completed": 3, "error": 0} for i in range(3)],
        }, value
        assert "Loop " not in output.stdout and "Total Time:" not in output.stdout
        assert "fixture opens=1 creates=3 joins=3 ioctls=9" in output.stderr

        value, _ = run(["1", "1", "0", "1", "0"])
        assert value["ioctl_p50_ns"] == value["ioctl_p99_ns"] == 1000
        value, _ = run(KD_TEST_MIXED="1")
        assert value["complete"]
        # Real clocks exercise the non-injected guest path, but sleeping ioctl
        # doubles are not a performance baseline or proof of translated code.
        value, _ = run(BENCH_REAL_CLOCK="1")
        assert value["complete"] and value["worker_cpu_ns"] > 0
        assert 0 < value["ioctl_p50_ns"] <= value["ioctl_p99_ns"] <= value["wall_ns"]
        assert math.isclose(value["ioctls_per_second"], 9e9 / value["wall_ns"],
                            rel_tol=1e-6)

        for options, completed in [
            ({"BENCH_IOCTL_FAIL": "1"}, 3),
            ({"BENCH_CLOCK_FAIL": "before"}, 0),
            ({"BENCH_CLOCK_FAIL": "after"}, 3),
            ({"BENCH_CLOCK_FAIL": "backward"}, 3),
            ({"BENCH_CLOCK_FAIL": "cpu"}, 9),
            ({"BENCH_CLOCK_FAIL": "end"}, 9),
            ({"KD_TEST_COMM": "name-exceeds-linux-task-limit"}, 0),
        ]:
            value, _ = run(status=1, **options)
            assert not value["complete"] and value["completed_ioctls"] == completed
            assert all(value[field] is None for field in (
                "wall_ns", "worker_cpu_ns", "ioctls_per_second",
                "ioctl_p50_ns", "ioctl_p99_ns"))
            assert sum(worker["completed"] for worker in value["workers"]) == completed
            assert all(worker["error"] for worker in value["workers"])

        for name in ("BENCH_OPEN_FAIL", "BENCH_CREATE_FAIL", "BENCH_JOIN_FAIL"):
            run(status=1, record=False, **{name: "1"})

        for index, invalid in (
            (0, "0"), (0, "-1"), (0, "2147483648"), (1, "0"),
            (1, "18446744073709551616"), (2, "2x"), (2, "+1"),
            (2, " 1"), (2, ""), (3, "0"), (3, "349526"),
            (4, "12"), (4, "4294967296"), (5, "4294967295"),
        ):
            args = ["3", "2", "10", "3", "4", "8"]
            args[index] = invalid
            _, output = run(args, status=1, record=False)
            assert "fixture opens=0 creates=0 joins=0 ioctls=0" in output.stderr
        _, output = run(status=1, record=False, KD_TEST_METRICS="yes")
        assert "fixture opens=0" in output.stderr
        _, output = run(record=False, KD_TEST_METRICS="0")
        assert output.stdout.count(" completed\n") == 9
        assert "Total Time:" in output.stdout
    print(f"[PASS] test_benchmark ({checks} production-driver scenarios)")
    check_pair_protocol()


if __name__ == "__main__":
    main()

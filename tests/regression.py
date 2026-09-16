"""Select bounded, nonduplicated live regressions by changed behavior.

No implicit baseline or success cache: a historical pass is not a new run.
Scripts retain their own JIT/protocol oracles; this runner controls scope,
evidence and fail-stop case boundaries, never forced module cleanup.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import regression_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]
WORKERS = re.compile(
    r"klock_test|daemon|kd_native|kd_renamed|kd_shadow_[0-2]|kd_mtask_[0-2]|kd_gate_[0-3]"
)
FAULTS = re.compile(
    r"BUG:|panic|double fault|soft lockup|unable to handle|WARNING:|scheduling while atomic",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Case:
    name: str
    script: str
    args: tuple = ()
    env: dict = field(default_factory=dict)

    def command(self):
        return ["bash", f"tests/{self.script}", *map(str, self.args)]

    def display(self):
        return shlex.join(
            ["env", *(f"{k}={v}" for k, v in self.env.items()), *self.command()]
        )


CASES = {}


def add(name, script, *args, **env):
    if name in CASES:
        raise ValueError(f"duplicate case: {name}")
    CASES[name] = Case(name, f"live/{script}", args, {k: str(v) for k, v in env.items()})


# Keep small diagnostics addressable, not prerequisites of every complex case.
for name, script in (
    ("module", "test_01_module_load.sh"),
    ("pipeline", "test_02_jit_engine.sh"),
    ("mutex-off", "test_05_mutex.sh"),
):
    add(name, script)
for mode in range(9):
    script = "test_09_jit_execution_modes.sh" if mode < 6 else "test_04_spinlock.sh"
    add(f"mode-{mode}", script, mode)
for mode, stage in ((0, 1), (3, 1), (1, 2), (4, 2), (1, 3), (4, 3), (8, 2), (8, 3)):
    add(
        f"registers-{mode}-{stage}",
        "test_10_native_resume.sh",
        mode,
        stage,
        KD_NATIVE_REGISTERS=1,
    )
for mode in (0, 3):
    add(
        f"control-{mode}",
        "test_10_native_resume.sh",
        mode,
        1,
        KD_NATIVE_REGISTERS=1,
        KD_NATIVE_CONTROL=1,
    )
for name, mode in (("spin", 10), ("mutex", 11), ("mixed", 3)):
    add(f"context-{name}", "test_12_context_native_only.sh" if mode == 3 else "test_24_gs_jit.sh", mode)
for api in (
    "irqsave",
    "bh",
    "percpu",
    "percpu-reg",
    "percpu-flow",
    "percpu-spill",
    "percpu-implicit",
    "percpu-rotate",
    "percpu-cmov",
):
    add(f"context-{api}", "test_12_context_native_only.sh", 3, KD_CONTEXT_LOCK_API=api)
add("mixed-spin", "test_17_spin_native_protocol.sh")
add("mixed-mutex", "test_11_mutex_native_protocol.sh", 1)
for mode in (1, 4):
    for stage in (3, 4):
        # Upgrade the accepted PENDING diagnostic to real native B contention
        # and same-CPU owner/waiter progress, without adding a daily case.
        env = (
            {"KD_NATIVE_PENDING_CONTENDED": 1, "KD_NATIVE_SHARED_CPU": 1}
            if (mode, stage) == (4, 4)
            else {}
        )
        add(f"native-{mode}-{stage}", "test_10_native_resume.sh", mode, stage, **env)
# Early A release must break the native C-owner dependency while B and six
# child locks remain borrowed. Ordinary held-B/register cases never exercise
# that progress contract; reuse the existing complex driver in each backend.
for backend, mode in (("spin", 1), ("mutex", 4)):
    add(
        f"native-{backend}-outer-dependency",
        "test_10_native_resume.sh",
        mode,
        3,
        KD_NATIVE_OOO=3,
        KD_NATIVE_OOO_DEPENDENCY=2,
    )
# Upgrade the existing depth case: the root and learned helper live in separate
# modules, while the same real capacity exit remains the execution oracle.
add("native-mutex-depth", "test_10_native_resume.sh", 4, 5, KD_NATIVE_SOURCE_MODULE=1)
# Upgrade the local checkpoint to a genuine queued acquisition plus follower.
# Value 1 remains a direct-script FAST diagnostic, not another daily case.
add("native-spin-acquired", "test_10_native_resume.sh", 1, 3, KD_NATIVE_SPIN_ACQUIRED=2)
# Same real B-owner topology, but a completed control detects a shared-stack
# write. This does not replace PENDING resource or ordinary CALL-miss exits.
add(
    "native-mutex-stack-change",
    "test_10_native_resume.sh",
    4,
    4,
    KD_NATIVE_PENDING_CONTENDED=1,
    KD_NATIVE_STACK_CHANGE=1,
)
add("shadow-capacity", "test_10_native_resume.sh", 1, 4, KD_NATIVE_SHADOW_CAPACITY=1)
for kind, value in (("context", 1), ("node", 2), ("ticket", 3)):
    add(
        f"virtual-{kind}-refusal",
        "test_10_native_resume.sh",
        8,
        4,
        KD_NATIVE_PENDING_CONTENDED=1,
        KD_NATIVE_VIRTUAL_RESOURCE=value,
        # Reuse the real ticket gate for map pressure during native progress.
        **({"KD_NATIVE_GATE_PRESSURE": 1} if value == 3 else {}),
    )
for name, mode in (("spin", 0), ("mutex", 3)):
    add(
        f"late-{name}-policy",
        "test_10_native_resume.sh",
        mode,
        1,
        KD_NATIVE_POLICY_COMPLETION=1,
    )
for depth in (1, 2, 8):
    for numa in (0, 1):
        add(
            f"node-physical-{depth}-{numa}",
            "test_14_spin_frame_depth.sh",
            depth,
            KD_CHAIN_TRACE_NODES=1,
            KD_CHAIN_NUMA=numa,
            KD_CHAIN_FORCE_PROMOTION=1,
        )
add("node-remote-plain", "test_21_remote_depth.sh", 4, 1, KD_DEEP_TRACE_NODES=1)
# These placements keep every role distinct on the documented 40-vCPU guest.
REMOTE_CPUS = "0,39,20,21,22,23,1,2,3,4,24,25,26,27,5,6,7,8"
REMOTE_ENV = {
    "KD_DEEP_NATIVE_OWNER": 1,
    "KD_DEEP_REVERSE": 1,
    "KD_NATIVE_RENAME": 1,
    "KD_DEEP_CROSS_NUMA": 1,
}
for stage in (2, 3, 4):
    add(
        f"remote-late-{stage}",
        "test_21_remote_depth.sh",
        4,
        stage,
        KD_DEEP_CPUS=REMOTE_CPUS,
        # Reuse the late all-unlocked schedule for actual waiter TID exit;
        # do not add another daily case or replay its simpler predecessor.
        **({"KD_DEEP_WAITER_EXIT": 1} if stage == 3 else {}),
        **REMOTE_ENV,
    )
add(
    "remote-multi-b",
    "test_21_remote_depth.sh",
    8,
    5,
    KD_DEEP_CPUS=REMOTE_CPUS
    + ",28,29,30,31,9,10,11,12,32,33,34,17,13,14,15,16,18,19,35",
    KD_DEEP_DEFER_LAYER=6,
    KD_DEEP_DEFER_COUNT=3,
    KD_DEEP_TRACE_NODES=1,
    **REMOTE_ENV,
)
add("kernel-task-local", "test_22_mutex_task_lifecycle.sh")
add(
    "kernel-task-cross-numa",
    "test_22_mutex_task_lifecycle.sh",
    KD_MUTEX_TASK_CPUS="0,20,21",
)
for first in (0, 1):
    add(
        f"parallel-drain-{first}",
        "test_23_mutex_parallel_native.sh",
        KD_MUTEX_PARALLEL_FIRST=first,
    )
add(
    "parallel-shared-cpu",
    "test_23_mutex_parallel_native.sh",
    KD_MUTEX_PARALLEL_FIRST=1,
    KD_MUTEX_PARALLEL_SHARED_CPU=1,
)
add(
    "parallel-node-pressure",
    "test_23_mutex_parallel_native.sh",
    KD_MUTEX_PARALLEL_FIRST=1,
    KD_MUTEX_PARALLEL_SHARED_CPU=1,
    KD_MUTEX_PARALLEL_PRESSURE=1,
)
# Forced cancellation holds native B through the waiter's final A ACK. The
# release races below allow B to unlock earlier, so they cannot replace this
# independent progress check even when their API return is also -EINTR.
for name, signal, api in (
    ("usr1", 10, 0),
    ("kill", 9, 0),
    ("interruptible", 10, 1),
    ("killable", 9, 2),
):
    add(
        f"waiter-{name}",
        "test_10_native_resume.sh",
        4,
        4,
        KD_NATIVE_PENDING_CONTENDED=1,
        KD_NATIVE_WAITER_SIGNAL=signal,
        KD_NATIVE_WAITER_API=api,
    )
for name, signal, api in (("int", 10, 1), ("kill", 9, 2)):
    for outcome, delay in (("cancelled", -50000), ("acquired", 50000), ("either", 0)):
        add(
            f"waiter-race-{name}-{outcome}",
            "test_10_native_resume.sh",
            4,
            4,
            KD_NATIVE_PENDING_CONTENDED=1,
            KD_NATIVE_WAITER_SIGNAL=signal,
            KD_NATIVE_WAITER_API=api,
            KD_NATIVE_WAITER_RACE=1,
            KD_NATIVE_WAITER_RACE_US=delay,
            KD_NATIVE_WAITER_EXPECT=outcome,
        )
for mode in (1, 3):
    add(f"native-peer-{mode}", "test_19_mutex_signals.sh", mode)


SUITES = {
    "baseline": ("module", "pipeline", "mutex-off"),
    # Pure-native reference measurements are explicit, not daily prerequisites
    # or actual-JIT positives. Reuse the register driver, not an external helper.
    "native-controls": ("control-0", "control-3"),
    # Deeper ordinary cases replace repeated single-lock smoke in daily runs.
    # Hostcall, out-of-order unlock and native recovery are separate semantics.
    "spin": ("mode-2", "mode-7", "mode-8"),
    "mutex": ("mode-4", "mode-5"),
    "hostcall": ("mode-2", "mode-5"),
    "registers": tuple(n for n in CASES if n.startswith("registers-")),
    "admission": tuple(n for n in CASES if n.startswith("context-")),
    "spin-native": (
        "registers-8-2",
        "registers-8-3",
        "native-spin-outer-dependency",
        "native-spin-acquired",
        "virtual-ticket-refusal",
        "shadow-capacity",
        "virtual-context-refusal",
        "virtual-node-refusal",
        "late-spin-policy",
    ),
    "mutex-native": (
        "registers-4-2",
        "registers-4-3",
        "native-mutex-outer-dependency",
        "native-4-4",
        "native-mutex-depth",
        "native-mutex-stack-change",
        "late-mutex-policy",
        "parallel-drain-0",
        "parallel-drain-1",
        "parallel-node-pressure",
    ),
    "spin-remote": (
        "node-physical-8-0",
        "node-physical-8-1",
        "node-remote-plain",
        "remote-multi-b",
        "remote-late-2",
        "remote-late-3",
        "remote-late-4",
    ),
    "mutex-signals": (
        "waiter-usr1",
        "waiter-kill",
        "native-peer-1",
        "native-peer-3",
        *(n for n in CASES if n.startswith("waiter-race-")),
    ),
    "protocol": (
        "mixed-spin",
        "mixed-mutex",
        "kernel-task-local",
        "kernel-task-cross-numa",
    ),
    # Real node pressure includes the earlier same-CPU refusal contract. Keep
    # the simpler placement point-selectable, not a repeated daily precursor.
    "mutex-parallel": (
        "parallel-drain-0",
        "parallel-drain-1",
        "parallel-node-pressure",
    ),
}
SUITES["core"] = (*SUITES["spin"], *SUITES["mutex"])
# These reviewed ordinary-success checks are covered by the named complex
# cases. This is selection policy, not a dependency graph or a historical PASS
# cache: --case still runs the diagnostic itself, without adding its replacement.
# Do not include mode-6: three locks in one frame are not the same assertion as
# a deeper chain of separate physical frames. Keep that distinction in extended.
# Nor shadow-capacity: physical frames inherit the earlier lock records and
# reject at logical depth eight, before the separate local-shadow capacity check.
COVERED_DIAGNOSTICS = {
    "mode-0": "mode-2",
    "mode-1": "mode-8",
    "mode-3": "mode-5",
    "node-physical-1-0": "node-physical-8-0",
    "node-physical-1-1": "node-physical-8-1",
    "node-physical-2-0": "node-physical-8-0",
    "node-physical-2-1": "node-physical-8-1",
    "parallel-shared-cpu": "parallel-node-pressure",
    "native-1-4": "virtual-ticket-refusal",
    # The same stage-3 workload, native probe and LIFO suffix remain, with
    # additional raw-register/CALL-stack checks. This does not cover early A.
    "native-1-3": "registers-1-3",
    "native-4-3": "registers-4-3",
}
# Even a broad regression need not repeat superseded diagnostics. Independent
# failure/register/protocol probes remain; this is not an exhaustive parameter
# sweep or the historical 67-case matrix. Pure-native controls have their own
# explicit scope even after replacing the historical external helper.
SUITES["extended"] = tuple(
    n
    for n in CASES
    if n not in SUITES["baseline"]
    and n not in SUITES["native-controls"]
    and n not in COVERED_DIAGNOSTICS
)


def select(suites, names):
    """Union stable case identities, so overlapping scopes never rerun a case."""
    selected = dict.fromkeys(n for suite in suites for n in SUITES[suite])
    selected.update(dict.fromkeys(names))
    return [CASES[n] for n in selected]


def child_environment(case=None):
    # Ambient fault/probe knobs must not silently change a named regression.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("KD_", "KDLOCK_"))}
    env.update(LC_ALL="C", KDLOCK_RECOVERY_CONFIRMED="1")
    if case is not None:
        env.update(case.env)
    return env


def source_hashes():
    # Only runtime/test inputs, not generated objects or evidence workspaces.
    hashes = {}
    for base in (
        "bench",
        "daemon",
        "disassem",
        "include",
        "kernel_module",
        "workload_modules",
        "tests",
        "kernel_baseline",
    ):
        for directory, dirs, files in os.walk(ROOT / base):
            dirs[:] = sorted(
                d for d in dirs if not d.startswith((".", "0x")) and d != "__pycache__"
            )
            for name in sorted(files):
                # Kbuild creates/rewrites these during normal and selftest
                # builds. They are outputs, not an edit of the frozen inputs.
                if name.endswith(".mod.c"):
                    continue
                path = Path(directory) / name
                # The install recipe affects translator behavior just like its
                # source; retain it without capturing arbitrary generated text.
                if name in ("Makefile", ".config", "requirements.txt") or path.suffix in (
                    ".c",
                    ".inc",
                    ".h",
                    ".S",
                    ".def",
                    ".py",
                    ".sh",
                    ".json",
                    ".config",
                    ".patch",
                ):
                    hashes[str(path.relative_to(ROOT))] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
    return hashes


def check_idle():
    modules = Path("/proc/modules").read_text().splitlines()
    if any(
        line.split()[0] in ("kdlock_km", "klock_module", "kd_depth_source")
        for line in modules
    ):
        raise RuntimeError(
            "modules remain loaded; inspect/drain manually, do not force unload"
        )
    processes = subprocess.check_output(["ps", "-eLo", "comm="], text=True, timeout=10)
    if any(WORKERS.fullmatch(name.strip()) for name in processes.splitlines()):
        raise RuntimeError("test callers/daemon remain; stop before another case")


def run(selected, out, timeout):
    frozen = source_hashes()
    (out / "source.json").write_text(json.dumps(frozen, indent=2) + "\n")
    (out / "selection.json").write_text(
        json.dumps(
            [{"name": c.name, "command": c.command(), "env": c.env} for c in selected],
            indent=2,
        )
        + "\n"
    )
    evidence.freeze_source(ROOT, out, frozen)
    evidence.environment(out, child_environment(), ROOT)
    print(f"Evidence: {out}", flush=True)
    for case in selected:
        # A preinstalled boundary stop allows cleanup to finish without editing
        # a running shell or interrupting a waiter that still owns a frame.
        if (out / "STOP").exists():
            print(f"Stopped before {case.name}; remaining cases NOT RUN", flush=True)
            return 93
        check_idle()
        if source_hashes() != frozen:
            raise RuntimeError(
                "source changed; start a new scoped run, never splice passes"
            )
        directory = out / case.name
        directory.mkdir()
        started = datetime.now(timezone.utc).isoformat()
        print(f"Running {case.name}: {case.display()}", flush=True)
        with (directory / "output.log").open("w") as log:
            status = subprocess.call(
                ["timeout", "--kill-after=5s", f"{timeout}s", *case.command()],
                cwd=ROOT,
                env=child_environment(case),
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        (directory / "exit-status").write_text(f"{status}\n")
        errors = []
        log = ""
        try:
            log = subprocess.check_output(["dmesg"], text=True, timeout=10)
            (directory / "dmesg.log").write_text(log)
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(f"dmesg unavailable: {error}")
        with (out / "results.tsv").open("a") as results:
            results.write(f"{case.name}\t{status}\n")
        drained = unchanged = captured = False
        try:
            check_idle()
            drained = True
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(f"drain not confirmed: {error}")
        try:
            unchanged = source_hashes() == frozen
            if not unchanged:
                errors.append("source changed during case; result is not accepted")
        except OSError as error:
            errors.append(f"source check failed: {error}")
        # Capture stable failure evidence too, before another test can delete
        # its daemon workspace. A live caller/writer is not a frozen archive.
        if drained:
            try:
                evidence.collect_case(ROOT, out, directory)
                captured = True
            except (OSError, RuntimeError) as error:
                errors.append(f"evidence incomplete: {error}")
        else:
            errors.append("archive skipped while callers/modules may still be active")
        fault = bool(FAULTS.search(log))
        accepted = not status and not fault and not errors and unchanged and captured
        evidence.write_json(
            directory / "result.json",
            {
                "started": started,
                "finished": datetime.now(timezone.utc).isoformat(),
                "script_exit": status,
                "kernel_fault": fault,
                "drained": drained,
                "source_unchanged": unchanged,
                "evidence_complete": captured,
                "accepted": accepted,
                "errors": errors,
            },
        )
        # A captured failed run remains failed. No automatic retry, force
        # unload or acceptance based only on a successful shell exit.
        if not accepted:
            print(
                f"FAIL {case.name}; inspect {directory}; remaining cases NOT RUN",
                flush=True,
            )
            return 1
        (directory / "accepted").touch()
        print(f"PASS {case.name}", flush=True)
    print(
        f"Passed {len(selected)} selected cases; unselected cases NOT RUN", flush=True
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", choices=SUITES, default=[])
    parser.add_argument("--case", action="append", choices=CASES, default=[])
    parser.add_argument(
        "--list", action="store_true", help="list scopes/cases without running"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print selected commands only"
    )
    parser.add_argument(
        "--jit-timing",
        action="store_true",
        help="opt in to inclusive JIT/native-owner intervals for selected cases",
    )
    parser.add_argument(
        "--output", type=Path, help="new evidence directory (must not exist)"
    )
    parser.add_argument(
        "--timeout", type=int, default=600, help="seconds per live case"
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    selected = select(args.suite, args.case)
    # Record the opt-in with each case, including multi-session scripts. Do not
    # mutate the catalog or inherit ambient KD_* settings into ordinary runs.
    if args.jit_timing:
        selected = [
            replace(case, env={**case.env, "KD_JIT_TIMING": "1"})
            for case in selected
        ]
    if args.list or not selected:
        for name, cases in SUITES.items():
            print(f"{name} ({len(cases)}): {', '.join(cases)}")
        print("Covered diagnostics (--case only; ordinary coverage shown below):")
        for name, replacement in COVERED_DIAGNOSTICS.items():
            print(f"  {name}: {replacement}")
    if args.dry_run or args.list or not selected:
        for case in selected:
            print(f"{case.name}: {case.display()}")
        return 0
    if ROOT != Path("/root/host_fs/kdlock") or os.geteuid() != 0:
        parser.error(
            "live execution is restricted to root in the documented guest checkout"
        )
    if os.environ.get("KDLOCK_RECOVERY_CONFIRMED") != "1":
        parser.error(
            "confirm the recovery snapshot before setting KDLOCK_RECOVERY_CONFIRMED=1"
        )
    check_idle()
    if args.output:
        out = args.output.resolve()
        if out.is_relative_to(ROOT):
            parser.error("evidence must be outside the source checkout")
        out.mkdir(parents=True, exist_ok=False)
    else:
        out = Path(tempfile.mkdtemp(prefix="kdlock-regression.", dir="/tmp"))
    return run(selected, out, args.timeout)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"FAIL: {error}; remaining cases NOT RUN") from error

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import regression_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]
WORKERS = re.compile(
    r"sc_worker|kd_test|daemon|klock_test|kd_native|kd_renamed|kd_shadow_[0-2]|kd_mtask_[0-2]|kd_gate_[0-3]"
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


# Current module lifecycle only. Actual direct JIT scenarios are selected by
# bench/tclock_compare/run.py; obsolete transparent-hook cases are not runnable.
add("module", "test_01_module_load.sh")
SUITES = {"baseline": ("module",)}


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
    # Also reject legacy leftovers; deleted launchers do not prove they are absent.
    modules = Path("/proc/modules").read_text().splitlines()
    if any(
        line.split()[0] in ("kdlock_km", "spin_cacheline", "tclock_backend_km", "tc_allocator_guard",
                               "hotlock_record_bench", "klock_module", "kd_depth_source")
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
        "--output", type=Path, help="new evidence directory (must not exist)"
    )
    parser.add_argument(
        "--timeout", type=int, default=600, help="seconds per live case"
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    selected = select(args.suite, args.case)
    if args.list or not selected:
        for name, cases in SUITES.items():
            print(f"{name} ({len(cases)}): {', '.join(cases)}")
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

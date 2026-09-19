"""Protect selection and stop boundaries without loading a kernel module.

Complex live scripts remain the execution proof. These fixtures ensure a
request for one scope cannot silently become a baseline sweep or skip errors.
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import regression as r
from unit import run as unit_runner


class UnitSelectionTests(unittest.TestCase):
    """Grouping must preserve explicit selection without triggering a sweep."""

    def test_basename_and_group_path_select_the_same_driver(self):
        expected = unit_runner.ROOT / "infrastructure/test_regression.py"
        self.assertEqual(unit_runner.select("test_regression.py"), expected)
        self.assertEqual(unit_runner.select("infrastructure/test_regression.py"), expected)
        for invalid in ("missing.py", "../regression.py", "run.py"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                unit_runner.select(invalid)

    def test_ambiguous_basename_requires_a_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for group in ("one", "two"):
                (root / group).mkdir()
                (root / group / "test_example.py").touch()
            with patch.object(unit_runner, "ROOT", root):
                with self.assertRaises(ValueError):
                    unit_runner.select("test_example.py")
                self.assertEqual(unit_runner.select("one/test_example.py"),
                                 root / "one/test_example.py")

    def test_list_does_not_execute_and_selection_forwards_arguments(self):
        with patch.object(unit_runner.runpy, "run_path") as execute:
            for args in ([], ["--list"]):
                with patch.object(sys, "argv", ["run.py", *args]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        unit_runner.main()
            execute.assert_not_called()
            with patch.object(sys, "argv", ["run.py", "test_regression.py", "-v"]):
                unit_runner.main()
                selected = str(unit_runner.ROOT / "infrastructure/test_regression.py")
                self.assertEqual(sys.argv, [selected, "-v"])
                execute.assert_called_once_with(selected, run_name="__main__")


class SelectionTests(unittest.TestCase):
    def test_catalog_is_resolvable_and_has_unique_commands(self):
        commands = set()
        for name, case in r.CASES.items():
            self.assertEqual(name, case.name)
            self.assertTrue((r.ROOT / "tests" / case.script).is_file())
            identity = (tuple(case.command()), tuple(sorted(case.env.items())))
            self.assertNotIn(identity, commands)
            commands.add(identity)
        for suite in r.SUITES.values():
            self.assertTrue(suite)
            self.assertEqual(len(suite), len(set(suite)))
            self.assertTrue(set(suite) <= r.CASES.keys())
        for diagnostic, replacement in r.COVERED_DIAGNOSTICS.items():
            self.assertIn(diagnostic, r.CASES)
            self.assertIn(replacement, r.CASES)
            self.assertNotIn(replacement, r.COVERED_DIAGNOSTICS)

    def test_scopes_union_without_baseline_or_single_lock_repetition(self):
        selected = r.select(["mutex", "hostcall", "mutex"], ["mode-5", "mode-5"])
        self.assertEqual([c.name for c in selected], ["mode-4", "mode-5", "mode-2"])
        self.assertEqual(len(r.select(["mutex-parallel"], [])), 3)
        for suite in ("mutex-parallel", "mutex-native"):
            self.assertIn("parallel-node-pressure", r.SUITES[suite])
            self.assertNotIn("parallel-shared-cpu", r.SUITES[suite])
        self.assertTrue(set(r.SUITES["core"]).isdisjoint(r.SUITES["baseline"]))
        self.assertTrue(set(r.SUITES["core"]).isdisjoint(("mode-0", "mode-3")))

    def test_all_routine_scopes_leave_superseded_diagnostics_opt_in(self):
        # Enforce the coverage policy across every daily scope, not only core.
        # Keep these names selectable for isolation; do not silently remove an
        # explicitly requested diagnostic or weaken independent failure probes.
        diagnostics = {
            *r.SUITES["baseline"],
            *r.SUITES["native-controls"],
            "mode-0",
            "mode-1",
            "mode-3",
            "mode-6",
            "parallel-shared-cpu",
            "native-1-4",
            "native-1-3",
            "native-4-3",
            *(f"node-physical-{depth}-{numa}" for depth in (1, 2) for numa in (0, 1)),
        }
        routine = [
            name
            for name in r.SUITES
            if name not in ("baseline", "extended", "native-controls")
        ]
        for name in routine:
            with self.subTest(suite=name):
                self.assertTrue(diagnostics.isdisjoint(r.SUITES[name]))
        selected = r.select(routine + routine, [])
        names = [case.name for case in selected]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set().union(*(r.SUITES[name] for name in routine)))
        explicit = sorted(diagnostics)
        self.assertEqual([case.name for case in r.select([], explicit)], explicit)

    def test_extended_omits_only_reviewed_coverage_and_honors_explicit_cases(self):
        # A larger frame count must not silently remove a different lock-depth
        # contract. Only reviewed replacements leave the broad regression;
        # explicitly selected diagnostics are neither skipped nor substituted.
        covered = {
            "mode-0",
            "mode-1",
            "mode-3",
            "parallel-shared-cpu",
            "native-1-4",
            "native-1-3",
            "native-4-3",
            *(f"node-physical-{depth}-{numa}" for depth in (1, 2) for numa in (0, 1)),
        }
        self.assertEqual(set(r.COVERED_DIAGNOSTICS), covered)
        expected = (
            r.CASES.keys()
            - set(r.SUITES["baseline"])
            - set(r.SUITES["native-controls"])
            - covered
        )
        self.assertEqual(set(r.SUITES["extended"]), expected)
        self.assertIn("mode-6", expected)
        for suite in r.SUITES.values():
            self.assertTrue(covered.isdisjoint(suite))
        for name in sorted(covered):
            with self.subTest(case=name):
                self.assertEqual(r.select([], [name]), [r.CASES[name]])
                selected = r.select(["extended", "extended"], [name, name])
                self.assertEqual(
                    [case.name for case in selected], [*r.SUITES["extended"], name]
                )

    def test_native_controls_are_separate_explicit_register_cases(self):
        self.assertEqual(r.SUITES["native-controls"], ("control-0", "control-3"))
        for mode in (0, 3):
            case = r.CASES[f"control-{mode}"]
            self.assertEqual(
                case.command(),
                ["bash", "tests/live/test_10_native_resume.sh", str(mode), "1"],
            )
            self.assertEqual(
                case.env, {"KD_NATIVE_REGISTERS": "1", "KD_NATIVE_CONTROL": "1"}
            )
            for suite, names in r.SUITES.items():
                if suite != "native-controls":
                    self.assertNotIn(case.name, names)
        selected = r.select(["native-controls", "native-controls"], ["control-3"])
        self.assertEqual([case.name for case in selected], ["control-0", "control-3"])

    def test_waiter_exit_reuses_only_the_all_unlocked_remote_case(self):
        # Lifetime scheduling strengthens a complex case already selected;
        # it must not silently add a new case or affect ACK-owning ancestors.
        self.assertEqual(
            [
                name
                for name, case in r.CASES.items()
                if "KD_DEEP_WAITER_EXIT" in case.env
            ],
            ["remote-late-3"],
        )
        case = r.CASES["remote-late-3"]
        self.assertEqual(case.args, (4, 3))
        self.assertEqual(case.env["KD_DEEP_WAITER_EXIT"], "1")
        self.assertEqual(len(r.SUITES["extended"]), 64)
        self.assertEqual(r.select([], [case.name, case.name]), [case])

    def test_shared_cpu_upgrades_the_pending_mutex_case(self):
        self.assertEqual(
            [
                name
                for name, case in r.CASES.items()
                if "KD_NATIVE_SHARED_CPU" in case.env
            ],
            ["native-4-4"],
        )
        case = r.CASES["native-4-4"]
        self.assertEqual(case.args, (4, 4))
        self.assertEqual(
            case.env, {"KD_NATIVE_PENDING_CONTENDED": "1", "KD_NATIVE_SHARED_CPU": "1"}
        )
        self.assertEqual(len(r.SUITES["extended"]), 64)
        for mode, env, reason in (
            (4, {"KD_NATIVE_SHARED_CPU": "2"}, "must be 0 or 1"),
            (8, {}, "requires mode 4 stage 4"),
            (4, {"KD_NATIVE_PENDING_CONTENDED": "0"}, "requires mode 4 stage 4"),
            (4, {"KD_NATIVE_STACK_CHANGE": "1"}, "cannot combine with stack_change"),
        ):
            with self.subTest(mode=mode, env=env):
                child = r.child_environment(case)
                child.update(env)
                result = subprocess.run(
                    ["bash", "tests/live/test_10_native_resume.sh", str(mode), "4"],
                    cwd=r.ROOT,
                    env=child,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout + result.stderr)

    def test_distinct_paths_are_not_dropped_by_complex_case_selection(self):
        self.assertEqual(r.SUITES["hostcall"], ("mode-2", "mode-5"))
        self.assertEqual(len(r.SUITES["registers"]), 8)
        self.assertEqual(len(r.SUITES["admission"]), 12)
        self.assertEqual(
            r.CASES["native-mutex-depth"].env, {"KD_NATIVE_SOURCE_MODULE": "1"}
        )
        self.assertEqual(
            r.CASES["native-mutex-stack-change"].env,
            {"KD_NATIVE_PENDING_CONTENDED": "1", "KD_NATIVE_STACK_CHANGE": "1"},
        )
        self.assertIn("native-mutex-stack-change", r.SUITES["mutex-native"])
        # Physical depth eight fills the inherited ledger first. It cannot
        # replace the later local-shadow check at logical depth one.
        self.assertIn("shadow-capacity", r.SUITES["spin-native"])
        self.assertNotIn("shadow-capacity", r.COVERED_DIAGNOSTICS)
        for case in (
            "virtual-node-refusal",
            "virtual-context-refusal",
            "virtual-ticket-refusal",
        ):
            self.assertIn(case, r.SUITES["spin-native"])
        self.assertEqual(
            r.CASES["virtual-ticket-refusal"].env,
            {
                "KD_NATIVE_PENDING_CONTENDED": "1",
                "KD_NATIVE_VIRTUAL_RESOURCE": "3",
                "KD_NATIVE_GATE_PRESSURE": "1",
            },
        )
        for case in ("kernel-task-local", "kernel-task-cross-numa"):
            self.assertIn(case, r.SUITES["protocol"])
        # Cancellation while B remains held through A's final ACK is not the
        # release-race contract. Keep both addressable in broad acceptance;
        # routine signal runs need not implicitly add the forced-cancel cases.
        for name, api, signum, number in (
            ("waiter-interruptible", "int", 10, 1),
            ("waiter-killable", "kill", 9, 2),
        ):
            forced = r.CASES[name]
            self.assertEqual(forced.args, (4, 4))
            self.assertEqual(
                forced.env,
                {
                    "KD_NATIVE_PENDING_CONTENDED": "1",
                    "KD_NATIVE_WAITER_SIGNAL": str(signum),
                    "KD_NATIVE_WAITER_API": str(number),
                },
            )
            self.assertNotIn(name, r.COVERED_DIAGNOSTICS)
            self.assertIn(name, r.SUITES["extended"])
            self.assertNotIn(name, r.SUITES["mutex-signals"])
            for outcome in ("acquired", "cancelled", "either"):
                race = r.CASES[f"waiter-race-{api}-{outcome}"]
                self.assertEqual(race.command(), forced.command())
                self.assertEqual({key: race.env[key] for key in forced.env}, forced.env)
                self.assertEqual(race.env["KD_NATIVE_WAITER_RACE"], "1")
                self.assertEqual(race.env["KD_NATIVE_WAITER_EXPECT"], outcome)
                self.assertIn(race.name, r.SUITES["mutex-signals"])
                self.assertIn(race.name, r.SUITES["extended"])
                self.assertEqual(
                    r.select([], [name, race.name, name, race.name]), [forced, race]
                )

    def test_early_outer_dependency_is_not_a_held_b_register_duplicate(self):
        # Keep the dependency-breaking schedule independently selectable in
        # each backend, while removing only reviewed ordinary-success repeats.
        for backend, mode in (("spin", 1), ("mutex", 4)):
            with self.subTest(backend=backend):
                name = f"native-{backend}-outer-dependency"
                case = r.CASES[name]
                self.assertEqual(case.script, "live/test_10_native_resume.sh")
                self.assertEqual(case.args, (mode, 3))
                self.assertEqual(
                    case.env, {"KD_NATIVE_OOO": "3", "KD_NATIVE_OOO_DEPENDENCY": "2"}
                )
                for suite in (f"{backend}-native", "extended"):
                    self.assertIn(name, r.SUITES[suite])
                    selected = r.select([suite, suite], [name, name])
                    self.assertEqual(sum(item.name == name for item in selected), 1)
                self.assertNotIn(name, r.COVERED_DIAGNOSTICS)
                self.assertNotIn(name, r.SUITES["baseline"])
                diagnostic = f"native-{mode}-3"
                replacement = f"registers-{mode}-3"
                self.assertEqual(r.COVERED_DIAGNOSTICS[diagnostic], replacement)
                plain, checked = r.CASES[diagnostic], r.CASES[replacement]
                self.assertEqual(plain.command(), checked.command())
                self.assertEqual(plain.env, {})
                self.assertEqual(checked.env, {"KD_NATIVE_REGISTERS": "1"})
                self.assertEqual(r.select([], [diagnostic]), [plain])
        self.assertEqual(len(r.COVERED_DIAGNOSTICS), 11)
        self.assertEqual(len(r.SUITES["extended"]), 64)

    def test_acquired_spin_is_an_independent_post_call_boundary(self):
        case = r.CASES["native-spin-acquired"]
        self.assertEqual(case.args, (1, 3))
        self.assertEqual(case.env, {"KD_NATIVE_SPIN_ACQUIRED": "2"})
        self.assertIn(case.name, r.SUITES["spin-native"])
        self.assertIn(case.name, r.SUITES["extended"])
        self.assertNotIn(case.name, r.COVERED_DIAGNOSTICS)
        self.assertEqual(r.select([], [case.name, case.name]), [case])
        for mode, stage, env, reason in (
            (1, 3, {"KD_NATIVE_SPIN_ACQUIRED": "3"}, "must be 0, 1 or 2"),
            (4, 3, {}, "requires mode 1 stage 3"),
            (1, 4, {}, "requires mode 1 stage 3"),
            (1, 3, {"KD_NATIVE_REGISTERS": "1"}, "cannot combine with registers"),
            (1, 3, {"KD_NATIVE_OOO": "1"}, "cannot combine with ooo"),
            (
                1,
                3,
                {"KD_NATIVE_PENDING_CONTENDED": "1"},
                "cannot combine with pending_contended",
            ),
        ):
            with self.subTest(mode=mode, stage=stage, env=env):
                child = r.child_environment(case)
                child.update(env)
                result = subprocess.run(
                    ["bash", "tests/live/test_10_native_resume.sh", str(mode), str(stage)],
                    cwd=r.ROOT,
                    env=child,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout + result.stderr)

    def test_ambient_injection_cannot_change_a_named_case(self):
        with patch.dict(os.environ, {"KD_NATIVE_REGISTERS": "1", "KDLOCK_NUMA": "1"}):
            env = r.child_environment(r.CASES["parallel-drain-1"])
        self.assertNotIn("KD_NATIVE_REGISTERS", env)
        self.assertNotIn("KDLOCK_NUMA", env)
        self.assertEqual(env["KD_MUTEX_PARALLEL_FIRST"], "1")
        self.assertEqual(env["KDLOCK_RECOVERY_CONFIRMED"], "1")

    def test_hashes_ignore_kbuild_outputs_but_detect_real_source_edits(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(r, "ROOT", Path(directory)),
        ):
            module = r.ROOT / "kernel_module"
            module.mkdir()
            source = module / "entry.c"
            source.write_text("source")
            before = r.source_hashes()
            (module / "kdlock_km.mod.c").write_text("generated by Kbuild")
            self.assertEqual(r.source_hashes(), before)
            baseline = r.ROOT / "kernel_baseline"
            baseline.mkdir()
            for name in ("guest.config", "linux-6.1.159-guest.patch"):
                (baseline / name).write_text("captured kernel input")
                self.assertIn("kernel_baseline/" + name, r.source_hashes())
            # Dependency pins must be frozen, while generated text stays out.
            translator = r.ROOT / "disassem"
            translator.mkdir()
            requirements = translator / "requirements.txt"
            requirements.write_text("miasm==0.1.5\n")
            pinned = r.source_hashes()
            self.assertEqual(pinned["disassem/requirements.txt"],
                             r.evidence.digest(requirements.read_bytes()))
            (translator / "generated.txt").write_text("not a source input")
            self.assertEqual(r.source_hashes(), pinned)
            requirements.write_text("miasm==0.1.3\n")
            self.assertNotEqual(r.source_hashes(), pinned)
            source.write_text("changed source")
            self.assertNotEqual(r.source_hashes(), before)

    def test_listing_and_dry_run_never_check_or_execute_guest(self):
        with patch.object(r, "check_idle") as idle, patch.object(r, "run") as run:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                for args in ([], ["--list"], ["--suite", "mutex", "--dry-run"],
                             ["--case", "mode-5", "--jit-timing", "--dry-run"]):
                    self.assertEqual(r.main(args), 0)
            self.assertIn("mode-4", output.getvalue())
            self.assertIn("Covered diagnostics (--case only", output.getvalue())
            self.assertIn("mode-0: mode-2", output.getvalue())
            self.assertIn("KD_JIT_TIMING=1", output.getvalue())
            self.assertNotIn("KD_JIT_TIMING", r.CASES["mode-5"].env)
            with contextlib.redirect_stdout(io.StringIO()) as ordinary:
                self.assertEqual(r.main(["--case", "mode-5", "--dry-run"]), 0)
            self.assertNotIn("KD_JIT_TIMING", ordinary.getvalue())
            idle.assert_not_called()
            run.assert_not_called()

    def test_invalid_selection_and_unsafe_live_start_fail(self):
        with patch.object(r, "run") as run, contextlib.redirect_stderr(io.StringIO()):
            for args in (["--case", "missing"], ["--timeout", "0"]):
                with self.assertRaises(SystemExit):
                    r.main(args)
            with (
                patch.object(r, "ROOT", Path("/tmp/not-the-guest")),
                self.assertRaises(SystemExit),
            ):
                r.main(["--case", "pipeline"])
            with (
                patch.object(r, "ROOT", Path("/root/host_fs/kdlock")),
                patch.object(os, "geteuid", return_value=0),
                patch.dict(os.environ, {"KDLOCK_RECOVERY_CONFIRMED": "0"}),
                self.assertRaises(SystemExit),
            ):
                r.main(["--case", "pipeline"])
            run.assert_not_called()

    def test_explicit_timing_applies_to_loads_and_rejects_ambiguity(self):
        # Exercise the real shell selection with all privileged operations
        # substituted. The EXIT cleanup is removed before invoking any load.
        script = r'''
source "$1"
trap - EXIT
shift
unload_modules() { echo unloaded; }
insmod() { printf 'insmod:%s\n' "$*"; }
sysctl() { :; }
sleep() { :; }
cat() { printf '%s\n' "$TIMING_LOADED"; }
timeout() { printf 'timeout:%s %s\n' "$1" "$2"; shift 2; "$@"; }
TEST_NAME=timing
if [[ "$TIMING_LOADER" == direct ]]; then
    load_kdlock --timeout 45 target_process=klock_test "$@"
else
    load_modules klock_test "$@"
fi
'''
        scenarios = (
            (None, "N", (), True), ("0", "N", (), True),
            ("1", "Y", (), True), ("1", "N", (), False),
            ("bad", "Y", (), False), ("1", "Y", ("jit_timing=1",), False),
        )
        for loader, (chosen, loaded, extra, success) in (
            (loader, scenario) for loader in ("direct", "both") for scenario in scenarios
        ):
            env = r.child_environment(r.CASES["mode-5"])
            env["TIMING_LOADED"] = loaded
            env["TIMING_LOADER"] = loader
            if chosen is not None:
                env["KD_JIT_TIMING"] = chosen
            result = subprocess.run(
                ["bash", "-c", script, str(r.ROOT / "tests/live/test_08_mutex_jit_modes.sh"),
                 str(r.ROOT / "tests/common.sh"), *extra],
                env=env, capture_output=True, text=True, timeout=5,
            )
            with self.subTest(loader=loader, chosen=chosen, loaded=loaded, extra=extra):
                self.assertEqual(result.returncode == 0, success, result)
                if success:
                    self.assertEqual(result.stdout.count("insmod:"), 1 if loader == "direct" else 2)
                    if loader == "direct":
                        self.assertIn("timeout:--kill-after=10s 45s", result.stdout)
                    if chosen is not None:
                        self.assertIn(f"jit_timing={chosen}", result.stdout)
                        self.assertIn(f"JIT timing selection: loaded={loaded}", result.stdout)
                    else:
                        self.assertNotIn("jit_timing=", result.stdout)
                elif chosen == "bad" or extra:
                    if loader == "direct":
                        self.assertNotIn("unloaded", result.stdout)
                    self.assertNotIn("insmod:", result.stdout)
                else:
                    self.assertEqual(result.stdout.count("insmod:"), 1)
        # A new direct insmod would silently bypass the declared experiment.
        for path in (r.ROOT / "tests/live").glob("test_*.sh"):
            self.assertNotRegex(path.read_text(), r"insmod[^\n]*kdlock_km\.ko")

    def test_leftover_optional_source_stops_another_case(self):
        # A failed optional-source cleanup must not be hidden by a default
        # rebuild or an empty workload process list before the next case.
        with (
            patch.object(
                Path, "read_text", return_value="kd_depth_source 4096 0 - Live 0\n"
            ),
            patch.object(r.subprocess, "check_output") as processes,
            self.assertRaisesRegex(RuntimeError, "modules remain"),
        ):
            r.check_idle()
        processes.assert_not_called()


class ModeDispatchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "live"
        self.root.mkdir()
        self.script = self.root / "test_09_jit_execution_modes.sh"
        self.script.write_bytes((r.ROOT / "tests/live" / self.script.name).read_bytes())
        self.log = self.root / "dispatch.log"
        # Execute the production dispatcher, substituting only live backends.
        # These records prove selection/stop behavior, never JIT execution.
        for name in (
            "../run_all.sh",
            "test_04_spinlock.sh",
            "test_07_mutex_jit.sh",
            "test_08_mutex_jit_modes.sh",
            "test_24_gs_jit.sh",
        ):
            (self.root / name).write_text(
                'printf "%s:%s\\n" "${0##*/}" "$*" >>"$KD_DISPATCH_LOG"\n'
                'exit "${KD_DISPATCH_STATUS:-0}"\n'
            )

    def test_native_control_rejects_wrong_modes_before_live_setup(self):
        # Run the real driver's argument guard with no live helpers available.
        # A bad control selector must not reach build, module or daemon setup.
        script = self.root / "test_10_native_resume.sh"
        script.write_bytes((r.ROOT / "tests/live" / script.name).read_bytes())
        (self.root.parent / "common.sh").write_text(
            'set -euo pipefail\nfail() { printf "%s\\n" "$2"; }\n'
        )
        for control, registers, mode, stage in (
            (2, 1, 0, 1),
            (1, 0, 0, 1),
            (1, 1, 4, 2),
            (1, 1, 3, 2),
            (1, 1, 8, 3),
        ):
            with self.subTest(control=control, mode=mode, stage=stage):
                result = subprocess.run(
                    ["bash", str(script), str(mode), str(stage)],
                    env=os.environ
                    | {
                        "KDLOCK_RECOVERY_CONFIRMED": "1",
                        "KD_NATIVE_CONTROL": str(control),
                        "KD_NATIVE_REGISTERS": str(registers),
                    },
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, "")
                self.assertIn("KD_NATIVE_CONTROL=1 requires", result.stdout)

    def invoke(self, *modes, recovery="1", status=0):
        self.log.unlink(missing_ok=True)
        result = subprocess.run(
            ["bash", str(self.script), *modes],
            env=os.environ
            | {
                "KDLOCK_RECOVERY_CONFIRMED": recovery,
                "KD_DISPATCH_LOG": str(self.log),
                "KD_DISPATCH_STATUS": str(status),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def test_no_arguments_only_lists_without_recovery(self):
        result, calls = self.invoke(recovery="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["run_all.sh:--list"])
        self.assertNotIn("translated instructions executed", result.stdout)

    def test_repeated_modes_run_once_in_requested_order(self):
        result, calls = self.invoke("4", "5", "4", "0", "5", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                "test_08_mutex_jit_modes.sh:4",
                "test_08_mutex_jit_modes.sh:5",
                "test_04_spinlock.sh:0",
            ],
        )

    def test_explicit_diagnostics_and_gs_modes_keep_their_backends(self):
        result, calls = self.invoke("0", "1", "2", "3", "4", "5", "10", "11")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                "test_04_spinlock.sh:0",
                "test_04_spinlock.sh:1",
                "test_04_spinlock.sh:2",
                "test_07_mutex_jit.sh:",
                "test_08_mutex_jit_modes.sh:4",
                "test_08_mutex_jit_modes.sh:5",
                "test_24_gs_jit.sh:10",
                "test_24_gs_jit.sh:11",
            ],
        )
        self.assertIn("mode 10: translated GS execution", result.stdout)
        self.assertIn("mode 11: translated GS execution", result.stdout)

    def test_invalid_trailing_mode_stops_before_any_backend(self):
        for mode in ("6", "missing", "--list", "$(false)"):
            with self.subTest(mode=mode):
                result, calls = self.invoke("4", mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsupported mode", result.stdout)
                self.assertEqual(calls, [])

    def test_explicit_execution_still_requires_recovery(self):
        result, calls = self.invoke("4", recovery="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KDLOCK_RECOVERY_CONFIRMED", result.stdout)
        self.assertEqual(calls, [])

    def test_backend_failure_stops_without_success_or_later_execution(self):
        result, calls = self.invoke("4", "5", "4", status=17)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(calls, ["test_08_mutex_jit_modes.sh:4"])
        self.assertNotIn("[PASS]", result.stdout)


from regression_boundary_cases import BoundaryTests


from regression_evidence_cases import EvidenceTests


if __name__ == "__main__":
    unittest.main()

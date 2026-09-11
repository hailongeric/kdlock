"""Protect selection and stop boundaries without loading a kernel module.

Complex live scripts remain the execution proof. These fixtures ensure a
request for one scope cannot silently become a baseline sweep or skip errors.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import regression as r
import verify_evidence as verifier


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
                ["bash", "tests/test_10_native_resume.sh", str(mode), "1"],
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
                    ["bash", "tests/test_10_native_resume.sh", str(mode), "4"],
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
                self.assertEqual(case.script, "test_10_native_resume.sh")
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
                    ["bash", "tests/test_10_native_resume.sh", str(mode), str(stage)],
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
            source.write_text("changed source")
            self.assertNotEqual(r.source_hashes(), before)

    def test_listing_and_dry_run_never_check_or_execute_guest(self):
        with patch.object(r, "check_idle") as idle, patch.object(r, "run") as run:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                for args in ([], ["--list"], ["--suite", "mutex", "--dry-run"]):
                    self.assertEqual(r.main(args), 0)
            self.assertIn("mode-4", output.getvalue())
            self.assertIn("Covered diagnostics (--case only", output.getvalue())
            self.assertIn("mode-0: mode-2", output.getvalue())
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
        self.root = Path(directory.name)
        self.script = self.root / "test_09_jit_execution_modes.sh"
        self.script.write_bytes((r.ROOT / "tests" / self.script.name).read_bytes())
        self.log = self.root / "dispatch.log"
        # Execute the production dispatcher, substituting only live backends.
        # These records prove selection/stop behavior, never JIT execution.
        for name in (
            "run_all.sh",
            "test_04_spinlock.sh",
            "test_07_mutex_jit.sh",
            "test_08_mutex_jit_modes.sh",
            "test_12_context_native_only.sh",
        ):
            (self.root / name).write_text(
                'printf "%s:%s\\n" "${0##*/}" "$*" >>"$KD_DISPATCH_LOG"\n'
                'exit "${KD_DISPATCH_STATUS:-0}"\n'
            )

    def test_native_control_rejects_wrong_modes_before_live_setup(self):
        # Run the real driver's argument guard with no live helpers available.
        # A bad control selector must not reach build, module or daemon setup.
        script = self.root / "test_10_native_resume.sh"
        script.write_bytes((r.ROOT / "tests" / script.name).read_bytes())
        (self.root / "common.sh").write_text(
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

    def test_explicit_diagnostics_and_native_only_modes_keep_their_backends(self):
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
                "test_12_context_native_only.sh:10",
                "test_12_context_native_only.sh:11",
            ],
        )
        self.assertNotIn("mode 10: translated", result.stdout)
        self.assertNotIn("mode 11: translated", result.stdout)

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


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name)
        # Mock only the runner's environment; never bypass a live script's
        # oracle or claim these subprocess fixtures executed translated code.
        for name, value in (("source_hashes", {}), ("check_idle", None)):
            helper = patch.object(r, name, return_value=value)
            setattr(self, name, helper.start())
            self.addCleanup(helper.stop)
        for name, value in (("call", 0), ("check_output", "clean\n")):
            helper = patch.object(r.subprocess, name, return_value=value)
            setattr(self, name, helper.start())
            self.addCleanup(helper.stop)
        root = patch.object(r, "ROOT", self.out / "source")
        root.start()
        self.addCleanup(root.stop)
        environment = patch.object(r.evidence, "environment")
        self.environment = environment.start()
        self.addCleanup(environment.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        # Boundary fixtures need two cases, not the live scope's growing list.
        self.cases = r.select([], ["parallel-drain-0", "parallel-drain-1"])

    def test_two_successful_cases_and_evidence(self):
        self.assertEqual(r.run(self.cases, self.out, 60), 0)
        self.assertEqual(self.call.call_count, 2)
        for case in self.cases:
            for name in (
                "accepted",
                "exit-status",
                "dmesg.log",
                "artifacts.tar.gz",
                "protocol.tar.gz",
                "post-case-builds.tar.gz",
                "evidence.json",
                "result.json",
            ):
                self.assertTrue((self.out / case.name / name).exists())
            result = json.loads((self.out / case.name / "result.json").read_text())
            self.assertTrue(result["accepted"] and result["evidence_complete"])
        self.assertTrue((self.out / "source.tar.gz").is_file())
        self.assertEqual(self.check_idle.call_count, 4)
        command = self.call.call_args.args[0]
        self.assertEqual(command[:3], ["timeout", "--kill-after=5s", "60s"])
        args = self.environment.call_args.args
        self.assertEqual((args[0], args[2]), (self.out, r.ROOT))
        self.assertEqual(args[1], r.child_environment())

    def test_environment_failure_stops_before_any_workload(self):
        # Missing provenance must not be accepted as a passed/skipped workload.
        self.environment.side_effect = RuntimeError("environment capture failed")
        with self.assertRaisesRegex(RuntimeError, "environment capture failed"):
            r.run(self.cases, self.out, 60)
        self.call.assert_not_called()
        self.assertTrue((self.out / "source.tar.gz").is_file())
        self.assertFalse((self.out / self.cases[0].name).exists())

    def test_script_failure_and_timeout_stop_before_second_case(self):
        for status in (1, 124, 137):
            out = self.out / str(status)
            out.mkdir()
            self.call.reset_mock()
            self.call.return_value = status
            self.assertEqual(r.run(self.cases, out, 60), 1)
            self.call.assert_called_once()
            self.assertFalse((out / self.cases[0].name / "accepted").exists())
            self.assertFalse((out / self.cases[1].name).exists())
            result = json.loads((out / self.cases[0].name / "result.json").read_text())
            self.assertEqual(result["script_exit"], status)
            self.assertTrue(result["drained"] and result["evidence_complete"])
            self.assertFalse(result["accepted"])

    def test_zero_exit_with_kernel_fault_is_not_accepted(self):
        self.check_output.return_value = "BUG: fixture kernel fault"
        self.assertEqual(r.run(self.cases, self.out, 60), 1)
        self.call.assert_called_once()
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())

    def test_incomplete_drain_stops_without_unloading(self):
        self.check_idle.side_effect = [None, RuntimeError("still active")]
        with patch.object(r.evidence, "collect_case") as capture:
            self.assertEqual(r.run(self.cases, self.out, 60), 1)
            capture.assert_not_called()
        self.call.assert_called_once()
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())
        result = json.loads((self.out / self.cases[0].name / "result.json").read_text())
        self.assertFalse(result["drained"] or result["evidence_complete"])
        self.assertIn("still active", result["errors"][0])

    def test_source_changes_invalidate_current_result(self):
        self.source_hashes.side_effect = [{}, {}, {"changed.c": "new"}]
        self.assertEqual(r.run(self.cases, self.out, 60), 1)
        self.call.assert_called_once()
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())
        result = json.loads((self.out / self.cases[0].name / "result.json").read_text())
        self.assertFalse(result["source_unchanged"])
        self.assertIn("source changed during", result["errors"][0])

    def test_capture_error_or_missing_dmesg_never_creates_acceptance(self):
        for failure in ("archive", "dmesg"):
            out = self.out / failure
            out.mkdir()
            target = r.evidence if failure == "archive" else r.subprocess
            method = "collect_case" if failure == "archive" else "check_output"
            self.call.reset_mock()
            with patch.object(target, method, side_effect=OSError(failure)):
                self.assertEqual(r.run(self.cases, out, 60), 1)
            self.call.assert_called_once()
            result = json.loads((out / self.cases[0].name / "result.json").read_text())
            self.assertFalse(result["accepted"])
            self.assertTrue(result["errors"])
            self.assertFalse((out / self.cases[1].name).exists())

    def test_failed_oracle_still_retains_generated_bytes(self):
        # Failure evidence must survive the next manual cleanup, without
        # turning that retained image into an accepted or executed JIT result.
        image = r.ROOT / "daemon/0x123/asm/jit.bin"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"captured generated bytes")
        self.call.return_value = 17
        self.assertEqual(r.run(self.cases, self.out, 60), 1)
        path = self.out / self.cases[0].name / "artifacts.tar.gz"
        with tarfile.open(path) as archive:
            self.assertEqual(
                archive.extractfile("daemon/0x123/asm/jit.bin").read(),
                image.read_bytes(),
            )
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())

    def test_stop_marker_does_not_interrupt_current_case(self):
        def finish(*args, **kwargs):
            (self.out / "STOP").touch()
            return 0

        self.call.side_effect = finish
        self.assertEqual(r.run(self.cases, self.out, 60), 93)
        self.call.assert_called_once()
        self.assertTrue((self.out / self.cases[0].name / "accepted").exists())
        self.assertFalse((self.out / self.cases[1].name).exists())

    def offline_run(self, status=0):
        # Reuse the real collector and existing substituted runner, not a
        # handwritten archive layout or any native/JIT execution claim.
        # Real captures live outside the checkout. Keep this fixture's source
        # separate too, so an extra case directory is not silently tolerated.
        source_directory = tempfile.TemporaryDirectory(prefix="kdlock-offline-source-")
        self.addCleanup(source_directory.cleanup)
        root = patch.object(r, "ROOT", Path(source_directory.name))
        root.start()
        self.addCleanup(root.stop)
        source = r.ROOT / "fixture.c"
        source.write_bytes(b"frozen fixture, never compiled\n")
        self.source_hashes.return_value = {
            "fixture.c": r.evidence.digest(source.read_bytes())
        }

        def environment(out, *args):
            notes = b"fixture boot notes"
            (out / "kernel.notes").write_bytes(notes)
            r.evidence.write_json(
                out / "environment.json",
                {"errors": {}, "kernel_notes_sha256": r.evidence.digest(notes)},
            )

        self.environment.side_effect = environment
        self.call.return_value = status
        return r.run(self.cases, self.out, 60)

    def test_offline_verification_uses_archived_bytes_and_never_runs_payloads(self):
        self.assertEqual(self.offline_run(), 0)
        (r.ROOT / "fixture.c").write_text("current checkout differs from old capture")
        for operation in (self.call, self.check_output, self.check_idle):
            operation.reset_mock()
        before = {p: p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        report = verifier.verify_run(self.out)
        self.assertTrue(report["all_recorded_accepted"])
        self.assertEqual(report["source_files"], 1)
        self.assertEqual(report["unrecorded_cases"], [])
        self.assertEqual(
            [c["name"] for c in report["cases"]], [c.name for c in self.cases]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(verifier.main([str(self.out)]), 0)
        self.assertEqual(json.loads(output.getvalue()), report)
        for operation in (self.call, self.check_output, self.check_idle):
            operation.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_offline_recorded_failure_and_unrecorded_cases_never_pass(self):
        self.assertEqual(self.offline_run(17), 1)
        report = verifier.verify_run(self.out)
        self.assertFalse(report["all_recorded_accepted"])
        self.assertFalse(report["cases"][0]["recorded_accepted"])
        self.assertEqual(report["unrecorded_cases"], [self.cases[1].name])
        self.assertEqual(verifier.main([str(self.out)]), 1)
        # No result is not proof of process termination or even of nonexecution.
        (self.out / self.cases[1].name).mkdir()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(verifier.main([str(self.out)]), 2)

    def test_offline_rejects_inconsistent_manifests_status_logs_and_links(self):
        self.assertEqual(self.offline_run(), 0)
        case = self.out / self.cases[0].name
        result = json.loads((case / "result.json").read_text())
        changes = [
            (self.out / "source.json", b"{}"),
            (self.out / "source.tar.gz", b"corrupted archive"),
            (self.out / "kernel.notes", b"different boot"),
            (self.out / "environment.json", b'{"errors":{},"errors":{"lost":"probe"}}'),
            (self.out / "results.tsv", b"duplicate\t0\nduplicate\t0\n"),
            (case / "exit-status", b"17\n"),
            (case / "dmesg.log", b"BUG: not recorded in the result\n"),
            (case / "accepted", b"not an empty marker"),
            (case / "result.json", json.dumps(result | {"accepted": 1}).encode()),
            (
                case / "result.json",
                json.dumps(result | {"errors": ["lost evidence"]}).encode(),
            ),
        ]
        for path, data in changes:
            old = path.read_bytes()
            with self.subTest(path=path, data=data[:40]):
                try:
                    path.write_bytes(data)
                    with self.assertRaises((RuntimeError, ValueError)):
                        verifier.verify_run(self.out)
                finally:
                    path.write_bytes(old)
        path = case / "protocol.tar.gz"
        old = path.read_bytes()
        path.unlink()
        with self.assertRaises(OSError):
            verifier.verify_run(self.out)
        path.symlink_to(self.out / "source.tar.gz")
        with self.assertRaises(RuntimeError):
            verifier.verify_run(self.out)
        path.unlink()
        path.write_bytes(old)
        extra = self.out / "unselected-case"
        extra.mkdir()
        with self.assertRaisesRegex(RuntimeError, "unselected"):
            verifier.verify_run(self.out)

    def test_offline_archive_members_need_exact_hashes_and_safe_unique_names(self):
        self.assertEqual(self.offline_run(), 0)
        case = self.out / self.cases[0].name
        manifest = json.loads((case / "evidence.json").read_text())
        name, payload = "daemon/0x1/asm/jit.bin", b"never execute these bytes"
        for damage in (
            "duplicate",
            "link",
            "device",
            "traversal",
            "missing",
            "extra",
            "hash",
        ):
            # Update the outer hash too, to exercise member validation rather
            # than stopping at the compressed-file checksum every time.
            with self.subTest(damage=damage):
                path = case / "artifacts.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    info = tarfile.TarInfo(
                        "../outside" if damage == "traversal" else name
                    )
                    info.size = len(payload)
                    if damage == "link":
                        info.type, info.linkname, info.size = (
                            tarfile.SYMTYPE,
                            "/etc/shadow",
                            0,
                        )
                    elif damage == "device":
                        info.type, info.size = tarfile.CHRTYPE, 0
                    if damage != "missing":
                        archive.addfile(info, io.BytesIO(payload))
                    if damage == "duplicate":
                        archive.addfile(info, io.BytesIO(payload))
                manifest["archives"]["artifacts"] = {
                    "sha256": r.evidence.digest(path.read_bytes()),
                    "files": {}
                    if damage == "extra"
                    else {
                        name: "0" * 64
                        if damage == "hash"
                        else r.evidence.digest(payload)
                    },
                }
                r.evidence.write_json(case / "evidence.json", manifest)
                expected = {
                    "duplicate": "duplicate archive member",
                    "link": "unsafe archive member",
                    "device": "unsafe archive member",
                    "traversal": "unsafe archive member",
                    "missing": "hashes/membership mismatch",
                    "extra": "unlisted archive member",
                    "hash": "hashes/membership mismatch",
                }
                with self.assertRaisesRegex(RuntimeError, expected[damage]):
                    verifier.verify_run(self.out)
        self.assertFalse((self.out / "outside").exists())

    def test_offline_read_limits_and_cross_file_mutation_are_not_silent(self):
        self.assertEqual(self.offline_run(), 0)
        for limit in ("MAX_METADATA", "MAX_ARCHIVE", "MAX_EXPANDED", "MAX_MEMBERS"):
            with (
                self.subTest(limit=limit),
                patch.object(verifier, limit, 0),
                self.assertRaisesRegex(RuntimeError, "limit"),
            ):
                verifier.verify_run(self.out)
        original = verifier.Snapshot.archive

        def mutate(snapshot, path, record):
            value = original(snapshot, path, record)
            if path.name == "protocol.tar.gz":
                # Keep JSON valid; only the end-of-inspection identity check
                # can detect a previously read file changing in this schedule.
                env = self.out / "environment.json"
                env.write_bytes(env.read_bytes() + b"\n")
            return value

        with (
            patch.object(verifier.Snapshot, "archive", mutate),
            self.assertRaisesRegex(RuntimeError, "changed file"),
        ):
            verifier.verify_run(self.out)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="kdlock-evidence-", dir="/tmp")
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.root = self.base / "checkout"
        self.out = self.base / "run"
        self.case = self.out / "case"
        self.root.mkdir()
        self.case.mkdir(parents=True)
        (self.case / "output.log").write_text("")

    def collect(self, text=""):
        (self.case / "output.log").write_text(text)
        return r.evidence.collect_case(self.root, self.out, self.case)

    def test_source_archive_contains_exact_bytes_and_rejects_changed_inputs(self):
        path = self.root / "fixture.c"
        path.write_bytes(b"source\n")
        frozen = {"fixture.c": r.evidence.digest(path.read_bytes())}
        r.evidence.freeze_source(self.root, self.out, frozen)
        with tarfile.open(self.out / "source.tar.gz") as archive:
            self.assertEqual(archive.extractfile("fixture.c").read(), b"source\n")
        other = self.base / "changed"
        other.mkdir()
        path.write_bytes(b"edited\n")
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            r.evidence.freeze_source(self.root, other, frozen)
        self.assertFalse((other / "source.tar.gz").exists())
        self.assertTrue((other / "source.tar.gz.partial").exists())

    def test_protocol_tree_and_log_declarations_are_deduplicated(self):
        protocol = self.base / "protocol"
        protocol.mkdir()
        nested = protocol / "writer"
        nested.mkdir()
        (nested / "result.json").write_text('{"closed": true}\n')
        daemon = protocol / "daemon.log"
        daemon.write_text("translation finished\n")
        result = self.collect(
            f"  [INFO] Evidence: {protocol}\nEvidence: {protocol}\n"
            f"Evidence: {nested}\n  [INFO] Evidence file: {daemon}\n"
        )
        self.assertEqual(result["directories"], [str(protocol)])
        self.assertEqual(result["files"], [])
        with tarfile.open(self.case / "protocol.tar.gz") as archive:
            self.assertEqual(len(archive.getmembers()), 2)
            self.assertEqual(
                archive.extractfile(str(daemon.relative_to(Path("/tmp")))).read(),
                b"translation finished\n",
            )

    def test_standalone_log_and_post_case_build_bytes_are_preserved(self):
        log = self.base / "daemon.log"
        log.write_text("not a JIT execution witness\n")
        binary = self.root / "daemon/daemon"
        binary.parent.mkdir()
        binary.write_bytes(b"post-case build, not loaded identity")
        result = self.collect(f"Evidence file: {log}\nEvidence file: {log}\n")
        self.assertEqual(result["files"], [str(log)])
        builds = result["archives"]["post-case-builds"]
        self.assertEqual(
            builds["files"], {"daemon/daemon": r.evidence.digest(binary.read_bytes())}
        )
        self.assertEqual(
            builds["sha256"],
            r.evidence.digest((self.case / "post-case-builds.tar.gz").read_bytes()),
        )

    def test_protocol_symlinks_are_metadata_never_followed_or_extracted(self):
        protocol = self.base / "protocol"
        protocol.mkdir()
        link = protocol / "compiler.py"
        target = self.base / "outside.py"
        target.write_text("must not be read through the protocol link\n")
        link.symlink_to(target)
        # A dangling link and a directory link are also non-payload metadata.
        (protocol / "missing").symlink_to(self.base / "missing-target")
        (protocol / "outside-dir").symlink_to(self.root, target_is_directory=True)
        result = self.collect(f"Evidence: {protocol}\n")
        self.assertEqual(len(result["symlinks"]), 3)
        self.assertEqual(
            result["symlinks"][str(link.relative_to(Path("/tmp")))], str(target)
        )
        with tarfile.open(self.case / "protocol.tar.gz") as archive:
            self.assertEqual(archive.getmembers(), [])
        self.assertNotIn("must not be read", (self.case / "evidence.json").read_text())

    def test_invalid_or_recursive_declared_paths_are_refused(self):
        for path in (
            "/etc/passwd",
            "/tmp/unrelated.log",
            "/tmp/kdlock-x/../secret",
            str(self.case),
            str(self.out),
            str(self.base),
        ):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                r.evidence.declared_paths(f"Evidence: {path}\n", self.out)

    def test_missing_declared_directory_and_file_are_errors(self):
        for kind in ("", " file"):
            with self.subTest(kind=kind), self.assertRaises((RuntimeError, OSError)):
                self.collect(f"Evidence{kind}: {self.base / 'missing'}\n")
            for path in self.case.glob("*.gz*"):
                path.unlink()
        self.assertFalse((self.case / "evidence.json").exists())

    def test_symlinks_and_special_files_are_not_archived(self):
        regular = self.base / "plain"
        regular.write_text("payload")
        for kind in ("file-link", "directory-link", "fifo"):
            target = self.base / kind
            if kind == "file-link":
                target.symlink_to(regular)
            elif kind == "directory-link":
                target.symlink_to(self.root, target_is_directory=True)
            else:
                os.mkfifo(target)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                r.evidence.tree_files(self.base)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                r.evidence.regular_bytes(target)
            target.unlink()

    def test_late_same_name_log_mutation_invalidates_capture(self):
        protocol = self.base / "protocol"
        protocol.mkdir()
        log = protocol / "role.log"
        log.write_text("original\n")
        real_archive = r.evidence.archive_files

        def mutate(destination, files, expected=None):
            result = real_archive(destination, files, expected)
            if destination.name == "protocol.tar.gz":
                log.write_text("late writer\n")
            return result

        with (
            patch.object(r.evidence, "archive_files", side_effect=mutate),
            self.assertRaisesRegex(RuntimeError, "evidence changed after"),
        ):
            self.collect(f"Evidence: {protocol}\n")
        self.assertFalse((self.case / "evidence.json").exists())

    def test_environment_retains_boot_dependencies_and_only_build_environment(self):
        # Reuse the real read-only guest capture; it is neither a build nor a
        # translated-code execution, and must never dump unrelated env secrets.
        env = r.child_environment()
        env["UNRELATED_TOKEN"] = "do not archive this value"
        env["CFLAGS"] = "-O1 -g"
        r.evidence.environment(self.out, env, r.ROOT)
        record = json.loads((self.out / "environment.json").read_text())
        self.assertEqual(record["uname"]["release"], os.uname().release)
        self.assertEqual(
            record["kernel_notes_sha256"],
            r.evidence.digest((self.out / "kernel.notes").read_bytes()),
        )
        self.assertTrue(record["online_cpus"])
        self.assertEqual(record["stage"], "before_cases")
        self.assertEqual(record["cwd"], str(r.ROOT))
        self.assertIn("preempt", record["runtime_settings"])
        self.assertFalse(record["errors"])
        self.assertIn("filesystems", record["mount"])
        self.assertEqual(record["build_environment"]["CFLAGS"], "-O1 -g")
        self.assertEqual(record["build_environment"]["LC_ALL"], "C")
        self.assertNotIn("UNRELATED_TOKEN", record["build_environment"])
        self.assertNotIn("do not archive this value", json.dumps(record))
        self.assertEqual(
            set(record["python"]["packages"]),
            {"miasm", "pyelftools", "future", "pyparsing"},
        )
        for name, probe in record["tools"].items():
            with self.subTest(tool=name):
                self.assertEqual(probe["returncode"], 0)
                self.assertNotIn("error", probe)
                self.assertEqual(
                    probe["sha256"],
                    r.evidence.digest(Path(probe["resolved"]).read_bytes()),
                )

    def test_probe_preserves_selected_path_and_bounds_failures(self):
        # Hash the target, but preserve the path used to launch a venv/tool.
        tools = self.root / "bin"
        tools.mkdir()
        binary = tools / "python-real"
        binary.write_bytes(b"fixture only: never executed")
        binary.chmod(0o755)
        link = tools / "python3"
        link.symlink_to(binary)
        env = {"PATH": "bin"}
        command = ["python3", "--version"]
        with patch.object(r.evidence.subprocess, "run") as launch:
            launch.return_value = subprocess.CompletedProcess(command, 0, "v\n", "")
            probe = r.evidence.command_observation(command, env, self.root)
            self.assertNotIn("error", probe)
            self.assertEqual(probe["resolved"], str(binary))
            self.assertEqual(launch.call_args.args[0], [str(link), "--version"])
            self.assertEqual(launch.call_args.kwargs["timeout"], 10)
            self.assertEqual(launch.call_args.kwargs["cwd"], self.root)
            for failure in (
                OSError("unavailable"),
                subprocess.TimeoutExpired(command, 10),
            ):
                launch.side_effect = failure
                probe = r.evidence.command_observation(command, env, self.root)
                self.assertIn("error", probe)
            launch.side_effect = None
            launch.return_value = subprocess.CompletedProcess(command, 17, "", "bad")
            probe = r.evidence.command_observation(command, env, self.root)
            self.assertEqual(probe["returncode"], 17)
            self.assertEqual(probe["stderr"], "bad")
            self.assertIn("error", probe)
            launch.reset_mock()
            probe = r.evidence.command_observation(["missing"], env, self.root)
            self.assertIn("error", probe)
            launch.assert_not_called()

    def test_failed_or_malformed_environment_probe_is_retained_not_accepted(self):
        for failure in ({"error": "missing package"}, {"stdout": "not JSON"}):
            with (
                self.subTest(probe=failure),
                patch.object(
                    r.evidence,
                    "command_observation",
                    side_effect=lambda *args, record=failure: record.copy(),
                ),
                self.assertRaisesRegex(RuntimeError, "environment capture failed"),
            ):
                r.evidence.environment(self.out, r.child_environment(), r.ROOT)
            record = json.loads((self.out / "environment.json").read_text())
            self.assertIn("error", record["tools"]["python3"])
            self.assertTrue((self.out / "kernel.notes").is_file())

        # A missing debugfs observation also retains a manifest and stops; it
        # must not look like a verified runtime configuration or a clean SKIP.
        read_text = Path.read_text

        def missing_preempt(path, *args, **kwargs):
            if str(path) == "/sys/kernel/debug/sched/preempt":
                raise PermissionError("preempt observation denied")
            return read_text(path, *args, **kwargs)

        with (
            patch.object(Path, "read_text", missing_preempt),
            patch.object(
                r.evidence, "command_observation", return_value={"stdout": "{}"}
            ),
            self.assertRaisesRegex(RuntimeError, "runtime_settings.preempt"),
        ):
            r.evidence.environment(self.out, r.child_environment(), r.ROOT)
        record = json.loads((self.out / "environment.json").read_text())
        self.assertIn(
            "preempt observation denied", record["errors"]["runtime_settings.preempt"]
        )


if __name__ == "__main__":
    unittest.main()

"""Guest-only caller-lifetime checks for production continuation probes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import mock_open, patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "jit_escape_runner", ROOT / "tests/kernel/jit_escape/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class OriginalInstructionReceipts(unittest.TestCase):
    def delta(self, entered=7, completed=7, native=0, instructions=0, reentries=0, suffixes=0):
        return dict(bench_jit_bodies=entered, bench_jit_completions=completed,
                    native_escape_count=native, origin_instruction_count=instructions,
                    origin_reentry_count=reentries, origin_suffix_count=suffixes)

    def test_cold_service_and_post_instruction_suffix_are_distinct(self):
        runner.validate_execution(self.delta(), False, True, 4)
        runner.validate_execution(self.delta(instructions=28, reentries=28), True, True, 4)
        runner.validate_execution(self.delta(instructions=7, reentries=7), True, True)
        runner.validate_execution(self.delta(completed=0, instructions=7, suffixes=7), True, True, 4, True)
        runner.validate_execution(self.delta(completed=0, native=7), True, False)

    def test_missing_reentry_replay_and_mixed_fallback_are_rejected(self):
        good = self.delta(instructions=28, reentries=28)
        for field, value in (('origin_instruction_count', 29), ('origin_reentry_count', 27),
                             ('origin_reentry_count', 29), ('origin_suffix_count', 1),
                             ('native_escape_count', 1), ('bench_jit_completions', 0)):
            with self.subTest(field=field, value=value), self.assertRaises(runner.rt.Failure):
                runner.validate_execution(dict(good, **{field:value}), True, True, 4)
        with self.assertRaises(runner.rt.Failure):
            runner.validate_execution(self.delta(completed=0, instructions=28, suffixes=7), True, True, 4, True)
        with self.assertRaises(runner.rt.Failure):
            runner.validate_execution(self.delta(entered=0, completed=0), False, True)

spec = importlib.util.spec_from_file_location(
    "address_guard_runner", ROOT / "tests/kernel/spin/address_guard/run.py")
address_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(address_runner)
spec = importlib.util.spec_from_file_location(
    "string_service_runner", ROOT / "tests/kernel/spin/string_service/run.py")
string_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(string_runner)


class Probe(runner.EscapeSession):
    """Use real phase/execute control flow without devices or kernel work."""
    def __init__(self, path):
        self.path = path
        self.translation_source = ROOT
        self.record = dict(cpus=[0, 1], worker_roles=["writer", "reader"],
                           reader_iterations=4, phase_timeout=1,
                           execution_status="PREPARING", drained=False)
        self.kmsg = os.open("/dev/null", os.O_RDONLY)
        self.cleanups = 0

    def prepare(self):
        pass

    def measure(self):
        self.phase("probe", 3, 0)

    def cleanup(self):
        self.cleanups += 1
        self.record["drained"] = True

    def verify(self):
        pass

    def save(self):
        pass

    def counts(self, label):
        return dict(hot=0)

    def counters(self):
        return dict(bench_jit_bodies=0, bench_jit_completions=0, native_escape_count=0)

    def faults(self):
        pass


class Caller:
    def __init__(self, argv, index, failure):
        self.args, self.pid = argv, 1000 + index
        self.failure = failure
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        if self.failure == "wait-timeout" or (
                self.failure == "partial-join" and self.pid == 1001):
            raise subprocess.TimeoutExpired(self.args, timeout)
        if self.failure == "wait-io":
            raise OSError("wait failed")
        # A nonzero exit after every join is safe for ordinary cleanup.
        self.returncode = 1
        return self.returncode


class AddressProbe(Probe):
    phase = address_runner.EscapeSession.phase


class StringProbe(Probe):
    phase = string_runner.StringSession.phase


native_spec = importlib.util.spec_from_file_location(
    "jit_native_call_runner", ROOT / "tests/kernel/jit_native_call/run.py")
native_runner = importlib.util.module_from_spec(native_spec)
native_spec.loader.exec_module(native_runner)


class NativeCallProbe(Probe):
    phase = native_runner.NativeCallSession.phase

    def counters(self):
        return dict(bench_jit_bodies=0, bench_jit_completions=0,
                    native_escape_count=0, native_call_probe_count=0,
                    native_started=0, native_completed=0, native_unlocks=0)


class CallerLifetimeTests(unittest.TestCase):
    def exercise(self, failure, runner=runner, probe=Probe):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            session, callers = probe(folder), []
            original_read = Path.read_text
            original_write = runner.rt.write_json
            original_barrier = getattr(runner, "publish_barrier", None)

            def spawn(argv, **kwargs):
                index = len(callers)
                if failure == "spawn" and index == 1:
                    raise OSError("spawn failed")
                caller = Caller(argv, index, failure)
                callers.append(caller)
                if original_barrier:
                    ready = folder / "probe-barrier" / f"ready-{index}.json"
                    value = dict(pid=caller.pid, cpu=index,
                                 role=session.record["worker_roles"][index],
                                 comm=runner.WORKER_COMM)
                    ready.write_text("{" if failure == "ready-json" else json.dumps(value))
                return caller

            def read(path, *args, **kwargs):
                if failure == "ready-io" and path.name.startswith("ready-"):
                    raise OSError("readiness read failed")
                return original_read(path, *args, **kwargs)

            def write(path, value):
                if failure == "receipt" and path.name.endswith("-callers.json"):
                    raise OSError("receipt write failed")
                return original_write(path, value)

            def barrier(path, value):
                if failure == "go":
                    raise OSError("GO publication failed")
                return original_barrier(path, value)

            with patch.object(runner.subprocess, "Popen", side_effect=spawn), \
                    patch.object(runner, "image_registry", return_value=[]), \
                    patch.object(Path, "read_text", read), \
                    patch.object(runner.rt, "write_json", side_effect=write), \
                    patch.object(runner, "publish_barrier", side_effect=barrier, create=True):
                with self.assertRaises(runner.rt.Failure) as raised:
                    session.execute()
            error = raised.exception
            saved = session.record["phases"][0]["callers"]
            self.assertEqual([row["pid"] for row in saved], [p.pid for p in callers])
            with self.assertRaises(OSError):
                os.fstat(session.kmsg)
            return session, callers, error

    def test_every_unjoined_failure_retains_callers_and_skips_cleanup(self):
        for failure in ("spawn", "receipt", "ready-json", "ready-io", "go",
                        "wait-timeout", "wait-io", "partial-join"):
            with self.subTest(failure=failure):
                session, callers, error = self.exercise(failure)
                self.assertTrue(error.unsafe)
                self.assertEqual(session.cleanups, 0)
                self.assertFalse(session.record["drained"])
                self.assertTrue(any(p.returncode is None for p in callers))

    def test_joined_worker_error_can_use_normal_cleanup(self):
        session, callers, error = self.exercise("joined-error")
        self.assertFalse(error.unsafe)
        self.assertEqual(error.status, "DATA_ERROR")
        self.assertTrue(all(p.returncode == 1 for p in callers))
        self.assertEqual(session.cleanups, 1)
        self.assertTrue(session.record["drained"])

    def test_address_string_and_native_callers_follow_the_same_join_rule(self):
        for module, probe in ((address_runner, AddressProbe),
                              (string_runner.probe, StringProbe),
                              (native_runner, NativeCallProbe)):
            for failure in ("spawn", "receipt", "wait-timeout", "wait-io", "partial-join"):
                with self.subTest(probe=probe.__name__, failure=failure):
                    session, callers, error = self.exercise(failure, module, probe)
                    self.assertTrue(error.unsafe)
                    self.assertEqual(session.cleanups, 0)
                    self.assertFalse(session.record["drained"])
                    self.assertTrue(any(p.returncode is None for p in callers))
            with self.subTest(probe=probe.__name__, failure="joined-error"):
                session, callers, error = self.exercise("joined-error", module, probe)
                self.assertFalse(error.unsafe)
                self.assertEqual(error.status, "DATA_ERROR")
                self.assertTrue(all(p.returncode == 1 for p in callers))
                self.assertEqual(session.cleanups, 1)
                self.assertTrue(session.record["drained"])


class RepeatedMarkerProbe(runner.EscapeSession):
    """Drive real measure/registry validators; only device/work receipts are fake."""
    def __init__(self, path, failure=None, family="mutex"):
        self.path, self.failure = path, failure
        self.current_phase = None
        self.names = []
        self.messages = ""
        self.image = dict(status=0, entry=0x1000, lock_kind=2 if family in ("mutex", "rwsem") else 1,
                          entry_abi={"mutex": 2, "rwsem": 2, "spin": 1, "rwlock": 3}[family],
                          generation=7, code=0x9000, requirements=1 if family in ("mutex", "rwsem") else 33)
        self.record = dict(warmup_iterations=10, iterations=10,
                           layout=dict(entry=0x1000, marker=0x1010),
                           registry_kind=self.image["lock_kind"], entry_abi=self.image["entry_abi"],
                           image_registry=[dict(self.image)], publication={"image": "exact-bytes"})

    def phase(self, name, iterations, hot, force_suffix=False):
        # This probe exercises ordinary reached markers, not instruction service.
        assert force_suffix is False
        self.current_phase = name
        self.names.append(name)
        delta = dict(bench_jit_bodies=5, bench_jit_completions=0 if hot else 5,
                     native_escape_count=5 if hot else 0)
        if self.failure == "no-cold-return" and name == "cold-after-escape":
            delta = dict.fromkeys(delta, 0)
        if self.failure == "no-repeated-marker" and name == "hot-repeat":
            delta = dict.fromkeys(delta, 0)
        if self.failure == "marker-count-mismatch" and hot:
            delta["native_escape_count"] = 4
        if self.failure == "native-counted-complete" and hot:
            delta["bench_jit_completions"] = 1
        if hot:
            (self.path / (name + "-callers.json")).write_text(json.dumps([
                dict(pid=123, role="writer"), dict(pid=124, role="reader")]))
            # Rate limiting may suppress the second phase's log entirely.
            if name == "hot-escape":
                pid = 124 if self.failure == "reader-marker" else 123
                action = ("native_suffix_and_disable" if self.failure == "old-action" else
                          "native_suffix_keep_eligible")
                self.messages += (f"reason=NATIVE_ESCAPE entry=0x1000 rip=0x1010 generation=7 "
                                  f"waiter_pid={pid} action={action}\n")
        return dict(name=name, jit_delta=delta)

    def current_registry(self):
        image = dict(self.image)
        if self.current_phase == "hot-escape":
            if self.failure == "sticky-ban":
                image["status"] = -3
            elif self.failure == "new-generation":
                image["generation"] += 1
        return [image]

    def publication(self):
        if self.failure == "changed-bytes" and self.current_phase == "hot-repeat":
            return {"image": "different-bytes"}
        return dict(self.record["publication"])

    def verify(self):
        pass

    def save(self):
        pass

    def faults(self):
        pass


class RepeatedMarkerTests(unittest.TestCase):
    def exercise(self, failure=None, family="mutex"):
        with tempfile.TemporaryDirectory() as directory:
            session = RepeatedMarkerProbe(Path(directory), failure, family)
            with patch("builtins.open", mock_open()), \
                    patch.object(runner.fcntl, "ioctl") as ioctl, \
                    patch.object(runner, "image_registry", side_effect=session.current_registry), \
                    patch.object(runner.rt, "parameters", return_value={}):
                runner.EscapeSession.measure(session)
            self.assertEqual([call.args[1] for call in ioctl.call_args_list],
                             [runner.COLD, runner.HOT, runner.COLD, runner.HOT])
            self.assertEqual(session.names, ["cold-warmup", "cold-delegated", "hot-escape",
                                             "cold-after-escape", "hot-repeat"])
            self.assertTrue(session.record["accepted"])
            self.assertEqual(session.record["jit_status"], "COLD_JIT_TAKEN_NATIVE_COLD_JIT_TAKEN_NATIVE")

    def test_each_family_requires_cold_taken_cold_taken_same_image(self):
        for family in ("mutex", "spin", "rwlock", "rwsem"):
            with self.subTest(family=family):
                self.exercise(family=family)

    def test_lost_eligibility_identity_and_completion_are_failures(self):
        for failure in ("no-cold-return", "no-repeated-marker", "marker-count-mismatch",
                        "native-counted-complete", "reader-marker", "old-action", "sticky-ban",
                        "new-generation", "changed-bytes"):
            with self.subTest(failure=failure), self.assertRaises(runner.rt.Failure):
                self.exercise(failure)


if __name__ == "__main__":
    unittest.main()

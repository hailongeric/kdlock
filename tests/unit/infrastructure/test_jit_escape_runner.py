"""Guest-only caller-lifetime checks for the production instruction probe."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "jit_escape_runner", ROOT / "tests/kernel/jit_escape/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


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


class CallerLifetimeTests(unittest.TestCase):
    def exercise(self, failure):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            session, callers = Probe(folder), []
            original_read = Path.read_text
            original_write = runner.rt.write_json
            original_barrier = runner.publish_barrier

            def spawn(argv, **kwargs):
                index = len(callers)
                if failure == "spawn" and index == 1:
                    raise OSError("spawn failed")
                caller = Caller(argv, index, failure)
                callers.append(caller)
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
                    patch.object(runner, "publish_barrier", side_effect=barrier):
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


if __name__ == "__main__":
    unittest.main()

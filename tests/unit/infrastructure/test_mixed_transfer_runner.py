"""Guest-only checks of the live mixed-transfer runner's setup and diagnostics.

No device/module work here: real runner decisions use explicit process, clock
and snapshot substitutes. The compiled payload and live staging remain separate.
"""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, mock_open, patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "mixed_transfer_runner", ROOT / "tests/kernel/mutex/mixed_transfer/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Probe(runner.MixedSession):
    def __init__(self, path):
        self.path = path
        self.record = dict(cpus=list(range(5)), warmup_iterations=5000, warmup_rounds=2)
        self.save = Mock()
        self.faults = Mock()


class MixedTransferRunnerTests(unittest.TestCase):
    def test_abort_only_closes_external_start_barrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "abort-starts.json").write_text("{}")
            go = path / "test-3-go.json"
            for already_released in (False, True):
                if already_released:
                    go.write_text("{}")
                with self.assertRaises(runner.rt.Failure) as failure:
                    runner.wait_worker_start(go)
                self.assertEqual(failure.exception.status, "SETUP_ABORTED")

    def test_observation_overlay_changes_only_export(self):
        original = (ROOT / "kernel_module/kd_hotlock.c").read_text()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "kernel_module/kd_hotlock.c"
            path.parent.mkdir()
            path.write_text(original)
            receipt = runner.observe_hotlock(root)
            export = "\nEXPORT_SYMBOL_GPL(kd_hotlock_query_mutex);"
            self.assertEqual(path.read_text().replace(export, ""), original)
            self.assertNotEqual(receipt["before"], receipt["after"])
            with self.assertRaises(runner.rt.Failure):
                runner.observe_hotlock(root)

    def test_snapshot_wire_keeps_signed_waiter_error(self):
        values = list(range(36)) + [-11]

        def ioctl(device, command, buffer, mutate):
            self.assertEqual(command, 0x81284D02)
            self.assertEqual(len(buffer), 296)
            buffer[:] = struct.pack("=36Qq", *values)

        with patch("builtins.open", mock_open()), patch.object(runner.fcntl, "ioctl", ioctl):
            self.assertEqual(runner.snapshot(), dict(zip(runner.FIELDS, values)))

    def test_failed_wait_preserves_last_snapshot_and_process_status(self):
        for reason in ("timeout", "payload", "exit"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)
                probe = Probe(path)
                process = Mock()
                process.poll.return_value = 7 if reason == "exit" else None
                observations = [dict(failures=0, gate=2, waiters=0),
                                dict(failures=int(reason == "payload"), gate=1, waiters=0)]
                if reason == "exit":
                    observations = observations[:1]
                clock = [0, 0, .01, 1]
                with patch.object(runner, "snapshot", side_effect=observations), \
                     patch.object(runner.time, "monotonic", side_effect=clock), \
                     patch.object(runner.time, "sleep"), \
                     self.assertRaises(runner.rt.Failure):
                    probe.wait_state("combiner-queued", lambda row: row["waiters"] == 1,
                                     [(process, dict(pid=123, role=runner.COMBINER))], timeout=.1)
                failure = json.loads((path / "combiner-queued.failed.json").read_text())
                self.assertEqual(failure["last_snapshot"], observations[-1])
                self.assertEqual(failure["callers"][0]["returncode"], process.poll.return_value)
                self.assertEqual(probe.record["failed_wait"], failure)
                process.terminate.assert_not_called()
                process.kill.assert_not_called()
                process.wait.assert_not_called()

    def test_warm_requires_each_actual_role_cpu(self):
        for eventual_hot in (False, True):
            with self.subTest(eventual_hot=eventual_hot), tempfile.TemporaryDirectory() as tmp:
                probe = Probe(Path(tmp))
                probe.launch = Mock(side_effect=lambda role, warm, round_number:
                                    (Mock(), dict(role=role, warm=warm, warm_round=round_number)))
                probe.wait_receipts = Mock()
                probe.join = Mock(return_value=[])
                rows = [dict(warm_ops=25000, prefix=0, suffix=0, started=0,
                             warm_eligible=1 << runner.WAITER),
                        dict(warm_ops=50000, prefix=0, suffix=0, started=0,
                             warm_eligible=runner.REQUIRED_ELIGIBILITY if eventual_hot else 0)]
                probe.counts = Mock(side_effect=rows)
                with patch.object(runner, "publish") as publish:
                    if eventual_hot:
                        self.assertEqual(probe.warm(), rows[-1])
                    else:
                        with self.assertRaises(runner.rt.Failure):
                            probe.warm()
                    self.assertEqual(publish.call_count, 2)
                self.assertEqual(probe.launch.call_count, 10)
                self.assertEqual(len(probe.record["warm_rounds"]), 2)

    def test_staging_owns_gate_before_queueing(self):
        class Staged(Exception):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            probe = Probe(Path(tmp))
            probe.verify = Mock()
            probe.launch = Mock(side_effect=lambda role: (Mock(), dict(role=role)))
            probe.wait_receipts = Mock()
            probe.warm = Mock()
            probe.counters = Mock(return_value=dict(bench_jit_bodies=1, bench_jit_completions=1))
            calls = []
            states = {
                "preholder-held": dict(ready=16, owner=200, t_task=200, gate=0),
                "gate-acquiring": dict(ready=17, owner=200, t_task=200, gate=2, entry_eligible=1),
                "gate-held": dict(owner=100, g_task=100, gate=1, preholder_done=1),
                "spin-held": dict(ready=19, b_word=1),
                "combiner-queued": dict(waiters=1, tail=77, entry_eligible=5),
                "waiter-queued": dict(waiters=2, tail=88, ready=31,
                                      entry_checked=13, entry_eligible=13),
            }

            def wait_state(label, predicate, processes):
                calls.append(label)
                self.assertTrue(predicate(states[label]), label)
                if label == "gate-held":
                    self.assertFalse(predicate(dict(states[label], gate=0)))
                return states[label]

            def control(command):
                calls.append(command)
                if command == runner.RELEASE:
                    raise Staged()

            probe.wait_state = wait_state
            with patch.object(runner, "publish"), patch.object(runner, "control", control), \
                 self.assertRaises(Staged):
                probe.measure()
            self.assertEqual(calls, [runner.ARM, "preholder-held", "gate-acquiring",
                                    runner.PREHOLDER_RELEASE, "gate-held", "spin-held",
                                    "combiner-queued", "waiter-queued", runner.RELEASE])


if __name__ == "__main__":
    unittest.main()

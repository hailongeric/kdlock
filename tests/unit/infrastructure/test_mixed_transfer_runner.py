"""Guest-only checks of the live mixed-transfer runner's setup and diagnostics.

No device/module work here: real runner decisions use explicit process, clock
and snapshot substitutes. The compiled payload and live staging remain separate.
"""
import importlib.util
import copy
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
        self.record = dict(cpus=list(range(5)), warmup_iterations=5000, warmup_rounds=2,
                           protocol="owner-handoff", case="simple")
        self.save = Mock()
        self.faults = Mock()
        self.messages = ""


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
        values = list(range(47)) + [-11]

        def ioctl(device, command, buffer, mutate):
            self.assertEqual(command, 0x81804D02)
            self.assertEqual(len(buffer), 384)
            buffer[:] = struct.pack("=47Qq", *values)

        with patch("builtins.open", mock_open()), patch.object(runner.fcntl, "ioctl", ioctl):
            self.assertEqual(runner.snapshot(), dict(zip(runner.FIELDS, values)))

    def test_outer_release_overlay_changes_only_existing_quiet_sink(self):
        source = (ROOT / "kernel_module/mutex/combiner.inc").read_text()
        loud = 'pr_info("kd_mutex outer release:'
        quiet = 'KD_PR_ROUTINE("kd_mutex outer release:'
        self.assertEqual(source.count(loud), 1)
        prepared = source.replace(loud, quiet, 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "kernel_module/mutex/combiner.inc"
            path.parent.mkdir(parents=True)
            path.write_text(prepared)
            receipt = runner.observe_outer_release(root)
            self.assertEqual(path.read_text(), source)
            self.assertEqual(receipt["path"], "kernel_module/mutex/combiner.inc")
            self.assertEqual(receipt["sites"], ["kd_mutex outer release:"])
            self.assertNotEqual(receipt["before"], receipt["after"])
            for invalid in (source, prepared + "\n" + quiet):
                path.write_text(invalid)
                with self.assertRaises(runner.rt.Failure):
                    runner.observe_outer_release(root)
                self.assertEqual(path.read_text(), invalid)

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
                with patch.object(runner, "publish") as publish, \
                     patch.object(runner, "validate_context", return_value=["checked"]) as contexts:
                    if eventual_hot:
                        self.assertEqual(probe.warm(), rows[-1])
                    else:
                        with self.assertRaises(runner.rt.Failure):
                            probe.warm()
                    self.assertEqual(publish.call_count, 2)
                    self.assertEqual(contexts.call_args_list,
                                     [unittest.mock.call([], "", "warmup")] * 2)
                self.assertEqual(probe.launch.call_count, 10)
                self.assertEqual(len(probe.record["warm_rounds"]), 2)
                self.assertTrue(all(row["contexts"] == ["checked"]
                                    for row in probe.record["warm_rounds"]))

    def test_original_context_requires_zero_migration_for_each_joined_role(self):
        workers = [dict(pid=100 + role, role=role) for role in range(5)]
        for phase in ("warmup", "run"):
            rows = [dict(phase=phase, role=str(role), pid=str(100 + role),
                         preempt_before="0", preempt_after="0", migration_before="0",
                         migration_after="0", irqs_before="0", irqs_after="0", errors="0")
                    for role in range(5)]

            def messages(values):
                return "".join("KD_MIXED_CONTEXT " + " ".join(f"{k}={v}" for k, v in row.items())
                               + "\n" for row in values)

            self.assertEqual(runner.validate_context(workers, messages(rows), phase), rows)
            for mutation in ("migration_before", "migration_after", "preempt_after", "irqs_after",
                             "errors", "role", "missing", "duplicate", "pid", "field", "phase"):
                with self.subTest(phase=phase, mutation=mutation):
                    changed = copy.deepcopy(rows)
                    if mutation in ("migration_before", "migration_after", "preempt_after",
                                    "irqs_after", "errors"):
                        changed[3][mutation] = "1"
                    elif mutation == "role":
                        changed[3]["role"] = "2"
                    elif mutation == "missing":
                        changed.pop()
                    elif mutation == "duplicate":
                        changed.append(copy.deepcopy(changed[3]))
                    elif mutation == "pid":
                        changed[3]["pid"] = "999"
                    elif mutation == "field":
                        del changed[3]["migration_after"]
                    else:
                        changed[3]["phase"] = "run" if phase == "warmup" else "warmup"
                    with self.assertRaises(runner.rt.Failure):
                        runner.validate_context(workers, messages(changed), phase)

    def test_warm_context_failure_prevents_eligibility_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Probe(Path(tmp))
            probe.launch = Mock(return_value=(Mock(), {}))
            probe.wait_receipts = Mock()
            probe.join = Mock(return_value=[])
            probe.counts = Mock()
            with patch.object(runner, "publish"), self.assertRaises(runner.rt.Failure):
                probe.warm()
            probe.counts.assert_not_called()

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
            probe.native_escape_count = Mock(return_value=0)
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

    def evidence(self, protocol="role-swap", case="simple"):
        early_waiter = case.startswith("w-early")
        swapped = protocol == "role-swap"
        native = not swapped or case == "c-native"
        record = dict(protocol=protocol, case=case, cpus=list(range(5)),
                      workers=[dict(role=role, pid=100 + role) for role in range(5)],
                      layout=dict(a=0xa, entry=0x100, spin_call=0x200, native_marker=0x300))
        after = dict(prefix=1, suffix=1, combiner_bodies=1, c_task=0xc, w_task=0xd,
                     owner_before=0xc, owner_after=0xd, samples=2, steal_attempts=10000,
                     steals=0, done=31, ready=31, started=31, prefix_observed=1, thief_done=1,
                     protocol=runner.PROTOCOLS.index(protocol), test_case=runner.CASES.index(case),
                     combiner_owner=0xd if swapped and not early_waiter else 0xc,
                     early_unlocked=int("early" in case), early_inner_held=int("early" in case),
                     c_native_task=0xc if case == "c-native" else 0,
                     c_native_owner=0xd if case == "c-native" else 0,
                     c_native_flags=0x95 if case == "c-native" else 0,
                     c_native_visits=int(case == "c-native"))
        delta = dict(bench_jit_bodies=2 if swapped and not early_waiter else 1,
                     bench_jit_completions=int(swapped and case in ("simple", "c-early-spin")))
        messages = ("kd_mutex role exchange: outer=a executor=102 owner=103 queued=111 head=222\n"
                    if swapped else "kd_mutex transfer: outer=a executor=102 owner=103 target=200 pending=1\n")
        if native:
            role, cpu, ip = (102, 3, "300") if swapped else (103, 2, "200")
            messages += (f"kd_native begin: task={role} outer=a entry=100 ip={ip} sp=999 "
                         f"held=1 mutex=1 cpu={cpu} outer_released=0 remaining=1\n"
                         f"kd_native ack: task={role} lock=a mutex=1 last_spin=0\n"
                         f"kd_native complete: task={role} outer=a mutex=1\n")
        if case == "c-early-spin":
            messages += "kd_mutex outer release: task=102 owner=103 owner_task=d outer=a next_task=0 remaining=1\n"
        return record, after, delta, messages

    def test_distinct_protocol_and_case_evidence(self):
        for protocol, cases in (("owner-handoff", ("simple",)), ("role-swap", runner.CASES)):
            for case in cases:
                with self.subTest(protocol=protocol, case=case):
                    evidence = self.evidence(protocol, case)
                    result = runner.validate_result(*evidence)
                    count = "1" if protocol == "owner-handoff" or case == "c-native" else "0"
                    self.assertEqual(result["expected_native_stats"],
                                     dict(started=count, completed=count, unlocks=count))

    def test_exchange_offer_does_not_replace_returned_c_jit(self):
        for field, replacement in (("completion", 0), ("owner", 0xc), ("bodies", 1)):
            with self.subTest(field=field):
                record, after, delta, messages = self.evidence()
                if field == "completion":
                    delta["bench_jit_completions"] = replacement
                elif field == "owner":
                    after["combiner_owner"] = replacement
                else:
                    delta["bench_jit_bodies"] = replacement
                with self.assertRaises(runner.rt.Failure):
                    runner.validate_result(record, after, delta, messages)

    def test_c_native_requires_new_executor_and_original_task_flags_ack(self):
        for mutation in ("task", "flags", "executor", "old-w-ack"):
            with self.subTest(mutation=mutation):
                record, after, delta, messages = self.evidence(case="c-native")
                if mutation == "task":
                    after["c_native_task"] = after["w_task"]
                elif mutation == "flags":
                    after["c_native_flags"] ^= 1
                elif mutation == "executor":
                    messages = messages.replace("cpu=3", "cpu=2")
                else:
                    messages = messages.replace("kd_native ack: task=102", "kd_native ack: task=103")
                with self.assertRaises(runner.rt.Failure):
                    runner.validate_result(record, after, delta, messages)

    def test_early_inner_lock_and_no_unexpected_w_relay(self):
        for case in ("c-early-spin", "w-early-spin", "w-early-mutex"):
            record, after, delta, messages = self.evidence(case=case)
            with self.subTest(case=case, mutation="inner-released"):
                with self.assertRaises(runner.rt.Failure):
                    runner.validate_result(record, dict(after, early_inner_held=0), delta, messages)
            with self.subTest(case=case, mutation="old-relay"):
                with self.assertRaises(runner.rt.Failure):
                    runner.validate_result(record, after, delta, messages +
                                           "kd_native ack: task=103 lock=a mutex=1 last_spin=0\n")
            if case.startswith("w-early"):
                with self.subTest(case=case, mutation="combining-under-B"):
                    with self.assertRaises(runner.rt.Failure):
                        runner.validate_result(record, after,
                            dict(bench_jit_bodies=2, bench_jit_completions=1), messages)

    def test_native_only_status_requires_exact_c_escape_and_immutable_identity(self):
        record, _, _, _ = self.evidence(case="c-native")
        record["publication"] = dict(
            entry=dict(status=0, pid=0, tgid=0, lock_kind=2, entry=0x100, code=0x400,
                       entry_abi=2, requirements=1, generation=7),
            source=dict(state=0, frames=0, writers=1, modules=1),
            images={name: name + "-hash" for name in ("jit.bin", "jit.S", "bin.txt")})
        after = copy.deepcopy(record["publication"])
        after["entry"]["status"] = -3
        message = ("[KD_JIT][WARN] reason=NATIVE_ESCAPE entry=0x100 rip=0x300 "
                   "generation=7 waiter_pid=102 action=native_suffix_and_disable\n")
        self.assertEqual(len(runner.validate_native_publication(record, after, message, 1)), 1)
        for mutation in ("status", "code", "generation", "image", "frames", "wrong-case",
                         "wrong-marker", "wrong-task", "wrong-count", "duplicate"):
            with self.subTest(mutation=mutation):
                changed, spec, trace, delta = copy.deepcopy(after), copy.deepcopy(record), message, 1
                if mutation in ("status", "code", "generation"):
                    changed["entry"][mutation] += 1
                elif mutation == "image":
                    changed["images"]["jit.bin"] = "replaced"
                elif mutation == "frames":
                    changed["source"]["frames"] = 1
                elif mutation == "wrong-case":
                    spec["case"] = "simple"
                elif mutation == "wrong-marker":
                    trace = trace.replace("rip=0x300", "rip=0x301")
                elif mutation == "wrong-task":
                    trace = trace.replace("waiter_pid=102", "waiter_pid=103")
                elif mutation == "wrong-count":
                    delta = 0
                else:
                    trace += trace
                with self.assertRaises(runner.rt.Failure):
                    runner.validate_native_publication(spec, changed, trace, delta)


if __name__ == "__main__":
    unittest.main()

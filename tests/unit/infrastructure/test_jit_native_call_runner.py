"""Guest-only validation oracles; device and caller work is explicitly mocked."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import mock_open, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("native_call_runner", ROOT / "tests/kernel/jit_native_call/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RepeatedCallProbe(runner.NativeCallSession):
    """Run the actual phase ordering/identity validators, with synthetic receipts."""
    def __init__(self, path, mode, failure=None):
        self.path, self.mode, self.failure = path, mode, failure
        self.names, self.messages, self.current_phase = [], "", None
        self.image = dict(status=0, pid=0, tgid=0, lock_kind=2, entry=0x1000, code=0x9000,
                          jump_from=0, target=0, entry_abi=2, requirements=0, generation=7)
        self.record = dict(warmup_iterations=10, iterations=10, call_mode=mode,
            layout=dict(entry=0x1000, call_site=0x1010, native_target=0x8000, lock_address=0x5000),
            call_audit=dict(length=5 if mode == "direct" else 2), entry_abi=2, registry_kind=2,
            image_registry=[dict(self.image)], publication={"bytes": "exact-image"})

    def phase(self, name, iterations, hot):
        self.names.append(name)
        self.current_phase = name
        delta = dict(bench_jit_bodies=5, bench_jit_completions=0 if hot else 5,
                     native_call_probe_count=5 if hot else 0, native_escape_count=0,
                     native_started=5 if hot else 0, native_completed=5 if hot else 0,
                     native_unlocks=5 if hot else 0)
        if self.failure == "no-cold-return" and name == "cold-after-native":
            delta = dict.fromkeys(delta, 0)
        if self.failure == "no-repeat" and name == "taken-repeat":
            delta = dict.fromkeys(delta, 0)
        for fail, key in (("missing-call", "native_call_probe_count"),
                          ("missing-begin", "native_started"), ("missing-complete", "native_completed"),
                          ("missing-unlock", "native_unlocks")):
            if self.failure == fail and hot:
                delta[key] -= 1
        if self.failure == "instruction-marker" and hot:
            delta["native_escape_count"] = 1
        if self.failure == "native-counted-complete" and hot:
            delta["bench_jit_completions"] = 1
        if name == "taken-native" and self.failure != "missing-event":
            reason = "INDIRECT_CALL_NATIVE" if self.mode == "indirect" else "NATIVE_CALL_TERMINAL"
            if self.failure == "wrong-reason": reason = "CALL_LIMIT_NATIVE"
            task = 999 if self.failure == "wrong-task" else 123
            target = 0x8001 if self.failure == "wrong-target" else 0x8000
            lock = 0x5001 if self.failure == "wrong-lock" else 0x5000
            entry = 0x1001 if self.failure == "wrong-entry" else 0x1000
            return_ip = 0x1010 + self.record["call_audit"]["length"] + int(self.failure == "wrong-return")
            sp = 0 if self.failure == "zero-stack" else 0x6000
            hostcall = int(self.failure == "hostcall")
            self.messages += (f"reason={reason} entry={entry:#x} ip={target:#x} sp={sp:#x} "
                              f"return={return_ip:#x} lock={lock:#x} task={task} hostcall={hostcall}\n")
        return dict(name=name, jit_delta=delta, callers=[dict(pid=123)])

    def publication(self):
        return {"bytes": "changed" if self.failure == "changed-bytes" and self.current_phase == "taken-repeat"
                else "exact-image"}

    def faults(self): pass
    def save(self): pass
    def verify(self): pass


class NativeCallRunnerTests(unittest.TestCase):
    def test_actual_call_label_and_encoding_gate(self):
        direct = ("0000000000000010 <jit_native_call_site>:\n"
                  "  10: e8 00 00 00 00     call 15 <native_call_body+0x15>\n"
                  "       11: R_X86_64_PLT32 _raw_spin_trylock-0x4\n")
        self.assertEqual(runner.audit_call(direct, "direct")["length"], 5)
        for raw, length in (("ff d0", 2), ("41 ff d3", 3)):
            text = f"0000000000000010 <jit_native_call_site>:\n  10: {raw}  call *%r11\n"
            self.assertEqual(runner.audit_call(text, "indirect")["length"], length)
        rejected = ((direct.replace("_raw_spin_trylock", "kd_spin_trylock"), "direct"),
                    (direct.replace("  10:", "  11:"), "direct"),
                    (direct.replace(" e8 ", " e9 "), "direct"),
                    (direct.replace("  call ", "  jmp "), "direct"),
                    (direct, "indirect"))
        for text, mode in rejected:
            with self.subTest(text=text), self.assertRaises(runner.rt.Failure):
                runner.audit_call(text, mode)
        for raw in ("ff e0", "ff 10", "f3 ff d0", "41 ff d3 90", "c3"):
            with self.subTest(raw=raw), self.assertRaises(runner.rt.Failure):
                runner.audit_call(f"0000000000000010 <jit_native_call_site>:\n  10: {raw} call *%rax\n", "indirect")

    def exercise(self, mode, failure=None):
        with tempfile.TemporaryDirectory() as folder:
            probe = RepeatedCallProbe(Path(folder), mode, failure)
            def registry():
                row = dict(probe.image)
                if probe.current_phase == "taken-repeat":
                    if failure == "changed-generation": row["generation"] += 1
                    if failure == "sticky-native": row["status"] = -3
                    if failure == "changed-code": row["code"] += 1
                return [row]
            with patch("builtins.open", mock_open()), patch.object(runner.fcntl, "ioctl"), \
                    patch.object(runner, "image_registry", side_effect=registry), \
                    patch.object(runner.rt, "parameters", return_value={}):
                probe.measure()
            return probe

    def test_repeated_direct_and_fresh_indirect_share_no_image_invalidation(self):
        for mode in ("direct", "indirect"):
            with self.subTest(mode=mode):
                probe = self.exercise(mode)
                self.assertTrue(probe.record["accepted"])
                self.assertEqual(probe.names, ["cold-warmup", "cold-delegated", "taken-native",
                                               "cold-after-native", "taken-repeat"])
                # Repeated phase needs its own positive count even when ratelimited
                # logs appear only for the first phase.
                self.assertEqual(len(probe.record["call_events"]), 1)

    def test_missing_effects_ack_or_exact_identity_are_rejected(self):
        failures = ("no-cold-return", "no-repeat", "missing-call", "missing-begin", "missing-complete",
                    "missing-unlock", "instruction-marker", "native-counted-complete", "missing-event",
                    "wrong-reason", "wrong-task", "wrong-target", "wrong-lock", "wrong-entry", "wrong-return",
                    "zero-stack", "hostcall", "changed-bytes", "changed-generation", "sticky-native", "changed-code")
        for mode in ("direct", "indirect"):
            for failure in failures:
                with self.subTest(mode=mode, failure=failure), self.assertRaises(runner.rt.Failure):
                    self.exercise(mode, failure)

    def test_private_overlay_only_observes_validated_and_existing_relay_counters(self):
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder)
            wrapper = tree / "kernel_module/execution/wrapper_entry.inc"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text((ROOT / "kernel_module/execution/wrapper_entry.inc").read_text())
            ledger = tree / "kernel_module/kd_exec.c"
            ledger.write_text((ROOT / "kernel_module/kd_exec.c").read_text())
            before = wrapper.read_text()
            runner.observe_provider(tree, tree / "observation.patch")
            after = wrapper.read_text()
            body = after[after.index("static int kd_jit_pending_call_native("):]
            expected = before[before.index("static int kd_jit_pending_call_native("):]
            counter = ('\tif (!strcmp(reason, "NATIVE_CALL_TERMINAL") || !strcmp(reason, "INDIRECT_CALL_NATIVE"))\n'
                       '\t\tatomic64_inc(&kd_native_call_probe_count);\n')
            self.assertEqual(body.replace(counter, "", 1), expected)
            self.assertLess(body.index("kd_exec_frame_save_continuation(frame, regs);"), body.index(counter))
            self.assertIn("atomic64_read(&kd_native_started)", ledger.read_text())
            self.assertIn("atomic64_read(&kd_native_completed)", ledger.read_text())
            self.assertIn("atomic64_read(&kd_native_unlocks)", ledger.read_text())
            self.assertIn("a/kernel_module/execution/wrapper_entry.inc", (tree / "observation.patch").read_text())
            with self.assertRaises(runner.rt.Failure):
                runner.observe_provider(tree, tree / "second.patch")


if __name__ == "__main__":
    unittest.main()

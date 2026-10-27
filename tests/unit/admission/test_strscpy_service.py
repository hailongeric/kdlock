"""Ordinary-call selection and legacy provider-only destination-write models."""
import struct
import unittest

from miasm.expression.expression import ExprId, ExprInt, ExprMem

from test_jit_diagnostics import decode, render, translator
from context_guards import EntryGuards
from context_registers import ContextFlowLimit
from context_values import FlowConstants
import context_memory
import hostcall
import strscpy_service as service


ADDRESSES = {"strscpy_pad": 0x2000}


def set_register(tracker, name, value):
    register = ExprId(name, 64)
    constant = ExprInt(value, 64)
    tracker.values[register] = frozenset({constant})
    tracker.origins[register] = constant


def call_graph():
    raw = b"\xe8" + struct.pack("<i", ADDRESSES["strscpy_pad"] - 0x1005) + b"\xc3"
    blocks, databases = translator.decode_regions([(raw, 0x1000, [0x1000])], 0,
                                                  {ADDRESSES["strscpy_pad"]})
    return blocks[0x1000].lines[0], databases[blocks[0x1000]]


class StrscpyServiceTests(unittest.TestCase):
    def reader(self, address, size):
        self.fail("original strscpy_pad code or data must not be inspected")

    def tracker(self):
        tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
        for name, value in (("RSP", 0x8000), ("RBP", 0x8100), ("RDI", 0x8040),
                            ("RSI", 0x9000), ("RDX", 64), ("RBX", 0x1234),
                            ("R12", 0x5678)):
            set_register(tracker, name, value)
        return tracker

    def test_legacy_writer_capability_cannot_select_a_string_summary(self):
        lookup = lambda name, default=0: ADDRESSES.get(name, default)
        for writing in (False, True):
            for audited in (False, True):
                resolved = hostcall.resolve_hostcalls(
                    lookup, string_write=writing, audited_strings=audited)
                self.assertNotIn(0x2000, resolved)
                self.assertEqual(service.targets(resolved), set())

    def test_missing_writer_is_an_ordinary_call_without_special_requirement(self):
        for count in (0, 16, 63, 64, 65):
            prefix = bytes.fromhex("488d7d90be00900000ba") + struct.pack("<I", count)
            raw = prefix + b"\xe8" + struct.pack("<i", 0x2000 - 0x1000 - len(prefix) - 5)
            raw += b"\xc3"
            options = {}
            assembly, log, status = render(
                raw.hex(), abi=1, kernel_symbols=ADDRESSES | {
                    "kd_raw_spin_lock_clobber_v1": 0x6000,
                    "kd_raw_spin_unlock_clobber_v1": 0x7000},
                string_write_capable=True, audited_strings_capable=True,
                build_options=options, return_status=True)
            self.assertEqual(status, 0, log)
            self.assertEqual(options["requirements"], 0)
            self.assertNotIn(b"KD_HOSTCALL id=5", assembly)
            self.assertNotIn(b"KD_DIRECT_STRING", assembly)

    def test_count_destination_and_sensitive_source_are_screened(self):
        line, db = call_graph()
        target = {ADDRESSES["strscpy_pad"]}
        self.assertIsNone(service.argument_rejection(line, db, self.tracker(), target, {}))
        for register, value, reason in (("RDX", 63, "exact count 64"),
                                        ("RDI", 0x80e0, "current-frame span"),
                                        ("RDI", 0x8100, "current-frame span"),
                                        ("RDI", 0x3000, "current-frame span")):
            tracker = self.tracker()
            set_register(tracker, register, value)
            with self.subTest(register=register, value=value):
                self.assertIn(reason, service.argument_rejection(line, db, tracker, target, {})[0])
        result = service.argument_rejection(line, db, self.tracker(), target, {0x903f: "current_task"})
        self.assertIn("context-sensitive strscpy_pad source", result[0])
        for register in ("RDI", "RSI", "RDX", "RBP"):
            tracker = self.tracker()
            tracker.values[ExprId(register, 64)] = None
            with self.subTest(widened=register), self.assertRaises(ContextFlowLimit):
                service.argument_rejection(line, db, tracker, target, {})



    def test_writer_is_not_readonly_and_keeps_complete_destination_effects(self):
        resolved = {ADDRESSES["strscpy_pad"]: service.SPEC}
        self.assertEqual(service.writer_targets(resolved), {ADDRESSES["strscpy_pad"]: 64})
        self.assertNotIn(ADDRESSES["strscpy_pad"], hostcall.readonly_waiter_targets(resolved))
        tracker = self.tracker()
        destination = 0x8040
        sentinel = ExprInt(0x1122334455667788, 64)
        for offset in range(-8, 72, 8):
            tracker.memory.store([({ExprInt(destination + offset, 64)}, {sentinel}, 64)])
        line, _ = call_graph()
        tracker.control_calls.add(id(line))
        tracker.writer_calls[id(line)] = 64
        tracker.update(line)
        for offset in range(64):
            self.assertEqual(tracker.memory.cells[ExprInt(destination + offset, 64)],
                             context_memory.UNKNOWN)
        for offset in (-8, 64):
            self.assertEqual(tracker.memory.load(ExprMem(ExprInt(destination + offset, 64), 64)),
                             (sentinel,))
        self.assertEqual(tracker.memory.load(ExprMem(ExprInt(0x7ff8, 64), 64)),
                         (ExprInt(0x1005, 64),))
        for name, value in (("RSP", 0x8000), ("RBP", 0x8100),
                            ("RBX", 0x1234), ("R12", 0x5678)):
            self.assertEqual(tracker.resolve_many(ExprId(name, 64)), [ExprInt(value, 64)])
        for name in ("RDI", "RSI", "RDX", "RAX"):
            self.assertNotIn(ExprId(name, 64), tracker.values)
            self.assertNotIn(ExprId(name, 64), tracker.origins)

    def test_writer_overlap_never_preserves_a_return_token_or_partial_word(self):
        # This violates the audited caller's local-destination guarantee (and
        # the old runtime preflight). Analysis independently retains the write:
        # it must not declare CALL slots or stack private.
        tracker = self.tracker()
        set_register(tracker, "RDI", 0x7ff8)
        line, _ = call_graph()
        tracker.control_calls.add(id(line))
        tracker.writer_calls[id(line)] = 64
        tracker.update(line)
        self.assertNotEqual(tracker.memory.load(ExprMem(ExprInt(0x7ff8, 64), 64)),
                            (ExprInt(0x1005, 64),))
        tracker = self.tracker()
        pointer = ExprInt(0x803c, 64)
        tracker.memory.store([({pointer}, {ExprInt(0x1122334455667788, 64)}, 64)])
        tracker.control_calls.add(id(line))
        tracker.writer_calls[id(line)] = 64
        tracker.update(line)
        self.assertTrue(any(context_memory.is_wide(value)
                            for value in tracker.memory.load(ExprMem(pointer, 64))))


if __name__ == "__main__":
    unittest.main()

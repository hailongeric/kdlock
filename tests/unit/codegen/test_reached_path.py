"""Guest-only real-decoder checks for execution-selected source segments."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "disassem"))

from miasm.core.asmblock import disasmEngine
from reached_path import (EdgeState, EventKind, decode_segment, transition)


BASE = 0xFFFFFFFFC1001000


class Source:
    def __init__(self, raw, base=BASE):
        self.raw = bytes.fromhex(raw) if isinstance(raw, str) else raw
        self.base = base
        self.requests = []

    def __call__(self, pc, size):
        self.requests.append((pc, size))
        if not self.base <= pc < self.base + len(self.raw):
            return b""
        offset = pc - self.base
        return self.raw[offset:offset + size]


class ReachedPathTests(unittest.TestCase):
    def decode(self, raw, **kwargs):
        source = Source(raw)
        # The old multi-block decoder must never become an implicit path.
        with patch.object(disasmEngine, "dis_multiblock",
                          side_effect=AssertionError("upfront CFG decoding")):
            segment = decode_segment(source, BASE, **kwargs)
        return source, segment

    def test_conditional_stops_before_either_successor(self):
        source, segment = self.decode("4885c0747f0fff")
        self.assertEqual([line.name for line in segment.instructions], ["TEST", "JZ"])
        self.assertEqual(segment.event.kind, EventKind.CONDITIONAL)
        self.assertEqual(segment.event.direct_target, BASE + 0x84)
        self.assertEqual(segment.event.next_pc, BASE + 5)
        self.assertEqual([pc for pc, _ in source.requests], [BASE, BASE + 3])

    def test_runtime_condition_selects_one_edge_without_reading_it(self):
        source, segment = self.decode("7502")
        state = EdgeState(BASE, 0x1000)
        for taken, target in ((True, BASE + 4), (False, BASE + 2)):
            with self.subTest(taken=taken):
                result = transition(segment.event, state, conditional_taken=taken)
                self.assertEqual(result, EdgeState(target, state.sp))
        self.assertEqual(source.requests, [(BASE, 15)])
        with self.assertRaisesRegex(ValueError, "actual runtime result"):
            transition(segment.event, state)

    def test_direct_call_does_not_decode_callee_or_continuation(self):
        source, segment = self.decode("e8000000100fff")
        event = segment.event
        self.assertEqual(event.kind, EventKind.CALL)
        self.assertEqual(event.direct_target, BASE + 5 + 0x10000000)
        self.assertIsNone(event.operand)
        self.assertEqual(source.requests, [(BASE, 15)])
        writes = []
        state = EdgeState(BASE, 0x1000)
        result = transition(event, state, write_word=lambda *args: writes.append(args))
        self.assertEqual(result, EdgeState(event.direct_target, 0xFF8))
        self.assertEqual(writes, [(0xFF8, BASE + 5)])

    def test_backward_relative_target_uses_actual_source_address(self):
        source, segment = self.decode("e9fbffffff")
        self.assertEqual(segment.event.kind, EventKind.JUMP)
        self.assertEqual(segment.event.direct_target, BASE)
        self.assertEqual(source.requests, [(BASE, 15)])

    def test_call_rsp_evaluates_before_source_stack_push(self):
        _, segment = self.decode("ffd4")
        operations = []
        state = EdgeState(BASE, 0x2000)

        def evaluate(operand, before):
            operations.append(("evaluate", str(operand), before.sp))
            return before.sp

        result = transition(segment.event, state, evaluate_operand=evaluate,
                            write_word=lambda *args: operations.append(("write", *args)))
        self.assertEqual(result, EdgeState(0x2000, 0x1FF8))
        self.assertEqual(operations, [("evaluate", "RSP", 0x2000),
                                      ("write", 0x1FF8, BASE + 2)])

    def test_call_stack_memory_operand_is_read_before_push(self):
        _, segment = self.decode("ff1424")
        operations = []
        stack = {0x3000: 0x12345678}
        state = EdgeState(BASE, 0x3000)

        def evaluate(operand, before):
            operations.append(("read_target", before.sp))
            self.assertTrue(operand.is_mem())
            return stack[before.sp]

        def write(address, value):
            operations.append(("push_return", address, value))
            stack[address] = value

        result = transition(segment.event, state, evaluate_operand=evaluate, write_word=write)
        self.assertEqual(result, EdgeState(0x12345678, 0x2FF8))
        self.assertEqual(operations, [("read_target", 0x3000),
                                      ("push_return", 0x2FF8, BASE + 3)])

    def test_indirect_jump_never_pushes_or_pops(self):
        _, segment = self.decode("ffe0")
        state = EdgeState(BASE, 0x4000)
        result = transition(segment.event, state,
                            evaluate_operand=lambda operand, before: 0x87654321,
                            read_word=lambda *_: self.fail("JMP popped source stack"),
                            write_word=lambda *_: self.fail("JMP pushed source stack"))
        self.assertEqual(result, EdgeState(0x87654321, state.sp))

    def test_ret_accepts_actual_inherited_native_return_word(self):
        source, segment = self.decode("c3")
        reads = []

        def read(address):
            reads.append(address)
            return 0xFFFFFFFF81234567

        result = transition(segment.event, EdgeState(BASE, 0x5000), read_word=read)
        self.assertEqual(result, EdgeState(0xFFFFFFFF81234567, 0x5008))
        self.assertEqual(reads, [0x5000])
        self.assertEqual(source.requests, [(BASE, 15)])

    def test_ret_immediate_preserves_unsigned_stack_adjustment(self):
        _, segment = self.decode("c2ffff")
        self.assertEqual(segment.event.return_adjustment, 0xFFFF)
        result = transition(segment.event, EdgeState(BASE, 0x6000), read_word=lambda _: 17)
        self.assertEqual(result, EdgeState(17, 0x6000 + 8 + 0xFFFF))

    def test_instruction_cap_has_explicit_fallthrough(self):
        source, segment = self.decode("9090900fff", max_instructions=2)
        self.assertEqual(len(segment.instructions), 2)
        self.assertEqual(segment.event.kind, EventKind.FALLTHROUGH)
        self.assertEqual(segment.event.pc, BASE + 2)
        self.assertEqual(segment.event.next_pc, BASE + 2)
        self.assertEqual(source.requests, [(BASE, 15), (BASE + 1, 15)])

    def test_pause_alias_preserves_raw_bytes_for_cold_executor(self):
        _, segment = self.decode("f390c3")
        self.assertEqual(segment.instructions[0].raw, b"\xf3\x90")
        self.assertEqual(segment.event.kind, EventKind.RETURN)

    def test_one_byte_complete_instruction_needs_no_fifteen_byte_window(self):
        source, segment = self.decode("c3")
        self.assertEqual(segment.event.kind, EventKind.RETURN)
        self.assertEqual(source.requests, [(BASE, 15)])

    def test_truncated_current_instruction_requests_supplementation(self):
        _, segment = self.decode("90488b")
        self.assertEqual(len(segment.instructions), 1)
        self.assertEqual(segment.event.kind, EventKind.NEED_SOURCE)
        self.assertEqual(segment.event.pc, BASE + 1)
        self.assertIsNone(segment.event.instruction)
        with self.assertRaisesRegex(ValueError, "runtime supplementation"):
            transition(segment.event, EdgeState(BASE + 1, 0x1000))

    def test_empty_source_is_not_a_completed_body(self):
        _, segment = self.decode("")
        self.assertEqual(segment.instructions, ())
        self.assertEqual(segment.event.kind, EventKind.NEED_SOURCE)
        self.assertEqual(segment.event.pc, BASE)

    def test_fifteen_prefix_bytes_are_explicitly_invalid(self):
        _, segment = self.decode("66" * 15)
        self.assertEqual(segment.event.kind, EventKind.INVALID)
        self.assertEqual(segment.instructions, ())

    def test_service_boundary_stops_at_instruction_without_successor_read(self):
        source, segment = self.decode("900f310fff", service_boundary=lambda line:
                                      "clock instruction" if line.name == "RDTSC" else None)
        self.assertEqual(segment.event.kind, EventKind.SERVICE)
        self.assertEqual(segment.event.pc, BASE + 1)
        self.assertEqual(segment.event.detail, "clock instruction")
        self.assertEqual(source.requests, [(BASE, 15), (BASE + 1, 15)])

    def test_unimplemented_context_transfer_is_not_an_ordinary_return(self):
        _, segment = self.decode("0f05")
        self.assertEqual(segment.event.kind, EventKind.SERVICE)
        self.assertEqual(segment.event.instruction.name, "SYSCALL")

    def test_reader_errors_and_oversized_reads_do_not_become_origin_execution(self):
        def unavailable(pc, size):
            raise OSError("source lease unavailable")

        with self.assertRaisesRegex(OSError, "source lease unavailable"):
            decode_segment(unavailable, BASE)
        with self.assertRaisesRegex(ValueError, "byte limit"):
            decode_segment(lambda *_: b"\x90" * 16, BASE)

    def test_invalid_limits_and_mismatched_event_state_are_refused(self):
        for count in (0, -1, 4097, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                decode_segment(Source("c3"), BASE, max_instructions=count)
        _, segment = self.decode("c3")
        with self.assertRaisesRegex(ValueError, "current source PC"):
            transition(segment.event, EdgeState(BASE + 1, 0), read_word=lambda _: 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

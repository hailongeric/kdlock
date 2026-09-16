"""Execute bounded entry predicates, never the speculative kernel-text replays."""

import ctypes
import io
import random
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "disassem"))

from context_guards import ENTRY_REFUSED, MASK, REGISTER_OFFSETS, EntryGuards
from miasm.expression.expression import ExprId, ExprInt, ExprMem
from test_jit_body_witness import render, run_image
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, decode, translator
from test_jit_diagnostics import render as translator_render


def address(name, offset=0):
    return ExprId("kd_entry_" + name, 64) if name else None, offset & MASK


def guarded(guards, raw="48c7c02a000000c3"):
    output = io.StringIO()
    guards.emit(output, 0x1000)
    assembly, _ = render(raw)
    return output.getvalue().encode("ascii") + assembly


class ScopedCallTests(unittest.TestCase):
    @staticmethod
    def call(target, source):
        return b"\xe8" + struct.pack("<i", target - source - 5)

    def graph(self, caller, callee):
        regions = [
            (bytes.fromhex(caller), 0x1000, [0x1000]),
            (bytes.fromhex(callee), 0x2000, [0x2000]),
        ]
        blocks, dbs = translator.decode_regions(
            regions,
            TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
            set(TEST_LOCK_SYMBOLS.values()),
        )
        return regions, blocks, dbs

    def multi_call(
        self, *, shared=False, redirect=False, skipped_body=None, lock_kind="spin"
    ):
        # The spill forces guarded admission. Two call sites may share one
        # callee or a RET tail; a rewritten return slot can skip site 1's
        # continuation, so only the emitted whitelist defines possible flow.
        caller = bytearray.fromhex("4d892c24c645f830498b04244c8930")
        caller += self.call(0x2000, 0x1000 + len(caller))
        first_return = 0x1000 + len(caller)
        caller += (
            bytes.fromhex("41c7470811000000") if skipped_body is None else skipped_body
        )
        caller += self.call(0x3000 if shared else 0x2000, 0x1000 + len(caller))
        second_return = 0x1000 + len(caller)
        caller += bytes.fromhex("41c747102a000000b82a000000")
        lock, unlock = (
            ("_raw_spin_lock", "_raw_spin_unlock")
            if lock_kind == "spin"
            else ("mutex_lock", "mutex_unlock")
        )
        for name in (lock, unlock, unlock):
            caller += self.call(TEST_LOCK_SYMBOLS[name], 0x1000 + len(caller))
        regions = [(bytes(caller), 0x1000, [0x1000])]
        for source in (0x2000, 0x3000) if shared else (0x2000,):
            body = bytearray.fromhex("49ff07")  # Increment caller-owned record.
            if redirect:
                body += b"\x48\xc7\x04\x24" + struct.pack("<I", second_return)
            if shared:
                body += b"\xe9" + struct.pack("<i", 0x4000 - source - len(body) - 5)
            else:
                body += b"\xc3"
            regions.append((bytes(body), source, [source]))
        if shared:
            regions.append((b"\xc3", 0x4000, [0x4000]))
        return regions, (first_return, second_return)

    def test_skipped_return_blocks_still_receive_unconditional_context_checks(self):
        # The callee always rewrites its return slot to site 2, so sequential
        # dataflow never visits site 1. Both source blocks and RET targets are
        # nevertheless emitted. Neither alias guards nor that value fact may
        # hide an explicit context/backend ban. Never execute these images.
        for kind in ("spin", "mutex"):
            foreign = TEST_LOCK_SYMBOLS[
                "mutex_lock" if kind == "spin" else "_raw_spin_lock"
            ]
            cases = {
                "fs": bytes.fromhex("64488b042500000000"),
                "cli": bytes.fromhex("fa"),
                "sti": bytes.fromhex("fb"),
                "gs_lods": bytes.fromhex("6548ad"),
                "fs_xlat": bytes.fromhex("64d7"),
                "swapgs": bytes.fromhex("0f01f8"),
                "current": bytes.fromhex("488b042508300000"),
                "foreign_lock": self.call(foreign, 0x1014),
            }
            for name, raw in cases.items():
                regions, returns = self.multi_call(
                    redirect=True, skipped_body=raw, lock_kind=kind
                )
                with self.subTest(kind=kind, instruction=name):
                    assembly, log, status = render(
                        "",
                        regions=regions,
                        lock_kind=kind,
                        symbols={0x3008: "current_task"},
                        return_status=True,
                    )
                    self.assertEqual((status, assembly), (2, b""), log)
                    self.assertIn("CONTEXT_NATIVE_ONLY", log)
                    self.assertIn(f'rip="0x{returns[0]:x}"', log)
                    self.assertNotIn("ENTRY_GUARDED_ADMISSION", log)
                    self.assertNotIn("FLAGS_UNPRESERVED", log)

    def nested_call(self, *, shared=True, control=False, corrupt=""):
        # Real prologues/epilogues preserve two different stack depths at a
        # shared RET. The guarded spill and record writes also exercise aliases;
        # no balanced-stack annotation or private-memory substitute is supplied.
        caller = bytearray.fromhex("4d892c24c645f830498b04244c8930")
        caller += self.call(0x2000, 0x1000 + len(caller))
        first_return = 0x1000 + len(caller)
        caller += bytes.fromhex("48c747102a000000488b4708")
        for name in ("mutex_lock", "mutex_unlock", "mutex_unlock"):
            caller += self.call(TEST_LOCK_SYMBOLS[name], 0x1000 + len(caller))
        outer = bytearray.fromhex("554889e5534889fb")
        outer += self.call(0x3000, 0x2000 + len(outer))
        second_return = 0x2000 + len(outer)
        outer += bytes.fromhex("4883430811488b5df8c9")
        inner = bytearray.fromhex("554889e55348ff07")
        inner += bytes.fromhex(corrupt)
        if control:
            inner += self.call(TEST_LOCK_SYMBOLS["mutex_lock"], 0x3000 + len(inner))
            inner += self.call(TEST_LOCK_SYMBOLS["mutex_unlock"], 0x3000 + len(inner))
        inner += bytes.fromhex("488b5df8c9")
        regions = [(bytes(caller), 0x1000, [0x1000])]
        for source, body in ((0x2000, outer), (0x3000, inner)):
            body += (
                b"\xe9" + struct.pack("<i", 0x4000 - source - len(body) - 5)
                if shared
                else b"\xc3"
            )
            regions.append((bytes(body), source, [source]))
        if shared:
            regions.append((b"\xc3", 0x4000, [0x4000]))
        return regions, (first_return, second_return)

    def test_nested_shared_ret_executes_with_proven_stack_partitions(self):
        regions, returns = self.nested_call()
        blocks, dbs = translator.decode_regions(
            regions, TEST_LOCK_SYMBOLS["mutex_unlock"], set(TEST_LOCK_SYMBOLS.values())
        )
        table = {}
        translator.indirect_jump.find(blocks, dbs, table)
        self.assertEqual(set(table[0x4001]), set(returns))
        assembly, log, status = render(
            "", regions=regions, lock_kind="mutex", return_status=True
        )
        self.assertEqual(status, 0, log)
        self.assertIn("scoped_calls=true", log)
        dispatch = assembly.split(b"ij_4001:\n", 1)[1].split(b"\n\n", 1)[0]
        for target in returns:
            self.assertIn(f"loc_{target:x}".encode(), dispatch)
        pointer, destination, unrelated = (ctypes.c_ulong() for _ in range(3))
        record = (ctypes.c_ulong * 3)()
        initial = {}

        def initialize(regs, _):
            regs[3] = ctypes.addressof(pointer)
            regs[2] = ctypes.addressof(destination)
            regs[1] = 42
            regs[4] = ctypes.addressof(unrelated) + 8
            regs[5] = 0x5555
            regs[14] = ctypes.addressof(record)
            initial.update(rsp=regs[19], rbp=regs[4])

        # Both CALLs and both visits to the same generated RET really run.
        # The final known lock stub exits without executing a native kernel API.
        regs, args = run_image(assembly, [0x1000], initialize)[0]
        self.assertEqual(
            (args, destination.value, list(record)), ([1, 1], 42, [1, 17, 42])
        )
        self.assertEqual((regs[4], regs[5], regs[10]), (initial["rbp"], 0x5555, 17))
        self.assertEqual(regs[19], initial["rsp"] - 8)
        self.assertEqual(regs[16], TEST_LOCK_SYMBOLS["mutex_lock"])

    def test_nested_ret_partition_budget_refuses_without_publishing(self):
        regions, _ = self.nested_call()
        with patch.object(
            translator.context_policy.FlowConstants, "MAX_STACK_PARTITIONS", 1
        ):
            assembly, log, status = render(
                "", regions=regions, lock_kind="mutex", return_status=True
            )
        self.assertEqual((assembly, status), (b"", 2))
        self.assertIn("partitions exceed their work budget", log)
        self.assertNotIn("ENTRY_GUARDED_ADMISSION", log)

    def test_nested_control_spill_clobber_is_not_mislabelled_as_a_shared_ret_fix(self):
        # Even private RETs cannot prove reloaded saved values after a control
        # CALL's memory clobber. Keep this separate from the solved graph join;
        # preserving GPRs at the handler boundary does not preserve stack words.
        for shared in (False, True):
            regions, _ = self.nested_call(shared=shared, control=True)
            with self.subTest(shared=shared):
                assembly, log, status = render(
                    "", regions=regions, lock_kind="mutex", return_status=True
                )
                self.assertEqual((assembly, status), (b"", 2))
                self.assertIn("CONTEXT_ADDRESS_WIDENED", log)
                self.assertNotIn("ENTRY_GUARDED_ADMISSION", log)

    def test_checked_nested_control_returns_execute_with_shared_or_private_ret(self):
        # The unchanged boundary permits saved-value reloads through BOTH real
        # CALL levels. Run the generated code, not only admission. The bridge
        # substitutes successful lock-control packets in userspace; it neither
        # executes Linux mutex APIs nor proves the kernel checkpoint itself.
        for shared in (False, True):
            with self.subTest(shared=shared):
                regions, returns = self.nested_call(shared=shared, control=True)
                assembly, log, status = render(
                    "",
                    regions=regions,
                    lock_kind="mutex",
                    mutex_stack_bytes=256,
                    return_status=True,
                )
                self.assertEqual(status, 0, log)
                self.assertIn("scoped_calls=true", log)
                self.assertIn("mutex_stack_bytes=256", log)
                if shared:
                    dispatch = assembly.split(b"ij_4001:\n", 1)[1].split(b"\n\n", 1)[0]
                    for target in returns:
                        self.assertIn(f"loc_{target:x}".encode(), dispatch)
                pointer, destination, unrelated = (ctypes.c_ulong() for _ in range(3))
                record = (ctypes.c_ulong * 3)()
                initial, calls = {}, []

                def initialize(
                    regs, _, state=(pointer, destination, unrelated, record, initial)
                ):
                    pointer, destination, unrelated, record, initial = state
                    regs[3] = ctypes.addressof(pointer)
                    regs[2] = ctypes.addressof(destination)
                    regs[1] = 42
                    regs[4] = ctypes.addressof(unrelated) + 8
                    regs[5] = 0x5555
                    regs[14] = ctypes.addressof(record)
                    initial.update(rsp=regs[19], rbp=regs[4])

                def resume(regs, args, stack, calls=calls):
                    self.assertEqual(list(args), [1, 1])
                    calls.append(regs[16])
                    if len(calls) == 3:
                        return False
                    self.assertLess(len(calls), 3)
                    self.assertEqual(
                        regs[16],
                        TEST_LOCK_SYMBOLS[
                            "mutex_lock" if len(calls) == 1 else "mutex_unlock"
                        ],
                    )
                    self.assertLessEqual(ctypes.addressof(stack), regs[19])
                    self.assertLess(
                        regs[19] + 8, ctypes.addressof(stack) + ctypes.sizeof(stack)
                    )
                    regs[16] = ctypes.c_ulong.from_address(regs[19]).value
                    regs[19] += 8
                    return True

                regs, args = run_image(assembly, [0x1000], initialize, resume=resume)[0]
                self.assertEqual(
                    calls,
                    [
                        TEST_LOCK_SYMBOLS[name]
                        for name in ("mutex_lock", "mutex_unlock", "mutex_lock")
                    ],
                )
                self.assertEqual(
                    (args, destination.value, list(record)), ([1, 1], 42, [1, 17, 42])
                )
                self.assertEqual(
                    (regs[4], regs[5], regs[10]), (initial["rbp"], 0x5555, 17)
                )
                self.assertEqual(regs[19], initial["rsp"] - 8)

    def test_checked_nested_control_keeps_sensitive_spill_and_unknown_alias_refusals(
        self,
    ):
        # A completed checkpoint does not undo earlier stores. Corrupt the
        # saved RBX directly, or write through an unresolved pointer that may
        # alias it; both remain unsafe even with the negotiated capability.
        for corrupt in ("48c745f808500000", "488b36c60630"):
            for shared in (False, True):
                with self.subTest(corrupt=corrupt, shared=shared):
                    regions, _ = self.nested_call(
                        shared=shared, control=True, corrupt=corrupt
                    )
                    assembly, log, status = render(
                        "",
                        regions=regions,
                        lock_kind="mutex",
                        mutex_stack_bytes=256,
                        symbols={0x5010: "current_task"},
                        return_status=True,
                    )
                    self.assertEqual((assembly, status), (b"", 2))
                    self.assertIn("CONTEXT_NATIVE_ONLY", log)
                    self.assertNotIn("ENTRY_GUARDED_ADMISSION", log)

    def test_unknown_shared_ret_joins_effects_without_unbounded_stack_partitions(self):
        # No saved-value reload here: the control CALL still clobbers its
        # return slot and can target either continuation. Converge by joining
        # effects, not by enumerating ever-increasing hypothetical pop depths.
        outer = bytearray.fromhex("4889fb")
        outer += self.call(0x3000, 0x2003)
        outer += bytes.fromhex("488b4308e9ef1f0000")
        inner = self.call(TEST_LOCK_SYMBOLS["mutex_lock"], 0x3000)
        inner += bytes.fromhex("e9f60f0000")
        regions = [
            (self.call(0x2000, 0x1000) + b"\xc3", 0x1000, [0x1000]),
            (bytes(outer), 0x2000, [0x2000]),
            (inner, 0x3000, [0x3000]),
            (b"\xc3", 0x4000, [0x4000]),
        ]
        blocks, dbs = translator.decode_regions(
            regions, TEST_LOCK_SYMBOLS["mutex_unlock"], set(TEST_LOCK_SYMBOLS.values())
        )
        table = {}
        translator.indirect_jump.find(blocks, dbs, table)
        self.assertEqual(set(table[0x4001]), {0x1005, 0x2008})
        self.assertIsNone(
            translator.find_segment_policy_error(
                blocks,
                db_dict=dbs,
                lock_kind="mutex",
                lock_symbols={TEST_LOCK_SYMBOLS["mutex_lock"]: ("mutex", "mutex_lock")},
                roots={0x1000},
                guards=EntryGuards(),
                scoped_calls=True,
            )
        )

    def test_long_callee_return_discovery_is_not_python_recursion_limited(self):
        # Actual decoded branches, not fabricated graph nodes. This is a
        # return-table test only; the long corpus is not executed in the kernel.
        _, blocks, dbs = self.graph("e8fb0f0000c3", "eb00" * 1200 + "c3")
        table = {}
        self.assertEqual(translator.indirect_jump.find(blocks, dbs, table), [])
        self.assertEqual(table[0x2000 + 2401], [0x1005])

    def test_return_discovery_preserves_history_and_bounds_cycles_and_work(self):
        _, blocks, dbs = self.graph("e8fb0f0000c3", "ebfe")
        table = {0x4444: [0x5555]}
        self.assertEqual(translator.indirect_jump.find(blocks, dbs, table), [])
        self.assertEqual(table, {0x4444: [0x5555], 0x1006: []})
        _, blocks, dbs = self.graph("e8fb0f0000c3", "eb00" * 8 + "c3")
        for budget in (2, 14):
            table = {0x4444: [0x5555]}
            with (
                self.subTest(budget=budget),
                self.assertRaisesRegex(
                    translator.indirect_jump.ReturnFlowError, "work budget"
                ),
            ):
                translator.indirect_jump.find(blocks, dbs, table, max_visits=budget)
            self.assertEqual(table, {0x4444: [0x5555]})

    def test_incomplete_return_graph_never_publishes_a_partial_whitelist(self):
        # All failures are mutations of real decoded code. Preserve prior IJ
        # history rather than leaking the partially discovered CALL/RET graph.
        for damage in ("database", "successor", "callee"):
            _, blocks, dbs = self.graph("e8fb0f0000c3", "eb00c3")
            table = {0x4444: [0x5555]}
            if damage == "database":
                del dbs[blocks[0x2000]]
            elif damage == "successor":
                del blocks[0x2002]
            with self.subTest(damage=damage):
                if damage == "callee":
                    with (
                        patch.object(
                            dbs[blocks[0x1000]],
                            "get_location_offset",
                            return_value=None,
                        ),
                        self.assertRaisesRegex(
                            translator.indirect_jump.ReturnFlowError, "unresolved"
                        ),
                    ):
                        translator.indirect_jump.find(blocks, dbs, table)
                else:
                    with self.assertRaisesRegex(
                        translator.indirect_jump.ReturnFlowError, "missing"
                    ):
                        translator.indirect_jump.find(blocks, dbs, table)
                self.assertEqual(table, {0x4444: [0x5555]})

    def test_final_emission_refuses_return_budget_without_guarded_retry(self):
        original = translator.indirect_jump.find

        def limited(blocks, dbs, table, **kwargs):
            return original(blocks, dbs, table, max_visits=1)

        # This ordinary MOV/RET entry passes unconditional admission. Exercise
        # the real builder's failure at final emission, not just the scoped
        # analysis exception handler or a fabricated successful rejection.
        with patch.object(translator.indirect_jump, "find", limited):
            assembly, log, status = render("48c7c02a000000c3", return_status=True)
        self.assertEqual((assembly, status), (b"", 2))
        self.assertIn("return dispatch exceeds its work budget", log)
        self.assertIn("CONTEXT_NATIVE_ONLY", log)
        self.assertNotIn("ENTRY_GUARDED_ADMISSION", log)

    def test_multisite_shared_tail_and_redirected_return_execute_real_images(self):
        for shared, redirect in ((False, False), (True, False), (False, True)):
            regions, returns = self.multi_call(shared=shared, redirect=redirect)
            blocks, dbs = translator.decode_regions(
                regions,
                TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
                set(TEST_LOCK_SYMBOLS.values()),
            )
            table = {}
            translator.indirect_jump.find(blocks, dbs, table)
            ret = 0x4001 if shared else 0x2004 + (8 if redirect else 0)
            self.assertEqual(set(table[ret]), set(returns))
            assembly, log, status = render("", regions=regions, return_status=True)
            with self.subTest(shared=shared, redirect=redirect):
                self.assertEqual(status, 0, log)
                self.assertIn("scoped_calls=true", log)
                pointer, destination, unrelated = (ctypes.c_ulong() for _ in range(3))
                record = (ctypes.c_ulong * 3)()

                def initialize(
                    regs,
                    _,
                    pointer=pointer,
                    destination=destination,
                    unrelated=unrelated,
                    record=record,
                ):
                    regs[3] = ctypes.addressof(pointer)
                    regs[2] = ctypes.addressof(destination)
                    regs[1] = 42
                    regs[4] = ctypes.addressof(unrelated) + 8
                    regs[0] = ctypes.addressof(record)

                regs, args = run_image(assembly, [0x1000], initialize)[0]
                self.assertEqual((args, regs[10], destination.value), ([1, 1], 42, 42))
                self.assertEqual(regs[16], TEST_LOCK_SYMBOLS["_raw_spin_lock"])
                # Exact effects distinguish redirected RET execution from
                # merely publishing a table containing both continuations.
                self.assertEqual(
                    list(record), [1 if redirect else 2, 0 if redirect else 17, 42]
                )

    def test_return_slot_alias_cannot_hide_a_different_callers_context_pointer(self):
        # Site 1 forms current_task arithmetically; its ordinary continuation
        # replaces RDI before site 2. A callee write selects site 2's return
        # instead, so propagating only a matching/balanced CALL would be unsafe.
        caller = bytearray.fromhex("bf003000004883c708")
        caller += self.call(0x2000, 0x1000 + len(caller))
        caller += bytes.fromhex("bf00400000")
        caller += self.call(0x2000, 0x1000 + len(caller))
        second_return = 0x1000 + len(caller)
        caller += bytes.fromhex("488b07c3")
        # Full known overwrite, unknown whole word, and unknown low byte must
        # all retain site 2 when reachable. Only exact facts may narrow RET flow;
        # neither an unknown source nor partial memory uncertainty means "return
        # to the matching caller".
        for write in (
            b"\x48\xc7\x04\x24" + struct.pack("<I", second_return),
            bytes.fromhex("48893424"),
            bytes.fromhex("40883424"),
        ):
            _, blocks, dbs = self.graph(caller.hex(), (write + b"\xc3").hex())
            with self.subTest(write=write.hex()):
                error = translator.find_segment_policy_error(
                    blocks,
                    db_dict=dbs,
                    symbols={0x3008: "current_task"},
                    roots={0x1000},
                    guards=EntryGuards(),
                    scoped_calls=True,
                )
                self.assertIsNotNone(error)
                self.assertIn("current_task", error[1])

    def test_call_packet_and_ret_effects_replace_fabricated_fallthrough(self):
        # Callee gets the real RDI and caller gets the actual returned RAX;
        # an independent seed or a clobbered CALL fall-through loses both facts.
        regions, blocks, dbs = self.graph("bf29000000e8f60f00004883c001c3", "4889f8c3")
        guards = EntryGuards()
        observations = []
        for start, block, tracker in translator.context_policy.constant_blocks(
            blocks, dbs, roots={0x1000}, guards=guards, scoped_calls=True
        ):
            if start == 0x100A:
                observations.append(tracker.values.get(ExprId("RAX", 64)))
            for line in block.lines:
                tracker.update(line)
        self.assertEqual(observations, [frozenset({ExprInt(41, 64)})])
        # Run only this bounded MOV/CALL/RET corpus in guest userspace. The
        # production wrapper and emitted RET whitelist are not mocked.
        assembly, _, status = render("", regions=regions, return_status=True)
        self.assertEqual(status, 0)
        predicate = io.StringIO()
        guards.emit(predicate, 0x1000)
        regs, args = run_image(predicate.getvalue().encode() + assembly, [0x1000])[0]
        self.assertEqual(regs[10], 42)
        self.assertEqual(args[1], 1)

    def test_callee_memory_writes_reach_caller_admission(self):
        # The callee corrupts a caller-visible pointer. No saved-register or
        # private-stack assumption may erase that write at the return boundary.
        _, blocks, dbs = self.graph(
            "4d892c24e8f70f0000498b0424488b00c3", "49c7042408300000c3"
        )
        error = translator.find_segment_policy_error(
            blocks,
            db_dict=dbs,
            symbols={0x3008: "current_task"},
            roots={0x1000},
            guards=EntryGuards(),
            scoped_calls=True,
        )
        self.assertIsNotNone(error)
        self.assertIn("current_task", error[1])

    def test_scoped_graph_rejects_indirect_and_adjusting_returns(self):
        for raw, reason in (("ffe0", "indirect control"), ("c20800", "plain RET")):
            _, blocks, dbs = self.graph("e8fb0f0000c3", raw)
            with (
                self.subTest(raw=raw),
                self.assertRaisesRegex(
                    translator.context_policy.ContextFlowLimit, reason
                ),
            ):
                list(
                    translator.context_policy.constant_blocks(
                        blocks,
                        dbs,
                        roots={0x1000},
                        guards=EntryGuards(),
                        scoped_calls=True,
                    )
                )

    def test_disconnected_learned_target_cannot_inherit_root_facts(self):
        _, blocks, dbs = self.graph("c3", "4889f8c3")
        with self.assertRaisesRegex(
            translator.context_policy.ContextFlowLimit, "unreached"
        ):
            for _, block, tracker in translator.context_policy.constant_blocks(
                blocks, dbs, roots={0x1000}, guards=EntryGuards(), scoped_calls=True
            ):
                for line in block.lines:
                    tracker.update(line)

    def test_scoped_recursion_keeps_the_flow_budget(self):
        _, blocks, dbs = self.graph("e8fb0f0000c3", "e8fbffffffc3")
        with self.assertRaisesRegex(
            translator.context_policy.ContextFlowLimit, "work budget"
        ):
            for _, block, tracker in translator.context_policy.constant_blocks(
                blocks,
                dbs,
                max_visits=2,
                roots={0x1000},
                guards=EntryGuards(),
                scoped_calls=True,
            ):
                for line in block.lines:
                    tracker.update(line)

    def test_indirect_history_cannot_enable_guarded_callee_admission(self):
        # This safe-looking target is reachable as a direct callee too, but an
        # additional learned IJ route invalidates inheritance from one CALL packet.
        caller = bytes.fromhex("4d892c24c645f830498b04244c8930")
        caller += self.call(0x2000, 0x1000 + len(caller))
        for name in ("_raw_spin_lock", "_raw_spin_unlock", "_raw_spin_unlock"):
            caller += self.call(TEST_LOCK_SYMBOLS[name], 0x1000 + len(caller))
        assembly, log, status = render(
            "",
            regions=[(caller, 0x1000, [0x1000]), (b"\xc3", 0x2000, [0x2000])],
            indirect_history={0x2001: [0x2000]},
            return_status=True,
        )
        self.assertEqual((assembly, status), (b"", 2), log)
        self.assertNotIn("ENTRY_GUARDED_ADMISSION", log)

    def test_all_generated_return_targets_must_have_checked_effect_edges(self):
        _, blocks, dbs = self.graph("e8fb0f0000c3", "c3")
        original = translator.indirect_jump.find

        def extra_target(blocks, dbs, table, **kwargs):
            result = original(blocks, dbs, table, **kwargs)
            table[0x2001].append(0x1000)
            return result

        # Even a target inside the checked image needs its RET incoming state.
        with (
            patch.object(translator.indirect_jump, "find", extra_target),
            self.assertRaisesRegex(
                translator.context_policy.ContextFlowLimit,
                "differ from generated dispatch",
            ),
        ):
            list(
                translator.context_policy.constant_blocks(
                    blocks, dbs, roots={0x1000}, guards=EntryGuards(), scoped_calls=True
                )
            )

    def test_guarded_learned_callee_really_executes_before_lock_exit(self):
        # Force the real conditional-admission retry with a potentially aliased
        # spill. A learned helper must execute and return before the lock exit.
        caller = bytes.fromhex("4d892c24c645f830498b04244c8930")
        caller += self.call(0x2000, 0x1000 + len(caller))
        for name in ("_raw_spin_lock", "_raw_spin_unlock", "_raw_spin_unlock"):
            caller += self.call(TEST_LOCK_SYMBOLS[name], 0x1000 + len(caller))
        for unsafe in (False, True):
            callee = bytes.fromhex("64488b042500000000c3" if unsafe else "b829000000c3")
            assembly, log, status = render(
                "",
                regions=[(caller, 0x1000, [0x1000]), (callee, 0x2000, [0x2000])],
                return_status=True,
            )
            with self.subTest(unsafe=unsafe):
                self.assertEqual(status, 2 if unsafe else 0, log)
                if unsafe:
                    self.assertEqual(assembly, b"")
                    self.assertIn("FS-prefixed", log)
                    continue
                self.assertIn("ENTRY_GUARDED_ADMISSION", log)
                self.assertIn("scoped_calls=true", log)
                pointer, destination, unrelated = (
                    ctypes.c_ulong(),
                    ctypes.c_ulong(),
                    ctypes.c_ulong(),
                )

                def initialize(
                    regs,
                    _,
                    pointer=pointer,
                    destination=destination,
                    unrelated=unrelated,
                ):
                    regs[3] = ctypes.addressof(pointer)
                    regs[2] = ctypes.addressof(destination)
                    regs[1] = 42
                    regs[4] = ctypes.addressof(unrelated) + 8

                regs, args = run_image(assembly, [0x1000], initialize)[0]
                self.assertEqual((args, regs[10], destination.value), ([1, 1], 41, 42))
                self.assertEqual(regs[16], TEST_LOCK_SYMBOLS["_raw_spin_lock"])


class EntryGuardTests(unittest.TestCase):
    def test_nested_precision_retry_fetches_and_checks_cold_paths(self):
        def call(name, offset):
            return b"\xe8" + struct.pack("<i", TEST_LOCK_SYMBOLS[name] - offset - 5)

        prefix = bytes.fromhex("4d892c24c645f830498b04244c8930")
        prefix += call("_raw_spin_lock", 0x1000 + len(prefix))
        prefix += b"\xe9" + struct.pack("<i", 0x3000 - (0x1000 + len(prefix) + 5))
        initial = (prefix, 0x1000, [0x1000])
        for unsafe in (False, True):
            cold = bytes.fromhex("64488b042500000000") if unsafe else b""
            cold += call("_raw_spin_unlock", 0x3000 + len(cold))
            cold += call("_raw_spin_unlock", 0x3000 + len(cold))
            # Only the text-read boundary is mocked. Actual CFG scope, flow
            # analysis and emission must include and check the fetched branch.
            with (
                self.subTest(unsafe=unsafe),
                patch.object(
                    translator.memread,
                    "extend_regions",
                    return_value=[initial, (cold, 0x3000, [0x3000])],
                ) as extend,
            ):
                assembly, log, status = render(
                    "", regions=[initial], return_status=True
                )
            extend.assert_called_once()
            self.assertIn("ENTRY_GUARD_WAIT_TEXT", log)
            self.assertEqual(status, 2 if unsafe else 0, log)
            if unsafe:
                self.assertEqual(assembly, b"")
                self.assertIn("FS-prefixed", log)
            else:
                self.assertIn("ENTRY_GUARDED_ADMISSION", log)
                self.assertIn(b"kd_entry_guard_refused", assembly)

    def test_automatic_nested_admission_checks_aliases_before_real_stores(self):
        # A partial alias can corrupt the spilled pointer before its use. The
        # safe packet must really execute; the overlapping packet must perform
        # none of these stores, rather than merely losing its body witness.
        raw = bytes.fromhex("4d892c24c645f830498b04244c8930")
        for name in ("_raw_spin_lock", "_raw_spin_unlock", "_raw_spin_unlock"):
            target = TEST_LOCK_SYMBOLS[name]
            raw += b"\xe8" + struct.pack("<i", target - (0x1000 + len(raw) + 5))
        assembly, log, status = render(raw.hex(), return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn("ENTRY_GUARDED_ADMISSION", log)
        self.assertIn(b"kd_entry_guard_refused", assembly)
        for overlap in (False, True):
            with self.subTest(overlap=overlap):
                pointer = ctypes.c_ulong(0x1234)
                destination = ctypes.c_ulong(0x5678)
                unrelated = ctypes.c_ulong(0)
                before = []

                def initialize(
                    regs,
                    _,
                    pointer=pointer,
                    destination=destination,
                    base=pointer if overlap else unrelated,
                    before=before,
                ):
                    regs[3] = ctypes.addressof(pointer)
                    regs[2] = ctypes.addressof(destination)
                    regs[1] = 42
                    regs[4] = ctypes.addressof(base) + 8
                    before.append(list(regs))

                regs, args = run_image(assembly, [0x1000], initialize)[0]
                if overlap:
                    self.assertEqual(args, [ENTRY_REFUSED, 0])
                    self.assertEqual(regs, before[0])
                    self.assertEqual(
                        (pointer.value, destination.value), (0x1234, 0x5678)
                    )
                else:
                    self.assertEqual(args, [1, 1])
                    self.assertEqual(regs[16], TEST_LOCK_SYMBOLS["_raw_spin_lock"])
                    self.assertEqual(pointer.value, ctypes.addressof(destination))
                    self.assertEqual((destination.value, unrelated.value), (42, 0x30))

    def test_guarded_analysis_keeps_explicit_context_rejections(self):
        original = translator.find_segment_policy_error

        def check(*args, **kwargs):
            return original(*args, **kwargs, guards=EntryGuards())

        # Use the real scope and policy; only supply the optional collector.
        # Guard assumptions must not bypass FS, IRQ or known-symbol admission.
        for raw in ("64488b042500000000c3", "fac3", "48c7c000300000488b00c3"):
            with (
                self.subTest(raw=raw),
                patch.object(translator, "find_segment_policy_error", check),
            ):
                assembly, log, status = translator_render(
                    raw, symbols={0x3000: "current_task"}, return_status=True
                )
                self.assertEqual(status, translator.context_policy.NATIVE_ONLY_EXIT)
                self.assertEqual(assembly, b"")
                self.assertIn("CONTEXT_NATIVE_ONLY", log)

    def test_entry_guards_require_one_explicit_root(self):
        policy = translator.context_policy
        for roots in (None, {0x1000, 0x2000}):
            with (
                self.subTest(roots=roots),
                self.assertRaisesRegex(
                    policy.ContextFlowLimit, "one explicit CFG root"
                ),
            ):
                list(
                    policy.constant_blocks(
                        {0x1000: object(), 0x2000: object()},
                        {},
                        roots=roots,
                        guards=EntryGuards(),
                    )
                )

    def test_analysis_refuses_exhausted_guard_collection_before_emission(self):
        original = translator.find_segment_policy_error

        def check(*args, **kwargs):
            return original(*args, **kwargs, guards=EntryGuards())

        # Two distinct stores and a RET need byte/word/stack alias premises.
        # A caller must not receive a successful policy verdict for a guard
        # set that cannot be emitted, even when the assembly is never built.
        raw = "49c704241100000049c7450022000000c3"
        for limit in ("MAX_RANGES", "MAX_GUARDS"):
            with (
                self.subTest(limit=limit),
                patch.object(EntryGuards, limit, 0),
                patch.object(translator, "find_segment_policy_error", check),
            ):
                assembly, log, status = translator_render(raw, return_status=True)
                self.assertEqual(status, translator.context_policy.NATIVE_ONLY_EXIT)
                self.assertEqual(assembly, b"")
                self.assertIn("CONTEXT_NATIVE_ONLY", log)
                if limit == "MAX_GUARDS":
                    self.assertIn("entry disjointness guard count exhausted", log)

    def test_store_guard_covers_every_byte_not_only_the_write_start(self):
        guards = EntryGuards()
        left, right = address("R12")[0], address("R13")[0]
        memory = translator.context_policy.context_memory.MemoryValues(
            frozenset({left, right}), guards
        )
        memory.store([({left}, {ExprInt(0x11, 8)}, 8)])
        memory.store([({right}, {ExprInt(0xAABBCCDDEEFF0011, 64)}, 64)])
        self.assertEqual(memory.load(ExprMem(left, 8)), (ExprInt(0x11, 8),))
        # A one-byte guard would incorrectly admit offsets 1..7 even though
        # the concrete store can overwrite the tracked byte at each offset.
        for offset in range(-2, 10):
            self.assertEqual(
                guards.accepts({"R12": 0x1000 + offset, "R13": 0x1000}),
                not 0 <= offset < 8,
            )

    def test_guards_do_not_hide_unknown_writes_or_callee_memory_clobbers(self):
        policy = translator.context_policy
        guards = EntryGuards()
        left = address("R12")[0]
        memory = policy.context_memory.MemoryValues(frozenset({left}), guards)
        memory.store([({left}, {ExprInt(0x11, 64)}, 64)])
        memory.store([({ExprId("unknown", 64)}, {ExprInt(0x30, 8)}, 8)])
        self.assertTrue(
            any(
                policy.context_memory.is_wide(v) for v in memory.load(ExprMem(left, 64))
            )
            or memory.load(ExprMem(left, 64)) != (ExprInt(0x11, 64),)
        )
        memory.clobber()
        self.assertTrue(
            any(
                policy.context_memory.is_wide(v) for v in memory.load(ExprMem(left, 64))
            )
        )
        self.assertEqual(guards.conditions(), [])

    def test_control_effects_preserve_only_saved_registers_not_memory(self):
        policy = translator.context_policy
        line = decode("e800000000")
        for controlled in (False, True):
            with self.subTest(controlled=controlled):
                constants = policy.FlowConstants(EntryGuards())
                original = dict(constants.origins)
                rsp, r12, rax = (ExprId(name, 64) for name in ("RSP", "R12", "RAX"))
                constants.values[r12] = frozenset({ExprInt(0x1234, 64)})
                constants.values[rax] = frozenset({ExprInt(0x5678, 64)})
                constants.memory.store([({original[rsp]}, {ExprInt(0x11, 64)}, 64)])
                if controlled:
                    constants.control_calls.add(id(line))
                constants.update(line)
                for name in ("RBX", "RBP", "RSP", "R12", "R13", "R14", "R15"):
                    reg = ExprId(name, 64)
                    self.assertEqual(
                        constants.origins.get(reg) == original[reg], controlled
                    )
                self.assertNotIn(rax, constants.origins)
                self.assertEqual(r12 in constants.values, controlled)
                self.assertTrue(
                    any(
                        policy.context_memory.is_wide(v)
                        for v in constants.memory.load(ExprMem(original[rsp], 64))
                    )
                )

    def test_checked_mutex_uses_post_push_memory_not_the_pre_call_snapshot(self):
        policy = translator.context_policy
        # Giving another control, hostcall or ordinary CALL a provider bound
        # is not authorization to retain its memory facts.
        for kind in ("mutex", "spin", "hostcall", "ordinary"):
            with self.subTest(kind=kind):
                constants = policy.FlowConstants(EntryGuards(), mutex_stack_bytes=256)
                line = decode("e800000000")
                rsp = ExprId("RSP", 64)
                window = constants.origins[rsp]
                token = constants.memory.offset(window, -8)
                constants.memory.store(
                    [
                        ({window}, {ExprInt(0x1234, 64)}, 64),
                        ({token}, {ExprInt(0x2222, 64)}, 64),
                    ]
                )
                if kind in {"mutex", "spin"}:
                    constants.control_calls.add(id(line))
                if kind == "mutex":
                    constants.mutex_calls.add(id(line))
                constants.update(line)
                self.assertEqual(
                    constants.memory.load(ExprMem(window, 64))
                    == (ExprInt(0x1234, 64),),
                    kind == "mutex",
                )
                self.assertNotIn(ExprMem(token, 64), constants.memory.words)
                self.assertIn(ExprInt(5, 8), constants.memory.cells[token])
                self.assertNotIn(ExprInt(0x22, 8), constants.memory.cells[token])

    def test_checked_capability_marks_only_guarded_mutex_control_targets(self):
        # Observe the production classifier, rather than manually labelling
        # call IDs as in the packet fixture. Foreign controls are rejected by
        # the existing backend policy; hostcalls/ordinary calls never qualify.
        policy = translator.context_policy
        lock_symbols = {
            target: ("mutex" if name.startswith("mutex") else "spin", name)
            for name, target in TEST_LOCK_SYMBOLS.items()
        }
        update = policy.FlowConstants.update
        for name in (*TEST_LOCK_SYMBOLS, "hostcall"):
            for guarded, bound in ((True, 256), (False, 256), (True, 0)):
                with self.subTest(name=name, guarded=guarded, bound=bound):
                    target = TEST_LOCK_SYMBOLS.get(name, 0x6000)
                    raw = ScopedCallTests.call(target, 0x1000) + b"\xc3"
                    blocks, dbs = translator.decode_regions(
                        [(raw, 0x1000, [0x1000])],
                        TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
                        set(TEST_LOCK_SYMBOLS.values()) | {0x6000},
                    )
                    observed = []

                    def observe(tracker, line, symbols=None, observed=observed):
                        if line.is_subcall():
                            observed.append(
                                bool(
                                    id(line) in tracker.mutex_calls
                                    and tracker.mutex_stack_bytes
                                )
                            )
                        return update(tracker, line, symbols)

                    with patch.object(policy.FlowConstants, "update", observe):
                        error = translator.find_segment_policy_error(
                            blocks,
                            db_dict=dbs,
                            roots={0x1000},
                            lock_kind=lock_symbols.get(target, ("mutex",))[0],
                            lock_symbols=lock_symbols,
                            guards=EntryGuards() if guarded else None,
                            mutex_stack_bytes=bound,
                        )
                    self.assertIsNone(error)
                    self.assertEqual(
                        observed, [bool(name.startswith("mutex") and guarded and bound)]
                    )

    def test_checked_mutex_requires_all_numeric_stack_paths_and_known_ir(self):
        policy = translator.context_policy
        constants = policy.FlowConstants(EntryGuards(), mutex_stack_bytes=256)
        line = decode("e800000000")
        rsp = ExprId("RSP", 64)
        constants.values[rsp] = frozenset({ExprInt(0x9000, 64), ExprInt(0x9010, 64)})
        for pointer in (0x9000, 0x9010, 0x90F8, 0x9100):
            constants.memory.store(
                [({ExprInt(pointer, 64)}, {ExprInt(0x1234, 64)}, 64)]
            )
        constants.control_calls.add(id(line))
        constants.mutex_calls.add(id(line))
        constants.update(line)
        self.assertEqual(
            set(constants.memory.words),
            {ExprMem(ExprInt(p, 64), 64) for p in (0x9010, 0x90F8)},
        )
        for opaque in (None, "wide"):
            with self.subTest(opaque=opaque):
                constants.values[rsp] = (
                    None if opaque == "wide" else frozenset({ExprInt(0x9010, 64), None})
                )
                constants.origins.pop(rsp, None)
                constants.update(line)
                self.assertFalse(constants.memory.words)
        # An altered CALL lowering cannot inherit the eight-byte checkpoint
        # interpretation just because its target has been registered.
        constants = policy.FlowConstants(EntryGuards(), mutex_stack_bytes=256)
        window = constants.origins[rsp]
        constants.memory.store([({window}, {ExprInt(0x1234, 64)}, 64)])
        constants.control_calls.add(id(line))
        constants.mutex_calls.add(id(line))
        entry, _, temps = constants.instruction_plan(line)
        altered = dict(entry)
        altered[rsp] = rsp - ExprInt(16, 64)
        with patch.object(
            constants, "instruction_plan", return_value=(altered, None, temps)
        ):
            constants.update(line)
        self.assertFalse(constants.memory.words)

    def test_overlap_adjacency_and_modular_wrap(self):
        guards = EntryGuards()
        self.assertTrue(guards.separate(address("R12", -8), address("R13"), 8, 4))
        # Compare against concrete byte sets, independently of interval arithmetic.
        for base in (0, 0x1000, MASK - 4):
            for offset in range(-24, 25):
                registers = {"R12": base, "R13": (base + offset) & MASK}
                left = {(base - 8 + i) & MASK for i in range(8)}
                right = {(registers["R13"] + i) & MASK for i in range(4)}
                self.assertEqual(guards.accepts(registers), not left & right)

    def test_collected_conditions_never_drop_a_requested_separation(self):
        guards = EntryGuards()
        spans = [(0, 8, 16, 4), (4, 8, 18, 4), (64, 4, 128, 8)]
        for x, n, y, m in spans:
            self.assertTrue(guards.separate(address("R12", x), address("R13", y), n, m))
        rng = random.Random(7)
        for _ in range(1000):
            a, b = rng.randrange(256), rng.randrange(256)
            if not guards.accepts({"R12": a, "R13": b}):
                continue
            for x, n, y, m in spans:
                self.assertFalse(
                    set(range(a + x, a + x + n)) & set(range(b + y, b + y + m))
                )

    def test_missing_identity_and_budgets_are_not_assumptions(self):
        guards = EntryGuards()
        self.assertFalse(guards.separate(None, address("R13")))
        self.assertFalse(guards.separate(address("R12"), address("R12", 8)))
        self.assertFalse(guards.separate((ExprId("R12", 64), 0), address("R13")))
        with patch.object(guards, "MAX_RANGES", 1):
            self.assertFalse(guards.separate(address("R12"), address("R13")))
        with self.assertRaises(ValueError):
            guards.conditions()
        guards = EntryGuards()
        guards.separate(address("R12"), address("R13"))
        with self.assertRaises(KeyError):
            guards.accepts({"R12": 0})
        with patch.object(guards, "MAX_GUARDS", 0), self.assertRaises(ValueError):
            guards.conditions()

    def test_real_wrapper_predicate_matches_reference(self):
        guards = EntryGuards()
        guards.separate(address("R12", -8), address("R13"), 8, 4)
        cases = [
            (base, (base + delta) & MASK)
            for base in (0, 0x1000, MASK - 4)
            for delta in range(-16, 17)
        ]
        iterator = iter(cases)

        def initialize(regs, _):
            regs[3], regs[2] = next(iterator)

        results = run_image(guarded(guards), [0x1000] * len(cases), initialize)
        for (a, b), (regs, args) in zip(cases, results):
            accepted = guards.accepts({"R12": a, "R13": b})
            self.assertEqual(args[1], int(accepted))
            self.assertEqual(args[0] == ENTRY_REFUSED, not accepted)
            self.assertEqual(regs[10], 42 if accepted else 0)
            self.assertEqual((regs[3], regs[2]), (a, b))

    def test_failure_keeps_all_registers_stack_and_memory_unchanged(self):
        guards = EntryGuards()
        guards.separate(address("R14"), address("R15"), 8, 8)
        before, stacks = [], []
        destination = ctypes.c_ulong(0x1234)

        def initialize(regs, stack):
            for index in range(15):
                regs[index] = 0x1000 + index
            regs[0] = regs[1]
            regs[14] = ctypes.addressof(destination)
            before.append(list(regs))
            stacks.append(stack)

        # This store must not run on the failed guard path, not merely lack a log.
        results = run_image(guarded(guards, "48c7072a000000c3"), [0x1000], initialize)
        self.assertEqual(results[0][0], before[0])
        self.assertEqual(results[0][1], [ENTRY_REFUSED, 0])
        self.assertEqual(destination.value, 0x1234)
        self.assertEqual(list(stacks[0]), [0] * 8 + [0x4444] + [0] * 7)

    def test_absolute_guard_and_saved_register_offsets(self):
        for name, offset in REGISTER_OFFSETS.items():
            if name == "RSP":
                continue
            with self.subTest(register=name):
                guards = EntryGuards()
                guards.separate(address(name), address("", 0x8000), 8, 8)

                def initialize(regs, _, offset=offset):
                    regs[offset // 8] = 0x8000

                self.assertEqual(
                    run_image(guarded(guards), [0x1000], initialize)[0][1],
                    [ENTRY_REFUSED, 0],
                )

    def test_stack_guard_reads_saved_virtual_rsp_not_wrapper_rsp(self):
        guards = EntryGuards()
        guards.separate(address("RSP", -8), address("R12"), 8, 8)

        def initialize(regs, _):
            regs[3] = regs[19] - 8

        self.assertEqual(
            run_image(guarded(guards), [0x1000], initialize)[0][1], [ENTRY_REFUSED, 0]
        )

    def test_no_guard_and_continuation_dispatch(self):
        self.assertEqual(guarded(EntryGuards()), render("48c7c02a000000c3")[0])
        guards = EntryGuards()
        guards.separate(address("R12"), address("R13"), 8, 8)
        # Non-root entry is a continuation; production must establish prior admission.
        image = guarded(guards, "eb0048c7c02a000000c3")
        result = run_image(image, [0x1002])[0]
        self.assertEqual(result[0][10], 42)
        self.assertEqual(result[1][1], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

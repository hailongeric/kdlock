"""Guest-only exact byte/alias proof and real emitted guard execution."""
import ctypes
import unittest

from miasm.expression.expression import ExprId, ExprInt, ExprMem
from test_jit_diagnostics import decode, translator
from test_jit_body_witness import render, run_image
from address_guards import AddressGuards, GuardSite, EXIT, REQUIREMENT, TAG
from context_values import FlowConstants
from conflict import block_init


class AddressGuardTests(unittest.TestCase):
    def model(self, *, guarded=True, destination="rsp", opaque=False):
        guards = AddressGuards() if guarded else None
        tracker = FlowConstants(address_guards=guards)
        # RAX is a dynamic pointer loaded through an entry argument. A source
        # CALL-like stack write may alias it, but no entry predicate names RAX.
        for offset, raw in enumerate(("488b07", "48897424f8" if destination == "rsp"
                                      else "488936", "488b18")):
            line = decode(raw)
            line.offset = 0x1000 + offset * 16
            if opaque and offset == 2:
                tracker.origins.pop(ExprId("RSP", 64), None)
                tracker.origins.pop(ExprId("RBP", 64), None)
            tracker.update(line)
        return tracker, guards

    def test_only_checked_stack_aliases_gain_precision(self):
        for guarded, destination, opaque, accepted in (
            (False, "rsp", False, False), (True, "rsp", False, True),
            (True, "rsi", False, False), (True, "rsp", True, False),
        ):
            with self.subTest(guarded=guarded, destination=destination, opaque=opaque):
                tracker, guards = self.model(guarded=guarded, destination=destination,
                                              opaque=opaque)
                if accepted:
                    tracker.resolve_many(ExprId("RBX", 64))
                    self.assertEqual(guards.sites[0x1020].ranges, {("RSP", -8, 0)})
                else:
                    with self.assertRaisesRegex(translator.context_policy.ContextFlowLimit,
                                                "bounded register-address"):
                        tracker.resolve_many(ExprId("RBX", 64))

    def guarded_image(self, *, start=-8, end=0):
        # Hand-constructed collector output isolates lowering from proof tests.
        # The exact source MOV overwrites no flags; following CMP makes its
        # flags dead for the failure continuation. No kernel code is executed.
        raw = "488b074839c0c3"
        assembly, _ = render(raw)
        line = decode("488b07")
        line.offset = 0x1000
        guards = AddressGuards()
        guards.sites[line.offset] = GuardSite(line, line.args[1], {("RSP", start, end)})
        code = guards.emit(line, block_init()).encode()
        self.assertIn(b"loc_1000:\n", assembly)
        assembly = assembly.replace(b"loc_1000:\n", b"loc_1000:\n" + code, 1)
        return (b"#ifndef KD_EMIT_GUARD_DIRECTORY\n" + assembly + b"#else\n"
                + guards.metadata().encode() + b"#endif\n")

    def test_real_guard_preserves_full_packet_on_failure_and_runs_actual_load(self):
        assembly = self.guarded_image()
        value = ctypes.c_ulong(42)
        for aliases in (False, True):
            initial = {}

            def initialize(regs, stack):
                for index in range(2, 17):
                    regs[index] = 0x1000000000000000 + index * 0x10101
                regs[2] = regs[1] + 32
                stack[7] = 77
                regs[16] = regs[1] - 8 if aliases else ctypes.addressof(value)
                initial.update(values=list(regs), sp=regs[1])

            with self.subTest(aliases=aliases):
                regs, args = run_image(assembly, [0x1000], initialize,
                                       requirements=REQUIREMENT)[0]
                if aliases:
                    self.assertEqual(args[0], EXIT)
                    self.assertEqual((regs[0], regs[1], regs[17]), (0x1000, initial["sp"], TAG))
                    self.assertEqual(regs[2:17], initial["values"][2:17])
                else:
                    self.assertEqual(regs[12], 42)
                    self.assertEqual(args[1], 1)
                    self.assertEqual(regs[2:12], initial["values"][2:12])
                    self.assertEqual(regs[13:17], initial["values"][13:17])

    def test_midblock_guard_flushes_dirty_virtual_registers_and_moved_frame(self):
        # Unlike the block-entry fixture, this reaches emit() through the real
        # instruction loop. Five logical GPR writes exhaust the scratch pool;
        # the three-register LEA also temporarily borrows a stable frame slot.
        # The final logical R11 lives in physical R15 at the guarded source PC.
        for virtual_pointer, frame_base in ((False, "RSP"), (True, "RBP")):
            prefix = (
                "49c7c311111111"  # MOV R11, 0x11111111
                "49c7c412121212"  # MOV R12, 0x12121212
                "49c7c513131313"  # MOV R13, 0x13131313
                "49c7c614141414"  # MOV R14, 0x14141414
                "49c7c715151515"  # MOV R15, 0x15151515
                "4f8d1c2c"        # LEA R11, [R12 + R13]
                "4d01de"          # ADD R14, R11
                "488d6424f0"      # LEA RSP, [RSP - 16]
                "488d6d08"        # LEA RBP, [RBP + 8]
            )
            if virtual_pointer:
                prefix += "4989fb"  # MOV R11, RDI
            guarded_pc = 0x1000 + len(bytes.fromhex(prefix))
            raw = bytes.fromhex(prefix + ("498b03" if virtual_pointer else "488b07")
                                + "4839c0488d642410c3")  # CMP; restore SP; RET
            blocks, dbs = translator.decode_regions([(raw, 0x1000, [0x1000])], 0, set())
            self.assertEqual(set(blocks), {0x1000})
            line = next(item for item in blocks[0x1000].lines
                        if item.offset == guarded_pc)
            snapshots = []

            class ObservedGuards(AddressGuards):
                def emit(self, source, reg_map):
                    if source.offset == guarded_pc:
                        snapshots.append((dict(reg_map), set(reg_map.dirty)))
                    return super().emit(source, reg_map)

            guards = ObservedGuards()
            # Both intervals name the same harmless local stack word after
            # the original source has moved SP and BP; no return slot aliases.
            interval = (-8, 0) if frame_base == "RSP" else (-64, -56)
            guards.sites[guarded_pc] = GuardSite(line, line.args[1],
                                                {(frame_base, *interval)})
            guards.validate(blocks, dbs)
            table = {}
            missing = translator.indirect_jump.find(blocks, dbs, table)
            assembly = translator.emit_jit_assembly(
                0x1000, blocks, dbs, table, missing, {}, set(),
                body_witness=True, address_guards=guards,
            ).encode()
            self.assertEqual(len(snapshots), 1)
            mapping, dirty = snapshots[0]
            self.assertEqual(mapping["15"], "11")
            self.assertTrue({"11", "14"}.issubset(dirty))
            value = ctypes.c_ulong(42)
            for aliases in (False, True):
                initial = {}

                def initialize(regs, stack):
                    for index in range(2, 17):
                        regs[index] = 0x2000000000000000 + index * 0x10101
                    regs[2] = regs[1] + 32
                    stack[5] = 77
                    regs[16] = regs[1] - 24 if aliases else ctypes.addressof(value)
                    initial.update(values=list(regs), sp=regs[1])

                with self.subTest(virtual_pointer=virtual_pointer,
                                  frame_base=frame_base, aliases=aliases):
                    regs, args = run_image(assembly, [0x1000], initialize,
                                           requirements=REQUIREMENT)[0]
                    expected = initial["values"][:]
                    expected[2] += 8
                    expected[3:8] = [0x15151515, 0x39393939, 0x13131313,
                                     0x12121212,
                                     expected[16] if virtual_pointer else 0x25252525]
                    self.assertEqual(args[1], 1)
                    if aliases:
                        self.assertEqual((args[0], regs[0], regs[1], regs[17]),
                                         (EXIT, guarded_pc, initial["sp"] - 16, TAG))
                    else:
                        expected[12] = 42
                        self.assertNotEqual(args[0], EXIT)
                        self.assertEqual((regs[0], regs[1]),
                                         (0x4444, initial["sp"] + 8))
                    self.assertEqual(regs[2:17], expected[2:17])

    def test_overlap_predicate_includes_partial_and_modulo_edges(self):
        # All overlapping reads exit before a load, so even noncanonical test
        # addresses are never dereferenced. Place a valid word in the exact
        # non-overlapping cases to execute the admitted edge too.
        assembly = self.guarded_image()
        for delta in range(-15, 8):
            initial = {}

            def initialize(regs, stack):
                regs[2] = regs[1] + 32
                regs[16] = regs[1] + delta
                initial["sp"] = regs[1]

            regs, args = run_image(assembly, [0x1000], initialize,
                                   requirements=REQUIREMENT)[0]
            with self.subTest(delta=delta):
                self.assertEqual(args[0] == EXIT, -15 <= delta < 0)
                if args[0] == EXIT:
                    self.assertEqual((regs[0], regs[1]), (0x1000, initial["sp"]))
        mask = (1 << 64) - 1
        for stack_pointer in (0, 4, mask - 4):
            for delta in (-15, -8, -1):
                def initialize(regs, _):
                    regs[1] = stack_pointer
                    regs[2] = stack_pointer
                    regs[16] = (stack_pointer + delta) & mask

                regs, args = run_image(assembly, [0x1000], initialize,
                                       requirements=REQUIREMENT)[0]
                self.assertEqual((args[0], regs[1]), (EXIT, stack_pointer))

    def test_successful_guard_preserves_flags_in_lowering(self):
        # Deliberately exercise lowering in isolation with a flag-reading
        # suffix. Admission correctly refuses this suffix in the next test.
        assembly = self.guarded_image()
        assembly = assembly.replace(b"/* Checked source-stack", b"CMP RAX, RAX\n/* Checked source-stack", 1)
        assembly = assembly.replace(b"kd_address_guard_done_1000:\n",
                                    b"kd_address_guard_done_1000:\nSETZ DL\n", 1)
        value = ctypes.c_ulong(42)

        def initialize(regs, _):
            regs[16] = ctypes.addressof(value)

        regs, args = run_image(assembly, [0x1000], initialize,
                               requirements=REQUIREMENT)[0]
        self.assertEqual((regs[14] & 0xff, regs[12], args[1]), (1, 42, 1))

    def test_flags_dead_proof_is_required_for_every_collected_site(self):
        for suffix, accepted in (("4839c0c3", True), ("7401c3c3", False)):
            raw = bytes.fromhex("488b07" + suffix)
            blocks, dbs = translator.decode_regions([(raw, 0x1000, [0x1000])], 0, set())
            line = blocks[0x1000].lines[0]
            guards = AddressGuards()
            guards.sites[0x1000] = GuardSite(line, line.args[1], {("RSP", -8, 0)})
            with self.subTest(accepted=accepted):
                if accepted:
                    guards.validate(blocks, dbs)
                else:
                    with self.assertRaises(translator.context_policy.ContextFlowLimit):
                        guards.validate(blocks, dbs)

    def test_specialized_branch_cannot_hide_native_continuation_flag_read(self):
        # Source CMP proves JNE untaken for JIT execution. A failed guard would
        # still resume the original MOV/JNE, where native restoration does not
        # preserve ZF. Proving only the specialized JMP graph would be unsafe.
        raw = bytes.fromhex("31c039c0488b03750329c0c30f0b")
        original, databases = translator.decode_regions([(raw, 0x1000, [0x1000])],
                                                        0, set())
        line = next(item for item in original[0x1000].lines if item.offset == 0x1004)
        guards = AddressGuards()
        guards.sites[line.offset] = GuardSite(line, line.args[1], {("RSP", -8, 0)})
        with self.assertRaises(translator.context_policy.ContextFlowLimit):
            guards.validate(original, databases)
        selected, selected_databases, branches = translator.constant_paths.specialize(
            original, databases, 0x1000)
        self.assertTrue(branches)
        guards.validate(selected, selected_databases)

        # Exercise the real coordinator too: a dynamic pointer loaded from a
        # source stack argument becomes widened after an unrelated stack write.
        # The ordinary image can use a checked load. The version with a proved
        # JNE/cold UD2 must retain refusal instead of using that rewritten graph
        # to authorize native continuation.
        prefix = ("48c7c633330000"  # MOV RSI, 0x3333
                  "488b442408"    # MOV RAX, [RSP + 8]
                  "48897424f8"    # MOV [RSP - 8], RSI
                  "31c939c9"      # XOR ECX, ECX; CMP ECX, ECX
                  "488b18")       # MOV RBX, [RAX] needs checked alias exclusion
        for specialized in (False, True):
            # Both dynamic loads can collect a predicate; each real native
            # continuation must overwrite all arithmetic flags before RET.
            suffix = ("750a" if specialized else "") + "4839c9488b134839d2c3"
            suffix += "0f0b" if specialized else ""
            assembly, log, status = render(
                prefix + suffix, abi=1, address_guard_capable=True,
                kernel_symbols={"kd_raw_spin_lock_clobber_v1": 0x3000,
                                "kd_raw_spin_unlock_clobber_v1": 0x4000},
                return_status=True,
            )
            with self.subTest(specialized=specialized):
                if specialized:
                    self.assertIn("CONSTANT_PATH_SPECIALIZATION", log)
                    self.assertNotIn("ADDRESS_GUARDED_ADMISSION", log)
                    self.assertEqual((assembly, status), (b"", 2), log)
                else:
                    self.assertEqual(status, 0, log)
                    self.assertIn("ADDRESS_GUARDED_ADMISSION", log)


if __name__ == "__main__":
    unittest.main()

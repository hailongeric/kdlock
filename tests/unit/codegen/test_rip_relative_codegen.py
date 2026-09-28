"""Guest-only: prove folded RIP operands retain addresses, widths and effects.

Kernel addresses are assembled and inspected, never executed in userspace.
Owned MAP_32BIT storage exercises actual folded loads/stores/RMW through the
real wrapper; high userspace storage exercises the unencodable fallback.
"""
import ctypes
import mmap
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_jit_diagnostics import conflict, decode, normal
from test_jit_body_witness import run_image
from miasm.arch.x86.arch import mn_x86
from miasm.core.locationdb import LocationDB


def lower(source, next_ip):
    line = mn_x86.fromstring(source, loc_db=LocationDB(), mode=64)
    return normal.process_normal(line.name, line.args, next_ip, conflict.block_init())


def machine_code(assembly):
    with tempfile.TemporaryDirectory(prefix="kd-rip-codegen-") as temporary:
        path = Path(temporary)
        (path / "body.S").write_text(".intel_syntax noprefix\n.text\n" + assembly)
        subprocess.run(["cc", "-c", str(path / "body.S"), "-o", str(path / "body.o")],
                       check=True, timeout=30)
        subprocess.run(["objcopy", "-O", "binary", "--only-section=.text",
                        str(path / "body.o"), str(path / "body.bin")],
                       check=True, timeout=30)
        return (path / "body.bin").read_bytes()


def execute(assembly, initialize=None):
    # This unit exercises ordinary-instruction lowering plus the real FULL
    # wrapper exit. It substitutes only CFG dispatch, not register materialization.
    assembly += "MOV R14, 0x4444\nMOV Stack_IJ, 0\nJMP exit\n"
    return run_image(assembly.encode(), [0x1000], initialize=initialize)[0][0]


class RipRelativeCodegenTests(unittest.TestCase):
    def test_kernel_address_encodes_without_scratch_or_truncation(self):
        assembly = lower("MOV RCX, QWORD PTR [RIP + 0x1234]", 0xffffffffc0000000)
        self.assertEqual(len(assembly.splitlines()), 1)
        # REX.W + MOV /r + no-base SIB + signed disp32: effective address is
        # ffffffffc0001234, not the positive 00000000c0001234 address.
        self.assertEqual(machine_code(assembly), bytes.fromhex("488b0c25341200c0"))
        assembly = lower("MOV DWORD PTR [RIP - 0x20], ECX", 0xffffffff80000020)
        self.assertEqual(machine_code(assembly), bytes.fromhex("890c2500000080"))

    def test_disp32_boundaries_and_unencodable_targets(self):
        for address in (0, 0x7fffffff, 0xffffffff80000000, 0xffffffffffffffff):
            with self.subTest(address=hex(address)):
                assembly = lower("MOV RCX, QWORD PTR [RIP]", address)
                self.assertEqual(len(assembly.splitlines()), 1)
                self.assertEqual(len(machine_code(assembly)), 8)
        for address in (0x80000000, 0xffffffff7fffffff, 0xffff888012340000):
            with self.subTest(address=hex(address)):
                assembly = lower("MOV RCX, QWORD PTR [RIP]", address)
                self.assertIn("MOVABS", assembly)
                self.assertEqual(len(assembly.splitlines()), 2)

    def test_lea_full_partial_and_virtual_register_results(self):
        # Decode real LEA encodings, including operand-size prefixes, to cover
        # precisely the expressions produced by production disassembly.
        for destination, raw, packet_index, mask in (
                ("RDX", "488d15e0ffffff", 14, (1 << 64) - 1),
                ("EDX", "8d15e0ffffff", 14, (1 << 32) - 1),
                ("R11", "4c8d1de0ffffff", 7, (1 << 64) - 1)):
            with self.subTest(destination=destination):
                line = decode(raw)
                self.assertEqual(line.name, "LEA")
                mapping = conflict.block_init()
                assembly = normal.process_normal(line.name, line.args,
                                                  0xffff888012340020, mapping)
                # Virtual R11 is spilled at the block boundary, as in codegen.
                assembly += conflict.release_conflict(mapping)
                registers = execute(assembly)
                self.assertEqual(registers[packet_index], 0xffff888012340000 & mask)
        # LEA r16 changes only the low word; MOV r16,imm16 must preserve the rest.
        line = decode("668d1534000000")
        assembly = normal.process_normal(line.name, line.args, 0xffff888012340000,
                                          conflict.block_init())
        def initialize(registers, stack):
            registers[14] = 0x123456789abcffff
        self.assertEqual(execute(assembly, initialize)[14], 0x123456789abc0034)

    def test_low_storage_load_store_rmw_and_flags(self):
        with mmap.mmap(-1, mmap.PAGESIZE, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS | 0x40,
                       prot=mmap.PROT_READ | mmap.PROT_WRITE) as storage:
            address = ctypes.addressof(ctypes.c_char.from_buffer(storage))
            self.assertLess(address + 32, 1 << 31)
            words = (ctypes.c_ulong * 4).from_address(address)
            words[:] = (0x123456789abc, 0, 0, 0)
            assembly = lower("MOV RAX, QWORD PTR [RIP]", address)
            assembly += lower("MOV QWORD PTR [RIP], RAX", address + 8)
            assembly += "LOCK " + lower("ADD QWORD PTR [RIP], 1", address + 8)
            assembly += "SETNZ BL\n"
            registers = execute(assembly)
            self.assertEqual(list(words), [0x123456789abc, 0x123456789abd, 0, 0])
            self.assertEqual(registers[12], 0x123456789abc)
            self.assertEqual(registers[8] & 0xff, 1)

    def test_high_storage_fallback_executes_original_address(self):
        words = (ctypes.c_ulong * 2)(0x123456789abcdef, 0)
        address = ctypes.addressof(words)
        self.assertGreaterEqual(address, 1 << 31)
        assembly = lower("MOV RAX, QWORD PTR [RIP]", address)
        assembly += lower("MOV QWORD PTR [RIP], RAX", address + 8)
        self.assertEqual(assembly.count("MOVABS"), 2)
        execute(assembly)
        self.assertEqual(list(words), [0x123456789abcdef, 0x123456789abcdef])

    def test_gs_base_and_non_rip_addresses_keep_original_lowering(self):
        assembly = lower("MOV RAX, QWORD PTR GS:[RIP + 0x20]", 0xffffffffc0000000)
        self.assertIn("Stack_RGS", assembly)
        self.assertIn("MOVABS", assembly)
        assembly = lower("MOV RAX, QWORD PTR [RBX + 0x20]", 0xffffffffc0000000)
        self.assertIn("RBX", assembly)
        self.assertNotIn("MOVABS", assembly)


if __name__ == "__main__":
    unittest.main(verbosity=2)

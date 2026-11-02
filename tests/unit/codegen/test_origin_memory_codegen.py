"""VM-only GS instruction codegen with an explicit instruction-service double.

The real wrapper, metadata and successor execute. The double replaces only the
original-CPU operation; actual GS/context/ACK execution needs the live fixture.
"""
import ctypes
import struct
import unittest

from test_jit_diagnostics import decode, render
from test_jit_body_witness import run_image
from test_origin_instruction_codegen import image_bytes
from test_rip_relative_codegen import machine_code
import origin_memory

SERVICE_TAG = 0x4b44535643524545
ARITHMETIC = 0x8d5


def compile_source(source):
    raw = machine_code(source)
    options = {}
    assembly, log, status = render(raw.hex(), lock_kind="mutex", abi=2,
        trusted_source=True, body_witness=True, origin_memory_capable=True,
        return_status=True, build_options=options)
    if status:
        raise AssertionError(log)
    return raw, assembly, options


def arithmetic(old, width, decrement, carry):
    mask = (1 << width) - 1
    value = (old + (-1 if decrement else 1)) & mask
    flags = carry | (int(value == 0) << 6) | ((value >> (width - 1)) << 7)
    flags |= int((value & 255).bit_count() % 2 == 0) << 2
    flags |= int(bool((old ^ value ^ 1) & 16)) << 4
    flags |= int(old == ((1 << (width - 1)) if decrement else
                        (1 << (width - 1)) - 1)) << 11
    return value, flags


class OriginMemoryCodegenTests(unittest.TestCase):
    def test_exact_encodings_and_nonservice_forms(self):
        accepted = {
            "65ff00": (1, 32),
            "6548ff08": (2, 64),
            "6549ff45f0": (1, 64),
            "654bff44e520": (1, 64),
            "65ff05fcffffff": (1, 32),
            "6548ff0c25f0ffffff": (2, 64),
        }
        for raw, expected in accepted.items():
            with self.subTest(raw=raw):
                self.assertEqual(origin_memory.descriptor(decode(raw)), expected)
        for raw in ("ff00", "64ff00", "6548ffc0", "65ff10",
                    "6566ff00", "65fe00", "f06548ff00", "656748ff00"):
            with self.subTest(raw=raw):
                self.assertIsNone(origin_memory.descriptor(decode(raw)))

    def test_immutable_directory_matches_source_and_successors(self):
        raw, assembly, options = compile_source("""
            inc DWORD PTR gs:[rax + rcx*4 - 8]
            dec QWORD PTR gs:[r13 + 16]
            ret
        """)
        self.assertEqual(options["requirements"], 1920)
        binary = image_bytes(assembly, options["requirements"])
        magic, offset, count = struct.unpack_from("<8sII", binary, len(binary) - 16)
        self.assertEqual((magic, count), (b"KDOM0001", 2))
        self.assertEqual(offset + count * 40, len(binary) - 16)
        cursor = 0
        for index, (operation, width) in enumerate(((1, 32), (2, 64))):
            ip, next_ip, target, length, actual_op, actual_width, reserved, encoded = (
                struct.unpack_from("<QQIBBBB16s", binary, offset + index * 40))
            self.assertEqual((ip, next_ip), (0x1000 + cursor, 0x1000 + cursor + length))
            self.assertEqual((actual_op, actual_width, reserved), (operation, width, 0))
            self.assertEqual(encoded, raw[cursor:cursor + length].ljust(16, b"\0"))
            self.assertTrue(64 <= target < offset)
            cursor += length
        self.assertNotIn(b"INC             DWORD PTR [RGS", assembly)
        self.assertIn(b"MOV             Stack_IJ, 13", assembly)

    def test_other_gs_mutations_reach_explicit_before_effects_marker(self):
        for instruction in ("inc WORD PTR gs:[rax]", "add DWORD PTR gs:[rax], 1",
                            "mov QWORD PTR gs:[rax], rbx", "xchg QWORD PTR gs:[rax], rbx",
                            "lock inc DWORD PTR gs:[rax]"):
            with self.subTest(instruction=instruction):
                _, assembly, options = compile_source(instruction + "\nret")
                binary = image_bytes(assembly, options["requirements"])
                _, offset, count = struct.unpack_from("<8sII", binary, len(binary) - 16)
                self.assertEqual(count, 1)
                _, _, continuation, _, operation, width, _, _ = struct.unpack_from(
                    "<QQIBBBB16s", binary, offset)
                self.assertEqual((continuation, operation, width), (0, 0, 0))
                # Invalid GS context deliberately makes ordinary execution
                # unsuitable here. The real wrapper must stop first instead.
                regs, args = run_image(assembly, [0x1000], abi=2,
                    requirements=options["requirements"])[0]
                self.assertEqual(args, [13, 1])
                self.assertEqual(regs[0], 0x1000)

    def test_no_call_word_and_flags_aware_reentry(self):
        for instruction, width, old, decrement in (
                ("inc DWORD PTR gs:[rax + rcx*4 - 8]", 32, 0xffffffff, False),
                ("dec QWORD PTR gs:[r13 + 16]", 64, 0x8000000000000000, True)):
            with self.subTest(instruction=instruction):
                raw, assembly, options = compile_source(f"""
                    add QWORD PTR[rbp], 1
                    mov rax, 0x100
                    mov rcx, 2
                    mov r11, 0x1111
                    mov r12, 0x1212
                    mov r13, 0x1313
                    mov r14, 0x1414
                    mov r15, 0x1515
                    stc
                    {instruction}
                    setc BYTE PTR[rbp + 8]
                    setz BYTE PTR[rbp + 9]
                    sets BYTE PTR[rbp + 10]
                    seto BYTE PTR[rbp + 11]
                    mov QWORD PTR[rbp + 16], r11
                    mov QWORD PTR[rbp + 24], r12
                    mov QWORD PTR[rbp + 32], r13
                    mov QWORD PTR[rbp + 40], r14
                    mov QWORD PTR[rbp + 48], r15
                    ret
                """)
                operation = machine_code(instruction)
                data = (ctypes.c_ulong * 7)()
                initial = []
                visited = []
                _, expected_flags = arithmetic(old, width, decrement, 1)
                def initialize(regs, stack):
                    regs[2] = ctypes.addressof(data)
                    initial.append((regs[1], regs[2], stack[8]))
                def service(regs, args, stack):
                    if args[0] != 13:
                        return False
                    visited.append(regs[0])
                    self.assertEqual(regs[0], 0x1000 + raw.index(operation))
                    self.assertEqual((regs[1], regs[2], stack[8]), initial[0])
                    self.assertEqual(regs[19] & 1, 1)
                    self.assertEqual((regs[12], regs[13]), (0x100, 2))
                    regs[19] = (regs[19] & ~ARITHMETIC) | expected_flags
                    regs[0] += len(operation)
                    regs[17] = SERVICE_TAG
                    return True
                regs, args = run_image(assembly, [0x1000], initialize=initialize,
                    resume=service, abi=2, requirements=options["requirements"])[0]
                self.assertEqual(len(visited), 1)
                self.assertEqual(data[0], 1)
                self.assertEqual(data[1], sum(((expected_flags >> bit) & 1) << shift
                    for bit, shift in ((0, 0), (6, 8), (7, 16), (11, 24))))
                self.assertEqual(list(data)[2:], [0x1111, 0x1212, 0x1313, 0x1414, 0x1515])
                self.assertEqual(regs[1], initial[0][0] + 8)
                self.assertEqual(args[1], 1)


if __name__ == "__main__":
    unittest.main()

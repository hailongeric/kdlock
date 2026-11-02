"""VM-only guarded GS reads, with an explicit origin-instruction double."""
import ctypes
import struct
import unittest

from test_jit_diagnostics import decode, render
from test_jit_body_witness import run_image
from test_origin_instruction_codegen import image_bytes
from test_rip_relative_codegen import machine_code
from test_instruction_policy import SYMBOLS
import origin_memory

PREEMPT = 0x18030
TAG = 0x4b44535643524545
ARITHMETIC = 0x8d5


def compile_source(source):
    raw = machine_code(source)
    options = {}
    assembly, log, status = render(raw.hex(), lock_kind="mutex", abi=2,
        kernel_symbols=SYMBOLS | {"__preempt_count": PREEMPT}, trusted_source=True,
        body_witness=True, origin_memory_capable=True, origin_context_read_capable=True,
        return_status=True, build_options=options)
    if status: raise AssertionError(log)
    return raw, assembly, options


class OriginContextReadCodegenTests(unittest.TestCase):
    def test_exact_read_opcodes_and_versioned_symbol(self):
        for encoded, expected in (("658b00", (3, 32)), ("654c8b38", (3, 64)),
                                  ("6566f74001ffff", (4, 16)),
                                  ("65f70001000000", (4, 32))):
            self.assertEqual(origin_memory.descriptor(decode(encoded)), expected)
        for encoded in ("658b20", "65668b00", "658500", "6548f70001000000"):
            self.assertIsNone(origin_memory.descriptor(decode(encoded)))
        _, assembly, options = compile_source("mov eax, DWORD PTR gs:[rax]\nret")
        self.assertEqual(options["requirements"], 3968)
        binary = image_bytes(assembly, options["requirements"])
        magic, offset, count, symbol = struct.unpack_from("<8sIIQ", binary, len(binary) - 24)
        self.assertEqual((magic, count, symbol), (b"KDOM0002", 1, PREEMPT))
        _, _, target, _, operation, width, flags, _ = struct.unpack_from("<QQIBBBB16s", binary, offset)
        self.assertEqual((operation, width, flags), (3, 32, 1))
        self.assertTrue(64 <= target < offset)

    def test_nonoverlap_keeps_actual_load_and_source_flags(self):
        _, assembly, options = compile_source(f"""
            xor eax,eax
            mov rax,{PREEMPT + 4}
            mov rcx,0xffffaaaa00000000
            stc
            mov ecx,DWORD PTR gs:[rax]
            mov QWORD PTR[rbp],rcx
            setc BYTE PTR[rbp+8]
            setz BYTE PTR[rbp+9]
            ret
        """)
        cpu = (ctypes.c_uint32 * 4)(0x80010001, 0xfedcba98, 0x12345678, 0)
        data = (ctypes.c_ulong * 2)()
        calls = []
        def initialize(regs, stack): regs[2] = ctypes.addressof(data)
        def service(regs, args, stack):
            if args[0] == 13: calls.append(regs[0])
            return False
        regs, args = run_image(assembly, [0x1000], initialize=initialize, resume=service,
            context=(ctypes.addressof(cpu) - PREEMPT, 0xbeef), abi=2,
            requirements=options["requirements"])[0]
        self.assertEqual(calls, [])
        self.assertEqual(list(data), [0xfedcba98, 0x101])
        self.assertNotEqual(args[0], 13)

    def test_dynamic_alias_load_zero_extends_only_its_destination(self):
        for address in ("rax+rcx*2-8", "rax"):
            with self.subTest(address=address):
                instruction = f"mov r15d,DWORD PTR gs:[{address}]"
                raw, assembly, options = compile_source(f"""
                    xor eax,eax
                    mov rax,{PREEMPT}
                    mov rcx,4
                    mov r15,0xffffaaaa12345678
                    stc
                    {instruction}
                    mov QWORD PTR[rbp],r15
                    setc BYTE PTR[rbp+8]
                    setz BYTE PTR[rbp+9]
                    ret
                """)
                encoded = machine_code(instruction)
                cpu = (ctypes.c_uint32 * 4)(0x80010001, 0, 0, 0)
                data = (ctypes.c_ulong * 2)()
                initial = []
                calls = []
                def initialize(regs, stack):
                    regs[2] = ctypes.addressof(data)
                    initial.append((regs[1], stack[8]))
                def service(regs, args, stack):
                    if args[0] != 13: return False
                    calls.append(regs[0])
                    self.assertEqual(regs[0], 0x1000 + raw.index(encoded))
                    self.assertEqual((regs[1], stack[8]), initial[0])
                    self.assertEqual((regs[12], regs[13], regs[3]),
                                     (PREEMPT, 4, 0xffffaaaa12345678))
                    regs[3] = 0x80000000
                    regs[0] += len(encoded)
                    regs[17] = TAG
                    return True
                _, args = run_image(assembly, [0x1000], initialize=initialize, resume=service,
                    context=(ctypes.addressof(cpu) - PREEMPT, 0xbeef), abi=2,
                    requirements=options["requirements"])[0]
                self.assertEqual(len(calls), 1)
                self.assertEqual(list(data), [0x80000000, 0x101])
                self.assertEqual(args[1], 1)

    def test_nonoverlap_complex_offsets_preserve_flags_and_source_registers(self):
        variants = (("rax", "rcx", "rax", "rcx", PREEMPT + 4, 4),
                    ("r12", "r13", "r12", "r13", PREEMPT + 4, 4),
                    ("r12", "r13", "r12d", "r13d",
                     0xffffaaaa00000000 | (PREEMPT + 4), 0x1234000000000004))
        for base, index, ea_base, ea_index, base_value, index_value in variants:
            with self.subTest(ea_base=ea_base, ea_index=ea_index):
                _, assembly, options = compile_source(f"""
                    xor eax,eax
                    mov {base},{base_value}
                    mov {index},{index_value}
                    mov r15,0xffffaaaa00000000
                    stc
                    mov r15d,DWORD PTR gs:[{ea_base}+{ea_index}*2-8]
                    mov QWORD PTR[rbp],r15
                    setc BYTE PTR[rbp+8]
                    setz BYTE PTR[rbp+9]
                    test DWORD PTR gs:[{ea_base}+{ea_index}*2-8],0x80000000
                    setz BYTE PTR[rbp+10]
                    setc BYTE PTR[rbp+11]
                    seto BYTE PTR[rbp+12]
                    mov QWORD PTR[rbp+16],{base}
                    mov QWORD PTR[rbp+24],{index}
                    ret
                """)
                cpu = (ctypes.c_uint32 * 4)(0x80010001, 0xfedcba98, 0, 0)
                data = (ctypes.c_ulong * 4)()
                calls = []
                def initialize(regs, stack): regs[2] = ctypes.addressof(data)
                def service(regs, args, stack):
                    if args[0] == 13: calls.append(regs[0])
                    return False
                run_image(assembly, [0x1000], initialize=initialize, resume=service,
                    context=(ctypes.addressof(cpu) - PREEMPT, 0xbeef), abi=2,
                    requirements=options["requirements"])
                self.assertEqual(calls, [])
                self.assertEqual(list(data), [0xfedcba98, 0x101, base_value, index_value])

    def test_nonoverlap_load_to_bp_keeps_the_updated_stable_value(self):
        _, assembly, options = compile_source(f"""
            xor eax,eax
            mov rax,{PREEMPT + 8}
            stc
            mov rbp,QWORD PTR gs:[rax]
            mov QWORD PTR[rbp],0x1234
            setc BYTE PTR[rbp+8]
            setz BYTE PTR[rbp+9]
            ret
        """)
        before = (ctypes.c_ulong * 2)()
        after = (ctypes.c_ulong * 2)()
        cpu = (ctypes.c_ulong * 2)(0x80010001, ctypes.addressof(after))
        calls = []
        def initialize(regs, stack): regs[2] = ctypes.addressof(before)
        def service(regs, args, stack):
            if args[0] == 13: calls.append(regs[0])
            return False
        regs, _ = run_image(assembly, [0x1000], initialize=initialize, resume=service,
            context=(ctypes.addressof(cpu) - PREEMPT, 0xbeef), abi=2,
            requirements=options["requirements"])[0]
        self.assertEqual(calls, [])
        self.assertEqual(list(before), [0, 0])
        self.assertEqual(list(after), [0x1234, 0x101])
        self.assertEqual(regs[2], ctypes.addressof(after))

    def test_partial_word_and_dword_tests_service_the_origin(self):
        for displacement, width, mask in ((1, "WORD", 0xffff), (0, "DWORD", 1),
                                          (-1, "WORD", 0xff00)):
            with self.subTest(displacement=displacement, width=width):
                instruction = f"test {width} PTR gs:[rax+rcx],{mask}"
                _, assembly, options = compile_source(f"""
                    mov rax,{PREEMPT}
                    mov rcx,{displacement}
                    stc
                    {instruction}
                    setz BYTE PTR[rbp]
                    setc BYTE PTR[rbp+1]
                    seto BYTE PTR[rbp+2]
                    ret
                """)
                encoded = machine_code(instruction)
                cpu = (ctypes.c_uint32 * 6)(0, 0x80010001, 0, 0, 0, 0)
                data = (ctypes.c_ulong * 1)()
                calls = []
                def initialize(regs, stack): regs[2] = ctypes.addressof(data)
                def service(regs, args, stack):
                    if args[0] != 13: return False
                    calls.append(regs[0])
                    self.assertEqual(regs[19] & 1, 1)
                    regs[19] = (regs[19] & ~ARITHMETIC) | 0x44
                    regs[0] += len(encoded)
                    regs[17] = TAG
                    return True
                run_image(assembly, [0x1000], initialize=initialize, resume=service,
                    context=(ctypes.addressof(cpu) + 4 - PREEMPT, 0xbeef), abi=2,
                    requirements=options["requirements"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(data[0], 1)

    def test_unsupported_overlapping_read_has_no_destination_effect(self):
        _, assembly, options = compile_source(f"""
            mov rax,{PREEMPT}
            mov rcx,0x11223344
            movzx ecx,BYTE PTR gs:[rax]
            ret
        """)
        regs, args = run_image(assembly, [0x1000], abi=2,
                              requirements=options["requirements"])[0]
        self.assertEqual(args, [13, 1])
        self.assertEqual(regs[13], 0x11223344)


if __name__ == "__main__": unittest.main()

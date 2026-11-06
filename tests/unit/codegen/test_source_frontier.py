"""Exact source frontier lowering and real generated-state export on the VM."""
import ctypes
import mmap
import unittest

from test_jit_diagnostics import render, translator
from test_jit_body_witness import run_image
from test_rip_relative_codegen import machine_code

frontier = translator.source_frontier


class SourceFrontierTests(unittest.TestCase):
    def compile(self, raw, *, capable=True, extended=False, controls=False, direction=False):
        options = {}
        assembly, log, status = render(raw.hex(), lock_kind='mutex', abi=2,
            trusted_source=True, body_witness=True, source_frontier_capable=capable,
            source_frontier_extensions=extended, source_frontier_controls=controls,
            source_frontier_direction=direction,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100},
            build_options=options, return_status=True)
        return assembly, log, status, options

    def test_reached_frontier_exports_exact_state_and_effect_once(self):
        raw = machine_code('''
            mov eax, 3
            lock xadd QWORD PTR [rbp], rax
            mov rdi, 0x1122
            mov rsi, 0x3344
            mov rdx, 0x5566
            mov r8, 0x7788
            .byte 0x67,0x48,0x0f,0xb9,0x3a
            mov QWORD PTR [rbp+8], 99
            ret
        ''')
        assembly, log, status, options = self.compile(raw)
        self.assertEqual(status, 0, log)
        self.assertTrue(options['requirements'] & frontier.REQUIREMENT)
        memory = (ctypes.c_ulong * 2)(5, 0)
        saved = []
        def initialize(regs, stack):
            regs[2] = ctypes.addressof(memory)
            saved.append((regs[1], stack))
        regs, result = run_image(assembly, [0x1000], initialize=initialize,
            abi=2, requirements=options['requirements'])[0]
        self.assertEqual(result, [frontier.EXIT, 1])
        self.assertEqual(regs[0], 0x1000 + raw.index(frontier.ENCODING))
        self.assertEqual(regs[1], saved[0][0])
        self.assertEqual(saved[0][1][8], 0x4444)
        self.assertEqual((regs[12], regs[16], regs[15], regs[14], regs[11]),
                         (5, 0x1122, 0x3344, 0x5566, 0x7788))
        self.assertEqual(list(memory), [8, 0])

    def test_other_branch_keeps_jit_execution(self):
        raw = machine_code('''
            cmp QWORD PTR [rbp], 0
            je done
            .byte 0x67,0x48,0x0f,0xb9,0x3a
        done:
            mov eax, 42
            ret
        ''')
        assembly, log, status, options = self.compile(raw)
        self.assertEqual(status, 0, log)
        memory = ctypes.c_ulong(0)
        regs, result = run_image(assembly, [0x1000],
            initialize=lambda regs, stack: regs.__setitem__(2, ctypes.addressof(memory)),
            abi=2, requirements=options['requirements'])[0]
        self.assertEqual(result, [15, 1])  # ordinary source RET dispatch
        self.assertEqual(regs[12], 42)

    def test_bytes_inside_an_immediate_are_not_a_frontier(self):
        raw = machine_code('mov rax, 0x3ab90f4867; ret')
        assembly, log, status, options = self.compile(raw)
        self.assertEqual(status, 0, log)
        self.assertFalse(options['requirements'] & frontier.REQUIREMENT)

    def test_unnegotiated_provider_cannot_emit_frontier_image(self):
        assembly, log, status, _ = self.compile(frontier.ENCODING + b'\xc3' + b'\x90' * 32,
                                               capable=False)
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_only_complete_exact_encoding_is_recognized(self):
        from miasm.core.bin_stream import bin_stream_str
        decoder = frontier.Decoder(type('Arch', (), {'dis': lambda *args: None})())
        self.assertTrue(frontier.descriptor(decoder.dis(bin_stream_str(frontier.ENCODING), 64, 0)))
        for index in range(len(frontier.ENCODING)):
            raw = bytearray(frontier.ENCODING);raw[index] ^= 1
            self.assertIsNone(decoder.dis(bin_stream_str(bytes(raw)), 64, 0))
        for size in range(len(frontier.ENCODING)):
            self.assertIsNone(decoder.dis(bin_stream_str(frontier.ENCODING[:size]), 64, 0))

    def test_observed_state_instructions_preserve_reached_and_other_paths(self):
        self.check_instruction_paths(frontier.EXTENDED_ENCODINGS, extended=True)

    def test_interrupt_boundaries_preserve_reached_and_other_paths(self):
        self.check_instruction_paths(frontier.CONTROL_ENCODINGS, controls=True)
        from miasm.core.bin_stream import bin_stream_str
        arch = type('Arch', (), {'dis': lambda *args: None})()
        for encoding in frontier.CONTROL_ENCODINGS:
            stream = bin_stream_str(encoding)
            self.assertIsNone(frontier.Decoder(arch, extended=True).dis(stream, 64, 0))
            self.assertTrue(frontier.descriptor(
                frontier.Decoder(arch, controls=True).dis(stream, 64, 0)))

    def test_direction_boundaries_preserve_reached_and_other_paths(self):
        self.check_instruction_paths(frontier.DIRECTION_ENCODINGS, direction=True)

    def test_direction_forms_require_exact_decode_and_negotiation(self):
        from miasm.core.bin_stream import bin_stream_str
        arch = type('Arch', (), {'dis': lambda *args: None})()
        for encoding in frontier.DIRECTION_ENCODINGS:
            stream = bin_stream_str(encoding)
            self.assertIsNone(frontier.Decoder(arch, extended=True, controls=True).dis(stream, 64, 0))
            self.assertTrue(frontier.descriptor(
                frontier.Decoder(arch, direction=True).dis(stream, 64, 0)))
            for prefix in (b'\x66', b'\xf3', b'\xf0'):
                self.assertIsNone(frontier.Decoder(arch, direction=True).dis(
                    bin_stream_str(prefix + encoding), 64, 0))
        assembly, log, status, options = self.compile(machine_code('mov eax,0xfdfc; ret'), direction=True)
        self.assertEqual(status, 0, log)
        self.assertFalse(options['requirements'] & frontier.REQUIREMENT)

    def test_direction_boundary_coexists_with_retained_memory_services(self):
        options = {}
        assembly, log, status = render(machine_code('inc QWORD PTR gs:[rax]; std; ret').hex(),
            lock_kind='mutex', abi=2, trusted_source=True, native_escape_capable=True,
            origin_memory_capable=True, source_frontier_capable=True,
            source_frontier_direction=True, return_status=True, build_options=options)
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)
        self.assertTrue(options['requirements'] & frontier.REQUIREMENT)
        self.assertTrue(options['requirements'] & (1 << 8))  # retained service queue
        self.assertFalse(options['requirements'] & translator.native_escape.REQUIREMENT)

    def test_pre_std_packet_preserves_copy_preparation_and_native_suffix(self):
        raw = machine_code('''
            inc QWORD PTR [rbp]
            mov rax,rdi
            mov rcx,rdx
            mov r11,QWORD PTR [rsi]
            mov r10,rdi
            lea rsi,[rsi+rdx-8]
            lea rdi,[rdi+rdx-8]
            shr rcx,3
            std
            rep movsq
            cld
            mov QWORD PTR [r10],r11
            ret
        ''')
        assembly, log, status, options = self.compile(raw, direction=True)
        self.assertEqual(status, 0, log)
        data = (ctypes.c_ulong * 6)(0xcafe, 0x11, 0x22, 0x33, 0x44, 0xbeef)
        before = list(data)
        source, destination = ctypes.addressof(data) + 8, ctypes.addressof(data) + 16
        effect = ctypes.c_ulong(0)
        saved = []
        def initialize(regs, stack):
            regs[2] = ctypes.addressof(effect)
            regs[14], regs[15], regs[16] = 24, source, destination
            saved.append((regs[1], stack))
        regs, result = run_image(assembly, [0x1000], initialize=initialize,
            abi=2, requirements=options['requirements'])[0]
        self.assertEqual(result, [frontier.EXIT, 1])
        self.assertEqual(regs[0], 0x1000 + raw.index(b'\xfd'))
        self.assertEqual(regs[1], saved[0][0])
        self.assertEqual(saved[0][1][8], 0x4444)
        self.assertEqual((regs[7], regs[9], regs[12], regs[13], regs[14], regs[15], regs[16]),
                         (0x11, destination, destination, 3, 24, source + 16, destination + 16))
        self.assertEqual(regs[19] & (1 << 10), 0)
        self.assertEqual(list(data), before)
        self.assertEqual(effect.value, 1)
        clear_ip = 0x1000 + raw.index(b'\xfc')
        self.assertNotIn(f'loc_{clear_ip:x}:'.encode(), assembly)

        # This bounded native-suffix double uses its own C stack after JIT has
        # returned. It checks prepared scalar values, overlap, DF clearing and
        # no replay; it does not substitute for kernel origin restoration.
        suffix = machine_code('''
            push rbx
            mov rbx,rdi
            mov rax,QWORD PTR [rbx+96]
            mov rcx,QWORD PTR [rbx+104]
            mov rsi,QWORD PTR [rbx+120]
            mov rdi,QWORD PTR [rbx+128]
            mov r10,QWORD PTR [rbx+72]
            mov r11,QWORD PTR [rbx+56]
            std
            rep movsq
            cld
            mov QWORD PTR [r10],r11
            pushfq
            pop QWORD PTR [rbx+152]
            pop rbx
            ret
        ''')
        packet = (ctypes.c_ulong * 21)(*regs)
        with mmap.mmap(-1, len(suffix), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC) as memory:
            memory.write(suffix)
            invoke = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))(
                ctypes.addressof(ctypes.c_char.from_buffer(memory)))
            self.assertEqual(invoke(packet), destination)
        self.assertEqual(list(data), [0xcafe, 0x11, 0x11, 0x22, 0x33, 0xbeef])
        self.assertEqual(packet[19] & (1 << 10), 0)
        self.assertEqual(effect.value, 1)

    def check_instruction_paths(self, encodings, **compile_options):
        from miasm.core.bin_stream import bin_stream_str
        for encoding in encodings:
            with self.subTest(encoding=encoding.hex()):
                raw = machine_code('mov eax,3; lock xadd QWORD PTR[rbp],rax')
                raw += encoding + machine_code('mov QWORD PTR[rbp+8],99; ret')
                assembly, log, status, options = self.compile(raw, **compile_options)
                self.assertEqual(status, 0, log)
                memory = (ctypes.c_ulong * 2)(5, 0)
                before = []
                def initialize(regs, stack):
                    regs[2] = ctypes.addressof(memory)
                    before.append(regs[1])
                regs, result = run_image(assembly, [0x1000], initialize=initialize,
                    abi=2, requirements=options['requirements'])[0]
                self.assertEqual(result, [frontier.EXIT, 1])
                self.assertEqual(regs[0], 0x1000 + raw.index(encoding))
                self.assertEqual(regs[1], before[0])
                self.assertEqual(list(memory), [8, 0])
                directives = ','.join(hex(value) for value in encoding)
                branch = machine_code('cmp QWORD PTR[rbp],0; je done; .byte ' +
                                      directives + '; done: mov eax,42; ret')
                assembly, log, status, options = self.compile(branch, **compile_options)
                self.assertEqual(status, 0, log)
                zero = ctypes.c_ulong(0)
                regs, result = run_image(assembly, [0x1000],
                    initialize=lambda regs, stack: regs.__setitem__(2, ctypes.addressof(zero)),
                    abi=2, requirements=options['requirements'])[0]
                self.assertEqual(result, [15, 1])
                self.assertEqual(regs[12], 42)
                legacy = frontier.Decoder(type('Arch', (), {'dis': lambda *args: None})())
                self.assertIsNone(legacy.dis(bin_stream_str(encoding), 64, 0))


if __name__ == '__main__':
    unittest.main(verbosity=2)

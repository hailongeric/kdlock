"""Exact source frontier lowering and real generated-state export on the VM."""
import ctypes
import unittest

from test_jit_diagnostics import render, translator
from test_jit_body_witness import run_image
from test_rip_relative_codegen import machine_code

frontier = translator.source_frontier


class SourceFrontierTests(unittest.TestCase):
    def compile(self, raw, *, capable=True):
        options = {}
        assembly, log, status = render(raw.hex(), lock_kind='mutex', abi=2,
            trusted_source=True, body_witness=True, source_frontier_capable=capable,
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
        assembly, log, status, _ = self.compile(frontier.ENCODING + b'\xc3', capable=False)
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


if __name__ == '__main__':
    unittest.main(verbosity=2)

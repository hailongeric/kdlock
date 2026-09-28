"""Inspect real wrapper imports; execution of GS/task inputs lives in segment tests."""
import os
from pathlib import Path
import re
import tempfile
import unittest

from test_jit_diagnostics import translator


class WrapperInputs(unittest.TestCase):
    def test_final_code_requirements_and_uncertainty(self):
        required = translator.wrapper_context_inputs
        self.assertEqual(required('/* MOV Stack_RGS, Stack_TASK */\nNOP\n'), (False, False))
        self.assertEqual(required('MOV R15, Stack_RGS\n'), (True, False))
        self.assertEqual(required('MOV R15, Stack_RCT\n'), (False, True))
        self.assertEqual(required('MOV R15, Stack_RGS\nMOV R14, Stack_TASK'), (True, True))
        for unknown in (None, '#include "more.S"', '.include "more.S"',
                        '.macro custom', '/* unclosed', 'MOV R15, MEM_ARG'):
            self.assertEqual(required(unknown), (True, True))

    def test_regular_and_clobber_imports_keep_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder/'asm').mkdir()
            (folder/'asm/jit.S').write_text('MOV R14, 0x1000\nJMP exit\n')
            os.chdir(folder)
            try:
                for inputs in (None, (False, False), (True, False), (False, True)):
                    translator.build_jit_binary(1, context_inputs=inputs)
                    disassembly = (folder/'asm/bin.txt').read_text()
                    gs, task = (True, True) if inputs is None else inputs
                    # Each retained context input has one store in both entry
                    # paths. Inspect assembled instructions, not #if text.
                    self.assertEqual(len(re.findall(r'mov\s+QWORD PTR \[rbp-0x78\],rax', disassembly)), 2*gs)
                    self.assertEqual(len(re.findall(r'mov\s+QWORD PTR \[rbp-0x80\],rax', disassembly)), 2*task)
                    image = (folder/'asm/jit.bin').read_bytes()
                    self.assertEqual(image[9:16], b'KDWB002')
                    self.assertEqual(image[25:32], b'KDWC002')
                    self.assertEqual(image[41:46], b'KDAB\x01')
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()

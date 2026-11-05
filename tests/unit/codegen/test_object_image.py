"""Guest assembler checks for complete raw JIT image extraction."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_jit_diagnostics import translator
from object_image import require_complete_object


class ObjectImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kdlock-object-image-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def assemble(self, source):
        assembly = self.directory / "source.S"
        obj = self.directory / "source.o"
        assembly.write_text(".intel_syntax noprefix\n.text\nmain:\nret\n" + source)
        subprocess.run(["gcc", "-c", str(assembly), "-o", str(obj)],
                       check=True, capture_output=True)
        return obj

    def test_undefined_code_reference_is_incomplete(self):
        obj = self.assemble("mov QWORD PTR [Stack_R], r13\n")
        with self.assertRaisesRegex(ValueError, r"emitted \.text.*Stack_R"):
            require_complete_object(obj)

    def test_defined_data_reference_still_needs_relocation(self):
        obj = self.assemble(".data\n.quad main\n")
        with self.assertRaisesRegex(ValueError, r"emitted \.data"):
            require_complete_object(obj)

    def test_allocated_metadata_reference_is_incomplete(self):
        obj = self.assemble('.section .kd_metadata,"a",@progbits\n.quad main\n')
        with self.assertRaisesRegex(ValueError, r"emitted \.kd_metadata"):
            require_complete_object(obj)

    def test_debug_only_relocation_does_not_affect_image(self):
        obj = self.assemble('.section .debug_info,"",@progbits\n.quad debug_value\n')
        require_complete_object(obj)

    def test_resolved_local_expressions_and_literal_call_fields(self):
        obj = self.assemble(".byte 0xe8\n.long 0\nnext:\nret\n.long next - main\n")
        require_complete_object(obj)

    def test_failed_build_removes_old_raw_output_and_retains_object(self):
        asm = self.directory / "asm"
        asm.mkdir()
        (asm / "jit.S").write_text("mov QWORD PTR [Stack_R], r13\njmp full_exit\n")
        for name in ("jit.bin", "bin.txt"):
            (asm / name).write_bytes(b"old image")
        previous = Path.cwd()
        os.chdir(self.directory)
        try:
            with self.assertRaisesRegex(ValueError, "Stack_R"):
                translator.build_jit_binary()
        finally:
            os.chdir(previous)
        self.assertTrue((asm / "jit.o").is_file())
        self.assertTrue((asm / "jit.S").is_file())
        self.assertFalse((asm / "jit.bin").exists())
        self.assertFalse((asm / "bin.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""VM-only target-byte checks for the original KD logical-current GS route.

Run this module alone with KDLOCK_KERNEL_GS_TEST_CONFIG naming an explicit JSON
receipt: vmlinux, vmlinux_sha256, system_map, system_map_sha256, kernel_config,
kernel_config_sha256, site, instruction_hex, current_task. File paths and exact
hashes bind the actual linked witness. No guessed per-CPU-relative offset,
loaded-module or running-kernel proof is inferred from this offline input.

Only the existing decoder and lowering construct assembly; no machine code is
assembled or executed. Derived LEA/address-width byte cases check the affected
architectural distinction; they are not additional actual kernel instructions.
Do not import/run this module on the source host. Missing inputs fail, not skip.
"""

import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

from disassem.backend.conflict import block_init
from disassem.backend.normal import NormalLowering
from disassem.source_decode import SourceBytes, decode_source


MASK64 = (1 << 64) - 1


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def word(value):
    actual = int(value, 0) if isinstance(value, str) else value
    if type(actual) is not int or not 0 <= actual <= MASK64:
        raise ValueError("explicit target address is outside unsigned64")
    return actual


def linked_bytes(path, address, length):
    """Read one file-backed ELF64 section at its actual linked address."""
    with path.open("rb") as stream:
        raw = stream.read(64)
        if len(raw) != 64:
            raise ValueError("incomplete target ELF header")
        header = struct.unpack("<16sHHIQQQIHHHHHH", raw)
        if header[0][:6] != b"\x7fELF\x02\x01" or header[2] != 62 or header[11] < 64:
            raise ValueError("target is not an x86_64 little-endian ELF")
        for index in range(header[12]):
            stream.seek(header[6] + index * header[11])
            section = stream.read(64)
            if len(section) != 64:
                raise ValueError("incomplete target section header")
            fields = struct.unpack("<IIQQQQIIQQ", section)
            virtual, offset, size = fields[3], fields[4], fields[5]
            if fields[1] == 1 and virtual <= address and length <= virtual + size - address:
                stream.seek(offset + address - virtual)
                data = stream.read(length)
                if len(data) != length:
                    raise ValueError("incomplete actual source instruction")
                return data
    raise ValueError("target source site is outside file-backed sections")


class KernelGSRIPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("KDLOCK_KERNEL_GS_TEST_CONFIG")
        if not path:
            raise RuntimeError("explicit actual-target GS test configuration is required")
        cls.config = json.loads(Path(path).read_text())
        paths = {}
        for name in ("vmlinux", "system_map", "kernel_config"):
            paths[name] = Path(cls.config[name])
            if not paths[name].is_absolute() or file_sha(paths[name]) != cls.config[name + "_sha256"]:
                raise ValueError("actual retained target input differs: " + name)
        cls.site = word(cls.config["site"])
        cls.current_task = word(cls.config["current_task"])
        cls.raw = bytes.fromhex(cls.config["instruction_hex"])
        if len(cls.raw) != 8 or cls.raw[:4] != bytes.fromhex("65 48 8b 05"):
            raise ValueError("witness is not the actual64-bit GS:RIP MOV load")
        if linked_bytes(paths["vmlinux"], cls.site, len(cls.raw)) != cls.raw:
            raise ValueError("linked target bytes differ from actual witness")
        symbols = {}
        for line in paths["system_map"].read_text().splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[2] in ("current_task", "const_current_task"):
                symbols[fields[2]] = int(fields[0], 16)
        if symbols != {"current_task": cls.current_task, "const_current_task": cls.current_task}:
            raise ValueError("actual linked current-task alias differs")
        effective = (cls.site + len(cls.raw) + int.from_bytes(cls.raw[4:], "little", signed=True)) & MASK64
        if effective != cls.current_task:
            raise ValueError("source RIP+displacement does not equal the actual full64 current-task alias")

    def decode(self, raw):
        decoded = decode_source({self.site: SourceBytes(raw)})
        self.assertFalse(decoded.decode_failures)
        self.assertFalse(decoded.unmodeled_transfers)
        instruction = decoded.instructions[self.site]
        self.assertEqual(instruction.raw, raw)
        return instruction

    def lower(self, instruction, current_task=None):
        before = repr(instruction.operands)
        lowerer = NormalLowering(self.current_task if current_task is None else current_task)
        code = lowerer.process_normal(instruction.name, list(instruction.operands),
                                      instruction.next_site, block_init())
        self.assertEqual(repr(instruction.operands), before)
        return lowerer, code

    def test_actual_linked_current_task_load_uses_logical_task(self):
        instruction = self.decode(self.raw)
        lowerer, code = self.lower(instruction)
        self.assertTrue(lowerer.is_current_task_operand(instruction.operands[1], instruction.next_site))
        self.assertIn("Stack_TASK", code)
        self.assertNotIn("Stack_RGS", code)
        self.assertNotIn(hex(instruction.next_site), code)

    def test_nearby_noncurrent_alias_keeps_original_gs_engine(self):
        instruction = self.decode(self.raw)
        lowerer, code = self.lower(instruction, (self.current_task + 8) & MASK64)
        self.assertFalse(lowerer.is_current_task_operand(instruction.operands[1], instruction.next_site))
        self.assertIn("Stack_RGS", code)
        self.assertIn(hex(instruction.next_site), code)
        self.assertNotIn("Stack_TASK", code)

    def test_lea_ignores_the_same_gs_override(self):
        instruction = self.decode(self.raw[:2] + b"\x8d" + self.raw[3:])
        self.assertEqual(instruction.name, "LEA")
        _lowerer, code = self.lower(instruction)
        self.assertIn(hex(self.current_task), code.lower())
        self.assertNotIn("Stack_TASK", code)
        self.assertNotIn("Stack_RGS", code)

    def test_address32_low_bits_are_not_the_full64_kernel_alias(self):
        self.assertGreater(self.current_task, (1 << 64) - (1 << 31))
        direct = bytes.fromhex("67 65 48 8b 04 25") + (self.current_task & 0xffffffff).to_bytes(4, "little")
        instruction = self.decode(direct)
        lowerer, code = self.lower(instruction)
        self.assertFalse(lowerer.is_current_task_operand(instruction.operands[1], instruction.next_site))
        self.assertNotIn("Stack_TASK", code)
        self.assertIn("Stack_RGS", code)

    def test_original_direct_gs_form_still_uses_logical_task(self):
        self.assertGreater(self.current_task, (1 << 64) - (1 << 31))
        direct = bytes.fromhex("65 48 8b 04 25") + (self.current_task & 0xffffffff).to_bytes(4, "little")
        instruction = self.decode(direct)
        lowerer, code = self.lower(instruction)
        self.assertTrue(lowerer.is_current_task_operand(instruction.operands[1], instruction.next_site))
        self.assertIn("Stack_TASK", code)
        self.assertNotIn("Stack_RGS", code)


if __name__ == "__main__":
    unittest.main()

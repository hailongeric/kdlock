"""Real miasm/codegen coverage for CFG edges outside the first text window."""

import struct
import unittest
from unittest.mock import patch

from test_jit_diagnostics import render, translator

memread = translator.memread
BASE = 0xFFFFFFFFC1000000


def branch(source, target, opcode=b"\xe9"):
    return opcode + struct.pack("<i", target - source - 5)


class TextRegionTests(unittest.TestCase):
    def setUp(self):
        self.text = bytearray(b"\xc3" * 0x90000)
        self.entry = BASE + 0x2125
        self.body = BASE + 0x1F63
        self.reads = []
        self.put(self.entry, branch(self.entry, self.body))
        self.put(self.body, bytes.fromhex("b8df9b5713c3"))

    def put(self, address, data):
        offset = address - BASE
        self.text[offset : offset + len(data)] = data

    def read_memory(self, address, size):
        self.reads.append((address, size))
        self.assertGreaterEqual(address, BASE)
        self.assertLessEqual(address + size, BASE + len(self.text))
        return bytes(self.text[address - BASE : address - BASE + size])

    def initial(self):
        return [[bytes(self.text[0x2000:0x4000]), BASE + 0x2000, [self.entry]]]

    def translate(self, **kwargs):
        return render(
            "",
            entry=self.entry,
            regions=self.initial(),
            memory_reader=self.read_memory,
            return_status=True,
            **kwargs,
        )

    def test_backward_page_branch_contains_the_actual_body(self):
        assembly, log, status = self.translate()
        self.assertEqual(status, 0, log)
        self.assertIn(f"loc_{self.body:x}:".encode(), assembly)
        self.assertIn(b"0x13579bdf", assembly.lower())
        self.assertIn("TEXT_RANGE_EXTEND", log)
        self.assertEqual(self.reads, [(BASE + 0x1000, 0x3000)])

    def test_new_text_is_checked_for_context_dependencies(self):
        self.put(self.body, bytes.fromhex("65488b042528000000c3"))
        assembly, log, status = self.translate()
        self.assertEqual(status, 2)
        self.assertEqual(assembly, b"")
        self.assertIn("TEXT_RANGE_EXTEND", log)
        self.assertIn("GS/current", log)
        self.assertIn(f'rip="{self.body:#x}"', log)

    def test_instruction_split_at_read_boundary_is_fetched_before_rejection(self):
        self.entry = BASE + 0x3FFF
        self.put(self.entry, bytes.fromhex("b8e0ac6824c3"))
        assembly, log, status = self.translate()
        self.assertEqual(status, 0, log)
        self.assertIn(b"0x2468ace0", assembly.lower())
        self.assertEqual(self.reads, [(BASE + 0x2000, 0x3000)])

    def test_fetched_branch_is_not_promoted_to_a_full_scan_callee(self):
        unlock = BASE + 0x9000
        self.put(
            self.body,
            branch(self.body, unlock, b"\xe8") + bytes.fromhex("65488b042528000000c3"),
        )
        assembly, log, status = self.translate(
            kernel_symbols={"_raw_spin_unlock": unlock}
        )
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)
        self.assertNotIn(b"GS:[", assembly)

    def test_real_block_wins_over_cross_region_bad_placeholder_in_both_orders(self):
        previous = [bytes(self.text[0x1000:0x2000]), BASE + 0x1000, [self.body]]
        current = self.initial()[0]
        for regions in ([previous, current], [current, previous]):
            with self.subTest(reverse=regions[0] is current):
                assembly, log, status = render(
                    "",
                    entry=self.entry,
                    regions=regions,
                    memory_reader=self.read_memory,
                    return_status=True,
                )
                self.assertEqual(status, 0, log)
                self.assertIn(b"0x13579bdf", assembly.lower())
        self.assertEqual(self.reads, [])

    def test_new_hot_path_seeds_another_block_in_already_fetched_cold_window(self):
        # Both windows are fetched in one round. Only then does the backward
        # hot path expose a second cold entry; byte coverage is not CFG coverage.
        first, second, hot = BASE + 0x7100, BASE + 0x7200, BASE + 0x1100
        self.put(
            self.entry,
            b"\x85\xc0\x0f\x84"
            + struct.pack("<i", first - self.entry - 8)
            + branch(self.entry + 8, hot),
        )
        self.put(hot, branch(hot, second))
        self.put(first, bytes.fromhex("b82a000000c3"))
        for raw, error in (
            ("b863000000c3", None),
            ("65488b042528000000c3", "GS/current"),
            ("0f04c3", "undecodable or empty basic block"),
        ):
            with self.subTest(error=error):
                self.reads.clear()
                self.put(second, bytes.fromhex(raw))
                assembly, log, status = self.translate()
                self.assertEqual(status, 2 if error else 0, log)
                self.assertEqual(log.count("reason=CFG_ROOT_EXTEND"), 1)
                if error:
                    self.assertEqual(assembly, b"")
                    self.assertIn(error, log)
                    self.assertIn(f'rip="{second:#x}"', log)
                else:
                    self.assertIn(f"loc_{second:x}:".encode(), assembly)
                    self.assertIn(b"0x63", assembly)
                self.assertEqual(
                    self.reads, [(BASE + 0x1000, 0x3000), (BASE + 0x7000, 0x2000)]
                )

    def test_additional_root_inside_existing_block_gets_a_dispatch_label(self):
        # A second source root may already have been decoded as a predecessor's
        # interior instruction. It still needs its own checked dispatch block.
        start = BASE + 0x2100
        raw = bytes.fromhex("b82a000000b863000000c3")
        assembly, log, status = render(
            "",
            entry=start + 5,
            regions=[(raw, start, [start, start + 5])],
            return_status=True,
        )
        self.assertEqual(status, 0, log)
        self.assertIn(f"loc_{start + 5:x}:".encode(), assembly)

    def test_cached_window_reseeding_shares_the_cfg_expansion_budget(self):
        # Alternating windows reveal one further target per pass without any
        # text read. The existing finite expansion limit must still apply.
        hot, cold = BASE + 0x2000, BASE + 0x7000
        for index in range(40):
            source, target = hot + index * 0x20, cold + index * 0x20
            self.put(source, branch(source, target))
            self.put(target, branch(target, source + 0x20))
        assembly, log, status = render(
            "",
            entry=hot,
            regions=[
                (bytes(self.text[0x2000:0x3000]), hot, [hot]),
                (bytes(self.text[0x7000:0x8000]), cold, [cold]),
            ],
            memory_reader=self.read_memory,
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertEqual(assembly, b"")
        self.assertIn("32 CFG expansions", log)
        self.assertEqual(log.count("reason=CFG_ROOT_EXTEND"), 32)
        self.assertEqual(self.reads, [])

    def test_overlapping_windows_are_merged_and_roots_preserved(self):
        with patch.object(
            memread, "read_kernel_addr_data", side_effect=self.read_memory
        ):
            result = memread.extend_regions(self.initial(), {self.body})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1:], [BASE + 0x1000, [self.body, self.entry]])
        self.assertEqual(len(result[0][0]), 0x3000)

    def test_byte_budget_refuses_before_read_or_codegen(self):
        with patch.object(memread, "MAX_TEXT_BYTES", 0x2000):
            assembly, log, status = self.translate()
        self.assertEqual(status, 2)
        self.assertEqual(assembly, b"")
        self.assertIn("reachable text exceeds 8192 bytes", log)
        self.assertEqual(self.reads, [])

    def test_short_reads_are_errors_not_executable_placeholders(self):
        with (
            patch.object(memread, "read_kernel_addr_data", return_value=b"\xc3"),
            self.assertRaisesRegex(RuntimeError, "incomplete kernel text read"),
        ):
            memread.extend_regions([], {self.entry})

    def test_non_kernel_branch_target_is_not_read(self):
        with (
            patch.object(memread, "read_kernel_addr_data") as reader,
            self.assertRaisesRegex(RuntimeError, "outside kernel space"),
        ):
            memread.extend_regions([], {0x1000})
        reader.assert_not_called()

    def test_expansion_count_is_bounded_even_when_byte_budget_allows_more(self):
        entry = BASE + 0x100
        for i in range(33):
            source = entry + i * 0x4000
            self.put(source, branch(source, source + 0x4000))
        with patch.object(memread, "MAX_TEXT_BYTES", 1024 * 1024):
            assembly, log, status = render(
                "",
                entry=entry,
                regions=[[bytes(self.text[:0x2000]), BASE, [entry]]],
                memory_reader=self.read_memory,
                return_status=True,
            )
        self.assertEqual(status, 2)
        self.assertEqual(assembly, b"")
        self.assertIn("32 CFG expansions", log)
        self.assertEqual(log.count("reason=TEXT_RANGE_EXTEND"), 32)
        self.assertLessEqual(
            max(start + size for start, size in self.reads), BASE + 0x82000
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

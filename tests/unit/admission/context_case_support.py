"""Shared byte/CFG fixtures; no test discovery or translator execution on import."""
import struct
from unittest.mock import mock_open, patch
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, render, translator
context_policy = translator.context_policy


class ContextCaseSupport:
    @staticmethod
    def mutex_calls(base, count):
        return (
            bytes.fromhex("4889df") + b"".join(
                b"\xe8" + struct.pack("<i", 0x3000 - (base + 3 + 5 * i + 5))
                for i in range(count)
            )
            + b"\xc3"
        )


    def assert_rejected(self, raw, **kwargs):
        assembly, log, status = render(raw, return_status=True, **kwargs)
        self.assertEqual(status, context_policy.NATIVE_ONLY_EXIT)
        self.assertEqual(assembly, b"")
        self.assertIn("CONTEXT_NATIVE_ONLY", log)
        self.assertNotIn("FLAGS_UNPRESERVED", log)
        return log


    @staticmethod
    def percpu_metadata():
        # CPU 1 is impossible and its offset is deliberately invalid. CPU 2
        # still needs coverage, independent of online CPU or current-CPU state.
        base = 0xFFFF888100000000
        metadata = {
            "__per_cpu_start": 0,
            "__per_cpu_end": 0x100,
            "__per_cpu_offset": 0xFFFFFFFF82000000,
            "nr_cpu_ids": 0xFFFFFFFF82000100,
            "__cpu_possible_mask": 0xFFFFFFFF82000200,
        }
        payloads = {
            metadata["nr_cpu_ids"]: struct.pack("<I", 3),
            metadata["__cpu_possible_mask"]: struct.pack("<Q", 5 | (1 << 63)),
            metadata["__per_cpu_offset"]: struct.pack("<QQQ", base, 0, base + 0x200),
        }
        text = "".join(f"{value:016x} A {name}\n" for name, value in metadata.items())
        text += (
            "90 A current_task\n98 A unrelated_percpu\nffffffff81000000 T schedule\n"
        )
        return base, metadata, payloads, text


    @staticmethod
    def masked_store_fixture(branch):
        # A known byte in an otherwise unknown word widens RCX, without an
        # unlocated store. Only a genuinely unknown index may taint [0x7000].
        prefix = "c604250060000001488b042500600000488b0c2500600000"
        store = "48890cc500200000"
        suffix = "488b3c2500700000488b17c3"
        return prefix + branch + store + suffix


    @staticmethod
    def root_graph(caller="c3"):
        return translator.decode_regions(
            [
                (bytes.fromhex(caller), 0x1000, [0x1000]),
                (bytes.fromhex("c3"), 0x2000, [0x2000]),
            ],
            TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
            set(TEST_LOCK_SYMBOLS.values()),
        )


    @staticmethod
    def context_ranges():
        # Deliberately unsorted, with an ordinary alias at the sensitive start.
        contents = (
            "3100 D ordinary_data\n"
            "3000 D __per_cpu_offset\n"
            "3000 D offset_alias\n"
            "4100 T ordinary_function\n"
            "4000 T __schedule.isra.0\n"
            "5000 T module_context_end [fixture]\n"
            "4800 T schedule_module [fixture]\n"
        )
        with patch("builtins.open", mock_open(read_data=contents)):
            return context_policy.load_context_symbols()

"""VM-only exact API-frontier regression; no kernel/JIT code is executed.

Synthetic instruction bytes isolate prefixed CALL and ordinary-ABI distinctions.
The caller still supplies actual linked targets/source provenance for deployment.
Do not import, parse or execute this module on the source host.
"""
import struct
import unittest

from disassem.compiler import DiscoveryLimits, SourceRegion, SourceSnapshot, compile_fragment_plan
from disassem.fragment import BoundaryKind
from disassem.source_boundaries import (
    BoundaryScanLimits, SourceEntryClass, SourceOperationTable,
    SourceOperationTarget, scan_source_boundaries,
)


class SourceBoundaryTests(unittest.TestCase):
    def scan(self, code, kind, entry_class, version="api-boundary-case"):
        target = SourceOperationTarget(0x3000, kind, entry_class, "exact_supplied_target")
        snapshot = SourceSnapshot(version, (SourceRegion(0x1000, code),
                                           SourceRegion(0x3000, b"\xc3")))
        result = scan_source_boundaries(snapshot, (0x1000,),
            SourceOperationTable(version, (target,)), BoundaryScanLimits(1, 15, 1))
        return snapshot, result

    def test_prefixed_native_call_stops_before_call_and_preserves_bytes(self):
        raw = b"\x2e\xe8" + struct.pack("<i", 0x3000 - 0x1006) + b"\xc3"
        original, result = self.scan(raw, BoundaryKind.SPECIAL_INSTRUCTION,
                                     SourceEntryClass.NATIVE_LINUX)
        self.assertEqual(result.calls[0].raw, raw[:6])
        self.assertEqual(result.calls[0].next_site, 0x1006)
        plan = compile_fragment_plan(result.snapshot, 0x1000,
                                     DiscoveryLimits(4, 60, 8, 5))
        self.assertEqual([(b.site, b.kind) for b in plan.fragment.boundaries],
                         [(0x1000, BoundaryKind.SPECIAL_INSTRUCTION)])
        self.assertEqual(original.regions, result.snapshot.regions)
        self.assertEqual(original.sites, ())

    def test_private_clobber_call_keeps_typed_operation(self):
        raw = b"\xe8" + struct.pack("<i", 0x3000 - 0x1005) + b"\xc3"
        _original, result = self.scan(raw, BoundaryKind.LOCK, SourceEntryClass.KD_CLOBBER)
        self.assertEqual({site.site: site.boundary for site in result.snapshot.sites},
                         {0x1000: BoundaryKind.LOCK, 0x3000: BoundaryKind.LOCK})
        self.assertEqual(result.calls[0].raw, raw[:5])

    def test_indirect_call_has_no_invented_target_or_call_site_cut(self):
        _original, result = self.scan(b"\xff\xd0\xc3", BoundaryKind.SPECIAL_INSTRUCTION,
                                     SourceEntryClass.NATIVE_LINUX)
        self.assertEqual(result.calls, ())
        self.assertEqual([(site.site, site.boundary) for site in result.snapshot.sites],
                         [(0x3000, BoundaryKind.SPECIAL_INSTRUCTION)])

    def test_version_and_budget_refusal_preserve_original_input(self):
        snapshot = SourceSnapshot("v1", (SourceRegion(0x1000, b"\xc3"),))
        table = SourceOperationTable("v2", ())
        with self.assertRaises(ValueError):
            scan_source_boundaries(snapshot, (0x1000,), table, BoundaryScanLimits(1, 15, 0))
        with self.assertRaises(ValueError):
            scan_source_boundaries(snapshot, (0x1000,), SourceOperationTable("v1", ()),
                                   BoundaryScanLimits(0, 15, 0))
        self.assertEqual(snapshot.sites, ())
        self.assertEqual(snapshot.regions[0].data, b"\xc3")


if __name__ == "__main__":
    unittest.main()

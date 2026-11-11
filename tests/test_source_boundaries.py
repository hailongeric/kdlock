"""VM-only exact API-frontier regression; no kernel/JIT code is executed.

Synthetic instruction bytes isolate prefixed CALL and ordinary-ABI distinctions.
The caller still supplies actual linked targets/source provenance for deployment.
Do not import, parse or execute this module on the source host.
"""
import struct
import unittest

from disassem.compiler import DiscoveryLimits, SourceRegion, SourceSnapshot, compile_fragment_plan
from disassem.fragment import BoundaryKind
from disassem.feedback import (DispositionKind, ExitKind, ExitPhase, RuntimeExit,
                               TargetClassification, adapt_runtime_exit)
from disassem.lowering import CodegenLimits, EntryMetadata, lower_compilation
from disassem.session import source_export_from_frame
from disassem.wire import SourceFrame
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

    def test_query_clobber_preserves_call_and_emits_query_without_lock_semantics(self):
        raw = b"\x2e\xe8" + struct.pack("<i", 0x3000 - 0x1006) + b"\xc3"
        _original, result = self.scan(raw, BoundaryKind.QUERY, SourceEntryClass.KD_CLOBBER)
        plan = compile_fragment_plan(result.snapshot, 0x1000, DiscoveryLimits(4, 60, 8, 5))
        image = lower_compilation(plan, EntryMetadata("kd_query_case", (0x1000,), 0xffffffff84425018),
                                  CodegenLimits(4, 8192, 8))
        self.assertNotIn(0x3000, plan.decoded.instructions)
        self.assertNotIn(0x1000, image.emitted_sites)
        self.assertEqual([(item.site, item.kind, item.raw, item.control_kind) for item in image.boundaries],
                         [(0x1000, BoundaryKind.QUERY, raw[:6], "call")])
        query = next(item for item in image.exits if item.detail == "KD_JIT_OP_QUERY")
        self.assertEqual((query.kind, query.source_ip, query.resume_ip, query.target, query.phase),
                         ("KD_JIT_EXIT_LOCK_OPERATION", 0x1000, 0x1000, 0x3000, "KD_JIT_PHASE_TARGET_READY"))
        disposition = adapt_runtime_exit(RuntimeExit(int(ExitKind.LOCK_OPERATION), 4, 0x1000, 0x3000,
                                                    0x1000, int(ExitPhase.TARGET_READY)),
                                         image, result.snapshot.version.encode(), TargetClassification.API)
        self.assertIs(disposition.kind, DispositionKind.SOURCE_OPERATION)
        self.assertIsNone(disposition.observation)

    def test_native_query_name_remains_special_before_actual_call(self):
        raw = b"\xe8" + struct.pack("<i", 0x3000 - 0x1005) + b"\xc3"
        snapshot = SourceSnapshot("native-query-case", (SourceRegion(0x1000, raw),
                                                       SourceRegion(0x3000, b"\xc3")))
        target = SourceOperationTarget(0x3000, BoundaryKind.SPECIAL_INSTRUCTION,
                                       SourceEntryClass.NATIVE_LINUX, "rwsem_is_write_locked")
        result = scan_source_boundaries(snapshot, (0x1000,), SourceOperationTable(snapshot.version, (target,)),
                                        BoundaryScanLimits(1, 15, 1))
        plan = compile_fragment_plan(result.snapshot, 0x1000, DiscoveryLimits(4, 60, 8, 5))
        image = lower_compilation(plan, EntryMetadata("kd_native_query_case", (0x1000,), 0xffffffff84425018),
                                  CodegenLimits(4, 8192, 8))
        self.assertNotIn(0x3000, plan.decoded.instructions)
        self.assertEqual(image.boundaries[0].kind, BoundaryKind.SPECIAL_INSTRUCTION)
        self.assertEqual(image.boundaries[0].raw, raw[:5])
        self.assertFalse(any(item.detail == "KD_JIT_OP_QUERY" for item in image.exits))
        self.assertTrue(any(item.kind == "KD_JIT_EXIT_SPECIAL_FRONTIER" and item.source_ip == 0x1000
                            and item.phase == "KD_JIT_PHASE_BEFORE_INSTRUCTION" for item in image.exits))

    def test_source_export_appended_query_kind_keeps_scalar_layout(self):
        frame = SourceFrame((1, 2, 3, 0xffffffff84425018, 1, 4, 0),
                            ((0x1000, b"\xc3"),), ((0x1000, 5),), b"query-export-case")
        exported = source_export_from_frame(frame, b"saved-query-source-reply")
        self.assertEqual(exported.snapshot.sites[0].boundary, BoundaryKind.QUERY)
        self.assertEqual(exported.slot_identity, 4)
        self.assertEqual(exported.epoch.current_task_gs_offset, 0xffffffff84425018)
        unknown = SourceFrame(frame.fixed, frame.regions, ((0x1000, 6),), frame.version)
        with self.assertRaises(ValueError):
            source_export_from_frame(unknown, b"saved-unknown-source-reply")

    def test_native_query_cannot_be_reclassified_as_a_typed_query_by_name(self):
        with self.assertRaises(ValueError):
            SourceOperationTarget(0x3000, BoundaryKind.QUERY, SourceEntryClass.NATIVE_LINUX,
                                  "kd_linux_rwsem_is_write_locked")

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

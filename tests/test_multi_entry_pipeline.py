"""VM-only regression for actual live2 source entries and shared discovery.

Uses the retained 949-byte source snapshot and its six explicit post-operation
entries. KDLOCK_PIPELINE_TEST_CONFIG supplies the same explicit discovery,
codegen and learning limits as test_runtime_pipeline.py. Missing dependencies or
inadequate limits fail; there are no defaults/skips or automatic installations.
No GNU build, kernel operation, source/machine-code execution or publication/ACK
is performed. The separate RET-root case is explicitly derived source input.
Do not import, parse or run this module on the source host.
"""
from dataclasses import replace
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

from disassem.compiler import (
    DiscoveryLimits, MissingKind, ResourceKind, SourceRegion, SourceSite,
    SourceSnapshot, compile_fragment_plan,
)
from disassem.fragment import BoundaryKind, EdgeKind, SourceCall, SourceEdge
from disassem.learning import CandidateBinding, EpochBinding, LearningCoordinator, LearningLimits
from disassem.lowering import CodegenLimits, EntryMetadata, lower_compilation


WITNESS_SHA256 = "1400ca8da3bdba6885f4fdee84271523ca6b624ceee2f2c937be8bf390dc1c1f"


class MultiEntryPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("KDLOCK_PIPELINE_TEST_CONFIG")
        if not configured:
            raise RuntimeError("explicit KDLOCK_PIPELINE_TEST_CONFIG is required")
        config = json.loads(Path(configured).read_text())
        for name, version in (("miasm", "0.1.5"), ("future", "1.0.0"), ("pyparsing", "2.4.7")):
            if metadata.version(name) != version:
                raise RuntimeError("pinned translation dependency differs: " + name)
        cls.discovery = DiscoveryLimits(**config["discovery"])
        cls.codegen = CodegenLimits(**config["codegen"])
        cls.learning = LearningLimits(**config["learning"])
        raw = (Path(__file__).parent / "fixtures/live2-entry-source.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != WITNESS_SHA256:
            raise ValueError("copied actual-source witness differs")
        cls.witness = json.loads(raw)
        regions = []
        for region in cls.witness["regions"]:
            data = bytes.fromhex(region["bytes_hex"])
            if hashlib.sha256(data).hexdigest() != region["sha256"]:
                raise ValueError("actual source region bytes differ")
            regions.append(SourceRegion(region["start"], data))
        cls.snapshot = SourceSnapshot(
            cls.witness["source_version"], tuple(regions),
            tuple(SourceSite(site["site"], BoundaryKind(site["boundary"]))
                  for site in cls.witness["sites"]),
        )
        cls.entries = tuple(cls.witness["entry_sites"])
        cls.primary = cls.witness["primary_entry"]
        cls.entry = EntryMetadata("multi_entry_regression", cls.entries,
                                  cls.witness["current_task_gs_offset"])
        cls.epoch = EpochBinding(b"entry-regression-epoch", cls.snapshot.version.encode(),
                                 b"entry-regression-configuration", b"entry-regression-load",
                                 cls.entry.current_task_gs_offset)
        if len(cls.entries) != 6 or cls.primary != cls.entries[0]:
            raise ValueError("actual six-entry construction contract differs")

    def test_actual_six_entries_reach_existing_learning_compile_lower_export(self):
        before = tuple(region.data for region in self.snapshot.regions)
        coordinator = LearningCoordinator(self.epoch, self.snapshot, self.learning)
        binding = CandidateBinding(b"candidate", b"slot", b"image", b"inputs", b"producer",
                                   b"update", b"owner", None)
        candidate = coordinator.construct_candidate(
            binding, (), entry=self.primary, discovery_limits=self.discovery,
            entry_metadata=self.entry, codegen_limits=self.codegen,
            descriptor_symbol="multi_entry_image", source_identity_symbol="multi_entry_epoch",
            feedback_producer_symbol="multi_entry_producer",
        )
        plan, image = candidate.compilation, candidate.lowered
        self.assertEqual(plan.entry_sites, self.entries)
        self.assertEqual(tuple(plan.entry_fragments), self.entries)
        self.assertEqual(image.entry.entry_sites, self.entries)
        self.assertEqual(json.loads(candidate.artifact.manifest_json)["entry_count"], 6)
        self.assertEqual(plan.snapshot.version, self.snapshot.version)
        self.assertEqual(tuple(region.data for region in plan.snapshot.regions), before)
        for site in self.entries:
            self.assertIn(f".Lkd_src_{site:x}:\n", image.assembly)
            self.assertIn(f".Lkd_enter_{site:x}:\n", image.assembly)
            self.assertIn(site, plan.entry_fragments[site].body_sites)
        for fragment in plan.entry_fragments.values():
            for boundary in fragment.boundaries:
                self.assertNotIn(boundary.site, fragment.body_sites)
                self.assertFalse(any(edge.source == boundary.site for edge in fragment.edges))
        for boundary in plan.fragment.boundaries:
            self.assertNotIn(boundary.site, plan.fragment.body_sites)
            self.assertFalse(any(edge.source == boundary.site for edge in plan.fragment.edges))
        blocked = self.witness["blocked_call"]
        self.assertIsInstance(plan.decoded.graph[blocked["site"]], SourceCall)
        self.assertEqual(plan.fragment.call_returns[blocked["site"]], frozenset())
        self.assertNotIn(SourceEdge(blocked["site"], blocked["return_site"], EdgeKind.CALL_RETURN),
                         plan.fragment.edges)
        self.assertLessEqual(plan.consumption.decode_sites, self.discovery.decode_sites)
        self.assertLessEqual(plan.consumption.decode_window_bytes, self.discovery.decode_window_bytes)
        self.assertLessEqual(plan.consumption.cfg_work_steps, self.discovery.cfg_work_steps)

    def test_single_root_still_rejects_unplanned_global_entry_table(self):
        plan = compile_fragment_plan(self.snapshot, self.primary, self.discovery)
        self.assertEqual(plan.entry_sites, (self.primary,))
        with self.assertRaisesRegex(ValueError, "canonical source labels"):
            lower_compilation(plan, self.entry, self.codegen)

    def test_secondary_roots_keep_exact_shared_decode_budget_frontiers(self):
        limits = replace(self.discovery, decode_sites=1)
        plan = compile_fragment_plan(self.snapshot, self.primary, limits, entry_sites=self.entries)
        self.assertEqual(plan.consumption.decode_sites, 1)
        self.assertEqual(len(plan.decoded.instructions), 1)
        image = lower_compilation(plan, self.entry, self.codegen)
        for site in self.entries[1:]:
            edge = SourceEdge(None, site)
            self.assertIn(edge, plan.entry_fragments[site].missing_edges)
            self.assertEqual(plan.missing_outcomes[edge], MissingKind.RESOURCE_BOUNDARY)
            stops = tuple(stop for stop in plan.resource_stops if stop.edge == edge)
            self.assertEqual(len(stops), 1)
            self.assertEqual((stops[0].resource, stops[0].limit, stops[0].consumed, stops[0].required),
                             (ResourceKind.DECODE_SITES, 1, 1, 1))
            self.assertTrue(any(exit.source_ip == site and exit.resume_ip == site
                                and exit.kind == "KD_JIT_EXIT_RESOURCE_BOUNDARY"
                                and exit.detail == "KD_JIT_DETAIL_DECODE_SITE_LIMIT"
                                and exit.phase == "KD_JIT_PHASE_BEFORE_INSTRUCTION"
                                for exit in image.exits))
        self.assertLessEqual(image.attempted_sites, 1)

    def test_separate_ret_root_does_not_prove_unknown_callee_returns(self):
        call = self.witness["blocked_call"]
        raw = bytes.fromhex(call["bytes_hex"])
        self.assertEqual((call["return_site"] + struct.unpack("<i", raw[1:])[0]) & ((1 << 64) - 1),
                         call["target"])
        # Keep the actual direct CALL bytes. The independently entered RET is
        # derived input, not a claim about its actual source continuation bytes.
        snapshot = SourceSnapshot(self.snapshot.version + "-derived-ret-root", (
            SourceRegion(call["site"], raw), SourceRegion(call["return_site"], b"\xc3"),
        ))
        roots = (call["site"], call["return_site"])
        plan = compile_fragment_plan(snapshot, roots[0], self.discovery, entry_sites=roots)
        self.assertIn(roots[1], plan.entry_fragments[roots[1]].return_sites)
        self.assertNotIn(roots[1], plan.entry_fragments[roots[0]].body_sites)
        self.assertEqual(plan.entry_fragments[roots[0]].call_returns[roots[0]], frozenset())
        self.assertEqual(plan.fragment.call_returns[roots[0]], frozenset())
        self.assertNotIn(SourceEdge(roots[0], roots[1], EdgeKind.CALL_RETURN), plan.fragment.edges)
        self.assertIn(SourceEdge(roots[0], call["target"], EdgeKind.CALL_TARGET), plan.fragment.missing_edges)
        image = lower_compilation(plan, EntryMetadata("separate_ret_root", roots,
                                                      self.entry.current_task_gs_offset), self.codegen)
        self.assertFalse(any(transfer.kind == "return_target" for transfer in image.transfers))
        self.assertTrue(any(exit.source_ip == roots[1] and exit.phase == "KD_JIT_PHASE_RETURN_CONSUMED"
                            for exit in image.exits))


if __name__ == "__main__":
    unittest.main()

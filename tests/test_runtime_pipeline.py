"""Focused VM-only checks for the source-built compiler/feedback data path.

Do not run on the source host. From the exact copied VM checkout:

    cd "$KDLOCK_PIPELINE_CHECKOUT"
    KDLOCK_PIPELINE_TEST_CONFIG="$KDLOCK_PIPELINE_TEST_CONFIG" \
        python3 -m unittest discover -s tests -p 'test_runtime_pipeline.py' -v

Required VM dependencies: disassem/requirements.txt's pinned miasm/future/
pyparsing plus GNU cpp, as, ld and objcopy. Missing configuration, dependencies
or tools is an ERROR/FAIL, with no automatic skip/install or fallback backend.
No kernel module, ioctl or generated machine code is executed by these cases.
Copied runtime exits/identity numbers are explicit input fixtures, not evidence
that a JIT body ran, a source/code lease exists, or kernel publication occurred.
In particular these tests construct no COMMITTED/coverage-ACK receipts.

KDLOCK_PIPELINE_TEST_CONFIG names a JSON object with these required keys:
  scratch_parent: existing absolute VM directory (every test directory retained)
  gs_offset: explicit integer current_task GS-offset input for the constructed ABI
  discovery: decode_sites, decode_window_bytes, cfg_work_steps (selected direct
             CALL default deliberately remains the implementation's five)
  codegen: lowered_sites, lowered_text_bytes, runtime_block_visits
  learning: records, claims, candidates, publications, acknowledgments
  wire: frame_bytes, rows, version_bytes, symbol_bytes, artifact_bytes
  source_export: regions, boundaries, source_bytes
  archive_bytes: explicit maximum serialized archive bytes
  archive_mode: explicit integer file mode, subject to the VM process umask
  toolchain: cpp, assembler, linker, objcopy (absolute paths),
             include_directories (absolute-path array), environment (object),
             page_size (explicit target page size)
  build: intermediate_bytes, elf_bytes, machine_bytes, metadata_bytes,
         diagnostic_bytes, total_seconds
  build_target: code_base, code_capacity (explicit integers, page aligned)

There are no numerical configuration defaults. Bounds must cover these finite
fixtures; inadequate bounds fail rather than count as a successful check.
The GNU case only assembles the original artifact at the supplied link address
and checks its extracted text. It does not reserve/publish kernel executable
memory or prove instruction equivalence. Archive cases perform real O_EXCL,
write/fsync and reread operations on the supplied filesystem; they are not a
power-loss experiment or proof of kernel settlement.
"""

from dataclasses import replace
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from disassem.archive import ArchiveWriteFailure, write_archive
from disassem.compiler import (
    DiscoveryLimits, IndirectKind, ObservationOutcome, ObservedTarget, ResourceKind,
    SourceRegion, SourceSite, SourceSnapshot, compile_fragment_plan,
)
from disassem.coverage import EmissionOutcome
from disassem.feedback import (
    DispositionKind, ExitDetail, ExitKind, ExitPhase, RuntimeExit,
    TargetClassification, adapt_runtime_exit,
)
from disassem.fragment import BoundaryKind
from disassem.image_builder import BuildLimits, GNUImageBuilder, Toolchain, flat_metadata
from disassem.learning import (
    CandidateBinding, ConsumerClaim, EpochBinding, LearningCoordinator, LearningFact,
    LearningLimits, MergeDisposition, candidate_input_keys,
)
from disassem.lowering import CodegenLimits, EntryMetadata, lower_compilation
from disassem.session import ProducerCatalog, ProducerMetadata, copied_claim
from disassem.wire import (
    Operation, SourceExportLimits, WireLimits, decode, decode_source, encode, token,
    token_word,
)


BASE = 0x1000
TARGET = 0x1100
RET_SITE = 0x1300
MISSING = 0x2200
VERSION = "focused-runtime-pipeline-v1"
U64 = struct.Struct("<Q")


class RuntimePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("KDLOCK_PIPELINE_TEST_CONFIG")
        if not path:
            raise RuntimeError("KDLOCK_PIPELINE_TEST_CONFIG is required; no checks ran")
        with open(path, "r", encoding="utf-8") as stream:
            cls.config = json.load(stream)
        for name, required in (("miasm", "0.1.5"), ("future", "1.0.0"), ("pyparsing", "2.4.7")):
            actual = metadata.version(name)
            if actual != required:
                raise RuntimeError(f"required {name}=={required}, found {actual}")
        cls.scratch_parent = Path(cls.config["scratch_parent"])
        if not cls.scratch_parent.is_absolute() or not cls.scratch_parent.is_dir():
            raise RuntimeError("scratch_parent must be an existing absolute VM directory")
        discovery = cls.config["discovery"]
        cls.discovery = DiscoveryLimits(discovery["decode_sites"], discovery["decode_window_bytes"],
                                        discovery["cfg_work_steps"])
        cls.codegen = CodegenLimits(**cls.config["codegen"])
        cls.ledger = LearningLimits(**cls.config["learning"])
        cls.wire = WireLimits(**cls.config["wire"])
        cls.source_bounds = SourceExportLimits(**cls.config["source_export"])
        cls.entry = EntryMetadata("pipeline_entry", (BASE,), cls.config["gs_offset"])
        cls.snapshot = SourceSnapshot(VERSION, (
            SourceRegion(BASE, b"\xff\xd0\xc3"),  # CALL RAX; RET
            SourceRegion(TARGET, b"\x90\xc3"),  # ordinary observed callee: NOP; RET
            SourceRegion(RET_SITE, b"\xc3"),
        ))
        cls.epoch = EpochBinding(token(11), VERSION.encode("utf-8"), token(12), token(13),
                                 cls.config["gs_offset"])
        cls.producer = lower_compilation(compile_fragment_plan(cls.snapshot, BASE, cls.discovery),
                                         cls.entry, cls.codegen)
        cls.ret_producer = lower_compilation(
            compile_fragment_plan(cls.snapshot, RET_SITE, cls.discovery),
            EntryMetadata("pipeline_ret_entry", (RET_SITE,), cls.config["gs_offset"]), cls.codegen,
        )

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="kdlock-runtime-pipeline-", dir=self.scratch_parent))
        # Keep successes and failures for the VM receipt; never delete build or
        # partial-archive evidence as an automatic cleanup action.
        self.addCleanup(lambda: print(f"{self.id()} artifacts: {self.work}", file=sys.stderr))

    def coordinator(self):
        return LearningCoordinator(self.epoch, self.snapshot, self.ledger)

    def fact(self, number=1, *, target=TARGET, classification=TargetClassification.ORDINARY,
             epoch=None):
        return LearningFact(token(100 + number), 1, token(201), token(301), epoch or self.epoch,
                            self.producer,
                            RuntimeExit(int(ExitKind.COVERAGE_MISS), int(ExitDetail.UNRESOLVED_TARGET),
                                        BASE, target, BASE, int(ExitPhase.TARGET_READY)),
                            0, classification)

    def returned_fact(self, number=3):
        target = 0x4400
        return LearningFact(token(100 + number), 1, token(202), token(302), self.epoch,
                            self.ret_producer,
                            RuntimeExit(int(ExitKind.COVERAGE_MISS), int(ExitDetail.RETURN_TARGET),
                                        RET_SITE, target, target, int(ExitPhase.RETURN_CONSUMED)),
                            0, TargetClassification.ORDINARY)

    def claim(self, facts, number=1, *, epoch=None):
        return ConsumerClaim(token(400 + number), token(500 + number), epoch or self.epoch, tuple(facts))

    def candidate(self, coordinator, claim, *, discovery=None):
        binding = CandidateBinding(token(601), token(602), token(603), token(604),
                                   token(605), token(606), token(607), None)
        return coordinator.construct_candidate(
            binding, (claim.identity,), entry=BASE, discovery_limits=discovery or self.discovery,
            entry_metadata=self.entry, codegen_limits=self.codegen,
            descriptor_symbol="pipeline_image", source_identity_symbol="pipeline_source_epoch",
            feedback_producer_symbol="pipeline_feedback_producer",
        )

    def learned(self):
        coordinator = self.coordinator()
        fact = self.fact()
        claim = self.claim((fact,))
        coordinator.record_claim(claim)
        return coordinator, fact, claim, self.candidate(coordinator, claim)

    def claim_wire(self, claim, operation):
        classes = {TargetClassification.UNCLASSIFIED: 0, TargetClassification.ORDINARY: 1,
                   TargetClassification.API: 2}
        rows = tuple((token_word(f.record_identity), f.incarnation, token_word(f.producer_identity),
                      token_word(f.image_identity), f.exit.kind, f.exit.detail, f.exit.source_ip,
                      f.exit.target, f.exit.cursor, f.exit.phase, classes[f.classification],
                      f.entry_result & ((1 << 64) - 1)) for f in claim.records)
        return encode(operation, (token_word(claim.identity), token_word(claim.holder_identity),
                                  token_word(claim.epoch.identity)), rows,
                      (claim.epoch.version,), (self.wire.version_bytes,), self.wire)

    def test_indirect_miss_merges_before_constructed_emission(self):
        self.assertNotIn(TARGET, self.producer.compilation.decoded.instructions)
        self.assertIn(BASE, self.producer.emitted_sites)
        self.assertNotIn(BASE + 2, self.producer.emitted_sites)
        coordinator, fact, claim, candidate = self.learned()
        observation = ObservedTarget(VERSION, BASE, TARGET, IndirectKind.CALL)
        self.assertEqual(coordinator.snapshot.observed_targets, (observation,))
        self.assertEqual(candidate.compilation.fragment.call_returns[BASE], frozenset({TARGET}))
        self.assertTrue({BASE, BASE + 2, TARGET, TARGET + 1} <= candidate.lowered.emitted_sites)
        self.assertEqual(candidate.artifact.receipt.emitted_observations, frozenset({observation}))
        self.assertEqual(candidate_input_keys(candidate, claim.identity), (fact.key,))
        # Construction is not kernel publication or an acknowledgment.
        self.assertEqual(coordinator.pending_keys(), (fact.key,))
        self.assertEqual(coordinator.facts()[0].publication_identities, ())
        self.assertEqual(coordinator.facts()[0].acknowledgment_identities, ())

    def test_consumed_ret_and_source_api_never_become_observations(self):
        returned = self.returned_fact()
        result = adapt_runtime_exit(returned.exit, returned.producer, returned.epoch.version,
                                    returned.classification)
        self.assertEqual(result.kind, DispositionKind.RETURN_CONSUMED)
        self.assertIsNone(result.observation)
        api = self.fact(classification=TargetClassification.API)
        result = adapt_runtime_exit(api.exit, api.producer, api.epoch.version, api.classification)
        self.assertEqual(result.kind, DispositionKind.API_TARGET)
        self.assertIsNone(result.observation)
        self.assertEqual(result.fact, api.exit)

    def test_preoperation_cut_retains_actual_call_without_callee_discovery(self):
        snapshot = SourceSnapshot(VERSION, self.snapshot.regions, (SourceSite(BASE, BoundaryKind.LOCK),))
        plan = compile_fragment_plan(snapshot, BASE, self.discovery)
        image = lower_compilation(plan, self.entry, self.codegen)
        self.assertNotIn(TARGET, plan.decoded.instructions)
        self.assertNotIn(BASE, image.emitted_sites)
        self.assertEqual(plan.decoded.instructions[BASE].raw, b"\xff\xd0")
        self.assertEqual(image.boundaries[0].control_kind, "call")
        self.assertTrue(any(exit.kind == "KD_JIT_EXIT_LOCK_OPERATION"
                            and exit.phase == "KD_JIT_PHASE_TARGET_READY" for exit in image.exits))

    def test_missing_and_resource_limited_inputs_remain_pending(self):
        with self.subTest(cause="missing supplied target"):
            coordinator = self.coordinator()
            fact = self.fact(target=MISSING)
            claim = self.claim((fact,))
            coordinator.record_claim(claim)
            candidate = self.candidate(coordinator, claim)
            observed = coordinator.snapshot.observed_targets[0]
            self.assertIn(MISSING, candidate.compilation.missing_source)
            self.assertEqual(candidate.artifact.receipt.outcomes[observed], EmissionOutcome.TARGET_NOT_EMITTED)
            self.assertEqual(candidate.artifact.receipt.emitted_observations, frozenset())
            self.assertEqual(coordinator.pending_keys(), (fact.key,))
        with self.subTest(cause="explicit zero decode budget"):
            coordinator = self.coordinator()
            fact = self.fact()
            claim = self.claim((fact,))
            coordinator.record_claim(claim)
            candidate = self.candidate(coordinator, claim, discovery=replace(self.discovery, decode_sites=0))
            observed = coordinator.snapshot.observed_targets[0]
            self.assertEqual(candidate.compilation.observation_outcomes[observed], ObservationOutcome.RESOURCE_BOUNDARY)
            self.assertEqual(candidate.artifact.receipt.outcomes[observed], EmissionOutcome.SOURCE_NOT_EMITTED)
            stop = candidate.compilation.resource_stops[0]
            self.assertEqual((stop.resource, stop.edge.target, stop.limit, stop.consumed, stop.required),
                             (ResourceKind.DECODE_SITES, BASE, 0, 0, 1))
            self.assertEqual(coordinator.pending_keys(), (fact.key,))

    def test_closed_and_foreign_epoch_facts_do_not_change_cumulative_input(self):
        coordinator = self.coordinator()
        coordinator.close_epoch()
        late = self.fact()
        result = coordinator.record_claim(self.claim((late,)))[0]
        self.assertEqual(result.feedback.kind, DispositionKind.OBSERVED)
        self.assertEqual(result.merge, MergeDisposition.CLOSED_EPOCH_LATE)
        foreign_epoch = replace(self.epoch, identity=token(99), version=b"another-source-version")
        foreign = replace(self.fact(2, epoch=foreign_epoch),
                          producer_identity=token(203), image_identity=token(303))
        result = coordinator.record_claim(self.claim((foreign,), 2, epoch=foreign_epoch))[0]
        self.assertEqual(result.merge, MergeDisposition.FOREIGN_EPOCH)
        self.assertEqual(coordinator.snapshot.observed_targets, ())
        self.assertEqual(set(coordinator.pending_keys()), {late.key, foreign.key})

    def test_copied_wire_claim_and_malformed_finite_extents(self):
        claim = self.claim((self.fact(),))
        raw = self.claim_wire(claim, Operation.CLAIM)
        catalog = ProducerCatalog(1, (ProducerMetadata(self.epoch, token(201), token(301), self.producer),))
        copied = copied_claim(raw, Operation.CLAIM, self.coordinator(), catalog,
                              token_word(claim.holder_identity), len(claim.records), self.wire)
        self.assertEqual(copied.records[0].key, claim.records[0].key)
        self.assertEqual(copied.records[0].exit, claim.records[0].exit)
        malformed = bytearray(raw)
        struct.pack_into("<Q", malformed, 24, self.wire.rows + 1)
        for invalid in (raw[:-1], bytes(malformed)):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                decode(invalid, Operation.CLAIM, 3, 12, (self.wire.version_bytes,), self.wire)
        with self.assertRaises(ValueError):
            decode(raw, Operation.CLAIM, 3, 12, (len(self.epoch.version) - 1,), self.wire)

    def test_flat_metadata_matches_the_shared_abi_for_the_learned_graph(self):
        _coordinator, _fact, _claim, candidate = self.learned()
        data = flat_metadata(candidate, self.config["build"]["metadata_bytes"])
        expected = struct.pack("<9Q", 1, 1, 168, 56, self.config["gs_offset"],
                               1, 4, 1, len(self.epoch.version)) + self.epoch.version + U64.pack(BASE)
        for site, raw, kind in ((BASE, b"\xff\xd0", 0), (BASE + 2, b"\xc3", 2),
                                (TARGET, b"\x90", 2), (TARGET + 1, b"\xc3", 2)):
            expected += struct.pack("<4Q", site, site + len(raw), kind, len(raw)) + raw
        expected += struct.pack("<4Q", BASE, TARGET, 0, 0)
        self.assertEqual(data, expected)

    def test_archive_preserves_all_typed_facts_and_never_acks_them(self):
        coordinator = self.coordinator()
        coordinator.close_epoch()
        claim = self.claim((self.fact(), self.fact(2, classification=TargetClassification.API), self.returned_fact()))
        coordinator.record_claim(claim)
        raw = self.claim_wire(claim, Operation.ARCHIVE_CLAIM)
        pending = coordinator.pending_keys()
        path = self.work / "facts.json"
        receipt = write_archive(str(path), coordinator=coordinator, claim=claim, raw_claim=raw,
                                construction_context=(("fixture", VERSION),),
                                byte_limit=self.config["archive_bytes"], file_mode=self.config["archive_mode"])
        actual = path.read_bytes()
        self.assertEqual(receipt.identity, hashlib.sha256(actual).digest())
        self.assertEqual(receipt.byte_length, len(actual))
        self.assertEqual(receipt.keys, tuple(f.key for f in claim.records))
        document = json.loads(actual)
        self.assertEqual(document["raw_claim"]["bytes_hex"], raw.hex())
        self.assertEqual(len(document["facts"]), 3)
        kinds = {row["feedback"]["fields"]["kind"]["name"] for row in document["facts"]}
        self.assertEqual(kinds, {"OBSERVED", "API_TARGET", "RETURN_CONSUMED"})
        self.assertEqual(len(document["producers"]), 2)
        self.assertTrue(document["cumulative_snapshot"]["fields"]["regions"])
        self.assertEqual(coordinator.pending_keys(), pending)
        self.assertTrue(all(not state.acknowledgment_identities for state in coordinator.facts()))
        with self.assertRaises(FileExistsError):
            write_archive(str(path), coordinator=coordinator, claim=claim, raw_claim=raw,
                          construction_context=(("fixture", VERSION),),
                          byte_limit=self.config["archive_bytes"], file_mode=self.config["archive_mode"])
        self.assertEqual(path.read_bytes(), actual)

    def test_archive_limit_failure_retains_partial_file_and_pending_records(self):
        coordinator = self.coordinator()
        coordinator.close_epoch()
        fact = self.fact()
        claim = self.claim((fact,))
        coordinator.record_claim(claim)
        path = self.work / "partial.json"
        with self.assertRaises(ArchiveWriteFailure) as failure:
            write_archive(str(path), coordinator=coordinator, claim=claim,
                          raw_claim=self.claim_wire(claim, Operation.ARCHIVE_CLAIM),
                          construction_context=(), byte_limit=0, file_mode=self.config["archive_mode"])
        self.assertEqual(failure.exception.written, 0)
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_size, 0)
        self.assertEqual(coordinator.pending_keys(), (fact.key,))

    def test_real_gnu_builder_links_original_backend_and_extracts_exact_text(self):
        _coordinator, _fact, _claim, candidate = self.learned()
        config = self.config["toolchain"]
        for name in ("cpp", "assembler", "linker", "objcopy"):
            self.assertTrue(Path(config[name]).is_absolute() and os.access(config[name], os.X_OK),
                            f"missing executable GNU tool: {name}={config[name]}")
        tools = Toolchain(config["cpp"], config["assembler"], config["linker"], config["objcopy"],
                          tuple(config["include_directories"]), tuple(sorted(config["environment"].items())),
                          str(self.work / "gnu-image"), config["page_size"])
        target = self.config["build_target"]
        built = GNUImageBuilder(tools, BuildLimits(**self.config["build"])).build(
            candidate, target["code_base"], target["code_capacity"],
        )
        self.assertEqual(built.code_base, target["code_base"])
        self.assertTrue(built.machine_code)
        self.assertLessEqual(len(built.machine_code), target["code_capacity"])
        self.assertEqual(built.machine_code, (Path(built.work_directory) / "image.bin").read_bytes())
        self.assertEqual(built.flat_metadata, flat_metadata(candidate, self.config["build"]["metadata_bytes"]))
        self.assertEqual(len(built.tools), 4)
        self.assertTrue(all(tool.returncode == 0 for tool in built.tools))
        self.assertEqual((Path(built.work_directory) / "image.S").read_text(encoding="utf-8"), candidate.artifact.assembly)

    def test_copied_source_export_preserves_identity_bytes_and_typed_boundaries(self):
        regions = self.snapshot.regions
        version = self.epoch.version
        body = struct.pack("<5Q", token_word(self.epoch.identity), token_word(self.epoch.configuration_identity),
                           token_word(self.epoch.load_identity), self.epoch.current_task_gs_offset, 1)
        for region in regions:
            body += struct.pack("<2Q", region.start, len(region.data)) + region.data
        body += struct.pack("<2Q", BASE, 1) + U64.pack(len(version)) + version
        raw = struct.pack("<4Q", 1, int(Operation.SOURCE_EXPORT), 32 + len(body), len(regions)) + body
        frame = decode_source(raw, self.source_bounds, self.wire)
        exported = SourceSnapshot(frame.version.decode("utf-8"),
                                  tuple(SourceRegion(start, data) for start, data in frame.regions),
                                  tuple(SourceSite(site, BoundaryKind.LOCK) for site, kind in frame.boundaries if kind == 1))
        self.assertEqual(frame.fixed[:4], (11, 12, 13, self.config["gs_offset"]))
        self.assertEqual(exported.regions, self.snapshot.regions)
        plan = compile_fragment_plan(exported, BASE, self.discovery)
        self.assertEqual(plan.fragment.body_sites, frozenset())
        self.assertEqual(plan.fragment.boundaries[0].site, BASE)
        with self.assertRaises(ValueError):
            decode_source(raw, replace(self.source_bounds, source_bytes=0), self.wire)

    def test_direct_call_default_five_does_not_limit_observed_indirect_depth(self):
        addresses = tuple(0x3000 + index * 0x10 for index in range(7))
        direct, indirect = [], []
        for index, site in enumerate(addresses):
            if index == 6:
                code = b"\xc3"
            else:
                code = b"\xe8" + struct.pack("<i", addresses[index + 1] - (site + 5)) + b"\xc3"
            direct.append(SourceRegion(site, code))
            indirect.append(SourceRegion(site, b"\xff\xd0\xc3" if index == 5 else code))
        ordinary = compile_fragment_plan(SourceSnapshot(VERSION, tuple(direct)), addresses[0], self.discovery)
        self.assertEqual(ordinary.limits.direct_call_edges, 5)
        self.assertTrue(any(stop.resource is ResourceKind.DIRECT_CALL_EDGES
                            and stop.edge.target == addresses[6] and stop.limit == 5
                            and stop.consumed == 5 for stop in ordinary.resource_stops))
        observed = ObservedTarget(VERSION, addresses[5], addresses[6], IndirectKind.CALL)
        learned = compile_fragment_plan(SourceSnapshot(VERSION, tuple(indirect), observed_targets=(observed,)),
                                        addresses[0], self.discovery)
        self.assertIn(addresses[6], learned.decoded.instructions)
        self.assertEqual(learned.minimum_call_depth[addresses[6]], 5)
        self.assertEqual(learned.observation_outcomes[observed], ObservationOutcome.ATTACHED)
        self.assertFalse(any(stop.resource is ResourceKind.DIRECT_CALL_EDGES for stop in learned.resource_stops))


if __name__ == "__main__":
    unittest.main()

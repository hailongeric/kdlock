"""Emit a CompilationPlan through the original UB-derived KD instruction map.

Only retained fragment body sites emit source instructions. Source-operation
boundaries, construction gaps and finite resource stops get separate reached
exit stubs; an unexecuted alternative cannot itself cause a runtime exit. All
source labels start with the selected canonical block-local SP/BP mapping.

The output is standalone GNU Intel assembly plus construction metadata, never
an executable publication or evidence that a body returned. Source lifetime,
exclusive S_W execution, native physical context and code publication remain
caller duties. General flags/SIMD use AS01; no general state subsystem is added.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from miasm.arch.x86.arch import conditional_branch
from miasm.expression.expression import ExprInt

from .backend.assist import get_inst_name
from .backend.conflict import block_init
from .backend.errors import LoweringInvariant, LoweringUnsupported, RegisterPressure
from .backend.instructions import InstructionLowering, lowering_instruction, opcode_bytes, validate_representation
from .compiler import CompilationPlan, MissingKind, ResourceKind, ResourceStop
from .fragment import BoundaryKind, EdgeKind, SourceCall, SourceEdge, SourceNode, SourceReturn
from .source_decode import MASK64


@dataclass(frozen=True)
class CodegenLimits:
    """Explicit caller bounds, with no selected default capacity.

    lowered_sites counts attempted source body lowerings, including failed
    representations. lowered_text_bytes counts accepted per-instruction lowering
    text, not fixed wrapper/dispatch/exit text or executable image bytes.
    runtime_block_visits bounds source-body label visits in one image entry;
    reaching zero exits before the next source instruction, without replay.
    """

    lowered_sites: int
    lowered_text_bytes: int
    runtime_block_visits: int

    def __post_init__(self):
        for value in (self.lowered_sites, self.lowered_text_bytes, self.runtime_block_visits):
            if type(value) is not int or not 0 <= value <= MASK64:
                raise ValueError("codegen limits must be explicit unsigned word quantities")


@dataclass(frozen=True)
class EntryMetadata:
    """One image's explicit complete-packet entry/reentry contract.

    entry_sites are canonical mapping labels, not arbitrary generated offsets.
    current_task_gs_offset belongs to this source/configuration identity. Fresh
    origin GS/task values arrive in the shared IO record on every runtime entry.
    """

    symbol: str
    entry_sites: tuple[int, ...]
    current_task_gs_offset: int

    def __post_init__(self):
        if not isinstance(self.symbol, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", self.symbol):
            raise ValueError("image entry needs one assembler/C identifier")
        if (not isinstance(self.entry_sites, tuple) or not self.entry_sites
                or len(set(self.entry_sites)) != len(self.entry_sites)):
            raise ValueError("entry sites must be a nonempty tuple of unique source addresses")
        for site in self.entry_sites:
            if type(site) is not int or not 0 <= site <= MASK64:
                raise ValueError("entry site must be an unsigned source address")
        if type(self.current_task_gs_offset) is not int or not 0 <= self.current_task_gs_offset <= MASK64:
            raise ValueError("current_task needs its exact unsigned GS offset")


@dataclass(frozen=True)
class EmittedTransfer:
    source: int
    target: int | None
    kind: str
    label: str


@dataclass(frozen=True)
class EmittedBoundary:
    site: int
    kind: BoundaryKind
    raw: bytes
    control_kind: str
    exit_label: str


@dataclass(frozen=True)
class EmittedExit:
    label: str
    kind: str
    detail: str
    source_ip: int | None
    resume_ip: int | None
    target: int | None
    phase: str
    reason: str
    edge: SourceEdge | None = None
    resource_stops: tuple[ResourceStop, ...] = ()


@dataclass(frozen=True)
class LoweredImage:
    assembly: str
    source_version: str
    abi_version: int
    packet_size: int
    io_size: int
    entry: EntryMetadata
    compilation: CompilationPlan
    emitted_sites: frozenset[int]
    transfers: tuple[EmittedTransfer, ...]
    boundaries: tuple[EmittedBoundary, ...]
    exits: tuple[EmittedExit, ...]
    refused_sites: Mapping[int, str]
    limits: CodegenLimits
    attempted_sites: int
    lowered_text_bytes: int


def _header_macros(include: Path) -> dict[str, str]:
    macros: dict[str, str] = {}
    for name in ("kd_regs.h", "asm_head.h"):
        for line in (include / name).read_text().splitlines():
            match = re.fullmatch(r"\s*#define\s+([A-Za-z_][A-Za-z_0-9]*)\s+(.+?)\s*", line)
            if match:
                macros[match[1]] = match[2]
    return macros


def _standalone(body: str, entry: EntryMetadata, include: Path) -> str:
    macros = _header_macros(include)
    if entry.symbol in macros:
        raise ValueError("entry symbol collides with a private assembly alias")
    template = (include / "wrapper.S").read_text()
    if template.count("/* KD_GENERATED_BODY */") != 1:
        raise ValueError("wrapper has no unique generated-body position")
    template = template.replace('#include "asm_head.h"', '')
    template = template.replace("/* KD_GENERATED_BODY */", body)
    template = re.sub(r"\bKD_JIT_ENTRY\b", entry.symbol, template)
    words = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")

    def expand(name, active=()):
        if name not in macros:
            return name
        if name in active:
            raise ValueError("assembly header contains a recursive alias")
        return words.sub(lambda match: expand(match[0], active + (name,)), macros[name])

    return words.sub(lambda match: expand(match[0]), template)


class _Emission:
    def __init__(self, plan, entry, limits):
        self.plan = plan
        self.entry = entry
        self.limits = limits
        self.lowerer = InstructionLowering(entry.current_task_gs_offset)
        self.chunks: dict[int, str] = {}
        self.call_stages: dict[int, str] = {}
        self.lines: dict[int, object] = {}
        self.refused: dict[int, tuple[str, str, str]] = {}
        self.exits: list[EmittedExit] = []
        self.transfers: list[EmittedTransfer] = []
        self.boundaries: list[EmittedBoundary] = []
        self.attempted = 0
        self.text_bytes = 0
        self.boundary_kinds = {item.site: item.kind for item in plan.fragment.boundaries}

    @staticmethod
    def source_label(site):
        return f".Lkd_src_{site:x}"

    def exit(self, kind, detail, source, resume, target, phase, reason, edge=None, stops=()):
        label = f".Lkd_exit_{len(self.exits)}"
        self.exits.append(EmittedExit(label, kind, detail, source, resume, target,
                                     phase, reason, edge, tuple(stops)))
        return label

    def missing(self, target, edge):
        candidates = [(key, kind) for key, kind in self.plan.missing_outcomes.items()
                      if key == edge or key.target == target]
        kinds = {kind for _, kind in candidates}
        if MissingKind.DECODE_FAILURE in kinds:
            return "KD_JIT_EXIT_UNMODELED_TRANSFER", "KD_JIT_DETAIL_DECODE_FAILURE", "source decoding is incomplete", ()
        if MissingKind.UNMODELED_TRANSFER in kinds:
            return "KD_JIT_EXIT_UNMODELED_TRANSFER", "KD_JIT_DETAIL_UNMODELED", "source transfer has no current representation", ()
        if MissingKind.RESOURCE_BOUNDARY in kinds:
            stops = tuple(stop for stop in self.plan.resource_stops if stop.edge == edge)
            if not stops:
                stops = tuple(stop for stop in self.plan.resource_stops if stop.edge.target == target)
            resource = {stop.resource for stop in stops}
            details = {
                ResourceKind.DECODE_SITES: "KD_JIT_DETAIL_DECODE_SITE_LIMIT",
                ResourceKind.DECODE_WINDOW_BYTES: "KD_JIT_DETAIL_DECODE_WINDOW_LIMIT",
                ResourceKind.CFG_WORK_STEPS: "KD_JIT_DETAIL_CFG_WORK_LIMIT",
                ResourceKind.DIRECT_CALL_EDGES: "KD_JIT_DETAIL_DIRECT_CALL_LIMIT",
            }
            detail = details[next(iter(resource))] if len(resource) == 1 else "KD_JIT_DETAIL_DISCOVERY_RESOURCE"
            return "KD_JIT_EXIT_RESOURCE_BOUNDARY", detail, "discovery stopped before this source site", stops
        return "KD_JIT_EXIT_COVERAGE_MISS", "KD_JIT_DETAIL_SOURCE_UNAVAILABLE", "ordinary source site is absent", ()

    def destination(self, source, target, edge_kind, phase, transfer_kind):
        edge = SourceEdge(source, target, edge_kind)
        if target in self.chunks or target in self.boundary_kinds:
            label = self.source_label(target)
        else:
            if target in self.refused:
                kind, detail, reason = self.refused[target]
                stops = ()
            else:
                kind, detail, reason, stops = self.missing(target, edge)
            attribution = target if phase == "KD_JIT_PHASE_BEFORE_INSTRUCTION" else source
            actual_target = 0 if phase == "KD_JIT_PHASE_BEFORE_INSTRUCTION" else target
            label = self.exit(kind, detail, attribution, target, actual_target,
                              phase, reason, edge, stops)
        self.transfers.append(EmittedTransfer(source, target, transfer_kind, label))
        return label

    def lower_sites(self):
        for site in sorted(self.plan.fragment.body_sites):
            if self.attempted >= self.limits.lowered_sites:
                self.refused[site] = ("KD_JIT_EXIT_RESOURCE_BOUNDARY", "KD_JIT_DETAIL_LOWERED_SITES", "body lowering site bound")
                continue
            self.attempted += 1
            record = self.plan.decoded.instructions.get(site)
            if record is None:
                raise ValueError("planned body site has no retained decoder object")
            try:
                line = lowering_instruction(record)
                validate_representation(line)
                reg_map = block_init()
                stage = ""
                node = self.plan.decoded.graph[site]
                if isinstance(node, SourceCall):
                    if (line.name != "CALL" or len(line.args) != 1
                            or line.args[0].size != 64
                            or node.return_site != record.next_site):
                        raise LoweringInvariant("source CALL record disagrees with decoded control")
                    self.lowerer.require_call_form(line)
                    if node.indirect:
                        if isinstance(line.args[0], ExprInt):
                            raise LoweringInvariant("indirect CALL has a decoded direct operand")
                        chunk = self.lowerer.resolve_target(line.args[0], record.next_site, reg_map)
                        chunk += self.lowerer.flush(reg_map)
                        chunk += "MOV R14, Stack_TARGET\n"
                        if node.known_targets:
                            stage = self.lowerer.stage_call(node.return_site, block_init())
                            stage += "MOV R14, Stack_TARGET\n"
                    else:
                        if (not isinstance(line.args[0], ExprInt)
                                or node.target != ((site + int(line.args[0])) & MASK64)):
                            raise LoweringInvariant("direct CALL target disagrees with source bytes")
                        chunk = self.lowerer.call(line, node.return_site, node.target, reg_map)
                elif isinstance(node, SourceReturn):
                    if line.name != "RET":
                        raise LoweringInvariant("source RET record disagrees with decoded control")
                    chunk = self.lowerer.ret(line, record.next_site, reg_map)
                elif line.name in conditional_branch or line.name.startswith("LOOP"):
                    # Branches see the same canonical SP/BP map. Their selected
                    # destination is emitted below, never copied as source PC.
                    chunk = ""
                elif line.name == "JMP":
                    self.lowerer.require_jump_form(line)
                    if node.indirect:
                        chunk = self.lowerer.resolve_target(line.args[0], record.next_site, reg_map)
                        chunk += self.lowerer.flush(reg_map)
                        chunk += "MOV R14, Stack_TARGET\n"
                    else:
                        chunk = ""
                else:
                    chunk = self.lowerer.ordinary(line, record.next_site, reg_map)
            except LoweringInvariant:
                raise
            except RegisterPressure as error:
                self.refused[site] = ("KD_JIT_EXIT_RESOURCE_BOUNDARY", "KD_JIT_DETAIL_REGISTER_PRESSURE", str(error))
                continue
            except (LoweringUnsupported, ValueError, KeyError) as error:
                self.refused[site] = ("KD_JIT_EXIT_UNMODELED_TRANSFER", "KD_JIT_DETAIL_LOWERING_UNSUPPORTED", str(error))
                continue
            quantity = len((chunk + stage).encode("utf-8"))
            if self.text_bytes + quantity > self.limits.lowered_text_bytes:
                self.refused[site] = ("KD_JIT_EXIT_RESOURCE_BOUNDARY", "KD_JIT_DETAIL_LOWERED_TEXT_BYTES", "accepted lowering text bound")
                continue
            self.chunks[site] = chunk
            self.call_stages[site] = stage
            self.lines[site] = line
            self.text_bytes += quantity

    def return_targets(self):
        """Associate each emitted RET only with modeled callers of its callee."""
        targets: dict[int, set[int]] = {}
        ordinary: dict[int, set[int]] = {}
        for edge in self.plan.fragment.edges:
            if edge.kind in {EdgeKind.ORDINARY, EdgeKind.CALL_RETURN, EdgeKind.JUMP_TARGET}:
                ordinary.setdefault(edge.source, set()).add(edge.target)
        for site in self.chunks:
            node = self.plan.decoded.graph[site]
            if not isinstance(node, SourceCall):
                continue
            for callee in self.plan.fragment.call_returns.get(site, ()):
                pending, seen = [callee], set()
                while pending:
                    current = pending.pop()
                    if current in seen or current not in self.chunks:
                        continue
                    seen.add(current)
                    if isinstance(self.plan.decoded.graph[current], SourceReturn):
                        targets.setdefault(current, set()).add(node.return_site)
                    else:
                        pending.extend(ordinary.get(current, ()))
        return targets

    def boundary(self, site, kind):
        record = self.plan.decoded.instructions[site]
        target, resume = 0, site
        phase = "KD_JIT_PHASE_BEFORE_INSTRUCTION"
        code, control_kind = "", "instruction"
        detail = {
            BoundaryKind.LOCK: "KD_JIT_OP_LOCK",
            BoundaryKind.UNLOCK: "KD_JIT_OP_UNLOCK",
            BoundaryKind.MODE_CHANGE: "KD_JIT_OP_MODE_CHANGE",
            BoundaryKind.SPECIAL_INSTRUCTION: "KD_JIT_DETAIL_NONE",
        }[kind]
        exit_kind = "KD_JIT_EXIT_SPECIAL_FRONTIER" if kind is BoundaryKind.SPECIAL_INSTRUCTION else "KD_JIT_EXIT_LOCK_OPERATION"
        try:
            line = lowering_instruction(record)
            if kind is not BoundaryKind.SPECIAL_INSTRUCTION:
                if line.name == "CALL":
                    control_kind = "call"
                    self.lowerer.require_call_form(line)
                    phase = "KD_JIT_PHASE_TARGET_READY"
                elif line.name == "JMP":
                    control_kind = "jump"
                    self.lowerer.require_jump_form(line)
                    phase = "KD_JIT_PHASE_JUMP_RESOLVED"
                else:
                    raise LoweringUnsupported("source operation needs an exact CALL/JMP or separate inline-entry recipe")
                if isinstance(line.args[0], ExprInt):
                    target = (site + int(line.args[0])) & MASK64
                else:
                    reg_map = block_init()
                    code += self.lowerer.resolve_target(line.args[0], record.next_site, reg_map)
                    code += self.lowerer.flush(reg_map)
                    code += "MOV R14, Stack_TARGET\n"
                    target = None
                if control_kind == "jump":
                    # A tail operation uses the source caller's existing frame.
                    # No source word is pushed or consumed by this boundary.
                    resume = target
        except LoweringInvariant:
            raise
        except RegisterPressure as error:
            exit_kind, detail = "KD_JIT_EXIT_RESOURCE_BOUNDARY", "KD_JIT_DETAIL_REGISTER_PRESSURE"
            code, target, resume, phase = "", 0, site, "KD_JIT_PHASE_BEFORE_INSTRUCTION"
            reason = str(error)
        except (LoweringUnsupported, ValueError, KeyError) as error:
            exit_kind, detail = "KD_JIT_EXIT_UNMODELED_TRANSFER", "KD_JIT_DETAIL_LOWERING_UNSUPPORTED"
            code, target, resume, phase = "", 0, site, "KD_JIT_PHASE_BEFORE_INSTRUCTION"
            reason = str(error)
        else:
            reason = "typed source boundary before its operation effects"
        label = self.exit(exit_kind, detail, site, resume, target, phase, reason)
        self.boundaries.append(EmittedBoundary(site, kind, record.raw, control_kind, label))
        return code + f"JMP {label}\n"

    def body(self):
        self.lower_sites()
        returns = self.return_targets()
        known = set(self.chunks) | set(self.refused) | set(self.boundary_kinds)
        for site in self.entry.entry_sites:
            if site not in known and site != self.plan.entry and not any(
                edge.target == site for edge in self.plan.fragment.missing_edges
            ):
                raise ValueError("entry is outside this fragment's canonical source labels")
        text = [".Lkd_dispatch:\n",
                f"MOVABS R14, {self.limits.runtime_block_visits}\nMOV Stack_BUDGET, R14\n",
                "MOV R14, QWORD PTR[REG_BANK + KD_REG_IP]\nPUSHFQ\n"]
        for site in self.entry.entry_sites:
            text.append(f"MOVABS R15, 0x{site:x}\nCMP R14, R15\nJE .Lkd_enter_{site:x}\n")
        refused_entry = self.exit("KD_JIT_EXIT_ENTRY_REFUSED", "KD_JIT_DETAIL_NONE", None,
                                  None, None, "KD_JIT_PHASE_BEFORE_INSTRUCTION", "entry IP is not a declared canonical label")
        text.append(f"POPFQ\nJMP {refused_entry}\n")
        for site in self.entry.entry_sites:
            text.append(f".Lkd_enter_{site:x}:\nPOPFQ\nJMP {self.source_label(site)}\n")
        for site in sorted(known | set(self.entry.entry_sites)):
            text.append(self.source_label(site) + ":\n")
            if site in self.boundary_kinds:
                text.append(self.boundary(site, self.boundary_kinds[site]))
                continue
            if site not in self.chunks:
                if site in self.refused:
                    kind, detail, reason = self.refused[site]
                    stops = ()
                else:
                    kind, detail, reason, stops = self.missing(site, SourceEdge(None, site))
                label = self.exit(kind, detail, site, site, 0,
                                  "KD_JIT_PHASE_BEFORE_INSTRUCTION", reason, stops=stops)
                text.append(f"JMP {label}\n")
                continue
            runtime_exit = self.exit("KD_JIT_EXIT_RESOURCE_BOUNDARY", "KD_JIT_DETAIL_RUNTIME_BLOCK_VISITS",
                                     site, site, 0, "KD_JIT_PHASE_BEFORE_INSTRUCTION", "runtime source-block visit bound")
            text.append(f"PUSHFQ\nCMP Stack_BUDGET, 0\nJE .Lkd_runtime_{site:x}\nDEC Stack_BUDGET\nPOPFQ\n")
            text.append(self.chunks[site])
            node = self.plan.decoded.graph[site]
            line = self.lines[site]
            if isinstance(node, SourceCall):
                if not node.indirect:
                    label = self.destination(site, node.target, EdgeKind.CALL_TARGET,
                                             "KD_JIT_PHASE_CALL_STAGED", "call_target")
                    text.append(f"JMP {label}\n")
                else:
                    # Classify the retained mutable target before any source
                    # CALL word. Unknown targets return to lock code, which can
                    # recognize an API and stage/forward the CALL exactly once.
                    unknown = self.exit(
                        "KD_JIT_EXIT_COVERAGE_MISS", "KD_JIT_DETAIL_UNRESOLVED_TARGET",
                        site, site, None, "KD_JIT_PHASE_TARGET_READY",
                        "actual indirect CALL target needs pre-push classification",
                    )
                    self.transfers.append(EmittedTransfer(site, None, "indirect_call_unresolved", unknown))
                    if node.known_targets:
                        text.append("PUSHFQ\n")
                        for target in node.known_targets:
                            text.append(f"MOVABS R15, 0x{target:x}\nCMP R14, R15\nJE .Lkd_icall_stage_{site:x}\n")
                        text.append(f"POPFQ\nJMP {unknown}\n.Lkd_icall_stage_{site:x}:\nPOPFQ\n")
                        text.append(self.call_stages[site])
                        text.append("PUSHFQ\n")
                        for target in node.known_targets:
                            text.append(f"MOVABS R15, 0x{target:x}\nCMP R14, R15\nJE .Lkd_icall_{site:x}_{target:x}\n")
                        changed = self.exit(
                            "KD_JIT_EXIT_INVARIANT_FAILURE", "KD_JIT_DETAIL_UNRESOLVED_TARGET",
                            site, None, None, "KD_JIT_PHASE_CALL_STAGED",
                            "retained ordinary CALL target changed while staging its word",
                        )
                        text.append(f"POPFQ\nJMP {changed}\n")
                        for target in node.known_targets:
                            label = self.destination(site, target, EdgeKind.CALL_TARGET,
                                                     "KD_JIT_PHASE_CALL_STAGED", "indirect_call_target")
                            text.append(f".Lkd_icall_{site:x}_{target:x}:\nPOPFQ\nJMP {label}\n")
                    else:
                        text.append(f"JMP {unknown}\n")
            elif isinstance(node, SourceReturn):
                # Consume the actual source word once, then validate only the
                # modeled continuations of calls that reach this RET.
                text.append("PUSHFQ\n")
                for target in sorted(returns.get(site, ())):
                    text.append(f"MOVABS R15, 0x{target:x}\nCMP R14, R15\nJE .Lkd_ret_{site:x}_{target:x}\n")
                label = self.exit("KD_JIT_EXIT_COVERAGE_MISS", "KD_JIT_DETAIL_RETURN_TARGET", site,
                                  None, None, "KD_JIT_PHASE_RETURN_CONSUMED", "actual source RET target is not a modeled continuation")
                self.transfers.append(EmittedTransfer(site, None, "return_miss", label))
                text.append(f"POPFQ\nJMP {label}\n")
                for target in sorted(returns.get(site, ())):
                    label = self.destination(site, target, EdgeKind.CALL_RETURN,
                                             "KD_JIT_PHASE_RETURN_CONSUMED", "return_target")
                    text.append(f".Lkd_ret_{site:x}_{target:x}:\nPOPFQ\nJMP {label}\n")
            elif line.name == "JMP" and node.indirect:
                if node.successors:
                    text.append("PUSHFQ\n")
                    for target in node.successors:
                        text.append(f"MOVABS R15, 0x{target:x}\nCMP R14, R15\nJE .Lkd_ijump_{site:x}_{target:x}\n")
                label = self.exit("KD_JIT_EXIT_COVERAGE_MISS", "KD_JIT_DETAIL_UNRESOLVED_TARGET", site,
                                  None, None, "KD_JIT_PHASE_JUMP_RESOLVED", "actual indirect JMP target needs source-versioned coverage")
                self.transfers.append(EmittedTransfer(site, None, "indirect_jump_unresolved", label))
                if node.successors:
                    text.append("POPFQ\n")
                text.append(f"JMP {label}\n")
                for target in node.successors:
                    label = self.destination(site, target, EdgeKind.JUMP_TARGET,
                                             "KD_JIT_PHASE_JUMP_RESOLVED", "indirect_jump_target")
                    text.append(f".Lkd_ijump_{site:x}_{target:x}:\nPOPFQ\nJMP {label}\n")
            elif line.name in conditional_branch or line.name.startswith("LOOP"):
                if len(node.successors) != 2:
                    raise ValueError("conditional source graph has no exact two alternatives")
                taken, fallthrough = node.successors
                yes = self.destination(site, taken, EdgeKind.ORDINARY,
                                       "KD_JIT_PHASE_JUMP_RESOLVED", "conditional_taken")
                no = self.destination(site, fallthrough, EdgeKind.ORDINARY,
                                      "KD_JIT_PHASE_JUMP_RESOLVED", "conditional_fallthrough")
                prefixes, _ = opcode_bytes(bytes(line.b))
                if line.name.startswith("LOOP") and 0x67 in prefixes:
                    # LOOP's count width is implicit; unlike JECXZ/JRCXZ it
                    # is not encoded by the mnemonic or the target operand.
                    text.append(".byte 0x67\n")
                text.append(f"{get_inst_name(line)} .Lkd_taken_{site:x}\nJMP {no}\n.Lkd_taken_{site:x}:\nJMP {yes}\n")
            else:
                if len(node.successors) != 1:
                    raise ValueError("ordinary source graph has no exact next instruction")
                target = node.successors[0]
                jump = line.name == "JMP"
                label = self.destination(site, target, EdgeKind.ORDINARY,
                                         "KD_JIT_PHASE_JUMP_RESOLVED" if jump else "KD_JIT_PHASE_BEFORE_INSTRUCTION",
                                         "direct_jump" if jump else "fallthrough")
                text.append(f"JMP {label}\n")
            text.append(f".Lkd_runtime_{site:x}:\nPOPFQ\nJMP {runtime_exit}\n")
        for item in self.exits:
            text.append(item.label + ":\n")
            if item.resume_ip is None:
                text.append("MOV Stack_RESUME, R14\n")
            else:
                text.append(f"MOVABS R15, 0x{item.resume_ip:x}\nMOV Stack_RESUME, R15\n")
            if item.source_ip is None:
                text.append("MOV Stack_SOURCE, R14\n")
            else:
                text.append(f"MOVABS R15, 0x{item.source_ip:x}\nMOV Stack_SOURCE, R15\n")
            if item.target is None:
                text.append("MOV Stack_TARGET, R14\n")
            else:
                text.append(f"MOVABS R15, 0x{item.target:x}\nMOV Stack_TARGET, R15\n")
            text.append(f"MOV Stack_KIND, {item.kind}\nMOV Stack_DETAIL, {item.detail}\nMOV Stack_PHASE, {item.phase}\nJMP .Lkd_export\n")
        return "".join(text)


def lower_compilation(plan: CompilationPlan, entry: EntryMetadata, limits: CodegenLimits) -> LoweredImage:
    """Construct coordinated assembly and exact static emission metadata only."""
    if not isinstance(plan, CompilationPlan) or not isinstance(entry, EntryMetadata) or not isinstance(limits, CodegenLimits):
        raise TypeError("lowering needs a CompilationPlan and explicit entry/codegen contracts")
    emission = _Emission(plan, entry, limits)
    body = emission.body()
    include = Path(__file__).resolve().parent.parent / "include"
    assembly = _standalone(body, entry, include)
    macros = _header_macros(include)
    return LoweredImage(
        assembly=assembly,
        source_version=plan.snapshot.version,
        abi_version=int(macros["KD_JIT_ABI_VERSION"], 0),
        packet_size=int(macros["KD_REG_SIZE"], 0),
        io_size=int(macros["KD_JIT_IO_SIZE"], 0),
        entry=entry,
        compilation=plan,
        emitted_sites=frozenset(emission.chunks),
        transfers=tuple(emission.transfers),
        boundaries=tuple(emission.boundaries),
        exits=tuple(emission.exits),
        refused_sites=MappingProxyType({site: reason for site, (_, _, reason) in emission.refused.items()}),
        limits=limits,
        attempted_sites=emission.attempted,
        lowered_text_bytes=emission.text_bytes,
    )

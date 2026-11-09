"""Private supplied-byte decoding into the original backend's source planner.

The x86_64 decoder API and relative-target arithmetic follow the preserved
UB-derived compiler at 7ce7db54334960fe0d9db2c425c5c581cdedf4b0, notably
translation_scope.py and reached_path.py. No provider, mapper, wrapper or image
publication machinery is imported here. These records are provisional compiler
data and select no machine-state or public lock ABI.

Each supplied site is decoded independently. The caller owns source identity,
residency, coherent stable bytes and exact source-operation metadata. Overlapping
supplied byte windows must agree; this adapter does not establish that source
snapshot's coherence or lifetime. Ordinary matched
source CALL/RET structure is an input contract, not a conclusion of decoding one
instruction. Known changed-return structures must be supplied as unmodeled
transfer metadata. No source read, successor discovery or discovery budget is
performed by this adapter.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from miasm.arch.x86.arch import conditional_branch, mn_x86
from miasm.core.bin_stream import bin_stream_str
from miasm.core.utils import Disasm_Exception
from miasm.expression.expression import ExprInt

from .fragment import (
    BoundaryKind,
    SourceCall,
    SourceInstruction,
    SourceNode,
    SourceReturn,
)


MASK64 = (1 << 64) - 1
# Architectural instruction length, not a source/CFG/discovery resource budget.
MAX_INSTRUCTION_BYTES = 15


@dataclass(frozen=True)
class SourceBytes:
    """Available bytes beginning at one exact source instruction site.

    boundary identifies a source operation before its instruction effects, not
    an internal lock implementation instruction. unmodeled_transfer records a
    known transfer structure outside the planner's current matched-CALL/RET
    input contract. These two classifications must not be combined at a site.
    Bytes after the first decoded instruction are not interpreted.
    """

    data: bytes
    boundary: BoundaryKind | None = None
    unmodeled_transfer: str | None = None


@dataclass(frozen=True)
class DecodedInstruction:
    site: int
    raw: bytes
    name: str
    operands: tuple[object, ...]

    @property
    def length(self) -> int:
        return len(self.raw)

    @property
    def next_site(self) -> int:
        return (self.site + self.length) & MASK64


@dataclass(frozen=True)
class DecodeFailure:
    site: int
    available: bytes
    detail: str


@dataclass(frozen=True)
class UnmodeledTransfer:
    site: int
    detail: str


@dataclass(frozen=True)
class DecodedSource:
    """Independent decode outcomes and the modeled subset of supplied sites.

    A site omitted from graph may have a decode_failure or unmodeled_transfer;
    absence from graph alone is not an ordinary coverage miss. Interpret a
    planner missing edge using these maps before attributing its cause. A target
    not supplied at all remains missing ordinary coverage, without reading it.
    Neither a failure nor an unmodeled transfer authorizes runtime handback.
    """

    instructions: Mapping[int, DecodedInstruction]
    graph: Mapping[int, SourceInstruction]
    decode_failures: Mapping[int, DecodeFailure]
    unmodeled_transfers: Mapping[int, UnmodeledTransfer]


def _direct_target(line) -> int | None:
    operand = line.args[0]
    if not isinstance(operand, ExprInt):
        return None
    # Miasm's relative ExprInt already includes the instruction length.
    # Its dstflow2label operation adds only the original source offset.
    return (line.offset + int(operand)) & MASK64


def _flow(line) -> tuple[SourceInstruction | None, str]:
    name = line.name.upper()
    next_site = (line.offset + line.l) & MASK64

    if name in {"CALL", "JMP"}:
        # The decoder can spell far FF /3 and FF /5 forms CALL/JMP too.
        if len(line.args) != 1 or line.args[0].size != 64:
            return None, "non-near CALL/JMP operand has no planner representation"
        target = _direct_target(line)
        if name == "CALL":
            if target is None:
                return None, "indirect CALL has no matched continuation representation"
            return SourceCall(target, next_site), ""
        if target is None:
            return SourceNode(unresolved_successor=True), ""
        return SourceNode((target,)), ""

    if name in conditional_branch or name.startswith("LOOP"):
        if len(line.args) != 1:
            return None, "conditional transfer has no single source target"
        target = _direct_target(line)
        if target is None:
            return None, "conditional transfer has no decoded direct source target"
        return SourceNode((target, next_site)), ""

    if name == "RET":
        # This is only structural return reachability. Preserve any decoded
        # immediate in the instruction record; no source stack effect occurs.
        return SourceReturn(), ""

    if line.breakflow() or line.dstflow() or line.is_subcall():
        return None, "control transfer has no current planner representation"
    return SourceNode((next_site,)), ""


def decode_source(sites: Mapping[int, SourceBytes]) -> DecodedSource:
    """Decode only the first instruction at every supplied source site.

    The modeled graph uses exact source addresses and contains no generated
    addresses or synthesized CALL/RET effects. Exact boundary metadata takes
    precedence over ordinary instruction-flow classification after decoding.
    A decode failure remains a decode failure even at a declared boundary;
    this adapter does not invent its instruction bytes or length.

    A normal instruction always retains its next-site edge, including when the
    caller did not supply that site. An indirect JMP retains unresolved flow;
    an indirect CALL or another unmodeled transfer produces no graph node and
    no fabricated fallthrough. Existing known limitations are not classified as
    special instructions. Dependency import failures remain environment errors,
    not source decode outcomes. No runtime route or instruction support claim is
    established by a successful decode.
    """

    instructions: dict[int, DecodedInstruction] = {}
    graph: dict[int, SourceInstruction] = {}
    failures: dict[int, DecodeFailure] = {}
    unmodeled: dict[int, UnmodeledTransfer] = {}

    for site, source in sites.items():
        if type(site) is not int or not 0 <= site <= MASK64:
            raise ValueError("source site must be an unsigned 64-bit address")
        if not isinstance(source, SourceBytes) or not isinstance(source.data, bytes):
            raise TypeError("each source site must supply SourceBytes with stable bytes")
        if source.boundary is not None and not isinstance(source.boundary, BoundaryKind):
            raise TypeError("source boundary must have an exact BoundaryKind")
        if source.unmodeled_transfer is not None:
            if not isinstance(source.unmodeled_transfer, str) or not source.unmodeled_transfer:
                raise ValueError("unmodeled transfer metadata needs a nonempty description")
            if source.boundary is not None:
                raise ValueError("source boundary and unmodeled transfer metadata overlap")

        raw = source.data[:MAX_INSTRUCTION_BYTES]
        try:
            line = mn_x86.dis(bin_stream_str(raw, base_address=site), 64, site)
        except (Disasm_Exception, IOError) as error:
            failures[site] = DecodeFailure(site, raw, str(error))
            continue
        if line.offset != site or not 1 <= line.l <= len(raw):
            failures[site] = DecodeFailure(
                site, raw, "decoder returned an incomplete or displaced instruction"
            )
            continue
        instructions[site] = DecodedInstruction(
            site, raw[:line.l], line.name, tuple(line.args)
        )

        if source.boundary is not None:
            graph[site] = SourceNode(boundary=source.boundary)
            continue
        if source.unmodeled_transfer is not None:
            unmodeled[site] = UnmodeledTransfer(site, source.unmodeled_transfer)
            continue
        node, detail = _flow(line)
        if node is None:
            unmodeled[site] = UnmodeledTransfer(site, detail)
        else:
            graph[site] = node

    return DecodedSource(
        instructions=MappingProxyType(instructions),
        graph=MappingProxyType(graph),
        decode_failures=MappingProxyType(failures),
        unmodeled_transfers=MappingProxyType(unmodeled),
    )

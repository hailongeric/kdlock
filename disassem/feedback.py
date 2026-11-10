"""Classify one copied runtime exit as an optional compiler input fact.

The caller retains the actual producing code/metadata and coherent source epoch,
then supplies their exact LoweredImage and epoch version bytes. It must prove the
loaded image, source/configuration identity and lifetime correspondence. Equal
version bytes alone establish neither that correspondence nor a source lease.
Only immutable scalars are accepted here; no live packet, operand, stack word,
file, provider or decoder is accessed. This adapter performs no source effects.

An ObservedTarget is input for SourceSnapshot.with_observed_targets, never an
emission/publication receipt or coverage ACK. Transport, retained storage,
capacity, saturation, late reports, dropping, reset and ACK policy remain C08
choices outside this stateless pass. The copied exit survives every disposition,
including a consumed RET, which authorizes no second pop or CALL observation.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from types import MappingProxyType

from .compiler import IndirectKind, ObservedTarget
from .fragment import SourceCall, SourceNode, SourceReturn
from .lowering import EmittedExit, LoweredImage


# Exact private ABI1 values from include/kd_regs.h; no header/file read or guess.
ABI_VERSION = 1
PACKET_SIZE = 168
IO_SIZE = 56
_WORD_MAX = (1 << 64) - 1


class ExitKind(IntEnum):
    NONE = 0
    LOCK_OPERATION = 1
    SPECIAL_FRONTIER = 2
    COVERAGE_MISS = 3
    UNMODELED_TRANSFER = 4
    RESOURCE_BOUNDARY = 5
    ENTRY_REFUSED = 6
    INVARIANT_FAILURE = 7


class ExitPhase(IntEnum):
    BEFORE_INSTRUCTION = 0
    TARGET_READY = 1
    CALL_STAGED = 2
    RETURN_CONSUMED = 3
    JUMP_RESOLVED = 4


class ExitDetail(IntEnum):
    NONE = 0
    SOURCE_UNAVAILABLE = 1
    DECODE_FAILURE = 2
    UNMODELED = 3
    DISCOVERY_RESOURCE = 4
    LOWERING_UNSUPPORTED = 5
    REGISTER_PRESSURE = 6
    LOWERED_SITES = 7
    LOWERED_TEXT_BYTES = 8
    RUNTIME_BLOCK_VISITS = 9
    UNRESOLVED_TARGET = 10
    RETURN_TARGET = 11
    DECODE_SITE_LIMIT = 12
    DECODE_WINDOW_LIMIT = 13
    CFG_WORK_LIMIT = 14
    DIRECT_CALL_LIMIT = 15


_EXIT_NAMES = MappingProxyType({f"KD_JIT_EXIT_{item.name}": int(item) for item in ExitKind})
_PHASE_NAMES = MappingProxyType({f"KD_JIT_PHASE_{item.name}": int(item) for item in ExitPhase})
_DETAIL_NAMES = MappingProxyType({
    **{f"KD_JIT_DETAIL_{item.name}": int(item) for item in ExitDetail},
    # Operation details share numeric values with ordinary exit details but are
    # interpreted only with LOCK_OPERATION, never as source-unavailable causes.
    "KD_JIT_OP_LOCK": 1,
    "KD_JIT_OP_UNLOCK": 2,
    "KD_JIT_OP_MODE_CHANGE": 3,
})


class TargetClassification(Enum):
    """Exact caller classification of this captured target, before learning."""

    ORDINARY = "ordinary"
    API = "source_api"
    UNCLASSIFIED = "unclassified"


class DispositionKind(Enum):
    OBSERVED = "ordinary_indirect_compiler_input"
    VERSION_MISMATCH = "epoch_and_producer_version_differ"
    ABI_MISMATCH = "producer_has_another_private_abi"
    PRODUCER_METADATA_MISMATCH = "producer_source_metadata_inconsistent"
    UNKNOWN_ABI_VALUE = "copied_exit_has_unknown_abi_value"
    NO_EXIT = "no_source_exit"
    SOURCE_OPERATION = "typed_source_operation"
    SOURCE_BOUNDARY = "source_site_is_a_typed_boundary"
    SPECIAL_FRONTIER = "reached_special_frontier"
    RESOURCE_BOUNDARY = "reached_resource_boundary"
    INVARIANT_FAILURE = "reached_invariant_failure"
    UNMODELED_TRANSFER = "reached_unmodeled_transfer"
    ENTRY_REFUSED = "image_entry_refused"
    PRODUCER_SITE_ABSENT = "source_record_absent_from_producer"
    SOURCE_NOT_EMITTED = "source_record_was_not_emitted"
    FLOW_MISMATCH = "copied_phase_and_source_flow_differ"
    PHASE_NOT_OBSERVABLE = "phase_has_no_indirect_target_input"
    CURSOR_MISMATCH = "copied_cursor_does_not_match_phase"
    EXIT_METADATA_MISMATCH = "no_matching_emitted_exit_template"
    DIRECT_CALL = "direct_call_has_no_indirect_observation"
    RETURN_CONSUMED = "source_return_already_consumed"
    NON_INDIRECT_TRANSFER = "source_flow_is_not_an_indirect_call_or_jump"
    API_TARGET = "captured_target_is_a_source_api"
    UNCLASSIFIED_TARGET = "captured_target_has_no_ordinary_classification"


def _word(value: int) -> None:
    if type(value) is not int or not 0 <= value <= _WORD_MAX:
        raise ValueError("runtime exit fields must be unsigned 64-bit integers")


@dataclass(frozen=True)
class RuntimeExit:
    """An already-copied immutable exit; cursor is canonical regs.ip."""

    kind: int
    detail: int
    source_ip: int
    target: int
    cursor: int
    phase: int

    def __post_init__(self) -> None:
        for value in (self.kind, self.detail, self.source_ip, self.target, self.cursor, self.phase):
            _word(value)


@dataclass(frozen=True)
class FeedbackDisposition:
    """Immutable output without a retained image/epoch pointer or lifetime hold."""

    kind: DispositionKind
    fact: RuntimeExit
    source_version: str
    epoch_version: bytes
    classification: TargetClassification
    observation: ObservedTarget | None


def _matches_exit(item: EmittedExit, fact: RuntimeExit) -> bool:
    # In the lowerer, None scalar fields use retained R14, whose captured value
    # is fact.target. It is never permission to reevaluate a mutable operand.
    return (
        _EXIT_NAMES.get(item.kind) == fact.kind
        and _DETAIL_NAMES.get(item.detail) == fact.detail
        and _PHASE_NAMES.get(item.phase) == fact.phase
        and (fact.target if item.source_ip is None else item.source_ip) == fact.source_ip
        and (fact.target if item.resume_ip is None else item.resume_ip) == fact.cursor
        and (fact.target if item.target is None else item.target) == fact.target
    )


def adapt_runtime_exit(
    fact: RuntimeExit,
    producer: LoweredImage,
    epoch_version: bytes,
    classification: TargetClassification,
) -> FeedbackDisposition:
    """Convert only a matched ordinary indirect exit into one ObservedTarget.

    The exact producer/epoch/load/configuration holds are caller preconditions,
    not conclusions of scalar matching. A known observed alternative may produce
    the same fact again; cumulative immutable merge belongs to the snapshot.
    Failure/incomplete decoding remains a producer's recorded construction gap,
    never proof of invalid source or a permanent capability disposition here.
    """
    if not isinstance(fact, RuntimeExit) or not isinstance(producer, LoweredImage):
        raise TypeError("feedback needs a copied RuntimeExit and its exact LoweredImage")
    if not isinstance(epoch_version, bytes):
        raise TypeError("the retained epoch version must be immutable bytes")
    if not isinstance(classification, TargetClassification):
        raise TypeError("target classification must be explicit")

    def result(kind: DispositionKind, observation: ObservedTarget | None = None) -> FeedbackDisposition:
        return FeedbackDisposition(kind, fact, producer.source_version, epoch_version, classification, observation)

    if (producer.abi_version, producer.packet_size, producer.io_size) != (ABI_VERSION, PACKET_SIZE, IO_SIZE):
        return result(DispositionKind.ABI_MISMATCH)
    if (not isinstance(producer.source_version, str) or not producer.source_version
            or producer.source_version != producer.compilation.snapshot.version):
        return result(DispositionKind.PRODUCER_METADATA_MISMATCH)
    try:
        version = producer.source_version.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return result(DispositionKind.PRODUCER_METADATA_MISMATCH)
    if epoch_version != version:
        return result(DispositionKind.VERSION_MISMATCH)
    if (fact.kind not in ExitKind._value2member_map_
            or fact.phase not in ExitPhase._value2member_map_
            or fact.detail not in ExitDetail._value2member_map_):
        return result(DispositionKind.UNKNOWN_ABI_VALUE)

    # Preserve intentional boundaries and failures before considering coverage.
    non_observations = {
        ExitKind.NONE: DispositionKind.NO_EXIT,
        ExitKind.LOCK_OPERATION: DispositionKind.SOURCE_OPERATION,
        ExitKind.SPECIAL_FRONTIER: DispositionKind.SPECIAL_FRONTIER,
        ExitKind.UNMODELED_TRANSFER: DispositionKind.UNMODELED_TRANSFER,
        ExitKind.RESOURCE_BOUNDARY: DispositionKind.RESOURCE_BOUNDARY,
        ExitKind.ENTRY_REFUSED: DispositionKind.ENTRY_REFUSED,
        ExitKind.INVARIANT_FAILURE: DispositionKind.INVARIANT_FAILURE,
    }
    if fact.kind in non_observations:
        return result(non_observations[fact.kind])

    record = producer.compilation.decoded.instructions.get(fact.source_ip)
    if record is None:
        return result(DispositionKind.PRODUCER_SITE_ABSENT)
    if (record.site != fact.source_ip or not isinstance(record.raw, bytes)
            or not 1 <= len(record.raw) <= 15 or not isinstance(record.name, str)):
        return result(DispositionKind.PRODUCER_METADATA_MISMATCH)
    node = producer.compilation.decoded.graph.get(fact.source_ip)
    if isinstance(node, SourceNode) and node.boundary is not None:
        return result(DispositionKind.SOURCE_BOUNDARY)
    if fact.source_ip not in producer.emitted_sites:
        return result(DispositionKind.SOURCE_NOT_EMITTED)

    if fact.phase == ExitPhase.RETURN_CONSUMED:
        if not isinstance(node, SourceReturn) or record.name.upper() != "RET":
            return result(DispositionKind.FLOW_MISMATCH)
        if fact.cursor != fact.target:
            return result(DispositionKind.CURSOR_MISMATCH)
        if not any(_matches_exit(item, fact) for item in producer.exits):
            return result(DispositionKind.EXIT_METADATA_MISMATCH)
        return result(DispositionKind.RETURN_CONSUMED)

    if isinstance(node, SourceCall) and record.name.upper() == "CALL":
        if not node.indirect:
            return result(DispositionKind.DIRECT_CALL)
        if fact.phase not in (ExitPhase.TARGET_READY, ExitPhase.CALL_STAGED):
            return result(DispositionKind.PHASE_NOT_OBSERVABLE)
        kind = IndirectKind.CALL
        expected_cursor = fact.source_ip if fact.phase == ExitPhase.TARGET_READY else fact.target
    elif isinstance(node, SourceNode) and node.indirect and record.name.upper() == "JMP":
        if fact.phase != ExitPhase.JUMP_RESOLVED:
            return result(DispositionKind.PHASE_NOT_OBSERVABLE)
        kind = IndirectKind.JUMP
        expected_cursor = fact.target
    else:
        return result(DispositionKind.NON_INDIRECT_TRANSFER)
    if fact.cursor != expected_cursor:
        return result(DispositionKind.CURSOR_MISMATCH)
    if not any(_matches_exit(item, fact) for item in producer.exits):
        return result(DispositionKind.EXIT_METADATA_MISMATCH)
    if classification is TargetClassification.API:
        return result(DispositionKind.API_TARGET)
    if classification is TargetClassification.UNCLASSIFIED:
        return result(DispositionKind.UNCLASSIFIED_TARGET)
    return result(DispositionKind.OBSERVED, ObservedTarget(
        producer.source_version, fact.source_ip, fact.target, kind,
    ))

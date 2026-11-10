"""Caller-driven feedback claim -> existing compiler -> actual channel receipts.

FdTransport uses the private Linux x86_64 ioctl channel. The channel's registered
provider reserves/loads real source/code objects and retains exact controls; this
module supplies no text provider or source lease. GNUImageBuilder assembles
only the existing artifact in the designated VM build context. Stage transmits
assembly/C metadata/manifest plus exact machine bytes and flat metadata to the
provider's reserved executable-image loader. No source packet or source execution is transported here.

One FeedbackSession is one explicit retained cycle, not a runtime admission gate.
advance() performs one step and never polls. Every successful raw reply is saved
before decoding; uncertain delivery retains the exact ioctl request for cached
redelivery. Actual COMMITTED and ACK replies are reconciled separately. Caller
serialization and retained producer/epoch mappings are required throughout.
"""

from dataclasses import dataclass
from enum import Enum
import ctypes
import fcntl
import os

from .compiler import DiscoveryLimits, SourceRegion, SourceSite, SourceSnapshot
from .fragment import BoundaryKind
from .feedback import RuntimeExit, TargetClassification
from .learning import (
    AcknowledgmentReceipt, CandidateBinding, CommittedUpdateReceipt, ConsumerClaim,
    EpochBinding, FactKey, LearningCandidate, LearningCoordinator, LearningFact,
    PublicationReceipt, candidate_input_keys,
)
from .lowering import CodegenLimits, EntryMetadata, LoweredImage
from .image_builder import BuiltImage, GNUImageBuilder
from .wire import (
    ABI, ENVELOPE, IOCTL, WORD_MAX, Operation, RecoveredExchange, WireLimits,
    SourceExportLimits, SourceFrame, decode, decode_query, decode_source, encode, signed, token, token_word, word,
)


class RecoveryRequired(RuntimeError):
    """The caller must reconcile retained local state with an actual cache."""


class ChannelStatusError(RuntimeError):
    def __init__(self, operation: Operation, sequence: int, status: int):
        self.operation = operation
        self.sequence = sequence
        self.status = status
        super().__init__(f"channel {operation.name} sequence={sequence} status={status}")


@dataclass(frozen=True)
class ExchangeResult:
    sequence: int
    status: int
    payload: bytes


@dataclass
class _Flight:
    operation: Operation
    sequence: int
    request: bytes
    input_buffer: bytearray
    output_buffer: bytearray
    input_view: object
    output_view: object
    input_pointer: int
    output_pointer: int
    header: bytearray


def _buffer(extent: bytearray) -> tuple[object, int]:
    if not extent:
        return None, 0
    view = (ctypes.c_ubyte * len(extent)).from_buffer(extent)
    return view, ctypes.addressof(view)


class FdTransport:
    """Actual bounded ioctl transport, without automatic retries or close.

    Open/query/adoption are explicit. A new process cannot reconstruct producer
    mappings or host ledger history from QUERY alone. The caller must restore
    those exact associations before adopting a nonfresh channel. The kernel
    retains configured controls/cache across close; close is no cleanup proof.
    """

    def __init__(self, fd: int, limits: WireLimits, recovery_capacity: int):
        if type(fd) is not int or fd < 0 or not isinstance(limits, WireLimits):
            raise ValueError("transport requires an actual fd and explicit wire limits")
        word(recovery_capacity)
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise ValueError("the channel requires the Linux x86_64 pointer ABI")
        self.fd = fd
        self.limits = limits
        self.recovery_capacity = recovery_capacity
        self._flight: _Flight | None = None
        self._next: int | None = None
        self._recovery: RecoveredExchange | None = None
        self._queried = False
        self._closed = False

    @classmethod
    def open(cls, path: str, limits: WireLimits, recovery_capacity: int) -> "FdTransport":
        """Open the caller-selected registered device; no path/default supplied."""
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        # Input validation should precede open; constructor failure here is a
        # host ABI/argument error before any channel command has been sent.
        try:
            return cls(fd, limits, recovery_capacity)
        except Exception:
            os.close(fd)
            raise

    @property
    def inflight(self) -> bool:
        return self._flight is not None

    @property
    def pending_sequence(self) -> int | None:
        return self._flight.sequence if self._flight is not None else None

    @property
    def recovery(self) -> RecoveredExchange | None:
        return self._recovery

    def _ioctl(self, flight: _Flight) -> ExchangeResult:
        capacity = len(flight.output_buffer)
        prefix = (ABI, int(flight.operation), flight.sequence, flight.input_pointer,
                  len(flight.input_buffer), flight.output_pointer, capacity)
        flight.header[:] = ENVELOPE.pack(*prefix, 0, 0)
        fcntl.ioctl(self.fd, IOCTL, flight.header, True)
        returned = ENVELOPE.unpack(flight.header)
        if returned[:7] != prefix or returned[7] > capacity or signed(returned[8]) > 0:
            raise ValueError("ioctl returned a different envelope or output extent")
        return ExchangeResult(flight.sequence, signed(returned[8]),
                              bytes(flight.output_buffer[:returned[7]]))

    def _new_flight(self, operation: Operation, sequence: int, payload: bytes,
                    capacity: int) -> _Flight:
        input_buffer = bytearray(payload)
        output_buffer = bytearray(capacity)
        input_view, input_pointer = _buffer(input_buffer)
        output_view, output_pointer = _buffer(output_buffer)
        return _Flight(operation, sequence, payload, input_buffer, output_buffer,
                       input_view, output_view, input_pointer, output_pointer,
                       bytearray(ENVELOPE.size))

    def query(self) -> RecoveredExchange:
        """Read actual cached exchange without changing its sequence or effects."""
        if self._closed or self._flight is not None:
            raise ValueError("query requires an open fd without an unresolved ioctl")
        flight = self._new_flight(Operation.QUERY, 0, b"", self.recovery_capacity)
        result = self._ioctl(flight)
        if result.status:
            raise ChannelStatusError(Operation.QUERY, 0, result.status)
        recovered = decode_query(result.payload, self.recovery_capacity, self.limits)
        self._queried = True
        if recovered.sequence:
            self._next = None
            self._recovery = recovered
        else:
            self._next = 1
            self._recovery = None
        return recovered

    def adopt_recovery(self, recovered: RecoveredExchange) -> None:
        """Caller confirms exact local controls/history were reconciled first."""
        if recovered is not self._recovery or self._flight is not None:
            raise ValueError("recovery adoption differs from the actual queried cache")
        self._next = recovered.sequence + 1 if recovered.sequence < WORD_MAX else 0
        self._recovery = None

    def exchange(self, operation: Operation, payload: bytes) -> ExchangeResult:
        if self._closed or operation is Operation.QUERY:
            raise ValueError("normal exchange requires an open channel and non-QUERY operation")
        if not isinstance(payload, bytes) or len(payload) > self.limits.frame_bytes:
            raise ValueError("request exceeds the explicit frame bound")
        if not self._queried:
            self.query()
        if self._recovery is not None:
            raise RecoveryRequired("adopt the exact queried exchange before any new command")
        if self._flight is None:
            if self._next is None or self._next == 0:
                raise ValueError("channel sequence is unavailable or cannot advance without wrap")
            self._flight = self._new_flight(operation, self._next, payload, self.limits.frame_bytes)
        elif self._flight.operation != operation or self._flight.request != payload:
            raise ValueError("uncertain ioctl permits only exact same-sequence redelivery")
        # Any syscall/envelope failure leaves the flight and both buffers intact.
        result = self._ioctl(self._flight)
        self._next = result.sequence + 1 if result.sequence < WORD_MAX else 0
        self._flight = None
        return result

    def resize_pending_reply(self, capacity: int, limits: WireLimits) -> None:
        """Raise an explicit reply bound after delivery failure, preserving effects.

        Caller serializes this with ioctl completion. The operation, sequence,
        exact input and its backing stay unchanged; only output backing/header
        capacity change before exact cached redelivery. No new dispatch occurs.
        """
        if self._flight is None or self._closed or not isinstance(limits, WireLimits):
            raise ValueError("reply resize requires an actual unresolved serialized ioctl")
        word(capacity)
        if (capacity <= len(self._flight.output_buffer) or capacity > limits.frame_bytes
                or len(self._flight.request) > limits.frame_bytes):
            raise ValueError("new finite reply/frame extent must preserve input and enlarge output")
        output = bytearray(capacity)
        view, pointer = _buffer(output)
        self._flight.output_buffer = output
        self._flight.output_view = view
        self._flight.output_pointer = pointer
        self.limits = limits

    def close(self) -> None:
        """Caller has ended actual session controls; no implicit provider drain."""
        if self._flight is not None or self._recovery is not None or not self._queried:
            raise ValueError("cannot close an unreconciled channel through this helper")
        if not self._closed:
            os.close(self.fd)
            self._closed = True


@dataclass(frozen=True)
class ProducerMetadata:
    epoch: EpochBinding
    producer_identity: bytes
    image_identity: bytes
    image: LoweredImage

    def __post_init__(self) -> None:
        token_word(self.epoch.identity)
        token_word(self.producer_identity)
        token_word(self.image_identity)
        if not isinstance(self.image, LoweredImage):
            raise TypeError("producer mapping needs the exact retained host LoweredImage")


class ProducerCatalog:
    """Finite host construction correspondence, with no task/S_W registry."""

    def __init__(self, capacity: int, entries: tuple[ProducerMetadata, ...]):
        word(capacity)
        self.capacity = capacity
        self._entries: dict[bytes, ProducerMetadata] = {}
        if not isinstance(entries, tuple):
            raise TypeError("initial producer mappings must be an immutable tuple")
        for entry in entries:
            self.register(entry)

    def register(self, entry: ProducerMetadata) -> None:
        if not isinstance(entry, ProducerMetadata):
            raise TypeError("catalog entry requires exact producer construction metadata")
        previous = self._entries.get(entry.producer_identity)
        if previous is not None:
            if (previous.epoch != entry.epoch or previous.image_identity != entry.image_identity
                    or previous.image is not entry.image):
                raise ValueError("durable producer identity was reassigned")
            return
        if len(self._entries) >= self.capacity:
            raise ValueError("producer catalog reaches its explicit retained-entry capacity")
        self._entries[entry.producer_identity] = entry

    def resolve(self, producer: int, image: int, epoch: int) -> ProducerMetadata:
        entry = self._entries[token(producer)]
        if entry.image_identity != token(image) or entry.epoch.identity != token(epoch):
            raise ValueError("copied producer/image/epoch identity mapping differs")
        return entry


@dataclass(frozen=True)
class SessionConfig:
    slot_identity: int
    expected_old_image_identity: int
    claim_holder_identity: int
    claim_capacity: int
    entry: int
    discovery_limits: DiscoveryLimits
    entry_metadata: EntryMetadata
    codegen_limits: CodegenLimits

    def __post_init__(self) -> None:
        token(self.slot_identity)
        word(self.expected_old_image_identity)
        token(self.claim_holder_identity)
        word(self.claim_capacity)
        word(self.entry)
        if (not isinstance(self.discovery_limits, DiscoveryLimits)
                or not isinstance(self.entry_metadata, EntryMetadata)
                or not isinstance(self.codegen_limits, CodegenLimits)):
            raise TypeError("session requires explicit existing compiler/lowerer inputs")


def copied_claim(payload: bytes, operation: Operation, coordinator: LearningCoordinator,
                 producers: ProducerCatalog, holder_identity: int, capacity: int,
                 limits: WireLimits) -> ConsumerClaim:
    """Resolve exact copied claim facts without source/code reads or mutation."""
    if operation not in (Operation.CLAIM, Operation.ARCHIVE_CLAIM):
        raise ValueError("copied claim has another operation schema")
    frame = decode(payload, operation, 3, 12, (limits.version_bytes,), limits)
    claim, holder, epoch = frame.fixed
    if holder != holder_identity or token(epoch) != coordinator.epoch.identity:
        raise ValueError("actual claim holder/epoch differs from the requested context")
    if len(frame.rows) > capacity:
        raise ValueError("actual claim exceeds requested finite record capacity")
    records = []
    classes = {0: TargetClassification.UNCLASSIFIED, 1: TargetClassification.ORDINARY,
               2: TargetClassification.API}
    for row in frame.rows:
        record, incarnation, producer, image, kind, detail, source, target, cursor, phase, classification, entry_result = row
        metadata = producers.resolve(producer, image, epoch)
        if classification not in classes:
            raise ValueError("copied classification is outside the actual kernel fact ABI")
        # Preserve copied version bytes, even a mismatch, in the fact.
        # A malformed wire value leaves the exact raw reply retained.
        actual = metadata.epoch
        copied_epoch = EpochBinding(actual.identity, frame.blobs[0], actual.configuration_identity,
                                    actual.load_identity, actual.current_task_gs_offset)
        records.append(LearningFact(token(record), incarnation, token(producer), token(image),
                                    copied_epoch, metadata.image,
                                    RuntimeExit(kind, detail, source, target, cursor, phase),
                                    signed(entry_result), classes[classification]))
    copied = ConsumerClaim(token(claim), token(holder), coordinator.epoch, tuple(records))
    return copied


class SessionPhase(Enum):
    CLAIM = "claim_command"
    CLAIM_REPLY = "copied_claim_reply"
    BUILD_START = "reserve_candidate_command"
    BUILD_REPLY = "copied_candidate_reservation"
    CONSTRUCT = "construct_existing_pipeline"
    ASSEMBLE = "assemble_existing_artifact_at_reserved_address"
    STAGE_LOAD = "stage_actual_artifact_command"
    STAGE_REPLY = "copied_loaded_candidate"
    PUBLISH = "actual_update_command"
    PUBLISH_REPLY = "copied_committed_reply"
    ACK = "actual_ack_command"
    ACK_REPLY = "copied_ack_reply"
    CLAIM_END = "end_exact_claim_command"
    END_REPLY = "copied_claim_end"
    ABORT = "abort_uncommitted_candidate_command"
    ABORT_REPLY = "copied_exact_abort"
    COMPLETE = "complete"


@dataclass(frozen=True)
class SessionResult:
    claim: ConsumerClaim
    raw_claim: bytes
    candidate: LearningCandidate | None
    built_image: BuiltImage | None
    publication: PublicationReceipt | None
    acknowledgment: AcknowledgmentReceipt | None
    raw_build: bytes | None
    raw_commit: bytes | None
    raw_ack: bytes | None
    aborted: bool


@dataclass(frozen=True)
class _Step:
    operation: Operation
    payload: bytes
    response_phase: Enum


class ChannelWorkflow:
    """Shared retained delivery state; subclasses supply only finite phases."""

    def __init__(self, transport: FdTransport):
        if not isinstance(transport, FdTransport):
            raise TypeError("workflow requires the actual configured fd transport")
        self.transport = transport
        self._reply: bytes | None = None
        self._pending: _Step | None = None
        self._pending_sequence: int | None = None
        self._last: tuple[_Step, ExchangeResult] | None = None

    def _frame(self, operation, fixed, rows=(), blobs=(), bounds=()) -> bytes:
        return encode(operation, fixed, rows, blobs, bounds, self.transport.limits)

    def _send(self, operation, payload, response_phase) -> None:
        step = _Step(operation, payload, response_phase)
        if self._pending is not None and self._pending != step:
            raise ValueError("session has an unresolved different actual command")
        self._pending = step
        try:
            result = self.transport.exchange(operation, payload)
        except Exception:
            self._pending_sequence = self.transport.pending_sequence
            raise
        self._accept(step, result)

    def _accept(self, step: _Step, result: ExchangeResult) -> None:
        self._last = (step, result)
        self._pending = None
        self._pending_sequence = None
        if result.status:
            raise ChannelStatusError(step.operation, result.sequence, result.status)
        # Save opaque actual response before any parsing or host-ledger action.
        self._reply = result.payload
        self.phase = step.response_phase

    def reconcile_recovery(self, transport: FdTransport, recovered: RecoveredExchange) -> None:
        """Retained same-process state only; no automatic restart reconstruction."""
        if transport.recovery is not recovered:
            raise ValueError("recovery must be the actual queried cache on the replacement fd")
        if self._pending is not None:
            step = self._pending
            if self._pending_sequence is None:
                raise RecoveryRequired("this host state has no retained dispatched sequence to reconcile")
            if (recovered.operation != int(step.operation) or recovered.request != step.payload
                    or (self._pending_sequence is not None
                        and recovered.sequence != self._pending_sequence)):
                raise RecoveryRequired("cache differs from the retained unresolved request")
            self.transport = transport
            transport.adopt_recovery(recovered)
            self._accept(step, ExchangeResult(recovered.sequence, recovered.status, recovered.response))
        elif self._last is not None:
            step, result = self._last
            if (recovered.operation != int(step.operation) or recovered.request != step.payload
                    or recovered.sequence != result.sequence or recovered.status != result.status
                    or recovered.response != result.payload):
                raise RecoveryRequired("cache differs from the retained completed exchange")
            self.transport = transport
            transport.adopt_recovery(recovered)
        else:
            raise RecoveryRequired("restore exact host ledger/control provenance before adoption")

    def _decode(self, operation, fixed, row_words, bounds=()):
        if self._reply is None:
            raise ValueError("session has no retained raw reply")
        return decode(self._reply, operation, fixed, row_words, bounds, self.transport.limits)


class FeedbackSession(ChannelWorkflow):
    """One persistent caller-driven control cycle with one exact kernel claim.

    The attached provider must preserve candidate/base/claim/code/source/control
    backing through actual end/abort and all response observers. BUILD_START is
    before CLOSING and reserves exact future descriptor/inputs/producer/receipt
    identities. STAGE_LOAD must bind those same loaded objects; PUBLISH performs
    the actual exact update and returns only its real post-grace receipt. ABI
    errors never authorize dropping controls or treating construction as commit.
    """

    def __init__(self, transport: FdTransport, coordinator: LearningCoordinator,
                 producers: ProducerCatalog, config: SessionConfig, builder: GNUImageBuilder):
        if not isinstance(transport, FdTransport) or not isinstance(coordinator, LearningCoordinator):
            raise TypeError("session requires an actual channel transport and learning coordinator")
        if not isinstance(producers, ProducerCatalog) or not isinstance(config, SessionConfig):
            raise TypeError("session requires exact producer mappings and explicit compiler configuration")
        if not isinstance(builder, GNUImageBuilder):
            raise TypeError("session requires the explicit existing-artifact machine-code builder")
        token_word(coordinator.epoch.identity)
        if config.claim_capacity > transport.limits.rows:
            raise ValueError("claim capacity exceeds explicit wire row capacity")
        super().__init__(transport)
        self.coordinator = coordinator
        self.producers = producers
        self.config = config
        self.builder = builder
        self.phase = SessionPhase.CLAIM
        self._claim: ConsumerClaim | None = None
        self._raw_claim: bytes | None = None
        self._raw_build: bytes | None = None
        self._raw_commit: bytes | None = None
        self._raw_ack: bytes | None = None
        self._binding: CandidateBinding | None = None
        self._symbols: tuple[str, ...] | None = None
        self._emission_identity: int | None = None
        self._candidate: LearningCandidate | None = None
        self._built: BuiltImage | None = None
        self._code_base: int | None = None
        self._code_capacity: int | None = None
        self._publication: PublicationReceipt | None = None
        self._ack: AcknowledgmentReceipt | None = None
        self._aborted = False
        self._result: SessionResult | None = None

    def _keys(self, rows) -> tuple[FactKey, ...]:
        return tuple(FactKey(self.coordinator.epoch.identity, token(row[0]), row[1]) for row in rows)

    def _parse_claim(self) -> None:
        copied = copied_claim(self._reply, Operation.CLAIM, self.coordinator, self.producers,
                              self.config.claim_holder_identity, self.config.claim_capacity,
                              self.transport.limits)
        self.coordinator.record_claim(copied)
        self._claim = copied
        self._raw_claim = self._reply
        self.phase = SessionPhase.BUILD_START

    def _parse_build(self) -> None:
        frame = self._decode(Operation.BUILD_START, 12, 0, (self.transport.limits.symbol_bytes,) * 4)
        candidate, slot, image, inputs, producer, update, owner, old, emission, epoch, code_base, code_capacity = frame.fixed
        if (slot != self.config.slot_identity or old != self.config.expected_old_image_identity
                or token(epoch) != self.coordinator.epoch.identity):
            raise ValueError("reserved candidate slot/base/source differs from the exact request")
        symbols = tuple(blob.decode("utf-8", errors="strict") for blob in frame.blobs)
        if symbols[3] != self.config.entry_metadata.symbol:
            raise ValueError("provider's reserved entry symbol differs from compiler entry metadata")
        self._binding = CandidateBinding(token(candidate), token(slot), token(image), token(inputs),
                                         token(producer), token(update), token(owner), token(old) if old else None)
        token(emission)
        token(code_base)
        if not code_capacity:
            raise ValueError("reserved code capacity is empty")
        self._code_base, self._code_capacity = code_base, code_capacity
        self._emission_identity = emission
        self._symbols = symbols
        self._raw_build = self._reply
        self.phase = SessionPhase.CONSTRUCT

    def _parse_publication(self) -> None:
        frame = self._decode(Operation.PUBLISH, 14, 2)
        publication, claim, holder, slot, update, owner, old, image, retired, epoch, emission, inputs, producer, candidate = frame.fixed
        binding = self._binding
        if binding is None or self._candidate is None or self._claim is None:
            raise ValueError("publication lacks a retained prepared candidate/claim")
        if (token(candidate) != binding.identity or token(inputs) != binding.inputs_identity
                or token(producer) != binding.producer_identity or emission != self._emission_identity
                or token(epoch) != self.coordinator.epoch.identity
                or token(claim) != self._claim.identity or token(holder) != self._claim.holder_identity):
            raise ValueError("actual publication inputs/emission/producer/claim mapping differs")
        if self._publication is None:
            update_receipt = CommittedUpdateReceipt(token(publication), token(slot), token(update), token(owner),
                                                    token(old) if old else None, token(image), token(retired) if retired else None)
            self._publication = PublicationReceipt(token(publication), binding, self.coordinator.epoch,
                                                   token(claim), token(holder), self._keys(frame.rows),
                                                   self._candidate.artifact.receipt, update_receipt)
        self.coordinator.record_publication(self._publication)
        self._raw_commit = self._reply
        self.phase = SessionPhase.ACK

    def _parse_ack(self) -> None:
        frame = self._decode(Operation.ACK, 5, 2)
        acknowledgment, publication, claim, holder, epoch = frame.fixed
        if (self._publication is None or token(epoch) != self.coordinator.epoch.identity
                or token(publication) != self._publication.identity
                or token(claim) != self._publication.claim_identity
                or token(holder) != self._publication.claim_holder_identity):
            raise ValueError("actual ACK lacks this exact source/publication/claim")
        if self._ack is None:
            self._ack = AcknowledgmentReceipt(token(acknowledgment), token(publication), token(claim),
                                               token(holder), self._keys(frame.rows))
        self.coordinator.confirm_ack(self._ack)
        self._raw_ack = self._reply
        self.phase = SessionPhase.CLAIM_END

    def request_abort(self) -> None:
        """Explicit precommit cleanup request; actual provider must confirm it."""
        allowed = (SessionPhase.BUILD_START, SessionPhase.CONSTRUCT, SessionPhase.ASSEMBLE, SessionPhase.STAGE_LOAD,
                   SessionPhase.STAGE_REPLY, SessionPhase.PUBLISH)
        if (self._claim is None or self._publication is not None or self.transport.inflight
                or self._pending is not None or self.phase not in allowed):
            raise ValueError("cannot abandon an unresolved or actually committed request")
        self._pending = None
        self.phase = SessionPhase.ABORT

    def finish_pending(self) -> None:
        """Explicitly end an unbuilt claim; copied pending facts remain retained."""
        if self.phase is not SessionPhase.BUILD_START or self._pending is not None:
            raise ValueError("only a recorded claim without candidate reservation can end directly")
        self.phase = SessionPhase.CLAIM_END

    def advance(self) -> SessionPhase:
        """Perform one finite caller-requested step; no retry/wait loop."""
        limits = self.transport.limits
        config = self.config
        epoch = token_word(self.coordinator.epoch.identity)
        if self.phase is SessionPhase.CLAIM:
            self._send(Operation.CLAIM, self._frame(Operation.CLAIM,
                       (epoch, config.claim_holder_identity, config.claim_capacity)), SessionPhase.CLAIM_REPLY)
        elif self.phase is SessionPhase.CLAIM_REPLY:
            self._parse_claim()
        elif self.phase is SessionPhase.BUILD_START:
            claim = self._claim
            self._send(Operation.BUILD_START, self._frame(Operation.BUILD_START,
                       (token_word(claim.identity), token_word(claim.holder_identity), epoch,
                        config.slot_identity, config.expected_old_image_identity)), SessionPhase.BUILD_REPLY)
        elif self.phase is SessionPhase.BUILD_REPLY:
            self._parse_build()
        elif self.phase is SessionPhase.CONSTRUCT:
            descriptor, source_identity, producer, _entry = self._symbols
            self._candidate = self.coordinator.construct_candidate(
                self._binding, (self._claim.identity,), entry=config.entry,
                discovery_limits=config.discovery_limits, entry_metadata=config.entry_metadata,
                codegen_limits=config.codegen_limits, descriptor_symbol=descriptor,
                source_identity_symbol=source_identity, feedback_producer_symbol=producer,
            )
            self.phase = SessionPhase.ASSEMBLE
        elif self.phase is SessionPhase.ASSEMBLE:
            self._built = self.builder.build(self._candidate, self._code_base, self._code_capacity)
            self.phase = SessionPhase.STAGE_LOAD
        elif self.phase is SessionPhase.STAGE_LOAD:
            artifact = self._candidate.artifact
            blobs = tuple(value.encode("utf-8", errors="strict") for value in
                          (artifact.assembly, artifact.c_metadata, artifact.manifest_json))
            blobs += (self._built.machine_code, self._built.flat_metadata)
            self._send(Operation.STAGE_LOAD, self._frame(Operation.STAGE_LOAD,
                       (token_word(self._binding.identity),), blobs=blobs,
                       bounds=((limits.artifact_bytes,) * 3
                               + (self.builder.limits.machine_bytes, self.builder.limits.metadata_bytes))),
                       SessionPhase.STAGE_REPLY)
        elif self.phase is SessionPhase.STAGE_REPLY:
            frame = self._decode(Operation.STAGE_LOAD, 1, 0)
            if token(frame.fixed[0]) != self._binding.identity:
                raise ValueError("loaded candidate differs from its reserved actual objects")
            self.producers.register(ProducerMetadata(self.coordinator.epoch, self._binding.producer_identity,
                                                     self._binding.image_identity, self._candidate.lowered))
            self.phase = SessionPhase.PUBLISH
        elif self.phase is SessionPhase.PUBLISH:
            keys = candidate_input_keys(self._candidate, self._claim.identity)
            rows = tuple((token_word(key.record_identity), key.incarnation) for key in keys)
            self._send(Operation.PUBLISH, self._frame(Operation.PUBLISH,
                       (token_word(self._binding.identity), token_word(self._claim.identity),
                        token_word(self._claim.holder_identity)), rows=rows), SessionPhase.PUBLISH_REPLY)
        elif self.phase is SessionPhase.PUBLISH_REPLY:
            self._parse_publication()
        elif self.phase is SessionPhase.ACK:
            self._send(Operation.ACK, self._frame(Operation.ACK,
                       (token_word(self._publication.identity),)), SessionPhase.ACK_REPLY)
        elif self.phase is SessionPhase.ACK_REPLY:
            self._parse_ack()
        elif self.phase is SessionPhase.CLAIM_END:
            self._send(Operation.CLAIM_END, self._frame(Operation.CLAIM_END,
                       (token_word(self._claim.identity), token_word(self._claim.holder_identity))), SessionPhase.END_REPLY)
        elif self.phase is SessionPhase.END_REPLY:
            frame = self._decode(Operation.CLAIM_END, 2, 0)
            if (token(frame.fixed[0]), token(frame.fixed[1])) != (self._claim.identity, self._claim.holder_identity):
                raise ValueError("actual claim_end receipt differs from the retained claim")
            self.coordinator.end_claim(self._claim.identity, self._claim.holder_identity)
            self._result = SessionResult(self._claim, self._raw_claim, self._candidate, self._built, self._publication,
                                         self._ack, self._raw_build, self._raw_commit, self._raw_ack, self._aborted)
            self.phase = SessionPhase.COMPLETE
        elif self.phase is SessionPhase.ABORT:
            candidate = token_word(self._binding.identity) if self._binding is not None else 0
            self._send(Operation.ABORT, self._frame(Operation.ABORT,
                       (candidate, token_word(self._claim.identity), token_word(self._claim.holder_identity))),
                       SessionPhase.ABORT_REPLY)
        elif self.phase is SessionPhase.ABORT_REPLY:
            frame = self._decode(Operation.ABORT, 3, 0)
            candidate = token_word(self._binding.identity) if self._binding is not None else 0
            if frame.fixed != (candidate, token_word(self._claim.identity), token_word(self._claim.holder_identity)):
                raise ValueError("actual abort differs from the exact retained precommit controls")
            self._aborted = True
            self.phase = SessionPhase.CLAIM_END
        return self.phase

    @property
    def raw_reply(self) -> bytes | None:
        """Exact retained response for diagnostics or missing producer resolution."""
        return self._reply

    @property
    def result(self) -> SessionResult:
        if self.phase is not SessionPhase.COMPLETE or self._result is None:
            raise ValueError("actual claim/control cycle has not completed")
        return self._result


@dataclass(frozen=True)
class ExportedSource:
    epoch: EpochBinding
    snapshot: SourceSnapshot
    slot_identity: int
    expected_old_image_identity: int
    raw_reply: bytes


def source_export_from_frame(frame: SourceFrame, raw_reply: bytes) -> ExportedSource:
    """Compose actual copied source and slot/base observations without guessing.

    Slot/base use the exact u64 channel values accepted by SessionConfig, with
    zero representing an empty slot. They are observations, not BASELINE holds;
    BUILD_START independently validates/pins the fresh actual matching base.
    """
    if not isinstance(frame, SourceFrame) or not isinstance(raw_reply, bytes):
        raise TypeError("source export requires its decoded typed frame and retained raw bytes")
    epoch, configuration, load, gs_offset, _boundary_count, slot, current_image = frame.fixed
    token(slot)
    word(current_image)
    binding = EpochBinding(token(epoch), frame.version, token(configuration), token(load), gs_offset)
    kinds = {1: BoundaryKind.LOCK, 2: BoundaryKind.UNLOCK,
             3: BoundaryKind.MODE_CHANGE, 4: BoundaryKind.SPECIAL_INSTRUCTION}
    if any(kind not in kinds for _site, kind in frame.boundaries):
        raise ValueError("exported source boundary has an unknown exact kind")
    snapshot = SourceSnapshot(frame.version.decode("utf-8", errors="strict"),
                              tuple(SourceRegion(start, data) for start, data in frame.regions),
                              tuple(SourceSite(site, kinds[kind]) for site, kind in frame.boundaries))
    return ExportedSource(binding, snapshot, slot, current_image, raw_reply)


class SourceExportPhase(Enum):
    REQUEST = "source_export_command"
    REPLY = "copied_source_export"
    COMPLETE = "complete"


class SourceExportSession(ChannelWorkflow):
    """Read the actual registered provider snapshot before compiler input use.

    The channel/provider retains the actual source epoch; copied bytes and
    identity tokens are not themselves a runtime text lease or mutation proof.
    """

    def __init__(self, transport: FdTransport, bounds: SourceExportLimits):
        super().__init__(transport)
        if not isinstance(bounds, SourceExportLimits):
            raise TypeError("source export needs explicit region/boundary/byte limits")
        self.bounds = bounds
        self.phase = SourceExportPhase.REQUEST
        self._result: ExportedSource | None = None

    def advance(self) -> SourceExportPhase:
        if self.phase is SourceExportPhase.REQUEST:
            self._send(Operation.SOURCE_EXPORT, self._frame(Operation.SOURCE_EXPORT, ()), SourceExportPhase.REPLY)
        elif self.phase is SourceExportPhase.REPLY:
            frame = decode_source(self._reply, self.bounds, self.transport.limits)
            self._result = source_export_from_frame(frame, self._reply)
            self.phase = SourceExportPhase.COMPLETE
        return self.phase

    @property
    def result(self) -> ExportedSource:
        if self.phase is not SourceExportPhase.COMPLETE or self._result is None:
            raise ValueError("actual source export is incomplete")
        return self._result

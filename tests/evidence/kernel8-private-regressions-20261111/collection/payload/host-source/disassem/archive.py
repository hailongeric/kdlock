"""Durable exact shutdown archive, independently of coverage acknowledgment.

The caller first closes source admission and drains actual native/JIT/producer
image users, then retains one exact archive claim through writing and settlement.
This writer preserves every claim fact/disposition, including late/invalid and
uncovered data. Its SHA256 identifies the exact canonical bytes actually written
and fsynced with their directory entry. It never marks coverage ACK, settles a
kernel record, ends a claim or proves the external source/user drain.

All inputs remain retained and caller-serialized during writing. The supplied
parent directory is stable caller-owned backing. O_EXCL prevents overwrite; a
failed or partial file remains for diagnosis and receives no ArchiveReceipt.
The caller must obtain and reconcile actual kernel settlement before claim_end.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path

from .learning import ConsumerClaim, EpochBinding, FactKey, LearningCoordinator
from .source_decode import DecodedInstruction
from .session import ChannelWorkflow, FdTransport, ProducerCatalog, copied_claim
from .wire import Operation, token, token_word, word


@dataclass(frozen=True)
class ArchiveReceipt:
    identity: bytes
    epoch: EpochBinding
    claim_identity: bytes
    claim_holder_identity: bytes
    keys: tuple[FactKey, ...]
    path: str
    byte_length: int


class ArchiveWriteFailure(OSError):
    def __init__(self, path: str, written: int, detail: str):
        self.path = path
        self.written = written
        super().__init__(f"archive {path}: written={written}: {detail}")


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _plain(value):
    """Finite typed construction data; raw decode bytes remain authoritative.

    Backend instruction/operand object internals are deliberately not serialized
    or reconstructed. Their exact source bytes, mnemonic, decoded graph, emitted
    assembly and all typed planning/lowering outcomes are retained instead.
    """
    if value is None or type(value) in (bool, int, str):
        return value
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, Enum):
        return {"enum": type(value).__module__ + "." + type(value).__qualname__, "name": value.name}
    if isinstance(value, DecodedInstruction):
        return {"type": "DecodedInstruction", "site": value.site, "raw": _plain(value.raw), "name": value.name}
    if is_dataclass(value) and not isinstance(value, type):
        return {"type": type(value).__module__ + "." + type(value).__qualname__,
                "fields": {field.name: _plain(getattr(value, field.name)) for field in fields(value)}}
    if isinstance(value, Mapping):
        pairs = [(_plain(key), _plain(item)) for key, item in value.items()]
        pairs.sort(key=lambda pair: _canonical(pair[0]))
        return {"mapping": pairs}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return {"set": sorted((_plain(item) for item in value), key=_canonical)}
    raise TypeError(f"archive construction field has no exact serialization: {type(value).__name__}")


def _fact_scalars(fact):
    return {"record_identity": _plain(fact.record_identity), "incarnation": fact.incarnation,
            "producer_identity": _plain(fact.producer_identity), "image_identity": _plain(fact.image_identity),
            "epoch": _plain(fact.epoch), "exit": _plain(fact.exit), "entry_result": fact.entry_result,
            "classification": _plain(fact.classification)}


def _document(coordinator, claim, raw_claim, context):
    states = {state.recorded.fact.key: state for state in coordinator.facts()}
    rows, producers = [], {}
    for fact in claim.records:
        state = states[fact.key]
        retained = state.recorded.fact
        if (_fact_scalars(retained) != _fact_scalars(fact) or retained.producer is not fact.producer):
            raise ValueError("archive claim differs from its exact retained immutable fact")
        producer = producers.get(fact.producer_identity)
        if producer is not None and (producer.producer is not fact.producer
                                     or producer.image_identity != fact.image_identity or producer.epoch != fact.epoch):
            # Invalid producer reassignment is a retained disposition; preserve
            # each exact construction rather than replacing its first mapping.
            producer_key = (fact.producer_identity, fact.key)
        else:
            producer_key = fact.producer_identity
        producers[producer_key] = fact
        rows.append({"key": _plain(fact.key), "fact": _fact_scalars(fact),
                     "feedback": _plain(state.recorded.feedback), "merge": _plain(state.recorded.merge),
                     "candidate_identities": _plain(state.candidate_identities),
                     "input_candidate_identities": _plain(state.input_candidate_identities),
                     "emitted_candidate_identities": _plain(state.emitted_candidate_identities),
                     "publication_identities": _plain(state.publication_identities),
                     "acknowledgment_identities": _plain(state.acknowledgment_identities)})
    construction = [{"producer_identity": _plain(fact.producer_identity),
                     "image_identity": _plain(fact.image_identity), "epoch": _plain(fact.epoch),
                     "construction": _plain(fact.producer)} for fact in producers.values()]
    construction.sort(key=_canonical)
    return {"format": "kdlock.feedback-archive", "format_version": 1,
            "epoch": _plain(coordinator.epoch), "learning_closed": coordinator.closed,
            "cumulative_snapshot": _plain(coordinator.snapshot),
            "claim": {"identity": _plain(claim.identity), "holder": _plain(claim.holder_identity),
                      "epoch": _plain(claim.epoch), "keys": _plain(tuple(f.key for f in claim.records))},
            "raw_claim": _plain(raw_claim), "facts": rows, "producers": construction,
            "construction_context": _plain(context)}


def write_archive(path: str, *, coordinator: LearningCoordinator, claim: ConsumerClaim,
                  raw_claim: bytes, construction_context: tuple[tuple[str, str], ...],
                  byte_limit: int, file_mode: int) -> ArchiveReceipt:
    """Write/fsync one fresh exact archive; return only after both fsyncs.

    byte_limit is the explicit maximum actual output bytes. file_mode is supplied
    by the caller and is still subject to its process umask. No path, capacity,
    overwrite, retention/rotation or settlement defaults are selected. raw_claim
    is the actual retained copied channel frame, never a reconstructed source
    packet. Caller additionally retains its exact frame-to-claim correspondence.
    """
    if not isinstance(coordinator, LearningCoordinator) or not isinstance(claim, ConsumerClaim):
        raise TypeError("archive requires the actual retained learning coordinator and claim")
    if claim.epoch != coordinator.epoch or not coordinator.closed:
        raise ValueError("shutdown archival requires this exact closed learning epoch")
    if not isinstance(raw_claim, bytes):
        raise TypeError("archive needs immutable copied raw claim bytes")
    if (not isinstance(construction_context, tuple)
            or not all(isinstance(item, tuple) and len(item) == 2
                       and all(isinstance(part, str) for part in item) for item in construction_context)):
        raise TypeError("construction provenance must be an explicit immutable string-pair tuple")
    if type(byte_limit) is not int or byte_limit < 0:
        raise ValueError("archive byte extent must be explicit and finite")
    if type(file_mode) is not int or not 0 <= file_mode <= 0o7777:
        raise ValueError("archive file mode must be explicit")
    target = Path(path)
    if not target.is_absolute() or target.name in ("", ".", ".."):
        raise ValueError("archive path must name an explicit absolute new file")
    document = _document(coordinator, claim, raw_claim, construction_context)
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    directory = os.open(str(target.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    descriptor = None
    written = 0
    digest = hashlib.sha256()
    try:
        descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                             file_mode, dir_fd=directory)
        for text in encoder.iterencode(document):
            chunk = text.encode("ascii", errors="strict")
            if len(chunk) > byte_limit - written:
                raise ArchiveWriteFailure(str(target), written, "explicit archive byte limit reached")
            position = 0
            while position < len(chunk):
                amount = os.write(descriptor, chunk[position:])
                if amount <= 0:
                    raise ArchiveWriteFailure(str(target), written, "write made no progress")
                digest.update(chunk[position:position + amount])
                position += amount
                written += amount
        os.fsync(descriptor)
        os.fsync(directory)
        closing = descriptor
        descriptor = None
        os.close(closing)
    finally:
        try:
            if descriptor is not None:
                os.close(descriptor)
        finally:
            os.close(directory)
    return ArchiveReceipt(digest.digest(), coordinator.epoch, claim.identity, claim.holder_identity,
                          tuple(f.key for f in claim.records), str(target), written)


@dataclass(frozen=True)
class ArchiveConfig:
    claim_holder_identity: int
    claim_capacity: int
    path: str
    byte_limit: int
    file_mode: int
    construction_context: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        token(self.claim_holder_identity)
        word(self.claim_capacity)
        if type(self.byte_limit) is not int or self.byte_limit < 0:
            raise ValueError("archive extent must be an explicit finite nonnegative quantity")
        if not Path(self.path).is_absolute():
            raise ValueError("archive requires an explicit absolute fresh file path")
        if type(self.file_mode) is not int or not 0 <= self.file_mode <= 0o7777:
            raise ValueError("archive file mode must be explicit")
        if (not isinstance(self.construction_context, tuple)
                or not all(isinstance(item, tuple) and len(item) == 2
                           and all(isinstance(value, str) for value in item)
                           for item in self.construction_context)):
            raise TypeError("archive construction provenance must be an immutable string-pair tuple")


@dataclass(frozen=True)
class SettlementReceipt:
    """Actual shutdown settlement of archived facts, never coverage ACK."""

    identity: bytes
    archive_identity: bytes
    epoch: EpochBinding
    claim_identity: bytes
    claim_holder_identity: bytes
    keys: tuple[FactKey, ...]
    raw_reply: bytes


@dataclass(frozen=True)
class ArchiveResult:
    archive: ArchiveReceipt
    settlement: SettlementReceipt
    claim: ConsumerClaim
    raw_claim: bytes
    raw_shutdown: bytes


class ArchivePhase(Enum):
    SHUTDOWN = "actual_source_shutdown_command"
    SHUTDOWN_REPLY = "copied_actual_source_shutdown"
    CLAIM = "closed_source_archive_claim_command"
    CLAIM_REPLY = "copied_archive_claim"
    WRITE = "write_and_fsync_exact_archive"
    SETTLE = "actual_archive_settlement_command"
    SETTLE_REPLY = "copied_actual_archive_settlement"
    END = "actual_claim_end_command"
    END_REPLY = "copied_actual_claim_end"
    COMPLETE = "complete"


class ShutdownSession(ChannelWorkflow):
    """One finite archive claim after actual provider shutdown, without polling.

    SHUTDOWN success comes only from actual closed source, NULL image slot and
    ended native/JIT/image users. FEEDBACK users deliberately survive for this
    archival path. A busy response leaves this phase for explicit caller retry;
    no runtime gate or shutdown wait loop is introduced. Multiple finite claims
    require distinct explicit sessions/paths, with no automatic repeated drain.
    """

    def __init__(self, transport: FdTransport, coordinator: LearningCoordinator,
                 producers: ProducerCatalog, config: ArchiveConfig):
        super().__init__(transport)
        if (not isinstance(coordinator, LearningCoordinator) or not isinstance(producers, ProducerCatalog)
                or not isinstance(config, ArchiveConfig)):
            raise TypeError("shutdown requires exact learning/producer state and explicit archive inputs")
        token_word(coordinator.epoch.identity)
        if config.claim_capacity > transport.limits.rows:
            raise ValueError("archive claim exceeds the explicit wire row capacity")
        self.coordinator = coordinator
        self.producers = producers
        self.config = config
        self.phase = ArchivePhase.SHUTDOWN
        self._path = config.path
        self._raw_shutdown: bytes | None = None
        self._raw_claim: bytes | None = None
        self._claim: ConsumerClaim | None = None
        self._archive: ArchiveReceipt | None = None
        self._settlement: SettlementReceipt | None = None
        self._result: ArchiveResult | None = None

    def set_archive_path(self, path: str) -> None:
        """Explicit new destination after a failed O_EXCL/partial write; no erase."""
        if self.phase is not ArchivePhase.WRITE or self._archive is not None or not Path(path).is_absolute():
            raise ValueError("a new archive path requires a retained unwritten claim")
        self._path = path

    def advance(self) -> ArchivePhase:
        if self.phase is ArchivePhase.SHUTDOWN:
            self._send(Operation.SHUTDOWN, self._frame(Operation.SHUTDOWN, ()), ArchivePhase.SHUTDOWN_REPLY)
        elif self.phase is ArchivePhase.SHUTDOWN_REPLY:
            frame = self._decode(Operation.SHUTDOWN, 1, 0)
            if token(frame.fixed[0]) != self.coordinator.epoch.identity:
                raise ValueError("actual shutdown source differs from the exact learning epoch")
            self._raw_shutdown = self._reply
            self.coordinator.close_epoch()
            self.phase = ArchivePhase.CLAIM
        elif self.phase is ArchivePhase.CLAIM:
            self._send(Operation.ARCHIVE_CLAIM, self._frame(Operation.ARCHIVE_CLAIM,
                       (token_word(self.coordinator.epoch.identity), self.config.claim_holder_identity,
                        self.config.claim_capacity)), ArchivePhase.CLAIM_REPLY)
        elif self.phase is ArchivePhase.CLAIM_REPLY:
            claim = copied_claim(self._reply, Operation.ARCHIVE_CLAIM, self.coordinator, self.producers,
                                 self.config.claim_holder_identity, self.config.claim_capacity,
                                 self.transport.limits)
            self.coordinator.record_claim(claim)
            self._claim = claim
            self._raw_claim = self._reply
            self.phase = ArchivePhase.WRITE
        elif self.phase is ArchivePhase.WRITE:
            self._archive = write_archive(
                self._path, coordinator=self.coordinator, claim=self._claim, raw_claim=self._raw_claim,
                construction_context=self.config.construction_context,
                byte_limit=self.config.byte_limit, file_mode=self.config.file_mode,
            )
            self.phase = ArchivePhase.SETTLE
        elif self.phase is ArchivePhase.SETTLE:
            rows = tuple((token_word(key.record_identity), key.incarnation) for key in self._archive.keys)
            self._send(Operation.SETTLE, self._frame(Operation.SETTLE,
                       (token_word(self._claim.identity), token_word(self._claim.holder_identity)),
                       rows=rows, blobs=(self._archive.identity,), bounds=(len(self._archive.identity),)),
                       ArchivePhase.SETTLE_REPLY)
        elif self.phase is ArchivePhase.SETTLE_REPLY:
            frame = self._decode(Operation.SETTLE, 3, 2)
            identity, claim, holder = frame.fixed
            keys = tuple(FactKey(self.coordinator.epoch.identity, token(record), incarnation)
                         for record, incarnation in frame.rows)
            if ((token(claim), token(holder)) != (self._claim.identity, self._claim.holder_identity)
                    or len(set(keys)) != len(keys) or set(keys) != set(self._archive.keys)):
                raise ValueError("actual settlement differs from the exact durable archive claim keys")
            self._settlement = SettlementReceipt(token(identity), self._archive.identity, self.coordinator.epoch,
                                                  token(claim), token(holder), keys, self._reply)
            self.phase = ArchivePhase.END
        elif self.phase is ArchivePhase.END:
            self._send(Operation.CLAIM_END, self._frame(Operation.CLAIM_END,
                       (token_word(self._claim.identity), token_word(self._claim.holder_identity))), ArchivePhase.END_REPLY)
        elif self.phase is ArchivePhase.END_REPLY:
            frame = self._decode(Operation.CLAIM_END, 2, 0)
            if (token(frame.fixed[0]), token(frame.fixed[1])) != (self._claim.identity, self._claim.holder_identity):
                raise ValueError("actual archive claim_end differs from the retained exact claim")
            # This ends host claim membership, not coverage history. The old
            # coordinator pending_keys remain unACKed history; settlement has
            # its own exact receipt and never manufactures an emitted outcome.
            self.coordinator.end_claim(self._claim.identity, self._claim.holder_identity)
            self._result = ArchiveResult(self._archive, self._settlement, self._claim,
                                         self._raw_claim, self._raw_shutdown)
            self.phase = ArchivePhase.COMPLETE
        return self.phase

    @property
    def raw_reply(self) -> bytes | None:
        return self._reply

    @property
    def result(self) -> ArchiveResult:
        if self.phase is not ArchivePhase.COMPLETE or self._result is None:
            raise ValueError("actual shutdown archive/settlement cycle is incomplete")
        return self._result

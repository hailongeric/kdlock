"""Finite ABI1 little-endian frames for the private feedback control channel.

The ioctl envelope is nine native x86_64 u64 words: ABI, operation, sequence,
input pointer/length, output pointer/capacity, actual output length and signed
status. Its command is _IOWR('K', 0, 72). Pointers are borrowed userspace buffers,
not serialized kernel addresses. Payload identities are compared only while
actual channel/provider retention remains valid; copying a number creates no hold.

Every framed payload starts with [ABI, operation, total_bytes, row_count], then
operation-specific fixed words, rows, then blobs [byte_length, bytes] without
padding. Receivers use explicit bounds and require exact consumption. Layouts:

CLAIM request [epoch, holder, capacity]; reply [claim, holder, epoch], rows
[record, incarnation, producer, image, kind, detail, source, target, cursor,
 phase, classification, signed-entry-result], then one version blob.
BUILD_START request [claim, holder, epoch, slot, old]; reply
[candidate, slot, image, inputs, producer, update, owner, old, emission, epoch,
 code_base, code_capacity],
then descriptor/source-identity/producer/entry symbol blobs.
STAGE_LOAD request [candidate] then assembly/Cmetadata/manifest/machine/flat-metadata blobs; reply
[candidate]. PUBLISH request [candidate, claim, holder] plus record/incarnation
rows; reply [publication, claim, holder, slot, update, owner, old, image,
retired, epoch, emission, inputs, producer, candidate] plus actual included rows.
ACK request [publication]; reply [ack, publication, claim, holder, epoch] plus
actual acknowledged record/incarnation rows. CLAIM_END request/reply
[claim, holder]. ABORT request/reply [candidate-or-zero, claim, holder].

All normal replies and requests without rows have row_count zero. QUERY is
unframed: six words then exact cached input and output bytes. No file is opened
or ioctl performed by this codec.
"""

from dataclasses import dataclass
from enum import IntEnum
import struct


ABI = 1
WORD_MAX = (1 << 64) - 1
IOCTL = 0xC0484B00
ENVELOPE = struct.Struct("<9Q")
_WORD = struct.Struct("<Q")
_FRAME = struct.Struct("<4Q")
_QUERY = struct.Struct("<6Q")


class Operation(IntEnum):
    QUERY = 0
    CLAIM = 1
    BUILD_START = 2
    STAGE_LOAD = 3
    PUBLISH = 4
    ACK = 5
    CLAIM_END = 6
    ABORT = 7
    SOURCE_EXPORT = 8
    SHUTDOWN = 9
    ARCHIVE_CLAIM = 10
    SETTLE = 11


@dataclass(frozen=True)
class WireLimits:
    frame_bytes: int
    rows: int
    version_bytes: int
    symbol_bytes: int
    artifact_bytes: int

    def __post_init__(self) -> None:
        for value in (self.frame_bytes, self.rows, self.version_bytes,
                      self.symbol_bytes, self.artifact_bytes):
            if type(value) is not int or not 0 <= value <= WORD_MAX:
                raise ValueError("wire limits must be explicit finite unsigned quantities")


@dataclass(frozen=True)
class Frame:
    operation: Operation
    fixed: tuple[int, ...]
    rows: tuple[tuple[int, ...], ...]
    blobs: tuple[bytes, ...]


@dataclass(frozen=True)
class RecoveredExchange:
    operation: int
    sequence: int
    status: int
    request: bytes
    response: bytes


def word(value: int) -> int:
    if type(value) is not int or not 0 <= value <= WORD_MAX:
        raise ValueError("wire word is not an unsigned 64-bit integer")
    return value


def token(value: int) -> bytes:
    """Preserve an actual non-NULL scalar identity without dereferencing it."""
    word(value)
    if not value:
        raise ValueError("required channel identity is NULL")
    return _WORD.pack(value)


def token_word(value: bytes) -> int:
    if not isinstance(value, bytes) or len(value) != _WORD.size:
        raise ValueError("channel identity needs its exact eight-byte mapping")
    result = _WORD.unpack(value)[0]
    if not result:
        raise ValueError("required channel identity is NULL")
    return result


def signed(value: int) -> int:
    word(value)
    return value - (1 << 64) if value & (1 << 63) else value


def encode(operation: Operation, fixed: tuple[int, ...], rows: tuple[tuple[int, ...], ...],
           blobs: tuple[bytes, ...], blob_limits: tuple[int, ...], limits: WireLimits) -> bytes:
    if not isinstance(operation, Operation) or operation is Operation.QUERY:
        raise ValueError("normal frames need a declared non-QUERY operation")
    if not isinstance(fixed, tuple) or not isinstance(rows, tuple) or not isinstance(blobs, tuple):
        raise TypeError("wire frame components must be immutable tuples")
    if len(rows) > limits.rows or len(blobs) != len(blob_limits):
        raise ValueError("frame rows or blob layout exceeds explicit bounds")
    words = list(fixed)
    for row in rows:
        if not isinstance(row, tuple):
            raise TypeError("wire rows must be immutable tuples")
        words.extend(row)
    for value in words:
        word(value)
    for blob, bound in zip(blobs, blob_limits):
        word(bound)
        if not isinstance(blob, bytes) or len(blob) > bound:
            raise ValueError("wire blob exceeds its explicit bound")
    total = _FRAME.size + len(words) * _WORD.size + sum(_WORD.size + len(b) for b in blobs)
    if total > limits.frame_bytes or total > WORD_MAX:
        raise ValueError("wire frame exceeds explicit frame-byte limit")
    return b"".join((
        _FRAME.pack(ABI, int(operation), total, len(rows)),
        b"".join(_WORD.pack(value) for value in words),
        b"".join(_WORD.pack(len(blob)) + blob for blob in blobs),
    ))


def decode(payload: bytes, operation: Operation, fixed_words: int, row_words: int,
           blob_limits: tuple[int, ...], limits: WireLimits) -> Frame:
    if (not isinstance(payload, bytes) or len(payload) < _FRAME.size
            or len(payload) > limits.frame_bytes):
        raise ValueError("reply frame length exceeds its explicit extent")
    abi, actual_op, length, count = _FRAME.unpack_from(payload)
    if abi != ABI or actual_op != int(operation) or length != len(payload) or count > limits.rows:
        raise ValueError("reply ABI, operation, exact length or row count differs")
    if type(fixed_words) is not int or fixed_words < 0 or type(row_words) is not int or row_words < 0:
        raise ValueError("frame schema needs explicit nonnegative word counts")
    if count and not row_words:
        raise ValueError("reply has rows where this operation has none")
    needed = (fixed_words + count * row_words) * _WORD.size
    cursor = _FRAME.size
    if needed > len(payload) - cursor:
        raise ValueError("reply word arrays exceed supplied bytes")

    def read_words(size: int) -> tuple[int, ...]:
        nonlocal cursor
        result = tuple(_WORD.unpack_from(payload, cursor + i * _WORD.size)[0] for i in range(size))
        cursor += size * _WORD.size
        return result

    fixed = read_words(fixed_words)
    rows = tuple(read_words(row_words) for _ in range(count))
    blobs = []
    for bound in blob_limits:
        word(bound)
        if len(payload) - cursor < _WORD.size:
            raise ValueError("reply has no complete blob length")
        length = read_words(1)[0]
        if length > bound or length > len(payload) - cursor:
            raise ValueError("reply blob exceeds its explicit bound or actual bytes")
        blobs.append(payload[cursor:cursor + length])
        cursor += length
    if cursor != len(payload):
        raise ValueError("reply contains bytes outside its declared schema")
    return Frame(operation, fixed, rows, tuple(blobs))


def decode_query(payload: bytes, capacity: int, limits: WireLimits) -> RecoveredExchange:
    word(capacity)
    if not isinstance(payload, bytes) or len(payload) < _QUERY.size or len(payload) > capacity:
        raise ValueError("QUERY reply exceeds the caller-provided recovery extent")
    abi, operation, sequence, status, input_length, output_length = _QUERY.unpack_from(payload)
    if (abi != ABI or operation not in Operation._value2member_map_
            or input_length > limits.frame_bytes or output_length > limits.frame_bytes
            or _QUERY.size + input_length + output_length != len(payload)):
        raise ValueError("QUERY cached operation or exact lengths differ")
    if sequence and not operation:
        raise ValueError("QUERY cannot report a cached QUERY operation")
    if sequence == 0 and (operation or status or input_length or output_length):
        raise ValueError("fresh channel QUERY contains cached activity")
    cursor = _QUERY.size
    return RecoveredExchange(operation, sequence, signed(status),
                             payload[cursor:cursor + input_length], payload[cursor + input_length:])


@dataclass(frozen=True)
class SourceExportLimits:
    regions: int
    boundaries: int
    source_bytes: int

    def __post_init__(self) -> None:
        for value in (self.regions, self.boundaries, self.source_bytes):
            word(value)


@dataclass(frozen=True)
class SourceFrame:
    fixed: tuple[int, ...]
    regions: tuple[tuple[int, bytes], ...]
    boundaries: tuple[tuple[int, int], ...]
    version: bytes


def decode_source(payload: bytes, bounds: SourceExportLimits, limits: WireLimits) -> SourceFrame:
    """SOURCE_EXPORT8 has variable-length region rows, not ordinary fixed rows."""
    if not isinstance(payload, bytes) or not _FRAME.size <= len(payload) <= limits.frame_bytes:
        raise ValueError("source export exceeds actual or configured frame bytes")
    abi, operation, total, count = _FRAME.unpack_from(payload)
    if (abi != ABI or operation != int(Operation.SOURCE_EXPORT) or total != len(payload)
            or count > bounds.regions or count > limits.rows):
        raise ValueError("source export ABI, exact length or finite region count differs")
    cursor = _FRAME.size

    def take():
        nonlocal cursor
        if len(payload) - cursor < _WORD.size:
            raise ValueError("source export has no complete next word")
        result = _WORD.unpack_from(payload, cursor)[0]
        cursor += _WORD.size
        return result

    def blob(length):
        nonlocal cursor
        if length > len(payload) - cursor:
            raise ValueError("source export byte extent exceeds actual supplied data")
        result = payload[cursor:cursor + length]
        cursor += length
        return result

    fixed = tuple(take() for _ in range(5))
    if fixed[4] > bounds.boundaries:
        raise ValueError("source boundary count exceeds its explicit limit")
    regions, used = [], 0
    for _ in range(count):
        start, length = take(), take()
        if not length or length > bounds.source_bytes - used:
            raise ValueError("source regions exceed their explicit total byte extent")
        regions.append((start, blob(length)))
        used += length
    boundaries = tuple((take(), take()) for _ in range(fixed[4]))
    length = take()
    if not length or length > limits.version_bytes:
        raise ValueError("source version exceeds its explicit byte extent")
    version = blob(length)
    if cursor != len(payload):
        raise ValueError("source export has trailing bytes outside its schema")
    return SourceFrame(fixed, tuple(regions), boundaries, version)

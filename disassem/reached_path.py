"""Decode only a reached x86-64 segment and describe its actual runtime edge.

The reader owns source residency and returns at most fifteen bytes at the
requested PC. This module never follows an edge, discovers a callee, reads a
return word or analyzes a CFG. An unavailable instruction is an explicit event
at its source PC; it is not permission to execute a suffix on the origin.
"""

from dataclasses import dataclass
from enum import Enum

from miasm_python314 import verify_runtime

DEPENDENCY_IDENTITY = verify_runtime()

from miasm.arch.x86.arch import mn_x86, conditional_branch
from miasm.core.bin_stream import bin_stream_str
from miasm.core.utils import Disasm_Exception
from miasm.expression.expression import ExprInt


MASK64 = (1 << 64) - 1
MAX_INSTRUCTION_BYTES = 15
DEFAULT_SEGMENT_INSTRUCTIONS = 64


class EventKind(str, Enum):
    FALLTHROUGH = "fallthrough"
    CONDITIONAL = "conditional"
    CALL = "call"
    JUMP = "jump"
    RETURN = "return"
    SERVICE = "service"
    NEED_SOURCE = "need_source"
    INVALID = "invalid"


@dataclass(frozen=True)
class Instruction:
    pc: int
    raw: bytes
    name: str
    operands: tuple

    @property
    def next_pc(self):
        return (self.pc + len(self.raw)) & MASK64


@dataclass(frozen=True)
class Event:
    kind: EventKind
    pc: int
    next_pc: int
    instruction: Instruction | None = None
    direct_target: int | None = None
    operand: object = None
    return_adjustment: int = 0
    detail: str = ""


@dataclass(frozen=True)
class Segment:
    entry: int
    instructions: tuple
    event: Event


def _target(line):
    operand = line.args[0]
    # The x86 decoder has already included instruction length in a relative
    # ExprInt. dstflow2label adds offset only; keep the same arithmetic without
    # creating a label or looking up any destination bytes.
    if isinstance(operand, ExprInt):
        return (line.offset + int(operand)) & MASK64, None
    return None, operand


def _near_target(line):
    # Miasm spells far FF /3 and FF /5 transfers CALL/JMP too. Their segment
    # operand is not a 64-bit near target and needs a distinct context service.
    return len(line.args) == 1 and line.args[0].size == 64


def decode_segment(reader, pc, *, max_instructions=DEFAULT_SEGMENT_INSTRUCTIONS,
                   service_boundary=None):
    """Decode one linear segment, stopping at its first reached event.

    ``reader(pc, 15)`` must return leased bytes beginning exactly at ``pc``.
    This is a bounded source window for one instruction, not successor
    decoding; bytes after the returned instruction are never interpreted.
    A short read is allowed at a source boundary. An incomplete/undecodable
    short instruction emits NEED_SOURCE; fifteen undecodable bytes emit
    INVALID. Neither result is a public API error or an origin continuation.

    ``service_boundary(line)`` may return a nonempty reason for a service that
    must run before that instruction. It sees this instruction only, without
    inspecting a predecessor, successor or a branch that was not selected.
    """
    if not isinstance(pc, int) or not 0 <= pc <= MASK64:
        raise ValueError("PC must be an unsigned 64-bit address")
    if (not isinstance(max_instructions, int) or isinstance(max_instructions, bool)
            or not 1 <= max_instructions <= 4096):
        raise ValueError("segment instruction limit must be in 1..4096")
    entry = pc
    instructions = []
    for _ in range(max_instructions):
        raw = reader(pc, MAX_INSTRUCTION_BYTES)
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise TypeError("source reader must return bytes")
        raw = bytes(raw)
        if len(raw) > MAX_INSTRUCTION_BYTES:
            raise ValueError("source reader exceeded the instruction byte limit")
        try:
            line = mn_x86.dis(bin_stream_str(raw, base_address=pc), 64, pc)
        except (Disasm_Exception, IOError) as error:
            kind = (EventKind.NEED_SOURCE if len(raw) < MAX_INSTRUCTION_BYTES
                    else EventKind.INVALID)
            return Segment(entry, tuple(instructions), Event(
                kind, pc, pc, detail=str(error)))
        if not 1 <= line.l <= len(raw):
            raise ValueError("decoder returned an incomplete instruction")
        decoded = Instruction(pc, raw[:line.l], line.name, tuple(line.args))
        instructions.append(decoded)
        next_pc = decoded.next_pc
        reason = service_boundary(line) if service_boundary is not None else None
        if reason:
            event = Event(EventKind.SERVICE, pc, next_pc, decoded, detail=str(reason))
        elif line.name in ("CALL", "JMP") and not _near_target(line):
            event = Event(EventKind.SERVICE, pc, next_pc, decoded,
                          detail="reached non-near control operand")
        elif line.name == "CALL":
            target, operand = _target(line)
            event = Event(EventKind.CALL, pc, next_pc, decoded, target, operand)
        elif line.name == "JMP":
            target, operand = _target(line)
            event = Event(EventKind.JUMP, pc, next_pc, decoded, target, operand)
        elif line.name in conditional_branch or line.name.startswith("LOOP"):
            target, operand = _target(line)
            event = Event(EventKind.CONDITIONAL, pc, next_pc, decoded, target, operand)
        elif line.name == "RET":
            adjustment = int(line.args[0]) if line.args else 0
            event = Event(EventKind.RETURN, pc, next_pc, decoded,
                          return_adjustment=adjustment)
        elif line.breakflow():
            # Far transfers, interrupts, SYS*, IRET and other context changes
            # require their own reached-instruction implementation. Do not
            # misclassify them as an ordinary near CALL/RET/JMP.
            event = Event(EventKind.SERVICE, pc, next_pc, decoded,
                          detail="reached context-changing control instruction")
        else:
            pc = next_pc
            continue
        return Segment(entry, tuple(instructions), event)
    return Segment(entry, tuple(instructions), Event(EventKind.FALLTHROUGH, pc, pc))


@dataclass(frozen=True)
class EdgeState:
    """Control-only state used by the encoder's edge contract checks.

    General instruction execution and Native/KD transaction dispatch belong to
    the runtime. This helper neither executes instruction bodies nor owns a
    packet; the caller commits its returned PC/SP after the operation succeeds.
    """

    pc: int
    sp: int


def transition(event, state, *, evaluate_operand=None, read_word=None,
               write_word=None, conditional_taken=None):
    """Apply one near control event without any return-target whitelist.

    The caller supplies the actual conditional result from source flags/count
    state. Operand evaluation receives the unchanged pre-event state. A CALL
    therefore reads CALL RSP / CALL [RSP] before writing the source return word.
    RET consumes the actual source word, including inherited Native frames.
    Service and unresolved events deliberately have no transition here.
    """
    if state.pc != event.pc:
        raise ValueError("event does not match the current source PC")
    if event.kind == EventKind.FALLTHROUGH:
        return EdgeState(event.next_pc, state.sp)
    if event.kind == EventKind.RETURN:
        if read_word is None:
            raise ValueError("RET requires the actual source-stack reader")
        target = read_word(state.sp)
        return EdgeState(target & MASK64,
                         (state.sp + 8 + event.return_adjustment) & MASK64)
    if event.kind == EventKind.CONDITIONAL:
        if not isinstance(conditional_taken, bool):
            raise ValueError("conditional edge requires its actual runtime result")
        if not conditional_taken:
            return EdgeState(event.next_pc, state.sp)
    elif event.kind not in (EventKind.CALL, EventKind.JUMP):
        raise ValueError("event requires runtime supplementation or instruction service")
    target = event.direct_target
    if target is None:
        if evaluate_operand is None:
            raise ValueError("indirect edge requires pre-event operand evaluation")
        target = evaluate_operand(event.operand, state)
    target &= MASK64
    if event.kind == EventKind.CALL:
        if write_word is None:
            raise ValueError("CALL requires the source-stack writer")
        next_sp = (state.sp - 8) & MASK64
        write_word(next_sp, event.next_pc)
        return EdgeState(target, next_sp)
    return EdgeState(target, state.sp)

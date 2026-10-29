"""Reviewed instructions that can end a JIT before native execution.

The instruction itself never runs in generated code. Its scalar effects below
are used only to check the original waiter's remaining source instructions for
uncaptured inputs. Unknown encodings and nonlocal state transitions stay refused.
"""
from copy import copy

from miasm.expression.expression import ExprId, ExprInt, ExprLoc, ExprMem

EXIT = 8
REQUIREMENT = 1
ROOT_REQUIREMENT = 1 << 5
ARITHMETIC_FLAGS = ("cf", "pf", "af", "zf", "nf", "of")
MASK32 = (1 << 32) - 1

# These native helpers are not ordinary translated nested controls. A missing
# callee normally transfers execution to the waiter, but must not hide a known
# acquisition/release from the bounded root-marker scope check. The ABI3 caller
# separately permits its fast-unlock helper only as a terminal native CALL;
# the helper body must never become part of this root image.
ROOT_CONTROL_SYMBOLS = (
    "kd_spin_direct_native_lock",
    "kd_spin_direct_native_contended",
    "kd_spin_direct_native_unlock",
    "kd_rwlock_lock_pinned_clobber_v1",
    "kd_rwlock_fast_write_unlock",
    "kd_read_lock",
    "kd_read_unlock",
    "kd_write_lock",
    "kd_write_unlock",
)

# Exact, unprefixed encodings only. Values are (implicit scalar inputs,
# completely defined scalar outputs). Native hardware state remains on the
# original waiter; none of these operations is simulated by the combiner.
INSTRUCTIONS = {
    "RDTSC": (b"\x0f\x31", {}, ("RAX", "RDX")),
    "RDTSCP": (b"\x0f\x01\xf9", {}, ("RAX", "RDX", "RCX")),
    "CPUID": (b"\x0f\xa2", {"RAX": MASK32, "RCX": MASK32},
              ("RAX", "RBX", "RCX", "RDX")),
    "RDMSR": (b"\x0f\x32", {"RCX": MASK32}, ("RAX", "RDX")),
    "WRMSR": (b"\x0f\x30", {"RCX": MASK32, "RAX": MASK32, "RDX": MASK32}, ()),
    "RDPMC": (b"\x0f\x33", {"RCX": MASK32}, ("RAX", "RDX")),
    "CLI": (b"\xfa", {}, ()),
    "STI": (b"\xfb", {}, ()),
    "CLD": (b"\xfc", {}, ()),
    "STD": (b"\xfd", {}, ()),
    "LAHF": (b"\x9f", {}, ()),
    "SAHF": (b"\x9e", {"RAX": 0xff00}, ()),
}


def descriptor(line):
    """Do not let a decoder alias, operand or redundant prefix widen review."""
    item = INSTRUCTIONS.get(line.name.upper())
    if (item is None or line.args or bytes(getattr(line, "b", b"")) != item[0]
            or getattr(line, "l", 0) != len(item[0])):
        return None
    return item


def normalize_decoded(blocks):
    """Repair one pinned decoder error using its complete instruction bytes.

    Miasm 0.1.5 names 0F 01 F9 ``INVLPG ECX``. Architecturally these three
    exact bytes are RDTSCP, with no explicit operands. Do not reinterpret an
    arbitrary INVLPG, an undecoded root, or a similarly named instruction.
    """
    for block in blocks.values():
        for index, line in enumerate(block.lines):
            if (line.name.upper() == "INVLPG" and line.l == 3
                    and bytes(getattr(line, "b", b"")) == b"\x0f\x01\xf9"
                    and line.args == [ExprId("ECX", 32)]):
                repaired = copy(line)
                repaired.name = "RDTSCP"
                repaired.args = []
                block.lines[index] = repaired


def apply_entry_effects(line, state):
    """Check native inputs and propagate defined bits through the native suffix."""
    _, inputs, outputs = descriptor(line)
    for name, mask in inputs.items():
        if state.get(ExprId(name, 64), 0) & mask:
            raise ValueError(f"native {line.name} input {name} is uncaptured")
    after = dict(state)
    for name in outputs:
        after[ExprId(name, 64)] = 0
    if line.name.upper() == "LAHF":
        tainted = any(state.get(ExprId(name, 1), 0)
                      for name in ARITHMETIC_FLAGS if name != "of")
        ax = ExprId("RAX", 64)
        after[ax] = (state.get(ax, 0) & ~0xff00) | (0xff00 if tainted else 0)
    elif line.name.upper() == "SAHF":
        for name in ARITHMETIC_FLAGS:
            if name != "of":
                after[ExprId(name, 1)] = 0
    elif line.name.upper() in {"CLD", "STD"}:
        after[ExprId("df", 1)] = 0
    return after


def apply_context_effects(line, constants):
    """Keep memory unchanged, but never invent numeric CPU-state results."""
    _, _, outputs = descriptor(line)
    names = set(outputs)
    if line.name.upper() == "LAHF":
        names.add("RAX")
    flags = set()
    if line.name.upper() == "SAHF":
        flags.update(name for name in ARITHMETIC_FLAGS if name != "of")
    if line.name.upper() in {"CLD", "STD"}:
        flags.add("df")
    for reg in ({ExprId(name, 64) for name in names}
                | {ExprId(name, 1) for name in flags}):
        constants.values.pop(reg, None)
        constants.origins.pop(reg, None)


def root_scope_rejection(blocks, databases, terminal_unlock, controls,
                         hostcalls, *, learned_indirect=False,
                         native_terminal_controls=()):
    """Check the full selected source before cutting native-marker successors.

    Ordinary decoded callees remain in the same invocation. A missing direct
    callee is a terminal native exit; its unselected native suffix is outside
    this proof. Services, nested controls and learned/indirect control could
    resume a progressed frame, so none can appear anywhere in a marker image.
    The ordinary context and minimal-entry proofs still check every selected
    source instruction, including the suffix following an instruction marker.
    """
    # Import after module initialization: context_values also uses the reviewed
    # instruction effects above while propagating source facts.
    from context_values import static_address

    if learned_indirect:
        return min(blocks), "root instruction markers reject learned indirect control"
    source_pcs = {line.offset for block in blocks.values() for line in block.lines}
    for start, block in sorted(blocks.items()):
        db = databases[block]
        for line in block.lines:
            name = line.name.upper()
            next_ip = line.offset + line.l
            branch = name == "CALL" or name.startswith("J")
            if branch and (len(line.args) != 1
                           or not isinstance(line.args[0], (ExprLoc, ExprInt))):
                return line.offset, "root instruction markers reject indirect control"
            if name == "RET" and line.args:
                return line.offset, "root instruction markers require plain RET"
            target = (static_address(line.args[0], db, next_ip)
                      if branch else None)
            if branch and target is None:
                return line.offset, "root instruction markers reject unresolved control"
            if branch and target in hostcalls:
                return line.offset, "root instruction markers reject hostcall services"
            terminal = (name == "CALL" and next_ip not in source_pcs
                        and (target == terminal_unlock
                             or (target in native_terminal_controls
                                 and target not in blocks)))
            # This includes direct tail calls and address-taking, so a known
            # control cannot be relabelled as an ordinary missing helper.
            for arg in line.args:
                address = static_address(arg.ptr if isinstance(arg, ExprMem) else arg,
                                         db, next_ip)
                if address in controls and not (terminal and arg is line.args[0]):
                    return line.offset, (
                        "root instruction markers reject nested or nonterminal "
                        f"lock control: {controls[address]}")
    return None


def emitted_scope(blocks, databases, *, origin_sites=()):
    """Cut each first marker's successor edge after full source admission.

    Independently selected blocks remain checked and addressable; this does not
    remove a cold path to make admission succeed. The coordinator recalculates
    reachability and the return table from these terminal emitted blocks.
    """
    selected, selected_dbs = {}, {}
    for start, original in blocks.items():
        block = original
        for index, line in enumerate(original.lines):
            if descriptor(line) and line.offset not in origin_sites:
                block = copy(original)
                block.lines = original.lines[:index + 1]
                block.bto = set()
                break
        selected[start] = block
        selected_dbs[block] = databases[original]
    return selected, selected_dbs

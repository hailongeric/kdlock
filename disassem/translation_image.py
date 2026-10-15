"""Emit assembly for the coordinator's already checked JIT block set.

Continuation labels, register mapping, wrapper dispatch and diagnostics retain
that exact scope; admission and artifact publication stay in disassem.py.
"""

from io import StringIO
import re

import assist
import conflict
import diagnostics
import indirect_jump
import solve_bug
import special_inst
from assist import make_inst
from miasm.arch.x86.arch import mn_x86
from miasm.expression.expression import ExprLoc
from translation_scope import find_resumable_call_continuations


def wrapper_context_inputs(assembly):
    """Find inputs used by final lowered code, including emitted entry guards.

    This is an import optimization, not admission. A caller with no known final
    image, an external include or an unknown macro keeps both ABI inputs.
    Source comments cannot make an unused input live. Stack slots never move.
    """
    if not isinstance(assembly, str):
        return True, True
    code = re.sub(r'/\*.*?\*/', '', assembly, flags=re.S)
    if ('/*' in code or '*/' in code or
            re.search(r'(?m)^\s*(?:#|\.include\b|\.macro\b)', code) or
            re.search(r'\b(?:ARG_REG|MEM_ARG2?)\b', code)):
        return True, True
    return (bool(re.search(r'\b(?:Stack_RGS|PT_GS)\b', code)),
            bool(re.search(r'\b(?:Stack_TASK|Stack_RCT|PT_TASK)\b', code)))


def mutex_context_error(assembly, lock_kind, *, requirements=0):
    """A sleeping origin task cannot serialize accesses to its CPU's GS data.

    Inspect the entire lowered image, including entry guards and learned calls.
    Logical current uses the separate task input and remains supported. Unknown
    assembly conservatively requires GS, as for wrapper input selection.
    """
    if (lock_kind == 'mutex-owned' and wrapper_context_inputs(assembly)[0]
            and requirements != 1):
        return "mutex cannot delegate origin-CPU GS storage"
    return None


def write_entry_dispatch(
    f, entry, block_dict, continuation_targets=None, *, body_witness=False,
):
    dispatch_targets = set(block_dict)
    dispatch_targets.update(continuation_targets or set())
    ordered_targets = [entry] + sorted(dispatch_targets - {entry})

    # R11 addresses shared kd_regs spill slots; the budget is independent state.
    # Count down to the same 2**24 branch-block visits. DEC supplies the test
    # flags itself, avoiding a second access to the wrapper's budget slot.
    f.write("MOV     Stack_BUDGET, 0x1000000\n")
    f.write("MOV     R14, PT_RIP\n")
    for offset in ordered_targets:
        f.write(f"CMP     R14, 0x{offset:x}\n")
        target = f"kd_body_entry_{offset:x}" if body_witness else f"loc_{offset:x}"
        f.write(f"JZ      {target}\n")
    f.write("MOV     Stack_IJ, 0x2\n")
    f.write("MOV     R15, R14\n")
    f.write("JMP     exit\n")
    if body_witness:
        # Only validated dispatch targets pass through these stubs. Internal
        # branches use loc_* directly: one witness store per wrapper entry,
        # including resumed CALL continuations, without stores on loop edges.
        # Entry guards and dispatch misses still return with a zero witness.
        for offset in ordered_targets:
            f.write(f"kd_body_entry_{offset:x}:\n")
            f.write(make_inst("MOV", ["Stack_JIT_WITNESS", "1"]))
            f.write(f"JMP     loc_{offset:x}\n")


def emit_jit_assembly(
    entry, block_dict, db_dict, jump_table, missing_callees,
    resolved_hostcalls, keep_call_stack, *, entry_guards=None, body_witness=False,
    terminal_clobber_unlocks=(), terminal_cabi_unlocks=(),
):
    continuation_targets = find_resumable_call_continuations(
        block_dict, db_dict, keep_call_stack
    )
    # The outer unlock's return PC may be in the native suffix trimmed by
    # critical_section_blocks. COMPLETE returns there physically; it is not
    # a resumable JIT label. Dispatch only to instructions still being emitted,
    # including interior CALL continuations, without widening admission scope.
    continuation_targets.intersection_update(
        line.offset for block in block_dict.values() for line in block.lines
    )
    continuation_labels = continuation_targets - set(block_dict)
    emitted_continuation_labels = set()
    emitted_offsets = {line.offset for block in block_dict.values() for line in block.lines}

    f = StringIO()
    if entry_guards is not None:
        entry_guards.emit(f, entry)
    write_entry_dispatch(
        f, entry, block_dict, continuation_targets, body_witness=body_witness,
    )
    budget_rips = []

    for offset, block in sorted(block_dict.items()):
        db = db_dict[block]
        f.write("/*\n" + block.to_string() + "\n */ \n")  # Comment source
        label = db.pretty_str(block.loc_key)

        f.write(label + ":\n")
        reg_map = conflict.block_init()

        len_block = len(block.lines)
        line_cnt = 0

        if assist.check_is_branch(block.lines) and label[0] == "l":
            budget_rips.append(offset)
            f.write("DEC             Stack_BUDGET\n")
            f.write(f"JZ              kd_budget_limit_{offset:x}\n")

        temp_i = 0
        temp_j = 0
        while temp_i < len(block.lines):
            line = block.lines[temp_i]
            # Keep the source location through the two synthetic LEA instructions.
            if temp_j == 0:
                diagnostics.set_instruction(offset, line)
            if (
                offset in continuation_labels
                and offset not in emitted_continuation_labels
            ):
                f.write(f"loc_{offset:x}:\n")
                emitted_continuation_labels.add(offset)
            if str(line) == "LEA        R13, QWORD PTR [R12 + R14]":
                diagnostics.warn(
                    "LEA_FLAGS_REWRITE",
                    "emit_mov_add",
                    "ADD changes flags although the original LEA does not",
                )
                temp_inst1 = mn_x86.fromstring("MOV R13, R14", loc_db=None, mode="64")
                temp_inst2 = mn_x86.fromstring("ADD R13, R12", loc_db=None, mode="64")
                block.lines[temp_i : temp_i + 1] = [temp_inst1, temp_inst2]
                offset = offset + line.l
                line_cnt = line_cnt + 1
                block_end = line_cnt == len_block
                temp_j = 2
                continue

            if temp_j == 0:
                solve_bug.solve_lea_ra_rb_c_rb(line)

            if temp_j == 0:
                offset = offset + line.l
                line_cnt = line_cnt + 1
                block_end = line_cnt == len_block

            # Only a known terminal control CALL can skip constructing its
            # virtual return slot. Resumed FULL entries and failed metadata
            # checks still materialize that exact CALL once before FULL exit.
            target = (db.get_location_offset(line.args[0].loc_key)
                      if line.name == 'CALL' and isinstance(line.args[0], ExprLoc)
                      else None)
            if target in terminal_cabi_unlocks and offset not in emitted_offsets:
                f.write(special_inst.terminal_cabi_unlock(target, offset, reg_map))
            elif target in terminal_clobber_unlocks and offset not in emitted_offsets:
                f.write(special_inst.terminal_clobber_unlock(target, offset, reg_map))
            else:
                f.write(special_inst.translate(line, offset, db, reg_map, block_end))
            temp_i += 1
            if temp_j > 0:
                temp_j -= 1
        f.write("\n\n")
    f.write(indirect_jump.make_jump_table(jump_table))
    f.write(indirect_jump.make_callee_table(missing_callees, resolved_hostcalls))
    # The source RIP is needed only if the budget expires. Keep its material-
    # ization off the frequently executed branch-block path; the exit resumes
    # at the same untouched source block as the previous INC/TEST sequence.
    for offset in budget_rips:
        f.write(f"kd_budget_limit_{offset:x}:\n")
        f.write(make_inst("MOVABS", ["R14", hex(offset)]))
        f.write("JMP             inst_limit\n")

    # A successful static/guarded analysis is not a runtime address or memory
    # freshness check. Report the contract once per generated image, without
    # pretending to enumerate every unknown access or changing its admission.
    diagnostics.set_instruction(entry, "<context admission scope>")
    diagnostics.warn(
        "CONTEXT_SCREENING_ONLY",
        "emit_unchanged",
        "static context screening does not validate runtime pointer targets or "
        "concurrent memory freshness; use only audited experimental workloads",
        runtime_address_guard=False,
        concurrent_memory_validated=False,
    )
    diagnostics.set_instruction(entry, "<entry/branch instrumentation>")
    diagnostics.warn(
        "FLAGS_UNPRESERVED",
        "emit_unchanged",
        "entry dispatch and branch budget may clobber live flags; liveness is unchecked",
        budget_blocks=len(budget_rips),
        first_budget_rip=(
            f"0x{budget_rips[0]:x}" if budget_rips else "n/a"
        ),
    )
    return f.getvalue()

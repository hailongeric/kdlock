"""Emit assembly for the coordinator's already checked JIT block set.

Continuation labels, register mapping, wrapper dispatch and diagnostics retain
that exact scope; admission and artifact publication stay in disassem.py.
"""

from io import StringIO

import assist
import conflict
import diagnostics
import indirect_jump
import solve_bug
import special_inst
from assist import make_inst
from miasm.arch.x86.arch import mn_x86
from translation_scope import find_resumable_call_continuations


def write_entry_dispatch(f, entry, block_dict, continuation_targets=None):
    dispatch_targets = set(block_dict)
    dispatch_targets.update(continuation_targets or set())

    # R11 addresses shared pt_regs spill slots; the budget is independent state.
    f.write("MOV     Stack_BUDGET, 0\n")
    f.write("MOV     R14, PT_RIP\n")
    f.write(f"CMP     R14, 0x{entry:x}\n")
    f.write(f"JZ      loc_{entry:x}\n")
    for offset in sorted(dispatch_targets):
        if offset == entry:
            continue
        f.write(f"CMP     R14, 0x{offset:x}\n")
        f.write(f"JZ      loc_{offset:x}\n")
    f.write("MOV     Stack_IJ, 0x2\n")
    f.write("MOV     R15, R14\n")
    f.write("JMP     exit\n")


def emit_jit_assembly(
    entry, block_dict, db_dict, jump_table, missing_callees,
    resolved_hostcalls, keep_call_stack, *, entry_guards=None, body_witness=False,
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

    f = StringIO()
    if entry_guards is not None:
        entry_guards.emit(f, entry)
    write_entry_dispatch(f, entry, block_dict, continuation_targets)
    budget_blocks = 0
    first_budget_rip = None

    for offset, block in sorted(block_dict.items()):
        db = db_dict[block]
        f.write("/*\n" + block.to_string() + "\n */ \n")  # Comment source
        label = db.pretty_str(block.loc_key)

        f.write(label + ":\n")
        if body_witness:
            # MOV observes body entry without changing guest GPRs or live flags.
            f.write(make_inst("MOV", ["Stack_JIT_WITNESS", "1"]))

        reg_map = conflict.block_init()

        len_block = len(block.lines)
        line_cnt = 0

        if assist.check_is_branch(block.lines) and label[0] == "l":
            budget_blocks += 1
            if first_budget_rip is None:
                first_budget_rip = offset
            f.write(make_inst("MOVABS", ["R14", hex(offset)]))
            f.write("INC             Stack_BUDGET\n")
            f.write("TEST            Stack_BUDGET, 0x1000000\n")
            f.write("JNZ             inst_limit\n")

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
                if body_witness:
                    f.write(make_inst("MOV", ["Stack_JIT_WITNESS", "1"]))
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

            f.write(special_inst.translate(line, offset, db, reg_map, block_end))
            temp_i += 1
            if temp_j > 0:
                temp_j -= 1
        f.write("\n\n")
    f.write(indirect_jump.make_jump_table(jump_table))
    f.write(indirect_jump.make_callee_table(missing_callees, resolved_hostcalls))

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
        budget_blocks=budget_blocks,
        first_budget_rip=(
            f"0x{first_budget_rip:x}" if first_budget_rip is not None else "n/a"
        ),
    )
    return f.getvalue()

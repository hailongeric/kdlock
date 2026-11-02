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
import native_escape
import origin_instructions
import origin_memory
import budget_resume
import returning_calls
from assist import make_inst
from miasm.arch.x86.arch import mn_x86
from miasm.expression.expression import ExprId, ExprLoc, ExprMem
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


def write_entry_dispatch(
    f, entry, block_dict, continuation_targets=None, *, body_witness=False,
    preserve_flags=True, root_only=False, origin_sites=None,
    budget_targets=None, returning_targets=None,
):
    dispatch_targets = {entry} if root_only else set(block_dict)
    if not root_only:
        dispatch_targets.update(continuation_targets or set())
    ordered_targets = [entry] + sorted(dispatch_targets - {entry})

    # R11 addresses shared kd_regs spill slots; the budget is independent state.
    # Count down to the same 2**24 branch-block visits. DEC supplies the test
    # flags itself, avoiding a second access to the wrapper's budget slot.
    f.write("MOV     Stack_BUDGET, 0x1000000\n")
    f.write("MOV     R14, PT_RIP\n")
    if preserve_flags:
        f.write("PUSHFQ\n")
    if budget_targets is not None:
        if not preserve_flags or root_only or origin_sites:
            raise ValueError("budget reentry requires a FULL arithmetic-flags contract")
        budget_resume.entry_dispatch(f, budget_targets)
    if origin_sites:
        if not preserve_flags or root_only:
            raise ValueError("original-task instruction dispatch requires a resumable flags contract")
        origin_instructions.entry_dispatch(f, origin_sites)
    if returning_targets:
        if not preserve_flags or root_only:
            raise ValueError("returning CALL needs a FULL arithmetic-flags contract")
        returning_calls.entry_dispatch(f, returning_targets)
    for offset in ordered_targets:
        f.write(f"CMP     R14, 0x{offset:x}\n")
        target = (f"kd_dispatch_{offset:x}" if preserve_flags else
                  f"kd_body_entry_{offset:x}" if body_witness else f"loc_{offset:x}")
        f.write(f"JZ      {target}\n")
    if preserve_flags:
        f.write("POPFQ\n")
    f.write("MOV     Stack_IJ, 0x2\n")
    f.write("MOV     R15, R14\n")
    f.write("JMP     exit\n")
    if body_witness or preserve_flags:
        # Only validated dispatch targets pass through these stubs. Internal
        # branches use loc_* directly: one witness store per wrapper entry,
        # including resumed CALL continuations, without stores on loop edges.
        # Entry guards and dispatch misses still return with a zero witness.
        for offset in ordered_targets:
            f.write((f"kd_dispatch_{offset:x}:\n" if preserve_flags else
                     f"kd_body_entry_{offset:x}:\n"))
            if preserve_flags:
                f.write("POPFQ\n")
            if body_witness:
                f.write(make_inst("MOV", ["Stack_JIT_WITNESS", "1"]))
            f.write(f"JMP     loc_{offset:x}\n")
    if origin_sites:
        origin_instructions.continuation_dispatch(f, origin_sites)
    if budget_targets is not None:
        budget_resume.continuation_dispatch(f, budget_targets)
    if returning_targets:
        returning_calls.continuation_dispatch(f, returning_targets)


def emit_jit_assembly(
    entry, block_dict, db_dict, jump_table, missing_callees,
    resolved_hostcalls, keep_call_stack, *, entry_guards=None, body_witness=False,
    terminal_clobber_unlocks=(),
    terminal_unlock_aliases=None,
    indirect_call_native=False,
    native_escapes=False,
    root_native_escape=False,
    address_guards=None,
    native_calls=None,
    trusted_source=False,
    origin_sites=None,
    memory_sites=None,
    memory_preempt_symbol=None,
    budget_resume_enabled=False, returning_targets=None, returning_services=(),
    nonreturning_targets=(),
):
    continuation_targets = find_resumable_call_continuations(
        block_dict, db_dict, set(keep_call_stack) - set(nonreturning_targets)
    )
    # The outer unlock's return PC may be in the native suffix trimmed by
    # critical_section_blocks. COMPLETE returns there physically; it is not
    # a resumable JIT label. Dispatch only to instructions still being emitted,
    # including interior CALL continuations, without widening admission scope.
    continuation_targets.intersection_update(
        line.offset for block in block_dict.values() for line in block.lines
    )
    if origin_sites:
        continuation_targets.update(line.offset + line.l for line, _ in origin_sites.values())
    if memory_sites:
        continuation_targets.update(line.offset + line.l
            for line, operation, _ in memory_sites.values() if operation)
        returning_targets = set(returning_targets or ()) | {
            line.offset + line.l for line, operation, _ in memory_sites.values() if operation}
    continuation_labels = continuation_targets - set(block_dict)
    emitted_continuation_labels = set()
    emitted_offsets = {line.offset for block in block_dict.values() for line in block.lines}

    f = StringIO()
    budget_targets = {
        offset for offset, block in block_dict.items()
        if assist.check_is_branch(block.lines)
        and db_dict[block].pretty_str(block.loc_key).startswith("l")
    } if budget_resume_enabled else None
    if entry_guards is not None:
        entry_guards.emit(f, entry)
    write_entry_dispatch(
        f, entry, block_dict, continuation_targets, body_witness=body_witness,
        preserve_flags=True,
        root_only=root_native_escape or native_calls is not None,
        origin_sites=origin_sites,
        budget_targets=budget_targets,
        returning_targets=returning_targets,
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
            # Source flags can cross block edges and ordinary CALL/RET pairs.
            # Instrumentation owns the physical stack; all source stack
            # accesses use virtual SP and every target consumes this save.
            f.write("PUSHFQ\n")
            f.write("DEC             Stack_BUDGET\n")
            f.write(f"JZ              kd_budget_limit_{offset:x}\n")
            f.write("POPFQ\n")

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
                    "emit_saved_flags_mov_add",
                    "save source flags around ADD",
                )
                f.write("PUSHFQ\n")
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
            if address_guards is not None:
                f.write(address_guards.emit(line, reg_map))
            if (memory_sites and line.offset in memory_sites and
                    origin_memory.read_operands(line)):
                f.write(origin_memory.read_guard(line, reg_map, memory_preempt_symbol))
            if (memory_sites and line.offset in memory_sites and
                    origin_memory.is_gs_mutation(line)):
                diagnostics.warn("ORIGIN_MEMORY_SERVICE", "emit_original_cpu_instruction",
                                 "retain the exact JIT successor after one GS memory instruction",
                                 source_ip=hex(line.offset), instruction=line.name)
                f.write(origin_memory.marker(line, reg_map))
                reg_map = conflict.block_init()
            elif origin_sites and line.offset in origin_sites:
                diagnostics.warn("ORIGIN_INSTRUCTION_SERVICE", "emit_waiter_instruction",
                                 "retain the same immutable JIT successor after one original-task instruction",
                                 source_ip=hex(line.offset), instruction=line.name)
                f.write(origin_instructions.marker(line, reg_map))
                # The wrapper will import the FULL packet, not the predecessor's
                # physical scratch allocation, when it returns at this label.
                reg_map = conflict.block_init()
            elif native_escapes and native_escape.descriptor(line):
                diagnostics.warn("NATIVE_ESCAPE_MARKER", "emit_waiter_exit",
                                 "resume this invocation's native suffix before the source instruction",
                                 source_ip=hex(line.offset), instruction=line.name)
                f.write(special_inst.native_escape_marker(line, reg_map))
            elif target in terminal_clobber_unlocks and offset not in emitted_offsets:
                f.write(special_inst.terminal_clobber_unlock(
                    target, offset, reg_map,
                    identity_target=(terminal_unlock_aliases or {}).get(target)))
            elif native_calls is not None and target in native_calls.services:
                f.write(native_calls.emit(line, offset, target, reg_map))
            else:
                f.write(special_inst.translate(line, offset, db, reg_map, block_end,
                                               trusted_source=trusted_source))
            temp_i += 1
            if temp_j > 0:
                temp_j -= 1
                if temp_j == 0:
                    f.write("POPFQ\n")
        f.write("\n\n")
    indirect_calls = {line.offset + line.l: line.offset
                      for block in block_dict.values() for line in block.lines
                      if indirect_call_native and line.name == "CALL" and line.args and
                      isinstance(line.args[0], (ExprId, ExprMem))}
    f.write(indirect_jump.make_jump_table(jump_table, preserve_flags=True,
                                        indirect_calls=indirect_calls))
    direct_targets = set(native_calls.services) if native_calls is not None else set()
    f.write(indirect_jump.make_callee_table(
        [target for target in missing_callees if target not in direct_targets],
        resolved_hostcalls, returning_services=returning_services))
    # The source RIP is needed only if the budget expires. Keep its material-
    # ization off the frequently executed branch-block path; the exit resumes
    # at the same untouched source block as the previous INC/TEST sequence.
    for offset in budget_rips:
        f.write(f"kd_budget_limit_{offset:x}:\n")
        if budget_resume_enabled:
            budget_resume.exhausted(f)
        else:
            f.write("POPFQ\n")
        f.write(make_inst("MOVABS", ["R14", hex(offset)]))
        f.write("JMP             inst_limit\n")

    # A successful static/guarded analysis is not a runtime address or memory
    # freshness check. Report the contract once per generated image, without
    # pretending to enumerate every unknown access or changing its admission.
    diagnostics.set_instruction(entry, "<context admission scope>")
    diagnostics.warn(
        "TRUSTED_SOURCE_EMISSION" if trusted_source else "CONTEXT_SCREENING_ONLY",
        "emit_unchanged",
        ("source safety is a caller assumption; no context/value or loop admission ran"
         if trusted_source else
         "static context screening does not validate runtime pointer targets or "
         "concurrent memory freshness; use only audited experimental workloads"),
        runtime_address_guard=False,
        concurrent_memory_validated=False,
    )
    diagnostics.set_instruction(entry, "<entry/branch instrumentation>")
    diagnostics.warn(
        "TRANSLATION_FLAGS_PRESERVED",
        "preserve_arithmetic_flags",
        "generated dispatch, block budgets, return checks and LEA lowering "
        "preserve source flags; entry and native continuation contracts are unchanged",
        budget_blocks=len(budget_rips),
        first_budget_rip=(
            f"0x{budget_rips[0]:x}" if budget_rips else "n/a"
        ),
    )
    result = f.getvalue()
    if native_calls is not None:
        # The provider fills these generated rel32 operands while the image is
        # private. No relocation or code mutation occurs after publication.
        result = ("#ifndef KD_EMIT_NATIVE_DIRECTORY\n" + result + "#else\n"
                  + native_calls.metadata() + "#endif\n")
    if address_guards is not None and address_guards.sites:
        # wrapper.S includes the same self-contained artifact a second time
        # after its exit code, placing the validated directory at image end.
        result = ("#ifndef KD_EMIT_GUARD_DIRECTORY\n" + result + "#else\n"
                  + address_guards.metadata() + "#endif\n")
    if origin_sites:
        if native_calls is not None or (address_guards is not None and address_guards.sites):
            raise ValueError("original-task instruction metadata cannot share another trailer")
        result = ("#ifndef KD_EMIT_ORIGIN_DIRECTORY\n" + result + "#else\n"
                  + origin_instructions.metadata(origin_sites) + "#endif\n")
    if memory_sites:
        if (origin_sites or native_calls is not None or
                (address_guards is not None and address_guards.sites)):
            raise ValueError("original-CPU memory metadata cannot share another trailer")
        result = ("#ifndef KD_EMIT_MEMORY_DIRECTORY\n" + result + "#else\n"
                  + origin_memory.metadata(memory_sites, memory_preempt_symbol) + "#endif\n")
    return result

# Translation coordinator: leased kernel text -> decoded JIT scope -> admission
# -> register-mapped assembly -> wrapper image. Refusal removes stale artifacts;
# I/O/environment errors are not native-only verdicts. The daemon publishes the
# resulting image; running this CLI alone neither uploads it nor proves JIT ran.
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import assist
import conflict
import context_guards
import context_policy
import diagnostics
import entry_abi
import hostcall
import indirect_jump
import memread
import normal
import solve_bug
import translation
from assist import make_inst
from miasm.analysis.machine import Machine
from miasm.arch.x86.arch import mn_x86
from miasm.core.bin_stream import bin_stream_str
from miasm.core.locationdb import LocationDB
from miasm.expression.expression import ExprLoc


def get_kernel_symbol(name, default=0):
    try:
        with open("/proc/kallsyms", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[2] == name:
                    return int(parts[0], 16)
    except OSError:
        pass
    return default


def get_percpu_symbol_offset(name):
    value = get_kernel_symbol(name)
    percpu_start = get_kernel_symbol("__per_cpu_start")
    if value and percpu_start and value >= percpu_start:
        return value - percpu_start
    return value


def find_segment_policy_error(
    block_dict,
    code_ranges=None,
    db_dict=None,
    symbols=None,
    lock_kind=None,
    lock_symbols=None,
    roots=None,
    native_exits=(),
    guards=None,
    scoped_calls=False,
    mutex_stack_bytes=0,
    entry_spill_guards=False,
    readonly_targets=(),
):
    # A guarded verdict is conditional: its complete predicates must be emitted
    # before body execution. Analysis and emission share this same collector.
    db_dict = db_dict or {}
    symbols = symbols or {}
    selected = {
        start: block
        for start, block in block_dict.items()
        if not code_ranges or any(left <= start < right for left, right in code_ranges)
    }
    for block_start, block in sorted(selected.items()):
        if not getattr(block, "lines", None):
            diagnostics.set_instruction(block_start, "<undecodable/empty block>")
            return block_start, "undecodable or empty basic block"
    # RET value refinement can leave a block without a propagated input, while
    # emission still retains that block and its return-table target. Entry alias
    # guards do not enforce runtime return-word contents. Apply unconditional
    # context/backend bans to every emitted block, before any precision retry;
    # native-only CALL suffixes have already been removed from this scope.
    for block_start, block in sorted(selected.items()):
        offset = block_start
        for line in block.lines:
            context_error = context_policy.instruction_rejection(
                line, offset, db_dict.get(block), symbols, lock_kind, lock_symbols
            )
            if context_error:
                reason, symbol = context_error
                diagnostics.set_instruction(offset, line)
                return offset, f"{reason}: {symbol}" if symbol else reason
            reason = normal.segment_policy_error(line)
            if reason:
                diagnostics.set_instruction(offset, line)
                return offset, reason
            offset += line.l
    try:
        for block_start, block, constants in context_policy.constant_blocks(
            selected,
            db_dict,
            roots=roots,
            control_targets=lock_symbols or (),
            clobber_targets={address for address, (_, name) in (lock_symbols or {}).items()
                             if name.endswith("_clobber_v1")},
            readonly_targets=readonly_targets,
            mutex_targets={
                address
                for address, (kind, name) in (lock_symbols or {}).items()
                if lock_kind == kind == "mutex"
                and name in {"mutex_lock", "mutex_unlock"}
            },
            mutex_stack_bytes=mutex_stack_bytes,
            native_exits=native_exits,
            guards=guards,
            scoped_calls=scoped_calls,
            entry_spill_guards=entry_spill_guards,
        ):
            offset = block_start
            for line in block.lines:
                context_error = context_policy.instruction_rejection(
                    line,
                    offset,
                    db_dict.get(block),
                    symbols,
                    lock_kind,
                    lock_symbols,
                    constants,
                )
                if context_error:
                    reason, symbol = context_error
                    diagnostics.set_instruction(offset, line)
                    return offset, f"{reason}: {symbol}" if symbol else reason
                constants.update(line, symbols)
                offset += line.l
    except context_policy.ContextFlowLimit as error:
        error.report()
        diagnostics.set_instruction(
            error.offset, error.instruction or "<register-address analysis>"
        )
        return error.offset, str(error)
    return None


def reject_translation(detail):
    diagnostics.warn("CONTEXT_NATIVE_ONLY", "reject_entry", detail)
    # A previous successful generation must never look like this result's image.
    for name in ("jit.S", "jit.o", "jit.bin", "bin.txt"):
        Path("asm", name).unlink(missing_ok=True)
    return context_policy.NATIVE_ONLY_EXIT


def run_build_step(command, **kwargs):
    try:
        return subprocess.run(command, check=True, **kwargs)
    except (OSError, subprocess.CalledProcessError) as error:
        diagnostics.error("BUILD_FAILED", "raise", str(error), command=command)
        raise


def build_jit_binary(abi=0):
    diagnostics.set_instruction(None, "<assemble/objcopy/objdump>")
    include_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "include"
    )
    run_build_step(
        [
            "gcc",
            f"-I{include_dir}",
            f"-DKD_GENERATED_ENTRY_ABI={abi}",
            "-I./asm/",
            "-c",
            "-fPIC",
            f"{include_dir}/wrapper.S",
            "-o",
            "./asm/jit.o",
        ],
    )
    run_build_step(
        ["objcopy", "--remove-section", ".note.gnu.property", "./asm/jit.o"],
    )
    run_build_step(["objcopy", "-O", "binary", "./asm/jit.o", "./asm/jit.bin"])
    with open("./asm/bin.txt", "w", encoding="ascii") as output:
        run_build_step(
            [
                "objdump",
                "-b",
                "binary",
                "-m",
                "i386:x86-64:intel",
                "-D",
                "./asm/jit.bin",
            ],
            stdout=output,
        )


def find_resumable_call_continuations(block_dict, db_dict, keep_call_stack):
    continuations = set()
    for block_start, block in block_dict.items():
        db = db_dict[block]
        offset = block_start
        for line in block.lines:
            offset += line.l
            if line.name != "CALL" or not isinstance(line.args[0], ExprLoc):
                continue
            callee = int(line.arg2str(line.args[0], 0, db).split("_")[1], 16)
            if callee in keep_call_stack:
                continuations.add(offset)
    return continuations


def write_entry_dispatch(f, entry, block_dict, continuation_targets=None):
    dispatch_targets = set(block_dict)
    dispatch_targets.update(continuation_targets or set())

    f.write("MOV     R11, 0\n")
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


def decode_regions(rets, raw_spin_unlock, keep_call_stack):
    cfgs = []
    ordering_bug_list = [0x2CE40, 0x2CE50, 0x4FFD0, 0x738D0, 0x67B0]

    for r in rets:
        c = bin_stream_str(r[0], base_address=r[1])
        machine = Machine("x86_64")
        loc_db = LocationDB()
        mdis = machine.dis_engine(c, loc_db=loc_db)
        mdis.follow_call = False
        # A root can already be an interior instruction of an earlier root's
        # block. Split there so every source entry has a checked dispatch label.
        mdis.split_dis = set(r[2])
        asmcfg = None
        job_done = set()

        mdis.dont_dis_retcall_funcs = {addr for addr in (raw_spin_unlock,) if addr}

        for t in r[2]:
            if t - r[1] in ordering_bug_list:  # To let buggy blocks first. MIASM bug
                asmcfg = mdis.dis_multiblock(t, asmcfg, job_done)

        for t in r[2]:
            if t - r[1] in ordering_bug_list:
                continue
            asmcfg = mdis.dis_multiblock(t, asmcfg, job_done)

        # mdis.dont_dis_retcall_funcs intentionally stops at endpoint calls.
        # The caller still needs the fall-through block when that same call
        # is nested in a translated critical section, so discover and add
        # those blocks before building the final dispatch table.
        while True:
            cfg_blocks = {}
            cfg_dbs = {}
            for block in asmcfg.blocks:
                label = asmcfg.loc_db.pretty_str(block.loc_key)
                block_start = int(label.split("_")[1], 16)
                cfg_blocks[block_start] = block
                cfg_dbs[block] = asmcfg.loc_db

            continuation_targets = find_resumable_call_continuations(
                cfg_blocks, cfg_dbs, keep_call_stack
            )
            existing_targets = set(cfg_blocks)
            chunk_end = r[1] + len(r[0])
            missing_targets = sorted(
                target
                for target in continuation_targets
                if target not in existing_targets and r[1] <= target < chunk_end
            )
            if not missing_targets:
                break
            for target in missing_targets:
                asmcfg = mdis.dis_multiblock(target, asmcfg, job_done)
        cfgs.append(asmcfg)

    block_dict = {}
    db_dict = {}
    for asmcfg in cfgs:
        for block in asmcfg.blocks:
            label = asmcfg.loc_db.pretty_str(block.loc_key)
            offset = int(label.split("_")[1], 16)
            # A cross-region edge may create a bad placeholder for a block
            # that another region has decoded. Never overwrite the real block.
            if offset in block_dict and block_dict[offset].lines and not block.lines:
                continue
            block_dict[offset] = block
            db_dict[block] = asmcfg.loc_db
    return block_dict, db_dict


# Complete text/CFG expansion and both admission passes before emitting bytes.
# One selected block set drives checking and codegen; waiter-only CALL suffixes
# stay outside this episode, but any alternate live path remains in scope.
def dis_assem(pid, entry, lock_kind="unknown", *, body_witness=False, abi=0):
    diagnostics.begin(pid, entry)
    os.makedirs("./asm", exist_ok=True)

    if lock_kind not in {"spin", "mutex"} or abi not in {0, 1} or (abi == 1 and lock_kind != "spin"):
        diagnostics.set_instruction(entry, "<entry lock kind>")
        return reject_translation("missing or invalid entry lock kind")

    diagnostics.set_instruction(entry, "<context symbol resolution>")
    try:
        control_symbols = context_policy.resolve_control_symbols(get_kernel_symbol)
        context_symbols = context_policy.load_context_symbols(
            read_memory=memread.read_kernel_addr_data,
            percpu_module_bytes=memread.device_session.percpu_module_bytes(),
        )
    except (OSError, ValueError, RuntimeError) as error:
        # Missing visibility is a retryable environment error, not a CS verdict.
        diagnostics.error(
            "CONTEXT_SYMBOLS_UNAVAILABLE", "retry_translation", str(error)
        )
        raise

    resolved_hostcalls = hostcall.resolve_hostcalls(get_kernel_symbol)
    hostcall_targets = set(resolved_hostcalls)
    readonly_targets = hostcall.readonly_waiter_targets(resolved_hostcalls) if abi == 1 else set()
    raw_spin_lock = control_symbols["_raw_spin_lock"]
    raw_spin_unlock = control_symbols["_raw_spin_unlock"]
    mutex_lock = control_symbols["mutex_lock"]
    mutex_unlock = control_symbols["mutex_unlock"]
    clobber_lock = get_kernel_symbol("kd_raw_spin_lock_clobber_v1")
    clobber_unlock = get_kernel_symbol("kd_raw_spin_unlock_clobber_v1")
    if abi == 1 and not (clobber_lock and clobber_unlock):
        return reject_translation("clobber entry symbols unavailable")
    lock_symbols = {
        addr: (kind, name)
        for addr, kind, name in (
            (raw_spin_lock, "spin", "_raw_spin_lock"),
            (raw_spin_unlock, "spin", "_raw_spin_unlock"),
            (clobber_lock, "spin", "kd_raw_spin_lock_clobber_v1"),
            (clobber_unlock, "spin", "kd_raw_spin_unlock_clobber_v1"),
            (mutex_lock, "mutex", "mutex_lock"),
            (mutex_unlock, "mutex", "mutex_unlock"),
        )
    }
    lock_symbols.pop(0, None)
    keep_call_stack = set(lock_symbols) | hostcall_targets
    # Analysis may use only the bound negotiated on this translation's live
    # device lease. New spin/scalar service summaries describe typed sequential
    # effects; they do not claim this mutex runtime stack-comparison capability.
    mutex_stack_bytes = (
        memread.device_session.mutex_stack_bytes() if lock_kind == "mutex" else 0
    )
    jump_table = {}
    diagnostics.set_instruction(entry, "<CFG text coverage>")
    try:
        rets = memread.read(entry, jump_table, excluded_callees=hostcall_targets)
    except (memread.TextReadLimit, memread.device_session.SourceRefused) as error:
        return reject_translation(str(error))

    # Newly fetched branch targets inherit their caller's lock depth. Only
    # originally discovered callees/IJ targets are independent full-scan roots.
    discovered_targets = {target for _, _, targets in rets for target in targets}
    entry_guards = None
    normal.set_current_task_offset(get_percpu_symbol_offset("current_task") or None)
    for expansion in range(33):
        block_dict, db_dict = decode_regions(rets, raw_spin_unlock, keep_call_stack)
        try:
            # Admission and emission must use the same executable scope. A
            # native-only suffix is not a service run on the combiner's context.
            block_dict, db_dict, native_exits = context_policy.jit_phase_blocks(
                block_dict,
                db_dict,
                discovered_targets | {entry},
                keep_call_stack,
            )
        except context_policy.ContextFlowLimit as error:
            diagnostics.set_instruction(error.offset, "<JIT phase scope>")
            return reject_translation(str(error))
        block_dict, boundary_error = context_policy.critical_section_blocks(
            block_dict,
            db_dict,
            entry,
            {raw_spin_lock, clobber_lock, mutex_lock},
            {raw_spin_unlock, clobber_unlock, mutex_unlock},
            discovered_targets,
            native_exits=native_exits,
        )
        if boundary_error:
            offset, reason = boundary_error
            diagnostics.set_instruction(offset, "<critical-section boundary>")
            return reject_translation(reason)
        if entry not in block_dict:
            return reject_translation("entry has no reachable decoded block")

        code_ranges = [(start, start + len(data)) for data, start, _ in rets]
        empty_blocks = {
            offset for offset, block in block_dict.items() if not block.lines
        }
        seeded_regions = []
        added_roots = set()
        for data, start, roots in rets:
            # Another window may discover this edge only after it is expanded.
            # Existing bytes do not imply that this window decoded that target.
            # These are decoder seeds, never new independent admission roots.
            additions = {
                offset
                for offset in empty_blocks
                if start <= offset and offset + 15 <= start + len(data)
            } - set(roots)
            added_roots.update(additions)
            seeded_regions.append((data, start, sorted(set(roots) | additions)))
        if added_roots:
            diagnostics.set_instruction(
                min(added_roots), "<covered undecoded CFG block>"
            )
            if expansion == 32:
                return reject_translation("reachable text exceeds 32 CFG expansions")
            diagnostics.warn(
                "CFG_ROOT_EXTEND",
                "decode_cfg",
                "decode newly reachable targets in existing text windows",
                targets=[hex(target) for target in sorted(added_roots)],
            )
            rets = seeded_regions
            continue
        # A truncated instruction at a read boundary also needs another window.
        missing = {
            offset
            for offset in empty_blocks
            if not any(
                start <= offset and offset + 15 <= end for start, end in code_ranges
            )
        }
        selected = {
            offset: block
            for offset, block in block_dict.items()
            if offset not in missing
        }
        segment_error = find_segment_policy_error(
            selected,
            code_ranges,
            db_dict,
            context_symbols,
            lock_kind,
            lock_symbols,
            roots=(discovered_targets | {entry}) & (block_dict.keys() - missing),
            native_exits=native_exits,
            mutex_stack_bytes=mutex_stack_bytes,
            readonly_targets=readonly_targets,
        )
        if (
            segment_error
            and segment_error[1].startswith("bounded register-address alternatives")
            and not jump_table
            and any(
                line.name.upper() == "CALL"
                and line.args
                and context_policy.static_address(
                    line.args[0], db_dict[block], line.offset + line.l
                )
                in {raw_spin_lock, clobber_lock, mutex_lock}
                for block in selected.values()
                for line in block.lines
            )
        ):
            if missing:
                # This is not admission: complete the selected cold paths and
                # rerun both analyses before collecting/emitting any predicates.
                segment_error = None
                diagnostics.warn(
                    "ENTRY_GUARD_WAIT_TEXT",
                    "complete_cfg",
                    "nested precision retry requires all selected branch text",
                )
            else:
                # Learned direct callees may inherit only real CALL packets
                # reachable from this checked root, never independent inputs.
                # IJ history cannot satisfy that single-entry contract above.
                candidate = context_guards.EntryGuards()
                segment_error = find_segment_policy_error(
                    selected,
                    code_ranges,
                    db_dict,
                    context_symbols,
                    lock_kind,
                    lock_symbols,
                    roots={entry},
                    native_exits=native_exits,
                    guards=candidate,
                    scoped_calls=bool(discovered_targets - {entry}),
                    mutex_stack_bytes=mutex_stack_bytes,
                    entry_spill_guards=abi == 1,
                    readonly_targets=readonly_targets,
                )
                if not segment_error:
                    entry_guards = candidate
                    diagnostics.set_instruction(
                        entry, "<entry disjointness predicates>"
                    )
                    diagnostics.warn(
                        "ENTRY_GUARDED_ADMISSION",
                        "emit_entry_checks",
                        "conditional nested admission; check all premises before body",
                        guards=len(candidate.conditions()),
                        scoped_calls=bool(discovered_targets - {entry}),
                        mutex_stack_bytes=mutex_stack_bytes,
                    )
        if segment_error:
            offset, reason = segment_error
            detail = f"{reason} at 0x{offset:x}" if offset else reason
            return reject_translation(detail)
        if not missing:
            break
        diagnostics.set_instruction(min(missing), "<missing reachable CFG block>")
        if expansion == 32:
            return reject_translation("reachable text exceeds 32 CFG expansions")
        diagnostics.warn(
            "TEXT_RANGE_EXTEND",
            "read_cfg",
            "fetch reachable branch text",
            targets=[hex(target) for target in sorted(missing)],
        )
        try:
            rets = memread.extend_regions(rets, missing)
        except (memread.TextReadLimit, memread.device_session.SourceRefused) as error:
            return reject_translation(str(error))

    # Final emission must also refuse an incomplete return graph when the
    # unconditional admission path did not need a scoped-call comparison.
    try:
        missing_callees = indirect_jump.find(block_dict, db_dict, jump_table)
    except indirect_jump.ReturnFlowError as error:
        diagnostics.set_instruction(error.offset, "<return dispatch>")
        return reject_translation(str(error))
    if abi == 1:
        reason = entry_abi.check_minimal_entry(
            block_dict, db_dict, entry, {clobber_lock, clobber_unlock},
            set(lock_symbols), jump_table,
        )
        if reason:
            return reject_translation(reason)
        if entry_guards is not None and entry_guards.register_dependencies() - {"RSP", "RBP"}:
            return reject_translation("entry guard requires an uncaptured GPR")
    continuation_targets = find_resumable_call_continuations(
        block_dict, db_dict, keep_call_stack
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
            f.write("INC             R11\n")
            f.write("TEST            R11, 0x1000000\n")
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

            f.write(translation.translate(line, offset, db, reg_map, block_end))
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
    Path("./asm/jit.S").write_text(f.getvalue(), encoding="utf-8")

    solve_bug.solve_cond_jmp_lock_cmpxchg("./asm/jit.S")

    build_jit_binary(abi)
    return 0


if __name__ == "__main__":
    import device_session

    pid = int(sys.argv[1])
    entry = int(sys.argv[2], 16)
    lock_kind = sys.argv[3] if len(sys.argv) > 3 else "unknown"
    try:
        body_witness = os.environ.get("KD_JIT_BODY_WITNESS", "0")
        if body_witness not in {"0", "1"}:
            raise ValueError("KD_JIT_BODY_WITNESS must be 0 or 1")
        diagnostics.begin(pid, entry)
        with device_session.session():
            result = dis_assem(pid, entry, lock_kind, body_witness=body_witness == "1",
                               abi=int(sys.argv[4]) if len(sys.argv) > 4 else 0)
        sys.exit(result)
    except Exception as error:
        diagnostics.error(
            "TRANSLATION_FAILED", "raise", f"{type(error).__name__}: {error}"
        )
        raise

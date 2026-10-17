"""Decode source regions and check every block selected for JIT emission.

The coordinator completes source coverage before accepting an admission result;
this module does not read kernel text, publish images, or relax scope checks.
"""

import context_policy
import diagnostics
import instruction_policy
import normal
from miasm.analysis.machine import Machine
from miasm.core.bin_stream import bin_stream_str
from miasm.core.locationdb import LocationDB
from miasm.expression.expression import ExprLoc


def find_undecoded_policy_error(blocks, regions):
    """Screen known state opcodes at selected undecodable CFG roots only."""
    for offset, block in sorted(blocks.items()):
        if block.lines:
            continue
        for data, start, _ in regions:
            if start <= offset < start + len(data):
                raw = data[offset - start:offset - start + 15]
                reason = instruction_policy.encoding_rejection(raw)
                if reason:
                    diagnostics.set_instruction(offset, "<undecoded " + raw.hex() + ">")
                    return offset, reason
    return None


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
                and name in {"mutex_lock", "mutex_unlock", "kd_mutex_lock_clobber_v1", "kd_mutex_unlock_clobber_v1", "kd_mutex_direct_lock_clobber_v1", "kd_mutex_direct_contended_clobber_v1", "kd_mutex_direct_unlock_clobber_v1"}
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

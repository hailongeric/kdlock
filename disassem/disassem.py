# Translation coordinator: leased kernel text -> decoded JIT scope -> admission
# -> register-mapped assembly -> wrapper image. Refusal removes stale artifacts;
# I/O/environment errors are not native-only verdicts. The daemon publishes the
# resulting image; running this CLI alone neither uploads it nor proves JIT ran.
# Decoding/admission and assembly emission live in translation_scope/image;
# helper reexports keep the existing translator API available to its callers.
import os
import subprocess
import sys
from pathlib import Path

from miasm_python314 import verify_runtime

# Dependency failure is an environment error, never an admission refusal.
# Check exact patched bytes before importing/using the semantic lifter.
DEPENDENCY_IDENTITY = verify_runtime()

import context_guards
import budget_resume
import address_guards as checked_addresses
import constant_paths
import context_policy
import diagnostics
import entry_abi
import hostcall
import indirect_jump
import memread
import normal
import native_escape
import origin_instructions
import origin_memory
import returning_calls
import native_terminals
import solve_bug
from miasm.expression.expression import ExprId, ExprMem, ExprLoc
from translation_image import emit_jit_assembly, write_entry_dispatch, wrapper_context_inputs
from translation_scope import (
    decode_regions, find_resumable_call_continuations, find_segment_policy_error,
    find_undecoded_policy_error,
)


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


def build_jit_binary(abi=0, *, context_inputs=None, requirements=0):
    diagnostics.set_instruction(None, "<assemble/objcopy/objdump>")
    include_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "include"
    )
    # Standalone/older callers have no proven requirements and keep both.
    gs, task = (True, True) if context_inputs is None else context_inputs
    run_build_step(
        [
            "gcc",
            f"-I{include_dir}",
            f"-DKD_GENERATED_ENTRY_ABI={abi}",
            f"-DKD_GENERATED_REQUIREMENTS={requirements}",
            f"-DKD_GENERATED_GS_INPUT={int(gs)}",
            f"-DKD_GENERATED_TASK_INPUT={int(task)}",
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


# Complete text/CFG expansion and both admission passes before emitting bytes.
# One selected block set drives checking and codegen; waiter-only CALL suffixes
# stay outside this episode, but any alternate live path remains in scope.
def dis_assem(pid, entry, lock_kind="unknown", *, body_witness=False, abi=0,
              trusted_source=True):
    diagnostics.begin(pid, entry)
    if type(trusted_source) is not bool:
        raise ValueError("trusted_source must be boolean")
    os.makedirs("./asm", exist_ok=True)

    if lock_kind not in {"spin", "mutex"} or abi not in {0, 1, 2, 3} or (abi in {1, 3} and lock_kind != "spin") or (abi == 2 and lock_kind != "mutex"):
        diagnostics.set_instruction(entry, "<entry lock kind>")
        return reject_translation("missing or invalid entry lock kind")

    diagnostics.set_instruction(entry, "<context symbol resolution>")
    try:
        control_symbols = context_policy.resolve_control_symbols(get_kernel_symbol)
        context_symbols = {} if trusted_source else context_policy.load_context_symbols(
            read_memory=memread.read_kernel_addr_data,
            percpu_module_bytes=memread.device_session.percpu_module_bytes(),
        )
    except (OSError, ValueError, RuntimeError) as error:
        # Missing visibility is a retryable environment error, not a CS verdict.
        diagnostics.error(
            "CONTEXT_SYMBOLS_UNAVAILABLE", "retry_translation", str(error)
        )
        raise

    # Only declared scalar services stop ordinary callee decoding. String
    # functions, including macro-expanded copies, use their actual leased text
    # and the same trust policy, stack and return handling as every other callee.
    if trusted_source:
        diagnostics.warn(
            "TRUSTED_SOURCE", "translate_without_safety_analysis",
            "kernel and module instructions are trusted by caller policy; "
            "context/value admission and entry-input proof are bypassed; "
            "compiler clobber-entry inputs are assumed; "
            "source leases, lowering, return routing and lock ownership remain")
    resolved_hostcalls = hostcall.resolve_hostcalls(get_kernel_symbol)
    indirect_call_native = memread.device_session.indirect_call()
    hostcall_targets = set(resolved_hostcalls)
    terminal_targets = set(native_terminals.resolve(get_kernel_symbol))
    returning_services = memread.device_session.service_calls() if abi == 2 else {}
    bound_controls = memread.device_session.rwsem_controls() if abi == 2 else {}
    readonly_targets = hostcall.readonly_waiter_targets(resolved_hostcalls) if abi in {1, 2, 3} else set()
    # The current provider exposes direct protocol entries. Resolve the same
    # identities as its executor, including the clobber unlock completion PC.
    raw_spin_lock = get_kernel_symbol("kd_spin_lock_legacy") or control_symbols["_raw_spin_lock"]
    raw_spin_unlock = get_kernel_symbol("kd_spin_unlock_legacy") or control_symbols["_raw_spin_unlock"]
    mutex_lock = get_kernel_symbol("kd_mutex_local_lock")
    mutex_unlock = get_kernel_symbol("kd_mutex_local_unlock")
    clobber_lock = (get_kernel_symbol("kd_spin_lock_clobber_v1") or
                    get_kernel_symbol("kd_raw_spin_lock_clobber_v1"))
    clobber_unlock = (get_kernel_symbol("kd_spin_unlock_clobber_v1") or
                      get_kernel_symbol("kd_raw_spin_unlock_clobber_v1"))
    pinned_spin_lock = get_kernel_symbol("kd_spin_lock_pinned_clobber_v1")
    cold_spin_unlock = get_kernel_symbol("kd_spin_direct_native_unlock")
    clobber_mutex_lock = 0
    clobber_mutex_unlock = 0
    direct_mutex_lock = get_kernel_symbol("kd_mutex_direct_lock_clobber_v1")
    direct_mutex_unlock = get_kernel_symbol("kd_mutex_direct_unlock_clobber_v1")
    contended_mutex_lock = get_kernel_symbol("kd_mutex_direct_contended_clobber_v1")
    outer_mutex_lock = get_kernel_symbol("kd_mutex_outer_contended_clobber_v1")
    # General retained services keep the source CALL word. The runtime binds
    # each operation to the exact acquisition; these targets must not be
    # decoded as ordinary helpers, including callable local acquisitions.
    service_acquire_names = (
        "kd_mutex_lock_interruptible_clobber_v1",
        "kd_mutex_lock_killable_clobber_v1",
        "kd_rwsem_down_write_clobber_v1",
        "kd_rwsem_down_write_interruptible_clobber_v1",
        "kd_rwsem_down_write_killable_clobber_v1",
        "kd_mutex_api_lock", "kd_mutex_lock_interruptible",
        "kd_mutex_lock_killable", "kd_down_write",
        "kd_down_write_interruptible", "kd_down_write_killable",
    )
    service_release_names = (
        "kd_rwsem_up_write_clobber_v1", "kd_mutex_api_unlock",
        "kd_up_write", "kd_up_read",
    )
    service_continue_names = ("kd_downgrade_write",)
    service_symbols = {
        address: name
        for name in (*service_acquire_names, *service_release_names,
                     *service_continue_names)
        if (address := get_kernel_symbol(name))
    }
    service_symbols.update({address: control['symbol']
                            for address, control in bound_controls.items()})
    service_acquires = {address for address, name in service_symbols.items()
                        if name in service_acquire_names}
    service_acquires.update(address for address, control in bound_controls.items()
                            if control['operation'] in (1, 2, 3))
    # Read release can end a downgraded tail, but may also release an unrelated
    # local read. Only the exact runtime record decides that endpoint; counting
    # it as a lexical writer unlock could cut the outer writer body early.
    service_releases = {address for address, name in service_symbols.items()
                        if name in service_release_names and name != "kd_up_read"}
    service_releases.update(address for address, control in bound_controls.items()
                            if control['operation'] == 5)
    service_clobbers = {address for address, name in service_symbols.items()
                        if name.endswith("_clobber_v1")}
    service_clobbers.update(address for address, control in bound_controls.items()
                            if control['flags'] & 1)
    rwsem_clobber_lock = get_kernel_symbol("kd_rwsem_down_write_clobber_v1")
    rwsem_clobber_unlock = get_kernel_symbol("kd_rwsem_up_write_clobber_v1")
    clobber_targets = ({clobber_lock, clobber_unlock, pinned_spin_lock, clobber_mutex_lock, clobber_mutex_unlock, direct_mutex_lock, contended_mutex_lock, outer_mutex_lock, direct_mutex_unlock} - {0, None}) | service_clobbers
    if ((abi in {1, 3} and not (clobber_lock and clobber_unlock)) or
        (abi == 2 and not ((direct_mutex_lock and direct_mutex_unlock) or
                           (clobber_mutex_lock and clobber_mutex_unlock) or
                           (rwsem_clobber_lock and rwsem_clobber_unlock)))):
        return reject_translation("clobber entry symbols unavailable")
    lock_symbols = {
        addr: (kind, name)
        for addr, kind, name in (
            (raw_spin_lock, "spin", "_raw_spin_lock"),
            (raw_spin_unlock, "spin", "_raw_spin_unlock"),
            (clobber_lock, "spin", "kd_raw_spin_lock_clobber_v1"),
            (clobber_unlock, "spin", "kd_raw_spin_unlock_clobber_v1"),
            (pinned_spin_lock, "spin", "kd_spin_lock_pinned_clobber_v1"),
            (cold_spin_unlock, "spin", "kd_spin_direct_native_unlock"),
            (direct_mutex_lock, "mutex", "kd_mutex_direct_lock_clobber_v1"),
            (contended_mutex_lock, "mutex", "kd_mutex_direct_contended_clobber_v1"),
            (outer_mutex_lock, "mutex", "kd_mutex_outer_contended_clobber_v1"),
            (direct_mutex_unlock, "mutex", "kd_mutex_direct_unlock_clobber_v1"),
            (mutex_lock, "mutex", "kd_mutex_local_lock"),
            (mutex_unlock, "mutex", "kd_mutex_local_unlock"),
            (clobber_mutex_lock, "mutex", "kd_mutex_lock_clobber_v1"),
            (clobber_mutex_unlock, "mutex", "kd_mutex_unlock_clobber_v1"),
        )
    }
    lock_symbols.pop(0, None)
    lock_symbols.pop(None, None)
    # Rwsem write/read-tail services use the ABI2 mutex continuation backend;
    # their distinct admission modes are interpreted by the runtime.
    lock_symbols.update({address: ("mutex", name)
                         for address, name in service_symbols.items()})
    keep_call_stack = set(lock_symbols) | hostcall_targets | set(returning_services)
    # Per-object bridges remain Native boundaries unless the exact terminal
    # outer-unlock metadata proves the selected KD object/class at runtime.
    api_unlock_name = {1: "kd_api_files_unlock_clobber", 2: "kd_api_pipe_unlock_clobber"}.get(abi)
    api_unlock = get_kernel_symbol(api_unlock_name) if api_unlock_name else 0
    terminal_unlock_aliases = ({api_unlock: (clobber_unlock if abi == 1 else direct_mutex_unlock)}
                               if api_unlock else {})
    excluded_targets = keep_call_stack | terminal_targets
    if entry in excluded_targets:
        return reject_translation("entry is a control or Native CALL boundary")
    # Analysis may use only the bound negotiated on this translation's live
    # device lease. New spin/scalar service summaries describe typed sequential
    # effects; they do not claim this mutex runtime stack-comparison capability.
    mutex_stack_bytes = (
        memread.device_session.mutex_stack_bytes() if lock_kind == "mutex" else 0
    )
    root_escape_capable = (lock_kind == "spin" and abi in {1, 3}
                           and memread.device_session.root_native_escape())
    escape_capable = (root_escape_capable or
                      (lock_kind == "mutex" and abi == 2
                       and memread.device_session.native_escape()))
    origin_capable = (lock_kind == "mutex" and abi == 2 and escape_capable
                      and memread.device_session.origin_instruction())
    root_controls = {address: name for address, (_, name) in lock_symbols.items()}
    if root_escape_capable:
        root_controls.update(
            {address: name for name in native_escape.ROOT_CONTROL_SYMBOLS
             if (address := get_kernel_symbol(name))})
    native_terminal_controls = (
        {get_kernel_symbol("kd_rwlock_fast_write_unlock")} - {0}
        if root_escape_capable and abi == 3 else set())
    jump_table = {}
    diagnostics.set_instruction(entry, "<CFG text coverage>")
    try:
        rets = memread.read(entry, jump_table, excluded_callees=excluded_targets)
    except (memread.TextReadLimit, memread.device_session.SourceRefused) as error:
        return reject_translation(str(error))
    # Decoder seeds do not independently authorize execution. Rebuild reachability
    # from the actual entry and its CALL/CFG/history edges on every generation.
    discovered_targets = {target for _, _, targets in rets for target in targets}
    entry_guards = None
    memory_guards = None
    service_queue_required = False
    direct_call_closure = (trusted_source and abi == 2 and lock_kind == "mutex"
                           and bool(returning_services))
    normal.set_current_task_offset(get_percpu_symbol_offset("current_task") or None)
    for expansion in range(33):
        block_dict, db_dict = decode_regions(rets, raw_spin_unlock, keep_call_stack)
        block_dict = {start: block for start, block in block_dict.items()
                      if start not in excluded_targets}
        db_dict = {block: db_dict[block] for block in block_dict.values()}
        if escape_capable:
            native_escape.normalize_decoded(block_dict)
        ordinary_call_targets = {
            db_dict[block].get_location_offset(line.args[0].loc_key)
            for block in block_dict.values() for line in block.lines
            if direct_call_closure and line.name == 'CALL' and line.args
            and isinstance(line.args[0], ExprLoc)
        } - excluded_targets
        try:
            # Admission and emission must use the same executable scope. A
            # native-only suffix is not a service run on the combiner's context.
            block_dict, db_dict, native_exits = context_policy.jit_phase_blocks(
                block_dict,
                db_dict,
                {entry},
                keep_call_stack | ordinary_call_targets,
                indirect_history=jump_table,
                indirect_call_native=indirect_call_native,
                returning_indirect=bool(returning_services),
            )
        except context_policy.ContextFlowLimit as error:
            diagnostics.set_instruction(error.offset, "<JIT phase scope>")
            return reject_translation(str(error))
        # A provider can declare many primitives. Only a reached source CALL
        # in this image requires the returning-service execution contract.
        # Unrelated ordinary images keep their existing publication format.
        if returning_services and any(
                line.name in ('CALL', 'JMP') and
                ((line.name == 'CALL' and not isinstance(line.args[0], ExprLoc)) or
                 isinstance(line.args[0], ExprLoc) and
                 db_dict[block].get_location_offset(line.args[0].loc_key) in returning_services)
                for block in block_dict.values() for line in block.lines):
            service_queue_required = True
        block_dict, boundary_error = context_policy.critical_section_blocks(
            block_dict,
            db_dict,
            entry,
            {raw_spin_lock, clobber_lock, pinned_spin_lock, mutex_lock, clobber_mutex_lock, direct_mutex_lock, contended_mutex_lock, outer_mutex_lock} | service_acquires,
            {raw_spin_unlock, clobber_unlock, cold_spin_unlock, mutex_unlock, clobber_mutex_unlock, direct_mutex_unlock} | service_releases,
            discovered_targets & block_dict.keys(),
            native_exits=native_exits,
            runtime_delimited=service_queue_required,
            retained_candidate=trusted_source and abi == 2 and lock_kind == "mutex",
        )
        if boundary_error and trusted_source and abi == 2 and lock_kind == "mutex":
            # The historical counter is only a lexical boundary. Deep or
            # changing/unknown-depth control flow uses retained owner records,
            # under a contract that the legacy fixed ledger cannot execute.
            service_queue_required = True
            block_dict, boundary_error = context_policy.critical_section_blocks(
                block_dict, db_dict, entry,
                {raw_spin_lock, clobber_lock, pinned_spin_lock, mutex_lock,
                 clobber_mutex_lock, direct_mutex_lock, contended_mutex_lock,
                 outer_mutex_lock} | service_acquires,
                {raw_spin_unlock, clobber_unlock, cold_spin_unlock, mutex_unlock,
                 clobber_mutex_unlock, direct_mutex_unlock} | service_releases,
                discovered_targets & block_dict.keys(), native_exits=native_exits,
                runtime_delimited=True,
            )
        if boundary_error:
            offset, reason = boundary_error
            diagnostics.set_instruction(offset, "<critical-section boundary>")
            return reject_translation(reason)
        if entry not in block_dict:
            return reject_translation("entry has no reachable decoded block")

        for block in block_dict.values():
            for line in block.lines:
                if (indirect_call_native and line.name == "CALL" and line.args and
                    isinstance(line.args[0], (ExprId, ExprMem)) and
                    native_terminals.indirect_call_length(line.b) != line.l):
                    diagnostics.set_instruction(line.offset, line)
                    return reject_translation("indirect CALL encoding lacks an exact native-continuation contract")

        source_has_escapes = escape_capable and any(
            native_escape.descriptor(line)
            for block in block_dict.values() for line in block.lines)
        if root_escape_capable and source_has_escapes:
            # Recheck each expanded original graph before any pruning. ABI3's
            # standard unlock has a native fast-writer branch: only its
            # terminal CALL can leave the image, never a learned helper body
            # or a continuation. No writer-byte value is assumed here.
            scope_error = native_escape.root_scope_rejection(
                block_dict, db_dict, clobber_unlock, root_controls,
                hostcall_targets, learned_indirect=any(
                    line.offset + line.l in jump_table
                    for block in block_dict.values() for line in block.lines),
                native_terminal_controls=native_terminal_controls)
            if scope_error:
                offset, reason = scope_error
                diagnostics.set_instruction(offset, "<root instruction-marker scope>")
                return reject_translation(reason)
        specialized_branches = ()
        if not trusted_source and abi == 1 and not jump_table and not source_has_escapes and any(
                line.name.upper() == "UD2"
                for block in block_dict.values() for line in block.lines):
            # A helper assertion can be impossible for the exact source CALL
            # argument (e.g. strscpy's constant count). Keep feasible traps
            # refused and leave the selected mutex/marker protocol untouched.
            block_dict, db_dict, specialized_branches = constant_paths.specialize(
                block_dict, db_dict, entry, indirect_history=jump_table)
            native_exits &= block_dict.keys()
            if specialized_branches:
                diagnostics.set_instruction(entry, "<proved helper branches>")
                diagnostics.warn("CONSTANT_PATH_SPECIALIZATION", "emit_proved_edges",
                                 "source-defined constants exclude these branch alternatives",
                                 branches=[hex(offset) for offset in specialized_branches])

        encoding_error = (None if trusted_source else
                          find_undecoded_policy_error(block_dict, rets))
        if encoding_error:
            offset, reason = encoding_error
            return reject_translation(f"{reason} at 0x{offset:x}")

        code_ranges = [(start, start + len(data)) for data, start, _ in rets]
        ordinary_call_targets = {
            db_dict[block].get_location_offset(line.args[0].loc_key)
            for block in block_dict.values() for line in block.lines
            if direct_call_closure and line.name == 'CALL' and line.args
            and isinstance(line.args[0], ExprLoc)
        } - excluded_targets
        empty_blocks = {
            offset for offset, block in block_dict.items() if not block.lines
        }
        empty_blocks.update(ordinary_call_targets - block_dict.keys())
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
            discovered_targets.update(added_roots)
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
        segment_error = None if trusted_source else find_segment_policy_error(
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
            native_escapes=escape_capable,
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
                in ({raw_spin_lock, clobber_lock, pinned_spin_lock, mutex_lock,
                     clobber_mutex_lock, direct_mutex_lock, contended_mutex_lock,
                     outer_mutex_lock} | service_acquires | (discovered_targets - {entry}))
                for block in selected.values()
                for line in block.lines
            )
        ):
            if missing:
                # A learned helper needs the same real CALL/RET proof as a
                # nested lock body: independent callee inputs can otherwise
                # destroy a caller spill's identity. This is not admission:
                # complete every selected cold path before collecting checks.
                segment_error = None
                diagnostics.warn(
                    "ENTRY_GUARD_WAIT_TEXT",
                    "complete_cfg",
                    "CALL precision retry requires all selected branch text",
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
                    entry_spill_guards=abi in {1, 2, 3},
                    readonly_targets=readonly_targets,
                    native_escapes=escape_capable,
                )
                if not segment_error:
                    entry_guards = candidate
                    diagnostics.set_instruction(
                        entry, "<entry disjointness predicates>"
                    )
                    diagnostics.warn(
                        "ENTRY_GUARDED_ADMISSION",
                        "emit_entry_checks",
                        "conditional CALL admission; check all premises before body",
                        guards=len(candidate.conditions()),
                        scoped_calls=bool(discovered_targets - {entry}),
                        mutex_stack_bytes=mutex_stack_bytes,
                    )
        # The guard's native continuation still executes original conditionals.
        # A specialized graph could hide a live source-flag read from its proof.
        # Until the original native graph is retained separately, never combine
        # these two admission mechanisms in the same selected image.
        if (segment_error and abi == 1 and not jump_table and not missing
                and not source_has_escapes
                and not specialized_branches
                and segment_error[1].startswith("bounded register-address alternatives")
                and memread.device_session.address_guard()):
            candidate = context_guards.EntryGuards()
            checked = checked_addresses.AddressGuards()
            segment_error = find_segment_policy_error(
                selected, code_ranges, db_dict, context_symbols, lock_kind,
                lock_symbols, roots={entry}, native_exits=native_exits,
                guards=candidate, scoped_calls=bool(discovered_targets - {entry}),
                entry_spill_guards=True, readonly_targets=readonly_targets,
                address_guards=checked,
            )
            if not segment_error:
                try:
                    checked.validate(selected, db_dict, terminal_calls={clobber_unlock},
                                     flag_dead_calls=())
                except context_policy.ContextFlowLimit as error:
                    segment_error = error.offset, str(error)
                else:
                    entry_guards = candidate
                    memory_guards = checked
                    diagnostics.set_instruction(entry, "<checked stack-alias loads>")
                    diagnostics.warn("ADDRESS_GUARDED_ADMISSION", "emit_use_checks",
                                     "check exact source-stack alias exclusions before each load",
                                     sites=len(checked.sites))
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
            discovered_targets.update(missing)
        except (memread.TextReadLimit, memread.device_session.SourceRefused) as error:
            return reject_translation(str(error))

    has_escapes = escape_capable and any(
        native_escape.descriptor(line)
        for block in block_dict.values() for line in block.lines
    )
    root_escapes = root_escape_capable and has_escapes
    if root_escapes:
        if memory_guards is not None and memory_guards.sites:
            return reject_translation(
                "root instruction markers cannot combine address guards")

    # Historical source PCs outside the actual reachable episode cannot create
    # orphan dispatch labels or pull their previously learned descendants back
    # into the image. Keep live targets for the return-graph check below.
    live_offsets = {line.offset + line.l
                    for block in block_dict.values() for line in block.lines}
    jump_table = {source: targets for source, targets in jump_table.items()
                  if source in live_offsets}

    # Final emission must also refuse an incomplete return graph when the
    # unconditional admission path did not need a scoped-call comparison.
    try:
        missing_callees = indirect_jump.find(block_dict, db_dict, jump_table,
                                            terminal_targets=excluded_targets)
    except indirect_jump.ReturnFlowError as error:
        diagnostics.set_instruction(error.offset, "<return dispatch>")
        return reject_translation(str(error))
    if not trusted_source and abi in {1, 2, 3}:
        reason = entry_abi.check_minimal_entry(
            block_dict, db_dict, entry, clobber_targets,
            set(lock_symbols), jump_table, native_escapes=has_escapes,
        )
        if reason:
            return reject_translation(reason)
        if entry_guards is not None and entry_guards.register_dependencies() - {"RSP", "RBP"}:
            return reject_translation("entry guard requires an uncaptured GPR")
    origin_sites = origin_instructions.sites(block_dict) if origin_capable else {}
    if has_escapes:
        # Both admission passes above checked the complete original scope,
        # including every cold branch and the native suffix. Only now remove
        # instructions that this generated invocation can never execute.
        block_dict, db_dict = native_escape.emitted_scope(block_dict, db_dict,
                                                        origin_sites=origin_sites)
        block_dict, db_dict, _ = context_policy.jit_phase_blocks(
            block_dict, db_dict, {entry} & block_dict.keys(),
            keep_call_stack,
            indirect_history=jump_table,
            indirect_call_native=indirect_call_native,
            returning_indirect=bool(returning_services),
        )
        live_offsets = {line.offset + line.l
                        for block in block_dict.values() for line in block.lines}
        jump_table = {source: [target for target in targets
                              if target in block_dict or target in excluded_targets]
                      for source, targets in jump_table.items() if source in live_offsets}
        try:
            missing_callees = indirect_jump.find(block_dict, db_dict, jump_table,
                                                terminal_targets=excluded_targets)
        except indirect_jump.ReturnFlowError as error:
            diagnostics.set_instruction(error.offset, "<native escape return dispatch>")
            return reject_translation(str(error))
    # A prior nonservice marker may have cut a later service on this branch.
    emitted_pcs = {line.offset for block in block_dict.values() for line in block.lines}
    origin_sites = {ip:site for ip,site in origin_sites.items()
                    if ip in emitted_pcs and ip + site[0].l in emitted_pcs}
    memory_sites = (origin_memory.sites(block_dict,
                    reads=memread.device_session.origin_context_read())
                    if lock_kind == "mutex" and abi == 2
                    and memread.device_session.origin_memory() else {})
    memory_preempt_symbol = None
    if any(origin_memory.read_operands(line) for line, _, _ in memory_sites.values()):
        memory_preempt_symbol = get_kernel_symbol("__preempt_count")
        if not memory_preempt_symbol:
            raise RuntimeError("source preemption symbol unavailable for GS read guards")
    if memory_sites:
        service_queue_required = True
    if service_queue_required and (has_escapes or root_escapes or origin_sites):
        return reject_translation("retained-service scope needs unsupported instruction services")
    budget_resume_enabled = (abi == 2 and lock_kind == "mutex"
                             and not has_escapes and not root_escapes
                             and not origin_sites)
    has_returning_call = bool(returning_services) and any(
        line.name in ('CALL', 'JMP') and
        ((line.name == 'CALL' and not isinstance(line.args[0], ExprLoc)) or
         isinstance(line.args[0], ExprLoc) and
         db_dict[block].get_location_offset(line.args[0].loc_key) in returning_services)
        for block in block_dict.values() for line in block.lines)
    returning_targets = {
        line.offset + line.l
        for block in block_dict.values() for line in block.lines
        if line.name == 'CALL' and has_returning_call
        and line.offset + line.l in emitted_pcs
    }
    assembly = emit_jit_assembly(
        entry, block_dict, db_dict, jump_table, missing_callees,
        resolved_hostcalls, keep_call_stack,
        entry_guards=entry_guards, body_witness=body_witness,
        terminal_clobber_unlocks=({clobber_unlock} if abi in {1, 3} else
                                 ({direct_mutex_unlock or clobber_mutex_unlock,
                                   rwsem_clobber_unlock} - {0, None}) if abi == 2 else set()) | set(terminal_unlock_aliases),
        terminal_unlock_aliases=terminal_unlock_aliases,
        indirect_call_native=indirect_call_native,
        native_escapes=has_escapes,
        root_native_escape=root_escapes,
        address_guards=memory_guards,
        trusted_source=trusted_source,
        origin_sites=origin_sites,
        memory_sites=memory_sites,
        memory_preempt_symbol=memory_preempt_symbol,
        budget_resume_enabled=budget_resume_enabled,
        returning_targets=returning_targets,
        returning_services=returning_services,
    )
    Path("./asm/jit.S").write_text(assembly, encoding="utf-8")

    solve_bug.solve_cond_jmp_lock_cmpxchg("./asm/jit.S")

    build_jit_binary(abi, context_inputs=wrapper_context_inputs(
        Path('./asm/jit.S').read_text(encoding='utf-8')),
        requirements=((native_escape.REQUIREMENT if has_escapes else 0)
                      | (native_escape.ROOT_REQUIREMENT if root_escapes else 0)
                      | (origin_instructions.REQUIREMENT if origin_sites else 0)
                      | (origin_memory.REQUIREMENT if memory_sites else 0)
                      | (origin_memory.READ_REQUIREMENT if memory_preempt_symbol is not None else 0)
                      | (checked_addresses.REQUIREMENT if memory_guards is not None
                         and memory_guards.sites else 0)
                      | (budget_resume.REQUIREMENT if budget_resume_enabled else 0)
                      | (context_policy.SERVICE_QUEUE_REQUIREMENT
                         if service_queue_required else 0)
                      | (returning_calls.REQUIREMENT if returning_targets or memory_sites else 0)))
    return 0


if __name__ == "__main__":
    import json
    print('[KD_DEPENDENCY] ' + json.dumps(DEPENDENCY_IDENTITY, sort_keys=True),
          file=sys.stderr, flush=True)
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

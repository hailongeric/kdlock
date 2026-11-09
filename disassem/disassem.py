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

try:
    import compiler_manifest
except Exception:
    compiler_manifest = None

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
import kernel_symbols
import memread
import normal
from object_image import require_complete_object
import native_escape
import origin_instructions
import origin_memory
import returning_calls
import native_terminals
import solve_bug
import source_frontier
from miasm.expression.expression import ExprId, ExprMem, ExprLoc
from translation_image import emit_jit_assembly, write_entry_dispatch, wrapper_context_inputs
from translation_scope import (
    decode_regions, find_resumable_call_continuations, find_segment_policy_error,
    find_undecoded_policy_error, find_direct_call_targets,
)


def _compiler_observe(action, *args, **kwargs):
    try:
        if compiler_manifest is not None:
            getattr(compiler_manifest, action)(*args, **kwargs)
    except Exception:
        pass


def get_kernel_symbol(name, default=0):
    cache = kernel_symbols.current()
    if cache is not None:
        try:
            memread.device_session.require()
        except RuntimeError:
            # Direct Python callers and substituted-text fixtures may have no
            # validated lease. Keep their original lookup boundary unchanged.
            pass
        else:
            return cache.lookup(name, default, opener=open, live=_get_kernel_symbol_live)
    return _get_kernel_symbol_live(name, default)


def _get_kernel_symbol_live(name, default=0):
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


def report_text_coverage(regions, blocks, *, expansion, pending_targets,
                         cfg_work=None, pending_kind="none"):
    """Separate source-cache storage from the selected decoded byte union."""
    ranges = [(start, start + len(data)) for data, start, _ in regions]
    instructions = {
        (line.offset, line.offset + line.l)
        for block in blocks.values() for line in block.lines
        if line.l > 0 and len(bytes(line.b)) == line.l and
        any(start <= line.offset and line.offset + line.l <= end
            for start, end in ranges)
    }
    cached = memread.union_bytes(ranges)
    decoded = memread.union_bytes(instructions)
    diagnostics.warn(
        "DECODED_TEXT_COVERAGE", "record_text_bytes",
        "decoded instruction coverage is not the source-cache budget",
        expansion=expansion, decode_pass=expansion + 1, cached_bytes=cached,
        decoded_instruction_bytes=decoded, decoded_instructions=len(instructions),
        cache_outside_selected_instructions=cached - decoded,
        blocks=len(blocks), incomplete_blocks=sum(not block.lines for block in blocks.values()),
        pending_targets=pending_targets, pending_targets_kind=pending_kind,
        **(cfg_work or {}),
    )


def run_build_step(command, **kwargs):
    try:
        return subprocess.run(command, check=True, **kwargs)
    except (OSError, subprocess.CalledProcessError) as error:
        diagnostics.error("BUILD_FAILED", "raise", str(error), command=command)
        raise


def build_jit_binary(abi=0, *, context_inputs=None, requirements=0):
    diagnostics.set_instruction(None, "<assemble/objcopy/objdump>")
    for name in ("jit.bin", "bin.txt"):
        Path("asm", name).unlink(missing_ok=True)
    include_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "include"
    )
    # Standalone/older callers have no proven requirements and keep both.
    gs, task = (True, True) if context_inputs is None else context_inputs
    _compiler_observe('capture_assembly', './asm/jit.S')
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
    try:
        require_complete_object("./asm/jit.o")
    except ValueError as error:
        diagnostics.error("IMAGE_RELOCATION_PENDING", "raise", str(error))
        raise
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
@kernel_symbols.translation_scope()
def dis_assem(pid, entry, lock_kind="unknown", *, body_witness=False, abi=0,
              trusted_source=True, direct_call_depth=5):
    diagnostics.begin(pid, entry)
    if type(trusted_source) is not bool:
        raise ValueError("trusted_source must be boolean")
    if type(direct_call_depth) is not int or not 0 <= direct_call_depth <= 32:
        raise ValueError("direct CALL depth must be between zero and 32")
    if not (trusted_source and lock_kind == 'mutex' and abi == 2):
        direct_call_depth = 0
    os.makedirs("./asm", exist_ok=True)
    _compiler_observe('capture', 'translation', pid=pid, entry=entry,
                      lock_kind=lock_kind, entry_abi=abi,
                      trusted_source=trusted_source,
                      direct_call_depth=direct_call_depth,
                      body_witness=body_witness)
    if abi != 2:
        _compiler_observe('capture', 'service_table', mode='not_read', reason='entry_abi')
        _compiler_observe('capture', 'controls', mode='not_read')

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
    indirect_tail_capable = (abi == 2 and lock_kind == "mutex" and
                             memread.device_session.indirect_tail())
    hostcall_targets = set(resolved_hostcalls)
    terminal_targets = set(native_terminals.resolve(get_kernel_symbol))
    returning_services = memread.device_session.service_calls() if abi == 2 else {}
    nonreturning_targets = {address for address, descriptor in returning_services.items()
                           if descriptor['context_kind'] == 11}
    try:
        bound_controls = memread.device_session.runtime_rwsem_controls(
            memread.device_session.rwsem_controls(), returning_services) if abi == 2 else {}
    except ValueError as error:
        return reject_translation(str(error))
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
    # A translated ABI2 unit ends at every physical release, regardless of
    # which owner it releases. The typed proxied downgrade is the narrow
    # exception: runtime changes logical mode while retaining that exact
    # writer gate, then resumes the real post-CALL continuation. Its matching
    # read unlock remains a release boundary. No source wrapper is skipped.
    # Legacy spin/rwlock images retain their existing boundary/refusal policy.
    unit_releases = set()
    proxy_downgrade_targets = set()
    terminal_clobber_targets = {direct_mutex_unlock or clobber_mutex_unlock,
                               rwsem_clobber_unlock} - {0, None}
    if abi == 2 and lock_kind == "mutex":
        unit_releases = ({raw_spin_unlock, clobber_unlock, cold_spin_unlock,
                          mutex_unlock, clobber_mutex_unlock, direct_mutex_unlock,
                          rwsem_clobber_unlock} - {0, None}) | set(terminal_unlock_aliases)
        unit_releases.update(address for address, name in service_symbols.items()
                             if name in service_release_names)
        unit_releases.update(address for address, control in bound_controls.items()
                             if control['operation'] in (5, 11, 13))
        unit_releases.update(address for address, descriptor in returning_services.items()
                             if descriptor['context_kind'] in (6, 8, 13))
        proxy_downgrade_targets = {
            address for address, name in service_symbols.items()
            if name in service_continue_names
        } | {address for address, control in bound_controls.items()
             if control['operation'] == 6}
    # Original bounded images learn ordinary CALL/IJ targets from actual
    # executions. Returning services do not require eager callee closure.
    direct_call_closure = False
    # One immutable policy covers initial history roots and every cold edge.
    # Ordinary translation paths retain their established page-aligned window.
    text_policy = (memread.RETAINED_WINDOW_POLICY if direct_call_closure else
                   memread.DEFAULT_WINDOW_POLICY)
    return_flow_work = (entry_abi.RETAINED_RETURN_FLOW_WORK if direct_call_closure
                        else entry_abi.RETURN_FLOW_WORK)
    jump_table = {}

    def has_proxy_downgrade(blocks, databases):
        return bool(proxy_downgrade_targets) and any(
            line.name in {'CALL', 'JMP'} and line.args and
            (context_policy.static_address(line.args[0], databases[block],
                                           line.offset + line.l) in proxy_downgrade_targets
             or set(jump_table.get(line.offset + line.l, ())) & proxy_downgrade_targets)
            for block in blocks.values() for line in block.lines)

    diagnostics.set_instruction(entry, "<CFG text coverage>")
    try:
        rets = memread.read(entry, jump_table, excluded_callees=excluded_targets,
                            policy=text_policy)
    except (memread.TextReadLimit, memread.device_session.SourceRefused) as error:
        return reject_translation(str(error))
    # Decoder seeds do not independently authorize execution. Rebuild reachability
    # from the actual entry and its CALL/CFG/history edges on every generation.
    discovered_targets = {target for _, _, targets in rets for target in targets}
    call_roots = set(discovered_targets) | {entry}
    diagnostics.warn('DIRECT_CALL_DEPTH', 'decode_callees',
        'ordinary direct CALL lookahead retains the original window and work limits',
        call_depth=direct_call_depth, root_depth=0, reached_seeds=len(call_roots))
    entry_guards = None
    memory_guards = None
    service_queue_required = False
    release_queue_required = False
    covered_rebuilds = source_extensions = 0
    decode_pass_limit = 65 if direct_call_closure else 33

    def cfg_work():
        return dict(
            retained_profile=direct_call_closure,
            covered_rebuilds=covered_rebuilds,
            source_extensions=source_extensions,
            covered_rebuild_limit=32, source_extension_limit=32,
            total_transition_limit=64 if direct_call_closure else 32,
            decode_pass_limit=decode_pass_limit,
        )

    def cfg_work_exhausted(kind):
        if not direct_call_closure:
            return covered_rebuilds + source_extensions >= 32
        return (covered_rebuilds if kind == "covered" else source_extensions) >= 32

    def refuse_cfg_work(kind, pending):
        # A covered seed count is not the full missing-source frontier. Keep
        # the work class explicit rather than reporting it as all pending CFG.
        report_text_coverage(rets, block_dict, expansion=expansion,
                             pending_targets=pending, pending_kind=kind,
                             cfg_work=cfg_work())
        diagnostics.warn(
            "CFG_WORK_LIMIT", "reject_incomplete_cfg",
            "bounded CFG work ended before complete source coverage",
            work_kind=kind,
            exhausted_budget=kind if direct_call_closure else "combined",
            decode_pass=expansion + 1, **cfg_work(),
        )
        detail = ("reachable text exceeds 32 CFG expansions"
                  if not direct_call_closure else
                  "reachable text exceeds 32 covered-root CFG rebuilds"
                  if kind == "covered" else
                  "reachable text exceeds 32 source-window CFG extensions")
        return reject_translation(detail)

    normal.set_current_task_offset(get_percpu_symbol_offset("current_task") or None)
    for expansion in range(decode_pass_limit):
        block_dict, db_dict = decode_regions(rets, raw_spin_unlock, keep_call_stack,
            source_frontiers=(trusted_source and abi == 2 and lock_kind == 'mutex'
                              and memread.device_session.source_frontier()),
            frontier_extensions=(trusted_source and abi == 2 and lock_kind == 'mutex'
                                 and memread.device_session.source_frontier_extensions()),
            frontier_controls=(trusted_source and abi == 2 and lock_kind == 'mutex'
                               and memread.device_session.source_frontier_controls()),
            frontier_direction=(trusted_source and abi == 2 and lock_kind == 'mutex'
                                and memread.device_session.source_frontier_direction()),
            unit_releases=unit_releases)
        block_dict = {start: block for start, block in block_dict.items()
                      if start not in excluded_targets}
        db_dict = {block: db_dict[block] for block in block_dict.values()}
        if escape_capable:
            native_escape.normalize_decoded(block_dict)
        # These constants only keep candidate return edges until the release
        # scope is clipped below. No callee bytes are discovered/read here.
        ordinary_call_targets = {
            db_dict[block].get_location_offset(line.args[0].loc_key)
            for block in block_dict.values() for line in block.lines
            if direct_call_depth and line.name == 'CALL' and line.args
            and isinstance(line.args[0], ExprLoc)
        } - excluded_targets
        try:
            # Source planning keeps the original conservative CALL-return
            # exploration, independently of the strict graph used for emission.
            # It may read caller bytes which the final release unit excludes.
            if unit_releases:
                discovery_blocks, discovery_dbs, _ = context_policy.jit_phase_blocks(
                    block_dict, db_dict, {entry}, keep_call_stack | ordinary_call_targets,
                    indirect_history=jump_table, indirect_call_native=indirect_call_native,
                    returning_indirect=bool(returning_services),
                    nonreturning_targets=nonreturning_targets,
                    unit_releases=unit_releases, deferred_call_targets=ordinary_call_targets,
                    max_visits=return_flow_work, discovery_only=True)
            old_fast_sites = set()
            if unit_releases:
                # Preserve only the fast exits which the old scope/emitter
                # already selected. An inner release newly made terminal by
                # unit clipping must not acquire this compatibility exemption.
                old_blocks, old_dbs, old_exits = context_policy.jit_phase_blocks(
                    block_dict, db_dict, {entry}, keep_call_stack | ordinary_call_targets,
                    indirect_history=jump_table, indirect_call_native=indirect_call_native,
                    returning_indirect=bool(returning_services),
                    nonreturning_targets=nonreturning_targets)
                old_services = service_queue_required or has_proxy_downgrade(
                    old_blocks, old_dbs) or any(
                    source_frontier.descriptor(line) or
                    indirect_tail_capable and returning_services and line.name == 'JMP'
                    and line.args and isinstance(line.args[0], (ExprId, ExprMem))
                    and native_terminals.indirect_tail_length(line.b) == line.l or
                    returning_services and (line.name == 'CALL' or line.name.startswith('J'))
                    and ((line.name == 'CALL' and not isinstance(line.args[0], ExprLoc))
                         or isinstance(line.args[0], ExprLoc) and
                         old_dbs[block].get_location_offset(line.args[0].loc_key)
                            in returning_services)
                    for block in old_blocks.values() for line in block.lines)
                if not old_services:
                    old_fast_sites = context_policy.terminal_clobber_sites(
                        old_blocks, old_dbs, entry,
                        {raw_spin_lock, clobber_lock, pinned_spin_lock, mutex_lock,
                         clobber_mutex_lock, direct_mutex_lock, contended_mutex_lock,
                         outer_mutex_lock} | service_acquires,
                        {raw_spin_unlock, clobber_unlock, cold_spin_unlock, mutex_unlock,
                         clobber_mutex_unlock, direct_mutex_unlock} | service_releases,
                        discovered_targets & old_blocks.keys(), terminal_clobber_targets,
                        native_exits=old_exits,
                        retained_candidate=trusted_source and abi == 2 and lock_kind == 'mutex',
                        nonreturning_targets=nonreturning_targets)
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
                nonreturning_targets=nonreturning_targets,
                unit_releases=unit_releases, deferred_call_targets=ordinary_call_targets,
                max_visits=return_flow_work,
            )
            release_queue_required = bool(unit_releases) and any(
                line.name in {'CALL', 'JMP'} and line.args
                and (context_policy.static_address(line.args[0], db_dict[block],
                                                    line.offset + line.l) in unit_releases
                     or set(jump_table.get(line.offset + line.l, ())) & unit_releases)
                and line.offset not in old_fast_sites
                for block in block_dict.values() for line in block.lines)
            # A logical-read/physical-write owner needs the retained runtime
            # even when an earlier cold edge omits its final read unlock.
            if has_proxy_downgrade(block_dict, db_dict):
                service_queue_required = True
        except context_policy.ContextFlowLimit as error:
            diagnostics.set_instruction(error.offset, "<JIT phase scope>")
            return reject_translation(str(error))
        # A provider can declare many primitives. Only a reached source CALL
        # in this image requires the returning-service execution contract.
        # Unrelated ordinary images keep their existing publication format.
        if any(source_frontier.descriptor(line)
               for block in block_dict.values() for line in block.lines):
            service_queue_required = True
        if returning_services and any(
                (line.name == 'CALL' or line.name.startswith('J')) and
                ((line.name == 'CALL' and not isinstance(line.args[0], ExprLoc)) or
                 isinstance(line.args[0], ExprLoc) and
                 db_dict[block].get_location_offset(line.args[0].loc_key) in returning_services)
                for block in block_dict.values() for line in block.lines):
            service_queue_required = True
        if indirect_tail_capable and returning_services and any(
                line.name == 'JMP' and line.args and
                isinstance(line.args[0], (ExprId, ExprMem)) and
                native_terminals.indirect_tail_length(line.b) == line.l
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
            nonreturning_targets=nonreturning_targets,
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
                nonreturning_targets=nonreturning_targets,
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
        ordinary_call_targets = find_direct_call_targets(
            block_dict, db_dict, call_roots, direct_call_depth, excluded_targets)
        # Keep the emitted scope release-clipped at the CALL-depth frontier.
        # Separate planning below may read additional caller bytes, but cannot
        # authorize those instructions or return targets for code generation.
        block_dict, db_dict, native_exits = context_policy.jit_phase_blocks(
            block_dict, db_dict, {entry}, keep_call_stack | ordinary_call_targets,
            indirect_history=jump_table, indirect_call_native=indirect_call_native,
            returning_indirect=bool(returning_services),
            nonreturning_targets=nonreturning_targets,
            unit_releases=unit_releases, deferred_call_targets=ordinary_call_targets,
            max_visits=return_flow_work)
        ordinary_call_targets = find_direct_call_targets(
            block_dict, db_dict, call_roots, direct_call_depth, excluded_targets)
        empty_blocks = {
            offset for offset, block in block_dict.items() if not block.lines
        }
        empty_blocks.update(ordinary_call_targets - block_dict.keys())
        frontier_blocks, frontier_call_targets = block_dict, ordinary_call_targets
        if unit_releases:
            discovery_targets = find_direct_call_targets(
                discovery_blocks, discovery_dbs, call_roots, direct_call_depth,
                excluded_targets)
            # Apply the same CALL-depth boundary to planning, but do not wait
            # for a callee RET proof before batching its caller continuation.
            discovery_blocks, discovery_dbs, _ = context_policy.jit_phase_blocks(
                discovery_blocks, discovery_dbs, {entry},
                keep_call_stack | discovery_targets,
                indirect_history=jump_table, indirect_call_native=indirect_call_native,
                returning_indirect=bool(returning_services),
                nonreturning_targets=nonreturning_targets,
                unit_releases=unit_releases, deferred_call_targets=discovery_targets,
                max_visits=return_flow_work, discovery_only=True)
            frontier_blocks = discovery_blocks
            frontier_call_targets = find_direct_call_targets(
                discovery_blocks, discovery_dbs, call_roots, direct_call_depth,
                excluded_targets)
        frontier_empty = {
            offset for offset, block in frontier_blocks.items() if not block.lines
        }
        frontier_empty.update(frontier_call_targets - frontier_blocks.keys())
        seeded_regions = []
        added_roots = set()
        for data, start, roots in rets:
            # Another window may discover this edge only after it is expanded.
            # Existing bytes do not imply that this window decoded that target.
            # These are decoder seeds, never new independent admission roots.
            additions = {
                offset
                for offset in frontier_empty
                if start <= offset and offset + 15 <= start + len(data)
            } - set(roots)
            added_roots.update(additions)
            seeded_regions.append((data, start, sorted(set(roots) | additions)))
        if added_roots:
            # Decoder seeds can be ordinary branches with the caller's lock
            # depth. Only actual CALL entries add independent callee scans;
            # preserve the conservative policy of the initial history roots.
            discovered_targets.update(added_roots & frontier_call_targets)
            diagnostics.set_instruction(
                min(added_roots), "<covered undecoded CFG block>"
            )
            if cfg_work_exhausted("covered"):
                return refuse_cfg_work("covered", len(added_roots))
            diagnostics.warn(
                "CFG_ROOT_EXTEND",
                "decode_cfg",
                "decode newly reachable targets in existing text windows",
                targets=[hex(target) for target in sorted(added_roots)],
                decode_pass=expansion + 1, next_covered_rebuild=covered_rebuilds + 1,
                **cfg_work(),
            )
            rets = seeded_regions
            covered_rebuilds += 1
            continue
        # A truncated instruction at a read boundary also needs another window.
        missing = {
            offset
            for offset in frontier_empty
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
            if empty_blocks:
                diagnostics.set_instruction(min(empty_blocks), "<undecodable CFG block>")
                report_text_coverage(rets, block_dict, expansion=expansion,
                                     pending_targets=len(empty_blocks), pending_kind="decode",
                                     cfg_work=cfg_work())
                return reject_translation("reachable CFG contains an undecodable block")
            report_text_coverage(rets, block_dict, expansion=expansion, pending_targets=0,
                                 cfg_work=cfg_work())
            break
        diagnostics.set_instruction(min(missing), "<missing reachable CFG block>")
        if cfg_work_exhausted("source"):
            return refuse_cfg_work("source", len(missing))
        diagnostics.warn(
            "TEXT_RANGE_EXTEND",
            "read_cfg",
            "fetch reachable branch text",
            targets=[hex(target) for target in sorted(missing)],
            decode_pass=expansion + 1, next_source_extension=source_extensions + 1,
            **cfg_work(),
        )
        try:
            rets = memread.extend_regions(rets, missing, policy=text_policy)
            discovered_targets.update(missing & frontier_call_targets)
            source_extensions += 1
        except (memread.TextReadLimit, memread.device_session.SourceRefused) as error:
            report_text_coverage(rets, block_dict, expansion=expansion,
                                 pending_targets=len(missing), pending_kind="source",
                                 cfg_work=cfg_work())
            return reject_translation(str(error))
    else:
        # No incomplete graph can reach emission even if progress accounting
        # changes later. Successful closure must take the explicit break above.
        return reject_translation("reachable text exceeds bounded CFG decode passes")

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
    diagnostics.warn(
        "RETURN_FLOW_WORK_PROFILE", "check_complete_return_graph",
        "finite retained graph headroom preserves the complete return proof",
        retained_profile=direct_call_closure, work_limit=return_flow_work,
    )
    try:
        missing_callees = indirect_jump.find(block_dict, db_dict, jump_table,
                                            terminal_targets=excluded_targets,
                                            max_visits=return_flow_work)
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
            nonreturning_targets=nonreturning_targets,
            unit_releases=unit_releases, deferred_call_targets=ordinary_call_targets,
            max_visits=return_flow_work,
        )
        live_offsets = {line.offset + line.l
                        for block in block_dict.values() for line in block.lines}
        jump_table = {source: [target for target in targets
                              if target in block_dict or target in excluded_targets]
                      for source, targets in jump_table.items() if source in live_offsets}
        try:
            missing_callees = indirect_jump.find(block_dict, db_dict, jump_table,
                                                terminal_targets=excluded_targets,
                                                max_visits=return_flow_work)
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
    service_queue_required = service_queue_required or release_queue_required
    memory_preempt_symbol = None
    if any(origin_memory.read_operands(line) for line, _, _ in memory_sites.values()):
        memory_preempt_symbol = get_kernel_symbol("__preempt_count")
        if not memory_preempt_symbol:
            raise RuntimeError("source preemption symbol unavailable for GS read guards")
    if memory_sites:
        service_queue_required = True
    if service_queue_required and (has_escapes or root_escapes or origin_sites):
        terminal_sites = {line.offset: line for block in block_dict.values()
                          for line in block.lines if native_escape.descriptor(line)}
        if terminal_sites:
            first = terminal_sites[min(terminal_sites)]
            diagnostics.set_instruction(first.offset, first)
        diagnostics.warn('RETAINED_TERMINAL_SITES', 'report_source_boundaries',
            'selected instruction sites at the retained compatibility boundary',
            has_escapes=has_escapes, root_escapes=root_escapes,
            origin_sites=[hex(ip) for ip in sorted(origin_sites)[:64]],
            site_count=len(terminal_sites), sites=[
                dict(ip=hex(ip), name=line.name, opcode=bytes(line.b).hex())
                for ip, line in sorted(terminal_sites.items())[:64]])
        return reject_translation("retained-service scope needs unsupported instruction services")
    budget_resume_enabled = (abi == 2 and lock_kind == "mutex"
                             and not has_escapes and not root_escapes
                             and not origin_sites)
    indirect_tails = {
        line.offset + line.l: line.offset
        for block in block_dict.values() for line in block.lines
        if indirect_tail_capable and returning_services and line.name == 'JMP' and
        line.args and isinstance(line.args[0], (ExprId, ExprMem)) and
        native_terminals.indirect_tail_length(line.b) == line.l
    }
    has_returning_call = bool(indirect_tails) or bool(returning_services) and any(
        (line.name == 'CALL' or line.name.startswith('J')) and
        ((line.name == 'CALL' and not isinstance(line.args[0], ExprLoc)) or
         isinstance(line.args[0], ExprLoc) and
         db_dict[block].get_location_offset(line.args[0].loc_key) in returning_services)
        for block in block_dict.values() for line in block.lines)
    returning_targets = {
        line.offset + line.l
        for block in block_dict.values() for line in block.lines
        if line.name == 'CALL' and has_returning_call
        and line.offset + line.l in emitted_pcs
        and (not line.args or not isinstance(line.args[0], ExprLoc) or
             db_dict[block].get_location_offset(line.args[0].loc_key) not in nonreturning_targets)
    }
    # ABI2 selects the flags-complete handback contract even for a cold image
    # which stops at its first ordinary callee before any service is reached.
    retained_misses = (abi == 2 and lock_kind == "mutex" and not has_escapes
                       and not root_escapes and not origin_sites)
    has_frontiers = any(source_frontier.descriptor(line)
        for block in block_dict.values() for line in block.lines)
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
        retained_misses=retained_misses,
        returning_targets=returning_targets,
        returning_services=returning_services,
        nonreturning_targets=nonreturning_targets,
        indirect_tails=indirect_tails,
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
                      | (returning_calls.REQUIREMENT
                         if returning_targets or memory_sites or indirect_tails else 0)
                      | (indirect_jump.RETAINED_TAIL_REQUIREMENT if indirect_tails else 0)
                      | (indirect_jump.RETAINED_MISS_REQUIREMENT
                         if retained_misses else 0)
                      | (source_frontier.REQUIREMENT if has_frontiers else 0)))
    _compiler_observe('complete', './asm/jit.bin', DEPENDENCY_IDENTITY)
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

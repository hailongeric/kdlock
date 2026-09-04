import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import assist
import conflict
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


def find_segment_policy_error(block_dict, code_ranges=None):
    saw_gs = False
    for block_start, block in sorted(block_dict.items()):
        if code_ranges and not any(
            start <= block_start < end for start, end in code_ranges
        ):
            continue
        if not getattr(block, "lines", None):
            return block_start, "undecodable or empty basic block"
        offset = block_start
        for line in block.lines:
            for arg in line.args:
                segment, _ = normal.segment_operand(arg)
                saw_gs = saw_gs or segment == "GS"
            reason = normal.segment_policy_error(line)
            if reason:
                return offset, reason
            offset += line.l
    if saw_gs and normal.current_task_offset is None:
        return 0, "current_task per-CPU offset is unavailable"
    return None


def write_unsupported_jit(reason):
    with open("./asm/jit.S", "w") as f:
        f.write(f"/* KD_UNSUPPORTED: {reason} */\n")
        f.write("MOV     R14, PT_RIP\n")
        f.write("MOV     Stack_INST_CNT, 0\n")
        f.write("MOV     Stack_IJ, 0x3\n")
        f.write("JMP     exit\n")


def build_jit_binary():
    include_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "include"
    )
    subprocess.run(
        [
            "gcc",
            f"-I{include_dir}",
            "-I./asm/",
            "-c",
            "-fPIC",
            f"{include_dir}/wrapper.S",
            "-o",
            "./asm/jit.o",
        ],
        check=True,
    )
    subprocess.run(
        ["objcopy", "--remove-section", ".note.gnu.property", "./asm/jit.o"],
        check=True,
    )
    subprocess.run(
        ["objcopy", "-O", "binary", "./asm/jit.o", "./asm/jit.bin"], check=True
    )
    with open("./asm/bin.txt", "w", encoding="ascii") as output:
        subprocess.run(
            [
                "objdump",
                "-b",
                "binary",
                "-m",
                "i386:x86-64:intel",
                "-D",
                "./asm/jit.bin",
            ],
            check=True,
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


def dis_assem(pid, entry):
    os.makedirs("./asm", exist_ok=True)

    resolved_hostcalls = hostcall.resolve_hostcalls(get_kernel_symbol)
    hostcall_targets = set(resolved_hostcalls)

    jump_table = {}
    rets = memread.read(entry, jump_table, excluded_callees=hostcall_targets)
    cfgs = []
    raw_spin_lock = get_kernel_symbol("_raw_spin_lock", 0xFFFFFFFF81E90A20)
    raw_spin_unlock = get_kernel_symbol("_raw_spin_unlock", 0xFFFFFFFF81E90B30)
    mutex_lock = get_kernel_symbol("mutex_lock", 0xFFFFFFFF81E8B570)
    mutex_unlock = get_kernel_symbol("mutex_unlock", 0xFFFFFFFF81E8A040)
    control_call_targets = {
        addr
        for addr in (
            raw_spin_lock,
            raw_spin_unlock,
            mutex_lock,
            mutex_unlock,
        )
        if addr
    }
    keep_call_stack = control_call_targets | hostcall_targets

    ordering_bug_list = [0x2CE40, 0x2CE50, 0x4FFD0, 0x738D0, 0x67B0]

    for r in rets:
        c = bin_stream_str(r[0], base_address=r[1])
        machine = Machine("x86_64")
        loc_db = LocationDB()
        mdis = machine.dis_engine(c, loc_db=loc_db)
        mdis.follow_call = False
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
            block_dict[offset] = block
            db_dict[block] = asmcfg.loc_db

    normal.set_current_task_offset(get_percpu_symbol_offset("current_task") or None)
    code_ranges = [(chunk[1], chunk[1] + len(chunk[0])) for chunk in rets]
    segment_error = find_segment_policy_error(block_dict, code_ranges)
    if segment_error:
        offset, reason = segment_error
        detail = f"{reason} at 0x{offset:x}" if offset else reason
        print("Rejecting translation:", detail)
        write_unsupported_jit(detail)
        build_jit_binary()
        return

    missing_callees = indirect_jump.find(block_dict, db_dict, jump_table)
    continuation_targets = find_resumable_call_continuations(
        block_dict, db_dict, keep_call_stack
    )
    continuation_labels = continuation_targets - set(block_dict)
    emitted_continuation_labels = set()

    f = StringIO()
    write_entry_dispatch(f, entry, block_dict, continuation_targets)

    for offset, block in sorted(block_dict.items()):
        db = db_dict[block]
        f.write("/*\n" + block.to_string() + "\n */ \n")  # Comment source
        label = db.pretty_str(block.loc_key)

        f.write(label + ":\n")

        reg_map = conflict.block_init()

        len_block = len(block.lines)
        line_cnt = 0

        if assist.check_is_branch(block.lines) and label[0] == "l":
            f.write(make_inst("MOVABS", ["R14", hex(offset)]))
            f.write("INC             R11\n")
            f.write("TEST            R11, 0x1000000\n")
            f.write("JNZ             inst_limit\n")

        temp_i = 0
        temp_j = 0
        while temp_i < len(block.lines):
            line = block.lines[temp_i]
            if (
                offset in continuation_labels
                and offset not in emitted_continuation_labels
            ):
                f.write(f"loc_{offset:x}:\n")
                emitted_continuation_labels.add(offset)
            if str(line) == "LEA        R13, QWORD PTR [R12 + R14]":
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
    f.write(
        indirect_jump.make_callee_table(
            missing_callees, keep_call_stack, resolved_hostcalls
        )
    )

    Path("./asm/jit.S").write_text(f.getvalue(), encoding="utf-8")

    solve_bug.solve_cond_jmp_lock_cmpxchg("./asm/jit.S")

    build_jit_binary()


if __name__ == "__main__":
    pid = int(sys.argv[1])
    entry = int(sys.argv[2], 16)
    dis_assem(pid, entry)

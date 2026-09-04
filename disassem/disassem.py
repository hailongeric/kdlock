import os

from miasm.analysis.machine import Machine
from miasm.core.locationdb import LocationDB 
from miasm.analysis.binary import Container
from miasm.core.bin_stream import bin_stream_str
from miasm.expression.expression import ExprMem, ExprId, ExprInt, ExprLoc
from miasm.arch.x86.arch import mn_x86
import hostcall, memread, translation
from assist import make_inst

import indirect_jump, conflict, assist, normal, solve_bug
import os, signal, sys
import time


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


def add_lines_after_specific_content(file_path, target_address):
    # 读取原始文件内容
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    # 查找包含目标内容的行号
    target_line_number = None
    for i, line in enumerate(lines):
        if "loc_" + target_address + ":" in line:
            target_line_number = i + 1
            break

    # 确保找到了目标内容
    if target_line_number is None:
        print("未找到包含目标内容的行")
        return

    # 插入新的行
    print("add call miss!")
    lines_to_add = [
        "MOVABS          R14, 0x" + target_address + "\n",
        "MOV             Stack_IJ, 0x1\n",
        "LEA             R13, QWORD PTR [R13 + 0x8]\n",
        "MOV             Stack_RSP, R13\n",
        "JMP             exit\n",
    ]

    new_lines = lines[:target_line_number] + lines_to_add + lines[target_line_number:]

    # 写回文件
    with open(file_path, "w", encoding="utf-8") as file:
        file.writelines(new_lines)


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

    f.write('MOV     R11, 0\n')
    f.write('MOV     R14, PT_RIP\n')
    f.write("CMP     R14, 0x%x\n" % entry)
    f.write("JZ      loc_%x\n" % entry)
    for offset in sorted(dispatch_targets):
        if offset == entry:
            continue
        f.write("CMP     R14, 0x%x\n" % offset)
        f.write("JZ      loc_%x\n" % offset)
    f.write("MOV     Stack_IJ, 0x2\n")
    f.write("MOV     R15, R14\n")
    f.write("JMP     exit\n")


def dis_assem(PID, entry, need_count, debug=0):
    os.makedirs("./asm", exist_ok=True)

    if need_count:
        # Get the target list
        total_count = 0
        count_targets = []
        fp = open("zz_utrace/u_trace.txt", "r")
        f_line = fp.readline()
        while f_line:
            count_targets.append(f_line[:-1])
            f_line = fp.readline()
        fp.close()

    resolved_hostcalls = hostcall.resolve_hostcalls(get_kernel_symbol)
    hostcall_targets = set(resolved_hostcalls)
    print("Hostcalls:", [
        "%s@%s" % (spec.symbol, hex(address))
        for address, spec in sorted(resolved_hostcalls.items())
    ])

    jump_table = dict()
    rets = memread.read(PID, entry, jump_table,
                        excluded_callees=hostcall_targets)
    cfgs = []
    raw_spin_lock = get_kernel_symbol("_raw_spin_lock",
                                      0xffffffff81e90a20)
    raw_spin_unlock = get_kernel_symbol("_raw_spin_unlock",
                                        0xffffffff81e90b30)
    mutex_lock = get_kernel_symbol("mutex_lock", 0xffffffff81e8b570)
    mutex_unlock = get_kernel_symbol("mutex_unlock", 0xffffffff81e8a040)
    control_call_targets = {
        addr for addr in (
            raw_spin_lock,
            raw_spin_unlock,
            mutex_lock,
            mutex_unlock,
        ) if addr
    }
    keep_call_stack = control_call_targets | hostcall_targets

    ordering_bug_list = [0x2CE40, 0x2CE50, 0x4FFD0, 0x738D0, 0x67B0]

    for r in rets:
        c = bin_stream_str(r[0], base_address=r[1])
        machine = Machine("x86_64")
        loc_db = LocationDB()
        mdis = machine.dis_engine(c,loc_db=loc_db)
        mdis.follow_call = False
        asmcfg = None
        job_done = set()

        mdis.dont_dis_retcall_funcs = {
            addr for addr in (raw_spin_unlock,) if addr
        }

        for t in r[2]:
            if t - r[1] in ordering_bug_list:  # To let buggy blocks first. MIASM bug
                asmcfg = mdis.dis_multiblock(t, asmcfg, job_done)
                # print("MIASM ordering bug")

        for t in r[2]:
            if t - r[1] in ordering_bug_list:
                continue
            # print(hex(t))
            asmcfg = mdis.dis_multiblock(t, asmcfg, job_done)

        # mdis.dont_dis_retcall_funcs intentionally stops at endpoint calls.
        # The caller still needs the fall-through block when that same call
        # is nested in a translated critical section, so discover and add
        # those blocks before building the final dispatch table.
        while True:
            cfg_blocks = dict()
            cfg_dbs = dict()
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
                target for target in continuation_targets
                if target not in existing_targets and
                r[1] <= target < chunk_end
            )
            if not missing_targets:
                break
            for target in missing_targets:
                asmcfg = mdis.dis_multiblock(
                    target, asmcfg, job_done
                )
        cfgs.append(asmcfg)

    block_dict = dict()
    db_dict = dict()
    for asmcfg in cfgs:
        for block in asmcfg.blocks:
            label = asmcfg.loc_db.pretty_str(block.loc_key)
            offset = int(label.split("_")[1], 16)
            block_dict[offset] = block
            db_dict[block] = asmcfg.loc_db

    missing_callees = indirect_jump.find(block_dict, db_dict, jump_table)
    continuation_targets = find_resumable_call_continuations(
        block_dict, db_dict, keep_call_stack
    )
    continuation_labels = continuation_targets - set(block_dict)
    emitted_continuation_labels = set()

    f = open("./asm/jit.S", "w")
    write_entry_dispatch(f, entry, block_dict, continuation_targets)

    for offset, block in sorted(block_dict.items()):

        db = db_dict[block]
        f.write("/*\n" + block.to_string() + "\n */ \n")  # Comment source
        label = db.pretty_str(block.loc_key)

        if need_count:
            # Get the addr and judge whether to count
            count_flag = 0
            label_addr = ""
            if label[0] == "l":
                label_addr = label[4:]
            elif label[0] == "i":
                print("ij_:" + label)
                label_addr = label[3:]
            if label_addr in count_targets:
                count_flag = True
                count_targets.remove(label_addr)

        f.write(label + ":\n")

        reg_map = conflict.block_init()

        len_block = len(block.lines)
        line_cnt = 0

        can_check = assist.check_flag_def_use(block.lines)
        normal.check_mem_base_block_init()

        if assist.check_is_branch(block.lines):
            line = block.lines[-1]
            if label[0] == 'l':
                f.write(make_inst('MOVABS', ['R14', hex(offset)]))
                f.write('INC             R11\n')
                f.write('TEST            R11, 0x1000000\n')
                f.write('JNZ             inst_limit\n')

        temp_i=0
        temp_j=0
        temp_check=None
        while temp_i < len(block.lines):
            line = block.lines[temp_i]
            if (offset in continuation_labels and
                    offset not in emitted_continuation_labels):
                f.write("loc_%x:\n" % offset)
                emitted_continuation_labels.add(offset)
            # print(line.b)
            if str(line)=="LEA        R13, QWORD PTR [R12 + R14]":
                temp_inst1=mn_x86.fromstring("MOV R13, R14",loc_db=None,mode="64")
                temp_inst2=mn_x86.fromstring("ADD R13, R12",loc_db=None,mode="64")
                block.lines[temp_i:temp_i+1]=[temp_inst1,temp_inst2]
                offset = offset + line.l
                line_cnt = line_cnt + 1
                block_end = line_cnt == len_block
                temp_j=2
                print("solve conflict at %x" % offset)
                continue

            if temp_j == 0:
                solve_bug.solve_lea_ra_rb_c_rb(line, offset)

            if debug:
                f.write(
                    assist.make_inst("MOV", ["Stack_RIPL", hex(offset % (1 << 32))])
                )
                f.write(assist.make_inst("MOV", ["Stack_RIPH", hex(offset >> 32)]))
                f.write("int3\n")
            if temp_j == 0:
                offset = offset + line.l
                line_cnt = line_cnt + 1
                block_end = line_cnt == len_block

            if need_count:
                # count line numbers after translation
                trans_str = translation.translate(
                    line, offset, db, reg_map, block_end, can_check.pop()
                )
                if count_flag:
                    total_count += len(trans_str.split("\n")) - 1

            else:
                if temp_j == 2:
                    temp_check=can_check.pop()
                    f.write(
                        translation.translate(
                            line, offset, db, reg_map, block_end, temp_check
                        )
                    )
                elif temp_j == 1:
                    f.write(
                        translation.translate(
                            line, offset, db, reg_map, block_end, temp_check
                        )
                    )
                else:
                    f.write(
                        translation.translate(
                            line, offset, db, reg_map, block_end, can_check.pop()
                        )
                    )
            temp_i+=1
            if temp_j > 0:
                temp_j-=1
        # for line in block.lines:

        #     # if line.b == b"H\x8d\x14\x7f":
        #     #     line.args[1]._ptr._args[1]._arg = 3
        #     #     print("miasm bug at %x" % offset)
        #     solve_bug.solve_lea_ra_rb_c_rb(line, offset)
        #     print(type(line))

        #     if debug:
        #         f.write(
        #             assist.make_inst("MOV", ["Stack_RIPL", hex(offset % (1 << 32))])
        #         )
        #         f.write(assist.make_inst("MOV", ["Stack_RIPH", hex(offset >> 32)]))
        #         f.write("int3\n")
        #     offset = offset + line.l
        #     line_cnt = line_cnt + 1
        #     block_end = line_cnt == len_block

        #     if need_count:
        #         # count line numbers after translation
        #         trans_str = translation.translate(
        #             line, offset, db, reg_map, block_end, can_check.pop()
        #         )
        #         if count_flag:
        #             total_count += len(trans_str.split("\n")) - 1

        #     else:
        #         f.write(
        #             translation.translate(
        #                 line, offset, db, reg_map, block_end, can_check.pop()
        #             )
        #         )

        f.write("\n\n")
    if need_count:
        print("---------Total count : %d ------------" % total_count)
    f.write(indirect_jump.make_jump_table(jump_table))
    f.write(indirect_jump.make_callee_table(
        missing_callees, keep_call_stack, resolved_hostcalls
    ))

    f.close()

    solve_bug.solve_cond_jmp_lock_cmpxchg("./asm/jit.S")

    # add_lines_after_specific_content("./asm/jit.S", "7ffff7fa6820")
    # add_lines_after_specific_content("./asm/jit.S", "7ffff7fa6800")

    # include/ is 2 dirs up from disassem/ (kdlock/include/).
    # daemon runs from daemon/, so the workspace is ./0xRIP/ or ./0xRIP/tgid/.
    # Use a depth-independent path based on this script's location.
    include_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "include")
    os.system(f"gcc -I{include_dir} -I./asm/ -c -fPIC {include_dir}/wrapper.S -o ./asm/jit.o && objcopy --remove-section .note.gnu.property ./asm/jit.o && objcopy -O binary ./asm/jit.o ./asm/jit.bin")
    os.system("objdump -b binary -m i386:x86-64:intel -D ./asm/jit.bin > ./asm/bin.txt")


if __name__ == "__main__":
    debug = 0
    pid = int(sys.argv[1])
    entry = int(sys.argv[2], 16)
    if len(sys.argv) > 3:
        debug = int(sys.argv[3])
    need_count = 0
    dis_assem(pid, entry, need_count, debug)
    exit(0)

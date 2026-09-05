from assist import make_inst
from miasm.expression.expression import ExprLoc


def dfs(entry, blocks, ret_addr, db_dict, visited, jump_table):
    offset = entry
    for line in blocks[entry].lines:
        offset = offset + line.l
        if line.name == "RET":
            if offset not in jump_table:
                jump_table[offset] = []
            jump_table[offset].append(ret_addr)
    for fork_dst in blocks[entry].bto:
        db = db_dict[blocks[entry]]
        tgt = db.pretty_str(fork_dst.loc_key)
        tgt = tgt.split("_")[1]
        tgt = int(tgt, 16)
        if tgt not in visited:
            visited.add(tgt)
            dfs(tgt, blocks, ret_addr, db_dict, visited, jump_table)


def find(blocks, db_dict, pre_jump_table):
    jump_table = pre_jump_table
    missing_callees = set()
    for offset, block in blocks.items():
        db = db_dict[block]
        for line in block.lines:
            offset = offset + line.l
            if line.name == "CALL" and isinstance(line.args[0], ExprLoc):
                callee = int(line.arg2str(line.args[0], 0, db).split("_")[1], 16)
                if callee in blocks:
                    visited = set()
                    dfs(callee, blocks, offset, db_dict, visited, jump_table)
                else:
                    missing_callees.add(callee)
            elif (
                (line.name[0] == "J" or line.name == "CALL")
                and not isinstance(line.args[0], ExprLoc)
                or line.name == "RET"
            ):
                if offset not in jump_table:
                    jump_table[offset] = []
    return sorted(missing_callees)


def make_jump_table(jump_table):
    ret_str = ""
    for offset, psb_targets in sorted(jump_table.items()):
        ret_str += "ij_" + hex(offset)[2:] + ":\n"
        dst_reg = "R14"  # jump_regs[offset]
        psb_reg = "R15"  # if dst_reg != 'R15' else 'R14'

        for psb_tgt in sorted(set(psb_targets)):
            ret_str += make_inst("MOVABS", [psb_reg, hex(psb_tgt)])
            ret_str += make_inst("CMP", [dst_reg, psb_reg])
            ret_str += make_inst("JZ", ["loc_" + hex(psb_tgt)[2:]])
        ret_str += make_inst("MOVABS", ["R15", hex(offset)])
        ret_str += make_inst("JMP", ["ij_failed"])
        ret_str += "\n"
    return ret_str


def make_callee_table(callee_list, hostcalls=None):
    hostcalls = hostcalls or {}
    ret_str = ""
    for offset in sorted(callee_list):
        service = hostcalls.get(offset)
        if service:
            ret_str += (
                f"/* KD_HOSTCALL id={service.service_id} symbol={service.symbol} */\n"
            )
        ret_str += "loc_" + hex(offset)[2:] + ":\n"
        ret_str += make_inst("MOVABS", ["R14", hex(offset)])
        ret_str += make_inst("MOV", ["Stack_IJ", "0x5" if service else "0x1"])
        # A miss resumes the original callee, with its return address intact.
        ret_str += make_inst("MOV", ["Stack_RSP", "R13"])
        ret_str += make_inst("JMP", ["exit"])
        ret_str += "\n"
    return ret_str

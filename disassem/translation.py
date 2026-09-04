from assist import conditional_branch, get_inst_name, unconditional_branch
from conflict import release_conflict
from normal import process_normal
from special_inst import process_jump, special_inst_dispatch, special_instruction


def translate(line, offset, db, reg_map, block_end):
    args = line.args
    name = get_inst_name(line)
    if line.name in special_instruction:
        return special_inst_dispatch(line, args, offset, db, reg_map, block_end)
    elif line.name in conditional_branch or line.name in unconditional_branch:
        return process_jump(line.name, line, args[0], offset, db, reg_map)
    else:
        return process_normal(name, args, offset, reg_map) + release_conflict(
            reg_map, block_end
        )

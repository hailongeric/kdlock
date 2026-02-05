from miasm.expression.expression import ExprMem, ExprId, ExprInt, ExprLoc, ExprOp

from special_inst import *   

from normal import *


# def translate(line, offset, db, reg_map, block_end, can_check = 1):
#     args =  line.args
#     name = get_inst_name(line)
#     if line.name in special_instruction:
#         return special_inst_dispatch(line, args, offset, db, reg_map, block_end)        
#     elif line.name in conditional_branch or line.name in unconditional_branch:
#         return process_jump(line.name, line, args[0], offset, db, reg_map)
#     else:
#         return process_normal(name, args, offset, reg_map, can_check) + \
#             release_conflict(reg_map, block_end)


trops = []

def translate(line, offset, db, reg_map, block_end, can_check = 1):
    args = line.args
    # print("line: " + str(line) + " offset: " + str(hex(offset)) +" reg_map: " + str(reg_map) + " block_end: " + str(block_end) + " can_check: " + str(can_check))
    # print("line: " + str(line) + " offset: " + str(hex(offset)) +"bytecode: " + str(line.b))
    name = get_inst_name(line)
    if name not in trops:
        # print(name, end = '         ')
        trops.append(name)
    if line.name in special_instruction:
        return special_inst_dispatch(line, args, offset, db, reg_map, block_end)
    elif line.name in conditional_branch or line.name in unconditional_branch:
        return process_jump(line.name, line, args[0], offset, db, reg_map)
    else:
        return process_normal(name, args, offset, reg_map, can_check) + \
            release_conflict(reg_map, block_end)



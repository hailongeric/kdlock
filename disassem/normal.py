# Lower ordinary operands/instructions using conflict.py's physical mapping.
# GS memory uses the pinned waiter's base; current_task uses its logical task.
# FS/base manipulation remains unsupported. No use-time bounds guard exists.
import diagnostics
from instruction_policy import segment_encoding_policy_error
from assist import make_inst
from conflict import (
    apply_map,
    conflict_resolve,
    extract_conflict_regs,
    mark_writes,
    recover_stable,
    release_IP,
)
from miasm.expression.expression import ExprId, ExprInt, ExprMem, ExprOp
from miasm_compat import (
    expr_args,
    expr_int_value,
    expr_op,
    expr_ptr,
    is_mem_segm_expr,
    set_expr_int_value,
)

current_task_offset = None


def set_current_task_offset(offset):
    global current_task_offset
    current_task_offset = offset


def segment_operand(arg):
    if not isinstance(arg, ExprMem) or not is_mem_segm_expr(arg):
        return None, None
    ptr_args = expr_args(expr_ptr(arg))
    if len(ptr_args) != 2:
        return None, None
    return str(ptr_args[0]).upper(), ptr_args[1]


def is_current_task_operand(arg):
    segment, address = segment_operand(arg)
    if segment != "GS" or current_task_offset is None:
        return False
    if not isinstance(address, ExprInt):
        return False
    mask = (1 << address.size) - 1
    return (expr_int_value(address) & mask) == (current_task_offset & mask)


def segment_policy_error(line):
    # miasm 0.1.5 misdecodes SWAPGS and two FSGSBASE encodings.
    encoding_error = segment_encoding_policy_error(getattr(line, "b", b""))
    if encoding_error:
        return encoding_error
    if line.name.upper() in {"RDFSBASE", "RDGSBASE", "WRFSBASE", "WRGSBASE", "SWAPGS"}:
        return "direct FS/GS base access is unsupported"

    for index, arg in enumerate(line.args):
        if isinstance(arg, ExprId) and str(arg).upper() in {"FS", "GS"}:
            return "direct FS/GS register access is unsupported"
        segment, _ = segment_operand(arg)
        if segment is None:
            continue
        if line.name.upper() == "NOP":
            continue
        if segment == "FS":
            return "FS-prefixed memory access is unsupported"
        if segment != "GS":
            return f"{segment}-prefixed memory access is unsupported"
        if not is_current_task_operand(arg):
            continue
        if (
            line.name.upper() != "MOV"
            or index != 1
            or len(line.args) != 2
            or arg.size != 64
            or not isinstance(line.args[0], ExprId)
        ):
            return "current_task is only supported as a 64-bit MOV source"
    return None


def extract_reg(arg, regs):
    if isinstance(arg, dict):
        regs.update(arg["regs"])
        if arg["mul"] != []:
            regs.add(arg["mul"][1])
    elif isinstance(arg, ExprId):
        regs.add(arg)


def rip_relative_address(arg, offset):
    """Resolve only ordinary 64-bit RIP+constant operands at translation time.

    offset is the original instruction's next IP, not the uploaded code's IP.
    Segment bases and nonconstant addresses retain the existing lowering.
    """
    if not isinstance(arg, ExprMem) or is_mem_segm_expr(arg):
        return None
    pointer = expr_ptr(arg)
    if pointer.size != 64:
        return None
    terms = (expr_args(pointer)
             if isinstance(pointer, ExprOp) and expr_op(pointer) == "+"
             else (pointer,))
    rip_count, displacement = 0, 0
    for term in terms:
        if isinstance(term, ExprId) and str(term) == "RIP":
            rip_count += 1
        elif isinstance(term, ExprInt):
            displacement += expr_int_value(term)
        else:
            return None
    return ((offset + displacement) & ((1 << 64) - 1)) if rip_count == 1 else None


def process_normal(name, args, offset, reg_map):
    if name.upper() == "NOP":
        return make_inst("NOP", [])

    # LEA needs no runtime address calculation when its source is RIP-relative.
    # Keep ordinary register mapping for virtual R11--R15 and partial writes.
    if name.upper() == "LEA" and len(args) == 2 and isinstance(args[0], ExprId):
        address = rip_relative_address(args[1], offset)
        if address is not None:
            return process_normal("MOVABS" if args[0].size == 64 else "MOV",
                                  [args[0], ExprInt(address & ((1 << args[0].size) - 1),
                                                    args[0].size)],
                                  offset, reg_map)

    purified_args = []
    conflict_regs = set()
    regs = set()
    pre_inst = ""
    post_inst = ""
    for arg in args:
        address = rip_relative_address(arg, offset)
        # A no-base SIB address sign-extends disp32 in 64-bit address mode.
        # Other targets still use the original scratch-register expansion;
        # never truncate an arbitrary kernel/direct-map address to 32 bits.
        if address is not None and (address < (1 << 31) or
                                    address >= (1 << 64) - (1 << 31)):
            arg = ExprMem(ExprInt(address, 64), arg.size)
        arg = arg_purify(arg, offset, is_current_task_operand(arg))
        purified_args.append(arg)
        extract_reg(arg, regs)
    for reg in regs:
        extract_conflict_regs(reg, conflict_regs)

    if len(conflict_regs) > 0:
        pre_inst = conflict_resolve(reg_map, conflict_regs, offset)
        mark_writes(reg_map, name, purified_args, conflict_regs)
        purified_args = apply_map(purified_args, reg_map)
        release_IP(reg_map)
        post_inst = recover_stable(reg_map, conflict_regs)

    return pre_inst + make_inst(name, purified_args) + post_inst


def mem_addr(arg, res):
    if isinstance(arg, ExprOp):
        if expr_op(arg) == "+":
            for x in list(expr_args(arg)):
                mem_addr(x, res)
        elif expr_op(arg) == "*":
            if len(res["mul"]) > 0:
                diagnostics.warn("MULTIPLE_INDEX", "keep_partial_address", str(arg))
                return
            args = expr_args(arg)
            if isinstance(args[0], ExprId) and isinstance(args[1], ExprInt):
                res["mul"].append(args[1])
                res["mul"].append(args[0])

                if expr_int_value(res["mul"][0]) % 2 == 1:
                    set_expr_int_value(res["mul"][0], expr_int_value(res["mul"][0]) - 1)
                    res["regs"].append(args[0])
            else:
                diagnostics.warn("INVALID_INDEX", "keep_partial_address", str(arg))
        else:
            diagnostics.warn("UNRESOLVED_ADDRESS_OP", "keep_partial_address", str(arg))
    elif isinstance(arg, ExprId):
        res["regs"].append(arg)
    elif isinstance(arg, ExprInt):
        res["im"] = arg
    else:
        diagnostics.warn("UNRESOLVED_ADDRESS_ARG", "keep_partial_address", str(arg))


def arg_purify(arg, offset, logical_task=False):
    if isinstance(arg, ExprOp):
        diagnostics.warn("UNRESOLVED_OPERAND_OP", "emit_empty_operand", str(arg))
        return ""
    if isinstance(arg, ExprMem):
        if logical_task:
            return ExprId("RCT", 64)
        res = {"sz": arg.size, "regs": [], "im": "", "mul": []}
        if is_mem_segm_expr(arg):
            ptr_args = expr_args(expr_ptr(arg))
            res["regs"].append(ExprId("R" + str(ptr_args[0]), 64))
            arg = ptr_args[1]
        else:
            arg = expr_ptr(arg)
        mem_addr(arg, res)
        return res
    elif isinstance(arg, (ExprId, ExprInt, dict)):
        return arg
    else:
        diagnostics.warn(
            "UNRESOLVED_OPERAND", "return_none", str(arg), next_rip=f"0x{offset:x}"
        )

# Lower ordinary operands/instructions using conflict.py's physical mapping.
# GS memory uses the captured origin base; current_task uses its logical task.
# FS/base manipulation remains unsupported. No use-time bounds guard exists.
from . import diagnostics
from .assist import make_inst
from .errors import LoweringUnsupported, RegisterPressure
from .conflict import (
    apply_map,
    conflict_resolve,
    extract_conflict_regs,
    mark_writes,
    recover_stable,
    release_IP,
)
from miasm.expression.expression import ExprId, ExprInt, ExprMem, ExprOp
from .compat import (
    expr_args,
    expr_int_value,
    expr_op,
    expr_ptr,
    is_mem_segm_expr,
)

class NormalLowering:
    """One private build's original operand lowering and logical-task offset."""

    def __init__(self, current_task_offset):
        self.current_task_offset = current_task_offset

    def segment_operand(self, arg):
        if not isinstance(arg, ExprMem) or not is_mem_segm_expr(arg):
            return None, None
        ptr_args = expr_args(expr_ptr(arg))
        if len(ptr_args) != 2:
            return None, None
        return str(ptr_args[0]).upper(), ptr_args[1]


    def is_current_task_operand(self, arg):
        segment, address = self.segment_operand(arg)
        if segment != "GS" or self.current_task_offset is None:
            return False
        if not isinstance(address, ExprInt):
            return False
        mask = (1 << address.size) - 1
        return (expr_int_value(address) & mask) == (self.current_task_offset & mask)


    def extract_reg(self, arg, regs):
        if isinstance(arg, dict):
            regs.update(arg["regs"])
            if arg["mul"] != []:
                regs.add(arg["mul"][1])
        elif isinstance(arg, ExprId):
            regs.add(arg)


    def rip_relative_address(self, arg, offset):
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


    def process_normal(self, name, args, offset, reg_map):
        if name.upper() == "NOP":
            return make_inst("NOP", [])
        if any(isinstance(arg, ExprId) and str(arg).upper() in {
            "CS", "DS", "ES", "SS", "FS", "GS"
        } for arg in args):
            raise LoweringUnsupported("direct segment-selector operands have no origin lowering")

        # LEA forms only the source offset; x86 ignores a segment override here.
        if name.upper() == "LEA":
            unsegmented = [ExprMem(self.segment_operand(arg)[1], arg.size)
                           if self.segment_operand(arg)[0] == "GS" else arg for arg in args]
            if unsegmented != args:
                return self.process_normal(name, unsegmented, offset, reg_map)

        for index, arg in enumerate(args):
            if self.is_current_task_operand(arg) and not (
                name.upper() == "MOV" and index == 1 and len(args) == 2
                and arg.size == 64 and isinstance(args[0], ExprId)
                and args[0].size == 64
            ):
                raise LoweringUnsupported("logical current_task needs its exact 64-bit MOV load")

        expanded = self.expand_segment_address(name, args, offset, reg_map)
        if expanded is not None:
            return expanded

        # LEA needs no runtime address calculation when its source is RIP-relative.
        # Keep ordinary register mapping for virtual R11--R15 and partial writes.
        if name.upper() == "LEA" and len(args) == 2 and isinstance(args[0], ExprId):
            address = self.rip_relative_address(args[1], offset)
            if address is not None:
                return self.process_normal("MOVABS" if args[0].size == 64 else "MOV",
                                      [args[0], ExprInt(address & ((1 << args[0].size) - 1),
                                                        args[0].size)],
                                      offset, reg_map)

        purified_args = []
        conflict_regs = set()
        regs = set()
        pre_inst = ""
        post_inst = ""
        for arg in args:
            address = self.rip_relative_address(arg, offset)
            # A no-base SIB address sign-extends disp32 in 64-bit address mode.
            # Other targets still use the original scratch-register expansion;
            # never truncate an arbitrary kernel/direct-map address to 32 bits.
            if address is not None and (address < (1 << 31) or
                                        address >= (1 << 64) - (1 << 31)):
                arg = ExprMem(ExprInt(address, 64), arg.size)
            arg = self.arg_purify(arg, offset, self.is_current_task_operand(arg))
            purified_args.append(arg)
            self.extract_reg(arg, regs)
        for reg in regs:
            extract_conflict_regs(reg, conflict_regs)

        if len(conflict_regs) > 0:
            pre_inst = conflict_resolve(reg_map, conflict_regs, offset)
            mark_writes(reg_map, name, purified_args, conflict_regs)
            purified_args = apply_map(purified_args, reg_map)
            release_IP(reg_map)
            post_inst = recover_stable(reg_map, conflict_regs)

        return pre_inst + make_inst(name, purified_args) + post_inst


    def expand_segment_address(self, name, args, offset, reg_map):
        """Keep a complex source EA separate from the saved segment base.

        x86 permits a base plus one scaled index. Adding GS as a third register
        requires a flag-neutral source LEA first. Reserve the temporary before
        mapping source operands so SP/BP recovery cannot occupy its physical slot.
        """
        for index, arg in enumerate(args):
            segment, address = self.segment_operand(arg)
            if segment != "GS" or self.is_current_task_operand(arg):
                continue
            source = ExprMem(address, arg.size)
            purified = self.arg_purify(source, offset)
            if address.size == 64 and len(purified["regs"]) + bool(purified["mul"]) <= 1:
                continue
            registers, used = set(), set()
            for original in args:
                self.extract_reg(self.arg_purify(original, offset, self.is_current_task_operand(original)),
                            registers)
            for register in registers:
                extract_conflict_regs(register, used)
            occupied = set(reg_map.values())
            temporary = next((candidate for candidate in ("T1", "T2")
                              if candidate not in used and candidate not in occupied), None)
            if temporary is None:
                raise RegisterPressure("no temporary available for segmented effective address")
            code = conflict_resolve(reg_map, {temporary}, offset)
            code += self.process_normal("LEA", [ExprId("R" + temporary, address.size), source],
                                   offset, reg_map)
            lowered = list(args)
            lowered[index] = {"sz": arg.size, "regs": [ExprId("RGS", 64),
                                                      ExprId("R" + temporary, 64)],
                              "im": "", "mul": []}
            code += self.process_normal(name, lowered, offset, reg_map)
            for physical, logical in reg_map.items():
                if logical == temporary:
                    reg_map[physical] = ""
            return code
        return None


    def mem_addr(self, arg, res):
        if isinstance(arg, ExprOp):
            if expr_op(arg) == "+":
                for x in list(expr_args(arg)):
                    self.mem_addr(x, res)
            elif expr_op(arg) == "*":
                if len(res["mul"]) > 0:
                    diagnostics.warn("MULTIPLE_INDEX", "keep_partial_address", str(arg))
                    return
                args = expr_args(arg)
                if isinstance(args[0], ExprId) and isinstance(args[1], ExprInt):
                    res["mul"].append(args[1])
                    res["mul"].append(args[0])

                    if expr_int_value(res["mul"][0]) % 2 == 1:
                        # Replace the expression; retained decoded source is read-only.
                        res["mul"][0] = ExprInt(expr_int_value(res["mul"][0]) - 1,
                                                res["mul"][0].size)
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


    def arg_purify(self, arg, offset, logical_task=False):
        if isinstance(arg, ExprOp):
            diagnostics.warn("UNRESOLVED_OPERAND_OP", "emit_empty_operand", str(arg))
            return ""
        if isinstance(arg, ExprMem):
            if logical_task:
                return ExprId("RCT", 64)
            res = {"sz": arg.size, "regs": [], "im": "", "mul": []}
            if is_mem_segm_expr(arg):
                segment, _ = self.segment_operand(arg)
                if segment != "GS":
                    raise ValueError("no origin input for this segment operand")
                ptr_args = expr_args(expr_ptr(arg))
                res["regs"].append(ExprId("R" + str(ptr_args[0]), 64))
                arg = ptr_args[1]
            else:
                arg = expr_ptr(arg)
            self.mem_addr(arg, res)
            return res
        elif isinstance(arg, (ExprId, ExprInt, dict)):
            return arg
        else:
            diagnostics.warn(
                "UNRESOLVED_OPERAND", "return_none", str(arg), next_rip=f"0x{offset:x}"
            )

"""Scalar address facts and block-local register transfer for admission.

These helpers neither track CFG joins nor forward memory contents. The bounded
cross-block transfer domain remains in context_values.FlowConstants.
"""

from copy import deepcopy

import diagnostics
import context_memory
from context_symbols import ContextSymbols
from miasm.analysis.machine import Machine
from miasm.arch.x86.regs import regs64_expr
from miasm.core.locationdb import LocationDB
from miasm.expression.expression import (
    ExprCompose, ExprId, ExprInt, ExprLoc, ExprOp, ExprSlice,
)
from miasm.ir.ir import IRBlock
from miasm.ir.symbexec import SymbolicExecutionEngine
from miasm_compat import expr_args, expr_int_value, expr_op


def static_address(expr, db, next_rip):
    if isinstance(expr, ExprInt):
        return expr_int_value(expr)
    if isinstance(expr, ExprLoc):
        return db.get_location_offset(expr.loc_key) if db is not None else None
    if isinstance(expr, ExprId) and str(expr).upper() == "RIP":
        return next_rip
    if isinstance(expr, ExprOp) and expr_op(expr) in {"+", "-"}:
        values = [static_address(arg, db, next_rip) for arg in expr_args(expr)]
        if values and all(value is not None for value in values):
            if expr_op(expr) == "+":
                return sum(values) & ((1 << 64) - 1)
            if len(values) == 2:
                return (values[0] - values[1]) & ((1 << 64) - 1)
    return None


class RegisterConstants:
    """Block-local address facts, not runtime memory or flags emulation."""

    def __init__(self):
        self.lifter = Machine("x86_64").lifter(LocationDB())
        self.location = self.lifter.loc_db.add_location()
        self.registers = frozenset(regs64_expr) - {ExprId("RIP", 64)}
        self.values = {}
        self.lifted = {}

    def resolve(self, expr):
        normalized = self.lifter.expr_fix_regs_for_mode(expr, 64)
        return SymbolicExecutionEngine(self.lifter, self.values).eval_expr(normalized)

    def resolve_many(self, expr, *, allow_wide=False):
        return (self.resolve(expr),)

    def assignments(self, line):
        key = id(line)
        if key in self.lifted:
            return self.lifted[key][1]
        try:
            # The lifter mutates decode metadata; never change codegen inputs.
            assignments, extra = self.lifter.instr2ir(deepcopy(line))
            if extra:
                result = None
            else:
                block = IRBlock(self.lifter.loc_db, self.location, [assignments])
                result = self.lifter.irbloc_fix_regs_for_mode(block, 64)[0]
        except (NotImplementedError, ValueError, KeyError, TypeError):
            result = None
        self.lifted[key] = (line, result)
        return result

    def update(self, line):
        if line.breakflow() or line.is_subcall():
            self.values.clear()
            return
        assignments = self.assignments(line)
        if assignments is None:
            # Forget facts for unmodelled instructions; do not silently retain
            # stale register values or introduce a new opcode refusal policy.
            self.values.clear()
            return
        engine = SymbolicExecutionEngine(self.lifter, self.values)
        updates = engine.eval_assignblk(assignments)
        for register, value in updates.items():
            if register not in self.registers:
                continue
            if isinstance(value, ExprInt):
                self.values[register] = value
            else:
                self.values.pop(register, None)


class ContextFlowLimit(ValueError):
    def __init__(self, detail, offset=0, instruction=None, *, diagnostic_fields=None):
        super().__init__(detail)
        self.offset = offset
        self.instruction = instruction
        self.diagnostic_fields = diagnostic_fields

    def report(self, offset=None, instruction=None):
        if self.diagnostic_fields is None:
            return
        diagnostics.set_instruction(
            self.offset if offset is None else offset,
            self.instruction if instruction is None else instruction,
        )
        diagnostics.warn(
            "CONTEXT_ADDRESS_WIDENED",
            "reject_entry",
            "analysis uncertainty, not evidence of a runtime context access",
            **self.diagnostic_fields,
        )


def known_bits(value):
    """Proven zero/one bits, without assumptions about flags or runtime data."""
    mask = (1 << value.size) - 1
    if isinstance(value, ExprInt):
        return mask ^ int(value), int(value)
    if isinstance(value, ExprSlice):
        zero, one = known_bits(value.arg)
        return (zero >> value.start) & mask, (one >> value.start) & mask
    if isinstance(value, ExprCompose):
        zero = one = offset = 0
        for part in value.args:
            part_zero, part_one = known_bits(part)
            zero |= part_zero << offset
            one |= part_one << offset
            offset += part.size
        return zero, one
    if isinstance(value, ExprOp) and value.op == "&":
        zero, one = 0, mask
        for part in value.args:
            part_zero, part_one = known_bits(part)
            zero |= part_zero
            one &= part_one
        return zero, one
    return 0, 0


def context_reference(expr, db, next_rip, symbols, size=1):
    # A GS displacement names origin-CPU storage, not a linear kernel address.
    # Lowering adds the pinned waiter's GS base (or supplies logical current).
    # Do not mistake an offset equal to current_task for an absolute reference;
    # ordinary linear per-CPU aliases still go through the checks below.
    if (
        isinstance(expr, ExprOp)
        and expr_op(expr) == "segm"
        and str(expr_args(expr)[0]).upper() == "GS"
    ):
        return None
    if context_memory.ordinary_call_pointer(expr):
        # Partial CALL aliases keep derivable constant bases and contiguous
        # high-prefix ranges. Unknown high bits are ordinary dynamic pointer
        # inputs, not evidence that every address in their interval hull is
        # accessed. Never recurse into tagged mask/offset metadata as addresses.
        for start, extent in context_memory.call_alias_ranges(expr, size):
            if isinstance(symbols, ContextSymbols):
                symbol = symbols.resolve(start, extent)
            else:
                symbol = next((name for address, name in symbols.items()
                               if start <= address < start + extent), None)
            if symbol:
                return symbol
        # Preserve the ordinary known-base rule for a literal offset written
        # outside the tag, even when adding it produces a different base.
        if isinstance(expr, ExprOp) and expr.op == "+":
            for arg in expr.args:
                if isinstance(arg, ExprInt):
                    symbol = context_reference(arg, db, next_rip, symbols, size)
                    if symbol:
                        return symbol
        return None
    address = static_address(expr, db, next_rip)
    if isinstance(symbols, ContextSymbols):
        symbol = symbols.resolve(address, size)
    else:
        # Plain mappings carry exact addresses, but operand overlap still counts.
        symbol = next(
            (
                name
                for start, name in symbols.items()
                if address is not None and address <= start < address + size
            ),
            None,
        )
    if symbol:
        return symbol
    # An unknown index does not hide a known base, e.g. offset_table[RAX].
    # This deliberately does not infer values from earlier register writes.
    if address is None and isinstance(expr, ExprOp):
        for arg in expr_args(expr):
            symbol = context_reference(arg, db, next_rip, symbols, size)
            if symbol:
                return symbol
    return None

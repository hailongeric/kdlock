# Isolate supported miasm expression/accessor differences from the lowerer.
# This is an API adapter, not a replacement decoder or instruction verifier.
from miasm.expression.expression import ExprInt

try:
    from miasm.arch.x86.arch import is_mem_segm as _is_mem_segm
except ImportError:
    _is_mem_segm = None


def expr_args(expr):
    return getattr(expr, "args", getattr(expr, "_args", ()))


def expr_op(expr):
    return getattr(expr, "op", getattr(expr, "_op", None))


def expr_ptr(expr):
    return getattr(expr, "ptr", getattr(expr, "_ptr", None))


def expr_int_value(expr):
    return getattr(expr, "arg", getattr(expr, "_arg", None))


def is_mem_segm_expr(expr):
    if _is_mem_segm is not None:
        return _is_mem_segm(expr)
    return expr.is_mem_segm()


def make_expr_int(value, size):
    if isinstance(value, float):
        value = int(value)
    return ExprInt(value, size)

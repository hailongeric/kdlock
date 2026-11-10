"""Turn incomplete original operand construction into a pre-instruction exit.

The original formatter could warn and retain partial operands. An instruction
with a partial representation is not emitted. This is a construction outcome,
not a semantic source-admission whitelist.
"""

from .errors import LoweringUnsupported


def warn(code, action, detail, **unused):
    raise LoweringUnsupported(f"{code}: {detail}")


def error(code, action, detail, **unused):
    raise LoweringUnsupported(f"{code}: {detail}")

# Shared instruction spelling, operand formatting and branch classification.
# These helpers serialize the lowerer's decisions; they do not admit a kernel
# instruction or establish that a warning-only lowering preserves its semantics.
from . import diagnostics
import re
# Spelling aliases from the original decoder/assembler bridge, not admission.
READ_PREFETCH_ALIASES = {
    "PREFETCH0": "PREFETCHT0",
    "PREFETCH1": "PREFETCHT1",
    "PREFETCH2": "PREFETCHT2",
}
from miasm.expression.expression import ExprId, ExprInt
from .compat import make_expr_int

conditional_branch = [
    "JO",
    "JNO",
    "JB",
    "JAE",
    "JZ",
    "JNZ",
    "JBE",
    "JA",
    "JS",
    "JNS",
    "JPE",
    "JNP",
    "JL",
    "JGE",
    "JLE",
    "JG",
    "JCXZ",
    "JECXZ",
    "JRCXZ",
]

unconditional_branch = ["JMP", "JMPF"]

sz2pfx = {
    128: "XMMWORD PTR",
    64: "QWORD PTR",
    32: "DWORD PTR",
    16: "WORD PTR",
    8: "BYTE PTR",
}


def check_in_list(name, l):
    return any(item in name for item in l)


def check_is_branch(lines):
    if not lines:
        return False
    name = get_inst_name(lines[-1])
    return check_in_list(name, conditional_branch) or check_in_list(
        name, unconditional_branch
    )


def make_mem_dict(size, regs=None, im=0):
    regs = regs or []
    res = {"sz": size, "regs": [], "im": "", "mul": []}
    if im != 0:
        res["im"] = make_expr_int(im, 64)
    for reg in regs:
        res["regs"].append(ExprId(reg, 64))
    return res


def im64_abs(arg):
    if isinstance(arg, ExprInt) and (arg.size == 64):
        return "ABS"
    return ""


def make_inst(name, args):
    processed_args = []
    if not isinstance(args, list):
        args = [args]
    for arg in args:
        if isinstance(arg, str):
            processed_args.append(arg)
        elif isinstance(arg, dict):
            if len(arg["regs"]) + len(arg["mul"]) / 2 > 2:
                diagnostics.warn(
                    "ADDRESS_REGISTER_OVERFLOW", "emit_unchanged", str(arg)
                )
            res = []
            for reg in arg["regs"]:
                res.append(str(reg))
            if arg["im"] != "":
                res.append(str(arg["im"]))
            if arg["mul"] != []:
                res.append(str(arg["mul"][0]) + " * " + str(arg["mul"][1]))
            res = sz2pfx[arg["sz"]] + " [" + " + ".join(res) + "]"
            processed_args.append(res)
        else:
            processed_args.append(str(arg))
    rendered = ", ".join(processed_args)
    # A source-valid AH/BH/CH/DH operand can become unencodable when source
    # SP/BP or virtual GPR mapping introduces a REX-only physical operand.
    if (re.search(r"\b(?:AH|BH|CH|DH)\b", rendered, re.I)
            and re.search(r"\b(?:R(?:[89]|1[0-5])(?:D|W|B)?|SPL|BPL|SIL|DIL)\b", rendered, re.I)):
        diagnostics.warn("HIGH_BYTE_REX_CONFLICT", "stop_before_instruction", rendered)
    return f"{name:<15} " + rendered + "\n"


def get_inst_name(inst):
    # GNU assembler uses
    # Intel's T0/T1/T2 names rather than Miasm 0.1.5's decoder aliases.
    o = READ_PREFETCH_ALIASES.get(inst.name, inst.name)
    if inst.additional_info.g1.value & 1:
        o = f"LOCK {o}"
    if inst.additional_info.g1.value & 2 and get_prefixed_default(inst) != b"\xf2":
        o = f"REPNE {o}"
    if inst.additional_info.g1.value & 8 and get_prefixed_default(inst) != b"\xf3":
        o = f"REP {o}"
    elif inst.additional_info.g1.value & 4 and get_prefixed_default(inst) != b"\xf3":
        o = f"REPE {o}"
    return o


def get_prefixed_default(inst):
    prefixed = inst.additional_info.prefixed
    if isinstance(prefixed, bytes):
        return prefixed
    return getattr(prefixed, "default", b"")

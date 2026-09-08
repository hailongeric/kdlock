import diagnostics
from miasm.expression.expression import ExprId, ExprInt
from miasm_compat import make_expr_int

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
            if len(arg["regs"]) + len(arg["mul"]) / 2 > 3:
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
    return f"{name:<15} " + ", ".join(processed_args) + "\n"


def get_inst_name(inst):
    o = inst.name
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

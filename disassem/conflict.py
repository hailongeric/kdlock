from assist import make_inst
from miasm.expression.expression import ExprId

special_regs = [
    "IP",
    "SP",
    "BP",
    "15",
    "14",
    "13",
    "12",
    "11",
    "FS",
    "GS",
    "CT",
    "T1",
    "T2",
]
stable_regs = ["T1", "T2", "SP", "BP"]

orig_stable_map = {"SP": "13", "BP": "12"}
# T2 for jump target
# T1 for push/pop temp target

sz2sfx = {64: "", 32: "d", 16: "w", 8: "b"}


def block_init():
    return {"15": "", "14": "", "13": "SP", "12": "BP"}


def release_IP(reg_map):
    p = ""
    for k, v in reg_map.items():
        if v == "IP":
            p = k
    if p != "":
        reg_map[p] = ""


def release_conflict(reg_map, block_end=True):
    if not block_end:
        return ""
    res = ""
    for k, v in reg_map.items():
        if v == "" or v in stable_regs:
            continue
        if v != "FS" and v != "GS" and v != "CT":
            res += make_inst("MOV", ["Stack_R" + v, "R" + k])
    return res


def release_tmp_conflict(reg_map):
    p = [k for k, v in reg_map.items() if v != "" and v[0] == "T"]
    for k in p:
        reg_map[k] = ""


def extract_conflict_regs(reg, conflict_regs):
    key = str(reg)
    possible_keys = [key[0:2]]
    if len(key) > 2:
        possible_keys.append(key[1:3])
    for key in possible_keys:
        if key in special_regs:
            conflict_regs.add(key)


def conflict_resolve(reg_map, conflict_regs, offset=0):
    resolved_regs = {v for v in reg_map.values() if v != ""}
    idle_regs = [k for k, v in reg_map.items() if v == ""]
    possible_victims = [
        k
        for k, v in reg_map.items()
        if v not in conflict_regs and v != "" and v not in stable_regs
    ]
    possible_stable_victims = [
        p
        for p, v in reg_map.items()
        if p not in conflict_regs and v in stable_regs and v[0] != "T"
    ]

    to_be_resolved = sorted(conflict_regs - resolved_regs)

    resolve_inst = ""

    for v in to_be_resolved:
        if len(idle_regs) > 0:
            p = idle_regs.pop(0)
        elif len(possible_victims) > 0:
            p = possible_victims.pop(0)
            resolve_inst += make_inst("MOV", ["Stack_R" + reg_map[p], "R" + p])
        else:  # No way but borrow stable regs
            p = possible_stable_victims.pop(0)
            resolve_inst += make_inst("MOV", ["Stack_R" + reg_map[p], "R" + p])

        if v == "IP":
            resolve_inst += make_inst("MOVABS", ["R" + p, hex(offset)])
        # Stable virtual registers already hold their current value.
        elif v not in stable_regs:
            resolve_inst += make_inst("MOV", ["R" + p, "Stack_R" + v])
        reg_map[p] = v
    return resolve_inst


def recover_stable(reg_map, conflict_regs):
    inv_map = {v: k for k, v in reg_map.items()}
    ret_str = ""
    for v in stable_regs:
        if v[0] == "T":
            continue
        if v not in inv_map:
            p = orig_stable_map[v]
            ret_str += make_inst("MOV", ["Stack_R" + reg_map[p], "R" + p])
            ret_str += make_inst("MOV", ["R" + p, "Stack_R" + v])
            reg_map[p] = v
    return ret_str


def apply_map(args, reg_map):
    processed = []
    inv_map = {v: k for k, v in reg_map.items()}
    for arg in args:
        if isinstance(arg, dict):
            res = {"im": arg["im"], "sz": arg["sz"]}
            res["regs"] = apply_map(arg["regs"], reg_map)
            res["mul"] = apply_map(arg["mul"], reg_map)
            processed.append(res)
        elif isinstance(arg, ExprId):
            key = str(arg)
            if len(key) > 2:
                k1 = str(arg)[1:3]
            else:
                k1 = ""
            k2 = str(arg)[0:2]
            if k1 in special_regs:
                k1 = "R" + inv_map[k1] + sz2sfx[arg.size]
                processed.append(ExprId(k1, arg.size))
            elif k2 in special_regs:
                k2 = "R" + inv_map[k2] + sz2sfx[arg.size]
                processed.append(ExprId(k2, arg.size))
            else:
                processed.append(arg)
        else:
            processed.append(arg)
    return processed


def reverse_reg(reg_map, arg):
    if isinstance(arg, ExprId):
        arg = str(arg)[1:3]
    elif isinstance(arg, str):
        arg = arg[1:3]
    else:
        print(f"Error, {arg!s} not a register")

    if arg in special_regs:
        inv_map = {v: k for k, v in reg_map.items()}
        if arg in inv_map:
            return inv_map[arg]
        return " "
    return arg

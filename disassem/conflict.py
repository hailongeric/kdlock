# Map virtual special registers onto the bounded physical scratch pool.
# GPR spills address shared kd_regs through reserved physical R11; context and
# control slots stay on the wrapper stack. R11 is never in this physical pool.
# Restore stable mappings at block boundaries so dispatch/exits find SP/BP.
import diagnostics
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
virtual_gprs = {"11", "12", "13", "14", "15"}

orig_stable_map = {"SP": "13", "BP": "12"}
# T2 for jump target
# T1 for push/pop temp target

sz2sfx = {64: "", 32: "d", 16: "w", 8: "b"}


class RegisterMap(dict):
    """Block-local mappings; only modified virtual GPRs need packet stores.

    SP/BP still use the existing stable-register protocol. This state exists
    only in the translator: every block starts afresh from the shared packet.
    """

    def __init__(self):
        super().__init__({"15": "", "14": "", "13": "SP", "12": "BP"})
        self.dirty = set()


def block_init():
    return RegisterMap()


def mark_writes(reg_map, name, args, conflict_regs):
    """Recognize simple operand roles; unknown instructions remain conservative.

    A memory destination does not modify its address registers. Partial GPR
    writes are dirty too, since their full logical value must reach the packet.
    """
    if name.upper() in {"CMP", "TEST"}:
        return
    writes = conflict_regs
    if name.upper() in {"MOV", "MOVABS", "MOVZX", "MOVSX", "MOVSXD", "LEA"}:
        writes = set()
        if args and isinstance(args[0], ExprId):
            extract_conflict_regs(args[0], writes)
    reg_map.dirty.update(writes & virtual_gprs)


def spill_register(reg_map, physical):
    logical = reg_map[physical]
    # A released IP may have borrowed SP's physical slot. Its empty mapping
    # has no logical value to store before stable SP is reloaded.
    if not logical:
        return ""
    if logical in virtual_gprs and logical not in reg_map.dirty:
        return ""
    return make_inst("MOV", ["Stack_R" + logical, "R" + physical])


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
            res += spill_register(reg_map, k)
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
        # conflict_regs names logical operands, not physical pool numbers.
        # A source using logical R12/R13 may still evict physical R12/R13
        # when those hold BP/SP; excluding by p exhausts a usable pool.
        if v not in conflict_regs and v in stable_regs and v[0] != "T"
    ]

    to_be_resolved = sorted(conflict_regs - resolved_regs)

    resolve_inst = ""

    for v in to_be_resolved:
        if len(idle_regs) > 0:
            p = idle_regs.pop(0)
        elif len(possible_victims) > 0:
            p = possible_victims.pop(0)
            resolve_inst += spill_register(reg_map, p)
        else:  # No way but borrow stable regs
            p = possible_stable_victims.pop(0)
            resolve_inst += spill_register(reg_map, p)

        if v == "IP":
            resolve_inst += make_inst("MOVABS", ["R" + p, hex(offset)])
        # Stable virtual registers already hold their current value.
        elif v not in stable_regs:
            resolve_inst += make_inst("MOV", ["R" + p, "Stack_R" + v])
        reg_map.dirty.discard(v)
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
            ret_str += spill_register(reg_map, p)
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
        diagnostics.error("EXPECTED_REGISTER", "continue_unchanged", str(arg))

    if arg in special_regs:
        inv_map = {v: k for k, v in reg_map.items()}
        if arg in inv_map:
            return inv_map[arg]
        return " "
    return arg

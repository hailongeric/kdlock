# Construct bounded CALL/RET and learned indirect-target dispatch tables.
# Build a complete staged whitelist before publishing it to emission. Sequential
# return-slot facts can narrow analysis, not justify dropping emitted checks.
from collections import defaultdict

from assist import make_inst
from miasm.expression.expression import ExprLoc


class ReturnFlowError(ValueError):
    """An incomplete/budgeted return graph cannot authorize generated dispatch."""

    def __init__(self, message, offset):
        super().__init__(message)
        self.offset = offset


def find(blocks, db_dict, pre_jump_table, *, max_visits=65536):
    # Stage the union with learned IJ history. On failure the caller must
    # reject, never observe a partially populated return whitelist.
    jump_table = {source: set(targets) for source, targets in pre_jump_table.items()}
    callers, returns = defaultdict(set), defaultdict(set)
    missing_callees = set()
    work = 0

    def spend(amount, offset):
        nonlocal work
        work += amount
        if work > max_visits:
            raise ReturnFlowError("return dispatch exceeds its work budget", offset)

    for start, block in sorted(blocks.items()):
        db = db_dict.get(block)
        if db is None:
            raise ReturnFlowError("missing return dispatch location database", start)
        offset = start
        for line in block.lines:
            spend(1, offset)
            offset += line.l
            name = line.name.upper()
            direct = bool(line.args) and isinstance(line.args[0], ExprLoc)
            if name == "CALL" and direct:
                # Location names are presentation, not a numeric CFG contract.
                callee = db.get_location_offset(line.args[0].loc_key)
                if callee is None:
                    raise ReturnFlowError("unresolved return dispatch callee", start)
                if callee in blocks:
                    callers[callee].add(offset)
                else:
                    missing_callees.add(callee)
            elif name == "RET" or (
                (name.startswith("J") or name == "CALL") and not direct
            ):
                jump_table.setdefault(offset, set())
                if name == "RET":
                    returns[start].add(offset)

    # Walk each callee once for all its call sites. Shared tails contribute
    # every continuation; no balanced-stack or matching-return assumption is
    # introduced. Iteration also handles long linear CFGs and cycles without
    # Python recursion, while an explicit budget bounds total graph work.
    for callee, continuations in sorted(callers.items()):
        pending, seen = [callee], set()
        while pending:
            start = pending.pop()
            if start in seen:
                continue
            seen.add(start)
            spend(1, start)
            block = blocks[start]
            if not block.lines:
                raise ReturnFlowError("empty block in return dispatch", start)
            for source in sorted(returns[start]):
                spend(len(continuations), source)
                jump_table[source].update(continuations)
            targets = set()
            for edge in block.bto:
                spend(1, start)
                target = db_dict[block].get_location_offset(edge.loc_key)
                if target not in blocks:
                    raise ReturnFlowError(
                        "missing CFG successor in return dispatch", start
                    )
                targets.add(target)
            pending.extend(sorted(targets - seen, reverse=True))

    pre_jump_table.update(
        {source: sorted(targets) for source, targets in jump_table.items()}
    )
    return sorted(missing_callees)


def make_jump_table(jump_table, *, preserve_flags=False):
    ret_str = ""
    for offset, psb_targets in sorted(jump_table.items()):
        ret_str += "ij_" + hex(offset)[2:] + ":\n"
        if preserve_flags:
            ret_str += "PUSHFQ\n"
        dst_reg = "R14"  # jump_regs[offset]
        psb_reg = "R15"  # if dst_reg != 'R15' else 'R14'

        for psb_tgt in sorted(set(psb_targets)):
            ret_str += make_inst("MOVABS", [psb_reg, hex(psb_tgt)])
            ret_str += make_inst("CMP", [dst_reg, psb_reg])
            ret_str += make_inst("JZ", [f"kd_ij_{offset:x}_{psb_tgt:x}"
                                       if preserve_flags else f"loc_{psb_tgt:x}"])
        if preserve_flags:
            ret_str += "POPFQ\n"
        ret_str += make_inst("MOVABS", ["R15", hex(offset)])
        ret_str += make_inst("JMP", ["ij_failed"])
        if preserve_flags:
            for target in sorted(set(psb_targets)):
                ret_str += f"kd_ij_{offset:x}_{target:x}:\nPOPFQ\n"
                ret_str += make_inst("JMP", [f"loc_{target:x}"])
        ret_str += "\n"
    return ret_str


def make_callee_table(callee_list, hostcalls=None):
    hostcalls = hostcalls or {}
    ret_str = ""
    for offset in sorted(callee_list):
        service = hostcalls.get(offset)
        if service:
            ret_str += (
                f"/* KD_HOSTCALL id={service.service_id} symbol={service.symbol} */\n"
            )
        ret_str += "loc_" + hex(offset)[2:] + ":\n"
        ret_str += make_inst("MOVABS", ["R14", hex(offset)])
        ret_str += make_inst("MOV", ["Stack_IJ", "0x5" if service else "0x1"])
        # The common exit publishes SP for COMPLETE, reduced and FULL packets.
        # A miss resumes the original callee, with its return address intact.
        ret_str += make_inst("JMP", ["exit"])
        ret_str += "\n"
    return ret_str

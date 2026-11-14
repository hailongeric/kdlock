"""Controlled ordinary-spin VM scene and exact continuous-owner witness."""


def continuous_pair(rows, has, typed_unlock, image, tasks, validate_retirement):
    """Return evidence only for two complete foreign bodies in one owner lifetime."""
    selected = [row for row in rows if has(row, "SELECT_PROXY")
                and row["task"] == tasks[2] and row["origin"] in (tasks[3], tasks[4])]
    if len(selected) != 2:
        return None
    selected.sort(key=lambda row: row["index"])
    if [row["origin"] for row in selected] != [tasks[3], tasks[4]]:
        raise AssertionError("spin batch skipped or reordered a queued source")
    owner = selected[0]["owner"]
    if not owner or selected[1]["owner"] != owner:
        return None
    if selected[1]["object"] != selected[0]["object"]:
        raise AssertionError("batch selections name different spin objects")
    if len({row["acquisition"] for row in selected}) != 2 or len({row["state"] for row in selected}) != 2:
        raise AssertionError("foreign bodies share acquisition or canonical state")
    ends = [row for row in rows if has(row, "PHYSICAL_END") and row["owner"] == owner]
    begins = [row for row in rows if has(row, "PHYSICAL_BEGIN") and row["owner"] == owner]
    if len(ends) != 1 or len(begins) != 1:
        raise AssertionError("batch lacks exactly one physical release callback")
    end, begin = ends[0], begins[0]
    proofs = []
    for request in selected:
        exact = [row for row in rows if row["node"] == request["node"]
                 and row["acquisition"] == request["acquisition"]]
        grants = [row for row in exact if has(row, "GRANT") and row["owner"] == owner]
        entries = [row for row in exact if has(row, "JIT_ENTER")]
        exits = [row for row in exact if has(row, "JIT_EXIT")]
        unlocks = [row for row in exact if typed_unlock(row, request["node"], image)]
        returned = [row for row in exact if has(row, "PROXY_RETURN") and row["result"] == 4]
        if (len(grants) != 1 or not entries or not exits or len(unlocks) != 1 or len(returned) != 1
                or any(row["task"] != tasks[2] or row["origin"] != request["origin"]
                       or row["image"] != image or not row["flags"] & (1 << 12) for row in entries)
                or any(row["result"] != 1 or row["image"] != image for row in exits)
                or any(has(row, "FORWARD") or has(row, "NATIVE_UNLOCK") for row in exact)):
            raise AssertionError("selection is not a complete foreign JIT critical section")
        if not (request["index"] < grants[0]["index"] < entries[0]["index"]
                < unlocks[0]["index"] < returned[0]["index"] < begin["index"] < end["index"]):
            raise AssertionError("generated completion did not precede physical release")
        validate_retirement(rows, request, None, 0, image)
        proofs.append(dict(origin=request["origin"], state=request["state"],
            acquisition=request["acquisition"], node=request["node"],
            grant=grants[0]["index"], jit_entry=entries[0]["index"],
            typed_unlock=unlocks[0]["index"], proxy_return=returned[0]["index"]))
    first = proofs[0]["grant"]
    interval = [row for row in rows if first <= row["index"] <= end["index"]]
    if (proofs[0]["proxy_return"] >= proofs[1]["grant"]
            or any(has(row, "ENQUEUE") and row["task"] == tasks[2] for row in interval)
            or any(row["object"] == selected[0]["object"] and
                   (has(row, "GRANT") or has(row, "PHYSICAL_BEGIN") or has(row, "PHYSICAL_END"))
                   and row["owner"] != owner for row in interval)
            or begin["related"] != end["related"] or not begin["related"]
            or begin["task"] != tasks[2] or end["task"] != tasks[2]):
        raise AssertionError("physical ownership changed between foreign bodies")
    return dict(owner=owner, executor=tasks[2], object=selected[0]["object"], image=image,
                bodies=proofs, physical_begin=begin["index"], physical_end=end["index"],
                continuous_physical_acquisitions=1, completed_foreign_jit_bodies=2)


class SpinBatchCases:
    def __init__(self, command, wait, observations, has, check_context, typed_unlock, retirement):
        self.command, self.wait, self.observations = command, wait, observations
        self.has, self.check_context = has, check_context
        self.typed_unlock, self.retirement = typed_unlock, retirement

    def round(self, image):
        start = len(self.observations())
        self.command("scene 0")
        _, ready = self.wait(lambda v: int(v["ready"], 16) == 31, "spin-batch-ready")
        tasks = [int(ready[f"role{i}"], 16) for i in range(5)]
        self.command("go 0")
        self.wait(lambda v: int(v["held"], 16) & 1, "spin-batch-holder")
        for role in (2, 3, 4):
            self.command(f"go {role}")
            self.wait(lambda v, role=role: int(v["queued"], 16) & (1 << role),
                      f"spin-batch-queue-{role}")
        # The independent B holder supplies no source body and no A history.
        self.command("release 1")
        self.command("go 1")
        self.command("release 0")
        raw, final = self.wait(lambda v: int(v["finished"]) == 5, "spin-batch-finished")
        self.check_context(final, 5)
        if (any(int(final[key]) for key in ("errors", "core_errors", "origin_errors", "overflow"))
                or any(int(final[key]) != value for key, value in
                       (("completed", 5), ("calls", 3), ("a", 3), ("b", 0), ("locks_clear", 1)))):
            raise AssertionError("spin batch source effects, original contexts or drain differ")
        rows = self.observations()[start:]
        queued = [row for row in rows if self.has(row, "ENQUEUE")
                  and row["task"] == tasks[2] and row["origin"] == tasks[2]]
        if not queued or not queued[0]["related"]:
            raise AssertionError("combiner warmup did not genuinely enter behind a predecessor")
        proof = continuous_pair(rows, self.has, self.typed_unlock, image, tasks, self.retirement)
        self.command("stop")
        return dict(start=start, end=start+len(rows), status=raw, proof=proof,
                    contended_combiner_enqueue=queued[0]["index"])

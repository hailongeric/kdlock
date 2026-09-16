"""Exact real-queue contract for the bounded two-attempt readmission test."""

from itertools import pairwise


def readmission_chain(links, placement, lock):
    cpus = placement["role_cpus"]
    head = 3 + 4 * placement.get("readmit_layer", 3)
    selected = [row for row in links if row["lock"] == lock]
    assert len(selected) <= 4
    if len(selected) < 4:
        return None
    by_cpu = {int(row["cpu"]): row for row in selected}
    assert len(by_cpu) == 4
    assert set(by_cpu) in (
        {cpus[18], cpus[19], cpus[head - 4], cpus[head + 2]},
        {cpus[18], cpus[19], cpus[head - 3], cpus[head + 2]},
    )
    lead, prefix, tail = (by_cpu[cpus[i]] for i in (18, 19, head + 2))
    request = next(row for row in selected if row not in (lead, prefix, tail))
    chain = [lead, prefix, request, tail]
    assert int(lead["previous_cpu"]) in (cpus[head], cpus[head + 1])
    for left, right in pairwise(chain):
        assert all(
            right["previous" + suffix] == left[key]
            for suffix, key in (("", "node"), ("_task", "task"), ("_cpu", "cpu"))
        )
    assert len({lead["previous"], *(row["node"] for row in chain)}) == 5
    assert len({lead["previous_task"], *(row["task"] for row in chain)}) == 5
    assert int(lead["previous_task"]) > 0 and all(int(row["task"]) > 0 for row in chain)
    assert all(int(row["node"], 16) for row in chain) and int(lead["previous"], 16)
    return dict(zip(("lead", "prefix", "request", "tail"), chain))


def validate_readmission(rows, placement, locks, pid, starts):
    """Validate the extra real attempt before passing the last one to the core."""
    count = placement["readmit"]
    layer = placement.get("readmit_layer", 3)
    nodes = placement["role_nodes"]
    links = rows("kd_defer link")
    assert all(row["lock"] == locks[layer] for _, row in links)
    observer_at, observer = rows("kd_deep observe")[0]
    late = [(at, row) for at, row in links if row["task"] == observer["task"]]
    initial = [(at, row) for at, row in links if row["task"] != observer["task"]]
    assert len(initial) == 4 and len(late) <= 1
    chain = readmission_chain([row for _, row in initial], placement, locks[layer])
    assert chain
    lead, prefix, request = (chain[key] for key in ("lead", "prefix", "request"))
    assert request["task"] == pid
    assert len(starts) == 4
    first, second = starts[layer - 1][1], starts[layer][1]
    assert first["outer"] == second["outer"] == locks[layer]
    assert first["parent_outer"] == second["parent_outer"] == locks[layer - 1]
    assert first["ip"] == second["ip"] != first["entry"]
    assert first["entry"] == second["entry"] == starts[0][1]["entry"]
    assert first["task"] == second["task"] == pid
    assert first["cpu"] == lead["previous_cpu"] and second["cpu"] == prefix["cpu"]
    assert first["owner_task"] != second["owner_task"]
    assert starts[layer - 1][0] < starts[layer][0]
    if late:
        at, row = late[0]
        tail = chain["tail"]
        assert layer < 3 and observer["comm"] == "klock_test"
        assert starts[layer][0] < at < observer_at
        assert row == {
            "lock": locks[layer],
            "node": row["node"],
            "task": observer["task"],
            "cpu": observer["cpu"],
            "previous": tail["node"],
            "previous_task": tail["task"],
            "previous_cpu": tail["cpu"],
        }
        assert int(row["node"], 16) and row["node"] not in {
            lead["previous"],
            *(item["node"] for item in chain.values()),
        }
    appends, splices = rows("kd_defer append"), rows("kd_defer splice")
    assert len(appends) == len(splices) == 1
    assert not rows("kd_defer restore") and not rows("kd_defer buffered")
    assert not rows("kd_defer buffer summary") and not rows("kd_deep follower")
    assert not rows("kd_deep deferred")
    append_at, append = appends[0]
    splice_at, splice = splices[0]
    assert append == {
        "lock": locks[layer],
        "owner": lead["previous_task"],
        "cpu": first["cpu"],
        "socket": str(nodes[3 + 4 * layer]),
        "request": lead["node"],
        "request_task": lead["task"],
        "request_cpu": lead["cpu"],
        "node": prefix["node"],
        "task": prefix["task"],
        "node_cpu": prefix["cpu"],
        "node_socket": str(nodes[19]),
        "head": prefix["node"],
        "tail": prefix["node"],
    }
    assert splice == {
        "lock": locks[layer],
        "owner": lead["previous_task"],
        "cpu": first["cpu"],
        "head": prefix["node"],
        "tail": prefix["node"],
        "head_task": prefix["task"],
        "head_cpu": prefix["cpu"],
        "next": request["node"],
        "next_task": pid,
        "next_cpu": request["cpu"],
        "outer": "0",
        "linked": "1",
    }
    assert (
        max(at for at, _ in initial)
        < append_at
        < starts[layer - 1][0]
        < splice_at
        < starts[layer][0]
    )
    attempts = rows("kd_readmit attempt")
    assert len(attempts) == 2
    for i, (_, row) in enumerate(attempts):
        start = (first, second)[i]
        refused = i < count
        assert row == {
            "index": str(i),
            "cpu": start["cpu"],
            "owner": start["owner_task"],
            "head": prefix["node"] if i == 0 else "0",
            "tail": prefix["node"] if i == 0 else "0",
            "initial": "1",
            "cancelled": str(int(refused)),
            "ended": "1",
            "executed": str(int(not refused)),
            "ret": "2" if refused else "4",
        }
    summary = rows("kd_readmit summary")
    assert len(summary) == 1
    witness = summary[0][1]
    parents = [
        row
        for _, row in rows("kd_spin outer release")
        if row["outer"] == locks[layer - 1]
    ]
    assert len(parents) == 1
    parent = parents[0]
    assert witness == {
        "refusals": str(count),
        "attempts": "2",
        "task": pid,
        "entry": first["entry"],
        "ip": first["ip"],
        "sp": witness["sp"],
        "lock": locks[layer],
        "outer": locks[layer - 1],
        "node": request["node"],
        "cancelled": str(count),
        "returned": "1",
        "ret": "2" if count == 2 else "3",
        "cpu": parent["cpu"],
        "owner": parent["owner_task"],
        "finished": "1",
        "end": "4",
        "return_valid": "1",
        "end_valid": "1",
        "unexpected": "0",
        "valid": "1",
    }
    assert int(witness["sp"], 16)
    assert witness["cpu"] == request["cpu"]
    following = rows("kd_readmit follow")
    if count == 2 and layer < 3:
        assert len(following) == 1
        follow = following[0][1]
        start = starts[layer + 1][1]
        assert follow == {
            "count": "1",
            "outer": locks[layer + 1],
            "ip": start["ip"],
            "sp": follow["sp"],
            "cpu": start["cpu"],
            "owner": start["owner_task"],
            "depth": str(layer + 1),
            "valid": "1",
        }
        assert int(follow["sp"], 16) and start["parent_outer"] == locks[layer - 1]
        assert follow["owner"] != witness["owner"]
    else:
        assert not following
    assert all(row["jit_disabled"] == "0" for _, row in rows("kd_spin lock stats"))
    ready = rows("kd_deep readmit")
    assert len(ready) == 1 and ready[0][1] == {"ready": "1", "valid": "1"}
    # No normalization until the discarded, unexecuted attempt and real
    # prefix publication are proven. The usual owner/RPC/drain oracle follows.
    return starts[: layer - 1] + starts[layer:], witness

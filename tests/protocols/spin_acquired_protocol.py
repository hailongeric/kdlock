"""Match a checked local spin acquisition to its post-CALL native suffix.

This log oracle does not prove full hardware registers, flags or arbitrary
fault recovery. The caller separately checks artifacts and exact CS records.
"""

import argparse
import json
import re
from pathlib import Path

from native_register_protocol import number, rows


def validate_queued(text, point, statuses):
    """Require actual private contention and native ownership, not a busy L
    that can still take the private FAST path. CPU barriers do not set results.
    """

    def one(label):
        found = rows(text, "kd_acquired " + label + ":")
        assert len(found) == 1, ("missing/duplicate queue witness", label)
        return found[0]

    queued, resumed = one("queued"), one("resumed")
    finish, trailer, stats = one("finish"), one("trailer"), one("stats")
    assert set(stats) == {
        "prepared",
        "prefix",
        "suffix",
        "completed",
        "queued",
        "trailer",
        "failures",
    }
    assert all(
        number(value) == (0 if key == "failures" else 1) for key, value in stats.items()
    )
    for row in (queued, resumed, finish):
        assert number(row["task"]) == point["task"] and number(row["prefix"]) == 1
    for row in (queued, resumed, trailer):
        assert number(row["valid"]) == 1
    assert number(queued["waiters"]) == 2 and number(queued["cpu"]) == 1
    assert number(queued["a_owner"], 16) == point["owner"]
    assert number(queued["b_owner"], 16) not in (0, point["owner"])
    assert number(resumed["cpu"]) == 0 and number(resumed["suffix"]) == 1
    assert (
        number(resumed["a_owner"], 16)
        == number(resumed["b_owner"], 16)
        == point["owner"]
    )
    assert number(resumed["waiter"], 16) not in (
        0,
        point["owner"],
        number(queued["b_owner"], 16),
    )
    assert number(finish["suffix"]) == number(finish["completed"]) == 1
    assert (
        number(trailer["cpu"]) == 2
        and number(trailer["prefix"]) == number(trailer["suffix"]) == 1
    )
    assert number(trailer["owner"], 16) not in (
        0,
        point["owner"],
        number(queued["b_owner"], 16),
    )
    roles = rows(text, "kd_acquired role:")
    assert len(roles) == 6 and {number(r["role"]) for r in roles} == {1, 2, 3, 4, 6, 8}
    tasks = {number(r["role"]): number(r["task"]) for r in roles}
    assert all(number(r["cpu"]) == number(r["role"]) for r in roles)
    assert len({point["task"], *tasks.values()}) == 7
    assert tasks[1] == number(queued["holder"]) and tasks[2] == number(trailer["task"])
    status = [line.split("\t") for line in statuses.splitlines()]
    assert len(status) == 7 and {int(r) for r, _ in status} == {0, 1, 2, 3, 4, 6, 8}
    assert all(value == "0" for _, value in status), "a queued role failed to join"
    assert re.search(
        r"spin JIT injected failure after nested lock=\w+ outer=\w+ val=\w+ kind=2\b",
        text,
    )
    assert len(rows(text, "kd_native begin:")) == 1
    pid = point["task"]
    assert (
        text.index("kd_acquired queued:")
        < text.index("reason=SPIN_ACQUIRED_NATIVE")
        < text.index("kd_acquired resumed:")
    )
    assert text.index("kd_acquired resumed:") < text.index(
        f"kd_native ack: task={pid} "
    )
    assert text.index("kd_acquired resumed:") < text.index("kd_acquired trailer:")
    assert text.rindex(f"kd_native ack: task={pid} ") < text.index(
        "kd_acquired finish:"
    )


def validate(text, outer, inner, target, *, queued=False, statuses=""):
    assert outer > 0 and inner > 0 and target > 0 and outer != inner
    marker = "reason=SPIN_ACQUIRED_NATIVE "
    checkpoints = rows(text, marker)
    assert len(checkpoints) == 1, "missing/duplicate acquisition checkpoint"
    row = checkpoints[0]
    assert set(row) == {
        "entry",
        "target",
        "lock",
        "ip",
        "sp",
        "call_sp",
        "return",
        "owner",
        "task",
    }
    point = {}
    for key, value in row.items():
        if key == "task":
            point[key] = number(value)
        else:
            assert value.startswith("0x"), "unprefixed checkpoint address"
            point[key] = number(value[2:], 16)
        assert point[key] > 0
    assert point["target"] == target and point["lock"] == inner
    assert point["ip"] == point["return"] != target
    assert point["sp"] == point["call_sp"] + 8, "CALL was replayed or advanced twice"
    injected = re.findall(
        r"spin JIT injected failure after nested lock=([0-9a-f]+) outer=([0-9a-f]+)",
        text,
    )
    assert len(injected) == 1 and tuple(int(v, 16) for v in injected[0]) == (
        inner,
        outer,
    )
    prefix, suffix = text.split(marker)
    assert "spin JIT injected failure after nested lock=" in prefix
    assert any(
        number(w["entry"], 16) == point["entry"]
        and number(w["lock"], 16) == outer
        and number(w["body"]) == 1
        for w in rows(prefix, "JIT body witness:")
    ), "no matching returned JIT prefix"
    begins = rows(text, "kd_native begin:")
    matches = [b for b in begins if number(b["task"]) == point["task"]]
    assert len(matches) == 1, "checkpoint has no unique native frame"
    begin = matches[0]
    for key, value in {
        "outer": outer,
        "entry": point["entry"],
        "ip": point["ip"],
        "sp": point["sp"],
    }.items():
        assert number(begin[key], 16) == value, ("wrong native packet", key)
    assert all(
        number(begin[k]) == v
        for k, v in {"held": 2, "mutex": 0, "outer_released": 0, "remaining": 2}.items()
    ), "acquired B was dropped from the ledger"
    pid = str(point["task"])
    assert f"kd_native begin: task={pid} " in suffix
    acks = [a for a in rows(suffix, "kd_native ack:") if a["task"] == pid]
    assert [
        (number(a["lock"], 16), number(a["mutex"]), number(a["last_spin"]))
        for a in acks
    ] == [(inner, 0, 0), (outer, 0, 1)], (
        "missing/replayed/out-of-order owner acknowledgment"
    )
    complete = [c for c in rows(suffix, "kd_native complete:") if c["task"] == pid]
    assert len(complete) == 1 and number(complete[0]["outer"], 16) == outer
    assert number(complete[0]["mutex"]) == 0
    assert suffix.index(f"kd_native begin: task={pid} ") < suffix.index(
        f"kd_native ack: task={pid} "
    )
    stats = rows(text, "kd_native stats:")
    assert len(stats) == 1
    assert number(stats[0]["started"]) == number(stats[0]["completed"]) == len(begins)
    assert number(stats[0]["unlocks"]) == len(rows(text, "kd_native ack:")) >= 2
    if queued:
        validate_queued(text, point, statuses)
    else:
        assert not statuses, "role statuses require a queued case"
    return {
        "task": point["task"],
        "entry": hex(point["entry"]),
        "post_call_ip": hex(point["ip"]),
        "post_call_sp": hex(point["sp"]),
        "checked_owner": hex(point["owner"]),
        "owner_acks": 2,
        "native_frames": len(begins),
        "full_registers_checked": False,
        "queue_owner_checked": queued,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    for name in ("outer", "inner", "target"):
        parser.add_argument(name, type=lambda value: int(value, 16))
    parser.add_argument("--queued", action="store_true")
    parser.add_argument("--statuses", type=Path)
    args = parser.parse_args()
    assert args.queued == bool(args.statuses), "queued/statuses must be used together"
    print(
        json.dumps(
            validate(
                args.log.read_text(),
                args.outer,
                args.inner,
                args.target,
                queued=args.queued,
                statuses=args.statuses.read_text() if args.statuses else "",
            )
        )
    )


if __name__ == "__main__":
    main()

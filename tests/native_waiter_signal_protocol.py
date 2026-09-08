"""Match a signalled native waiter to its actual JIT prefix and final owner ACK.

Only ordinary, uninterruptible mutex_lock is covered. A fatal client exit alone
is not success: every preceding store, acquisition and acknowledgement remains
mandatory. This parser checks evidence, not arbitrary signal/RCU schedules.
"""

import argparse
import csv
import io
import json
import re
from pathlib import Path


def validate(text, client, statuses, signum):
    assert signum in (9, 10)

    def rows(source, name):
        return [
            (match.start(), dict(re.findall(r"(\w+)=([-\w]+)", match[1])))
            for match in re.finditer(re.escape(name) + r": ([^\n]+)", source)
        ]

    def one(name, source=text):
        found = rows(source, name)
        assert len(found) == 1, (name, found)
        return found[0]

    def expect(fields, **wanted):
        for key, value in wanted.items():
            assert int(fields[key]) == value, (key, fields)

    def address(fields, key):
        return int(fields[key], 16)

    _, entry = one("pending client enter", client)
    pid = int(entry["pid"])
    expect(entry, signal=signum)
    begin_at, begin = one("kd_native begin")
    blocked_at, blocked = one("kd_pending mutex blocked")
    queued_at, queued = one("kd_waiter signal queued")
    acquired_at, acquired = one("kd_pending mutex acquired")
    signal_acquired_at, signal_acquired = one("kd_waiter signal acquired")
    finished_at, finished = one("kd_native complete")
    ack_at, ack = one("kd_native ack")
    complete_at, complete = one("kd_waiter signal complete")
    for packet in (
        begin,
        blocked,
        queued,
        acquired,
        signal_acquired,
        finished,
        ack,
        complete,
    ):
        expect(packet, task=pid)
    expect(begin, held=1, mutex=1, remaining=1, outer_released=0)
    expect(blocked, queued=1, valid=1)
    assert blocked["holder_comm"] == "kd_native"
    owners = [address(blocked, key) for key in ("waiter", "a_owner", "b_owner")]
    assert all(owners) and len(set(owners)) == 3
    for key in ("a_owner", "b_owner"):
        assert address(queued, key) == address(blocked, key)
    fatal = int(signum == 9)
    expect(
        queued,
        signal=signum,
        samples=128,
        pending=1,
        fatal=fatal,
        queued=1,
        before=1,
        called=0,
        after=0,
    )
    expect(acquired, preserved=1)
    assert acquired["waiter"] == blocked["waiter"] == acquired["b_owner"]
    assert acquired["a_owner"] == blocked["a_owner"]
    expect(signal_acquired, signal=signum, pending=1, fatal=fatal)
    expect(finished, mutex=1)
    expect(ack, mutex=1, last_spin=0)
    assert address(begin, "outer") == address(finished, "outer") == address(ack, "lock")
    expect(complete, signal=signum, pending=1, fatal=fatal, before=1, called=1, after=1)
    assert (
        address(complete, "value") == ((int(complete["record"]) + 1) * 3 + 17) ^ 0x5A5A
    )

    pending = list(re.finditer(r"reason=PENDING_LOCK_NATIVE ([^\n]+)", text))
    assert len(pending) == 1
    packet = dict(re.findall(r"(\w+)=([-\w]+)", pending[0][1]))
    expect(packet, task=pid, mutex=1, error=-7, outer_released=0)
    assert address(packet, "entry") == address(begin, "entry")
    assert (
        address(packet, "target")
        == address(begin, "ip")
        == address(packet, "staged_ip")
    )
    assert address(packet, "sp") == address(begin, "sp") == address(packet, "staged_sp")
    assert address(packet, "return") != 0
    body = [
        at
        for at, fields in rows(text, "JIT body witness")
        if address(fields, "entry") == address(begin, "entry")
        and address(fields, "lock") == address(begin, "outer")
        and int(fields["body"]) == 1
        and at < pending[0].start()
    ]
    assert body, "matching returned JIT body witness is required"
    order = [
        pending[0].start(),
        begin_at,
        blocked_at,
        queued_at,
        acquired_at,
        signal_acquired_at,
        finished_at,
        ack_at,
        complete_at,
    ]
    assert order == sorted(order), "signal must not shortcut B or the final owner ACK"
    _, summary = one("kd_waiter signal stats")
    expect(
        summary,
        signal=signum,
        delivered=1,
        samples=128,
        acquired=1,
        completed=1,
        failures=0,
    )
    _, native = one("kd_native stats")
    expect(native, started=1, completed=1, unlocks=1)
    _, tasks = one("kd_mutex tasks")
    expect(tasks, active_tasks=0, task_alloc_failure=0)
    assert "kd_waiter signal error:" not in text

    exits = list(csv.reader(io.StringIO(statuses), delimiter="\t"))
    assert len(exits) == 7 and all(len(row) == 2 for row in exits)
    exits = [(int(role), int(status)) for role, status in exits]
    assert sorted(role for role, _ in exits) == list(range(7))
    for role, status in exits:
        assert status == (137 if role == 0 and fatal else 0), (role, status)
    returned = rows(client, "pending client return")
    if fatal:
        assert not returned, "SIGKILL must prevent the userspace ioctl return"
    else:
        assert len(returned) == 1
        expect(returned[0][1], pid=pid, signal=signum, ret=0, errno=0, signals=1)
    return {
        "signal": signum,
        "task": pid,
        "samples": 128,
        "jit": True,
        "owner_acks": 1,
        "fatal_exit": bool(fatal),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmesg", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--statuses", type=Path, required=True)
    parser.add_argument("--signal", type=int, choices=(9, 10), required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate(
                args.dmesg.read_text(),
                args.client.read_text(),
                args.statuses.read_text(),
                args.signal,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

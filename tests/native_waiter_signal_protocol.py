"""Match a signalled native waiter to its actual JIT prefix and final owner ACK.

Ordinary B must acquire; native interruptible/killable B may acquire or cancel
in a release race. Cancellation must skip B. A fatal client exit alone is never
success. Both paths retain JIT stores and the final owner ACK; this is bounded
evidence, not arbitrary signal/RCU schedule coverage.
"""

import argparse
import csv
import errno
import io
import json
import re
from pathlib import Path


def validate(
    text,
    client,
    statuses,
    signum,
    api=0,
    target=None,
    publication=None,
    race=None,
    expected="either",
):
    assert (api, signum) in {(0, 9), (0, 10), (1, 10), (2, 9)}
    assert expected in ("either", "acquired", "cancelled")
    assert race is not None or expected == "either"

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

    def completed_record(fields):
        expect(fields, before=1, called=1, after=1)
        assert address(fields, "value") == (
            ((int(fields["record"]) + 1) * 3 + 17) ^ 0x5A5A
        )

    # The race's actual API return selects its oracle, never the requested bias.
    cancelled = bool(api)
    if race is not None:
        assert api in (1, 2)
        result_at, result = one("kd_waiter race result")
        assert int(result["ret"]) in (0, -errno.EINTR)
        cancelled = int(result["ret"]) != 0
        assert expected == "either" or cancelled == (expected == "cancelled")

    _, entry = one("pending client enter", client)
    pid = int(entry["pid"])
    expect(entry, signal=signum)
    begin_at, begin = one("kd_native begin")
    blocked_at, blocked = one("kd_pending mutex blocked")
    finished_at, finished = one("kd_native complete")
    ack_at, ack = one("kd_native ack")
    complete_at, complete = one("kd_waiter signal complete")
    for packet in (
        begin,
        blocked,
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
    fatal = int(signum == 9)
    expect(finished, mutex=1)
    expect(ack, mutex=1, last_spin=0)
    assert address(begin, "outer") == address(finished, "outer") == address(ack, "lock")
    expect(complete, signal=signum)
    if race is None or cancelled:
        expect(complete, pending=1, fatal=fatal)
    else:
        assert int(complete["pending"]) in (0, 1)
        assert int(complete["fatal"]) in (0, 1)
    completed_record(complete)
    if target is not None:
        assert address(begin, "ip") == target

    pending = list(re.finditer(r"reason=PENDING_LOCK_NATIVE ([^\n]+)", text))
    samples = 0 if api else 128
    if not api:
        queued_at, queued = one("kd_waiter signal queued")
        acquired_at, acquired = one("kd_pending mutex acquired")
        signal_acquired_at, signal_acquired = one("kd_waiter signal acquired")
        for fields in (queued, acquired, signal_acquired):
            expect(fields, task=pid)
        for key in ("a_owner", "b_owner"):
            assert address(queued, key) == address(blocked, key)
        expect(
            queued,
            signal=signum,
            samples=samples,
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
        assert not rows(text, "kd_waiter signal cancelled")
        assert not rows(text, "kd_waiter signal held-after-ack")
        assert len(pending) == 1
        packet = dict(re.findall(r"(\w+)=([-\w]+)", pending[0][1]))
        expect(packet, task=pid, mutex=1, error=-errno.E2BIG, outer_released=0)
        assert address(packet, "entry") == address(begin, "entry")
        assert (
            address(packet, "target")
            == address(begin, "ip")
            == address(packet, "staged_ip")
        )
        assert (
            address(packet, "sp")
            == address(begin, "sp")
            == address(packet, "staged_sp")
        )
        assert address(packet, "return") != 0
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
    else:
        # A real ordinary miss must target the native API, not an injected
        # lock-resource error or a helper that hides the API from admission.
        assert not pending and target is not None and publication is not None
        assert address(begin, "sp") != 0
        entries = [
            e for e in publication if address(e, "entry") == address(begin, "entry")
        ]
        assert len(entries) == 1
        entry = entries[0]
        expect(entry, pid=0, kind=2, status=1)
        assert address(entry, "target") == target and address(entry, "code")
        assert int(entry["tgid"]) > 0
        if race is not None:
            ready_at, ready = one("kd_waiter race ready")
            expect(ready, task=pid, signal=signum, api=api)
            for key in ("a_owner", "b_owner"):
                assert address(ready, key) == address(blocked, key)
            owner_pid = int(ready["owner_task"])
            assert owner_pid > 0 and owner_pid != pid
            expect(result, task=pid, api=api, queued=0, before=1, called=0, after=0)
            assert result["record"] == complete["record"]
            assert address(result, "value") == (int(result["record"]) + 1) * 3
            for key in ("waiter", "a_owner"):
                assert address(result, key) == address(blocked, key)
            assert (address(result, "b_owner") == owners[0]) == (not cancelled)
            assert int(result["pending"]) in (0, 1) and int(result["fatal"]) in (0, 1)
            unlocks = rows(text, "kd_waiter race unlock")
            assert len(unlocks) == 2
            (unlock_at, unlock), (released_at, released) = unlocks
            expect(unlock, done=0, task=owner_pid, waiter=pid)
            expect(released, done=1, task=owner_pid, waiter=pid)
            assert address(unlock, "owner") == address(blocked, "b_owner")
            assert ready_at < unlock_at < released_at
            assert 0 < int(unlock["ns"]) < int(released["ns"])
            assert race["pid"] == pid and race["signal"] == signum
            assert -50000 <= race["offset_us"] <= 50000
            trigger = race["trigger"]
            for key, cpu in (("signal", 7), ("release", 9)):
                row = trigger[key]
                assert row["cpu"] == cpu and 0 < row["before_ns"] <= row["after_ns"]
            expect(trigger["signal"], pid=pid, signum=signum, pidfd=1)
            expect(trigger["release"], written=2)
            assert trigger["release"]["before_ns"] <= int(unlock["ns"])
            for event in (
                "kd_waiter signal sent",
                "kd_waiter signal queued",
                "kd_waiter signal held-after-ack",
            ):
                assert not rows(text, event)
            if cancelled:
                expect(result, pending=1, fatal=fatal)
                assert int(result["ns"]) >= trigger["signal"]["before_ns"]
                cancelled_at, failed = one("kd_waiter signal cancelled")
                expect(
                    failed,
                    task=pid,
                    api=api,
                    signal=signum,
                    ret=-errno.EINTR,
                    pending=1,
                    fatal=fatal,
                    queued=0,
                )
                completed_record(failed)
                assert failed["record"] == complete["record"]
                assert failed["value"] == complete["value"]
                assert address(failed, "a_owner") == address(blocked, "a_owner")
                assert address(failed, "b_owner") != owners[0]
                assert not rows(text, "kd_pending mutex acquired")
                assert not rows(text, "kd_waiter signal acquired")
                middle = [result_at, cancelled_at]
            else:
                assert int(result["ns"]) >= int(unlock["ns"])
                acquired_at, acquired = one("kd_pending mutex acquired")
                seen_at, seen = one("kd_waiter signal acquired")
                expect(acquired, task=pid, preserved=1)
                assert acquired["waiter"] == blocked["waiter"] == acquired["b_owner"]
                assert acquired["a_owner"] == blocked["a_owner"]
                expect(seen, task=pid, signal=signum)
                assert int(seen["pending"]) in (0, 1) and int(seen["fatal"]) in (0, 1)
                assert not rows(text, "kd_waiter signal cancelled")
                middle = [unlock_at, acquired_at, result_at, seen_at]
            # A cancelled request can ACK before B is unlocked. An acquired one
            # can ACK before B owner's post-unlock log; neither is a protocol error.
            order = [
                begin_at,
                blocked_at,
                ready_at,
                *middle,
                finished_at,
                ack_at,
                complete_at,
            ]
        else:
            sent_at, sent = one("kd_waiter signal sent")
            cancelled_at, failed = one("kd_waiter signal cancelled")
            held_at, held = one("kd_waiter signal held-after-ack")
            for fields in (sent, failed, held):
                expect(fields, task=pid, api=api)
            expect(sent, signal=signum)
            expect(
                failed,
                signal=signum,
                ret=-errno.EINTR,
                pending=1,
                fatal=fatal,
                queued=0,
            )
            completed_record(failed)
            assert failed["record"] == complete["record"]
            assert failed["value"] == complete["value"]
            for key in ("a_owner", "b_owner"):
                assert (
                    address(sent, key) == address(failed, key) == address(blocked, key)
                )
            expect(held, completed=1)
            assert address(held, "b_owner") == address(blocked, "b_owner")
            for event in (
                "kd_waiter signal queued",
                "kd_pending mutex acquired",
                "kd_waiter signal acquired",
            ):
                assert not rows(text, event), "cancelled B must not report acquisition"
            order = [
                begin_at,
                blocked_at,
                sent_at,
                cancelled_at,
                finished_at,
                ack_at,
                complete_at,
                held_at,
            ]

    if race is None:
        for event in (
            "kd_waiter race ready",
            "kd_waiter race result",
            "kd_waiter race unlock",
        ):
            assert not rows(text, event)

    body = [
        at
        for at, fields in rows(text, "JIT body witness")
        if address(fields, "entry") == address(begin, "entry")
        and address(fields, "lock") == address(begin, "outer")
        and int(fields["body"]) == 1
    ]
    assert len(body) == 1 and body[0] < order[0], "exact JIT prefix witness is required"
    assert order == sorted(order), "signal must not shortcut B or the final owner ACK"
    _, summary = one("kd_waiter signal stats")
    expect(
        summary,
        signal=signum,
        delivered=int(race is None),
        samples=samples,
        acquired=int(not cancelled),
        completed=1,
        failures=0,
        api=api,
        cancelled=int(cancelled),
        held_ack=int(bool(api) and race is None),
        race=int(race is not None),
        phase=3 if race is not None else 0,
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
    ioctl = rows(client, "pending client ioctl")
    if race is not None:
        assert len(ioctl) <= 1
        if not fatal:
            assert len(ioctl) == 1
        if ioctl:
            expect(ioctl[0][1], pid=pid, signal=signum, ret=0, errno=0)
            assert int(ioctl[0][1]["signals"]) in (0, 1)
    else:
        assert not ioctl
    if fatal:
        assert not returned, "SIGKILL must prevent the userspace ioctl return"
    else:
        assert len(returned) == 1
        expect(returned[0][1], pid=pid, signal=signum, ret=0, errno=0, signals=1)
    return {
        "signal": signum,
        "api": api,
        "task": pid,
        "samples": samples,
        "cancelled": cancelled,
        "race": race is not None,
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
    parser.add_argument("--api", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument("--target", type=lambda value: int(value, 16))
    parser.add_argument("--publication", type=Path)
    parser.add_argument("--race-trigger", type=Path)
    parser.add_argument(
        "--expect", choices=("either", "acquired", "cancelled"), default="either"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            validate(
                args.dmesg.read_text(),
                args.client.read_text(),
                args.statuses.read_text(),
                args.signal,
                args.api,
                args.target,
                json.loads(args.publication.read_text()) if args.publication else None,
                json.loads(args.race_trigger.read_text())
                if args.race_trigger
                else None,
                args.expect,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

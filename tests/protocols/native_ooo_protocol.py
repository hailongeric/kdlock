"""Verify original-waiter A-before-B native unlocks, not executor log ordering."""

import argparse
import re
from collections import defaultdict
from pathlib import Path


def validate(
    text,
    mutex,
    expected_records,
    outer,
    inner,
    probe,
    after_outer=False,
    pending_after_outer=False,
    dependency=0,
):
    after_outer = after_outer or pending_after_outer
    expected_acks = 7 if pending_after_outer else 2 - int(after_outer)

    def fields(line):
        return dict(re.findall(r"(\w+)=(-?\w+)", line))

    def rows(label):
        return [
            (match.start(), fields(match[1]))
            for match in re.finditer(re.escape(label) + r": ([^\n]*)", text)
        ]

    def expect(row, **values):
        assert all(row.get(key) == str(value) for key, value in values.items()), (
            row,
            values,
        )

    checkpoints = defaultdict(list)
    for position, row in rows("kd_ooo checkpoint"):
        checkpoints[int(row["record"])].append((position, row))
    assert len(checkpoints) == expected_records, checkpoints
    begins = rows("kd_native begin")
    assert begins, "no actual JIT/native continuation"
    by_task = {row["task"]: (position, row) for position, row in begins}
    assert len(by_task) == len(begins), "unexpected multiple frames per request"
    borrowed_tasks = set()
    all_acks = rows("kd_native ack")
    backend = "mutex" if mutex else "spin"
    releases = rows(f"kd_{backend} outer release")
    assert len(releases) == len(begins), releases
    assert not rows(f"kd_{'spin' if mutex else 'mutex'} outer release")
    children = rows("kd_ooo pending lock")
    pending = [
        (m.start(), fields(m[1]))
        for m in re.finditer(r"reason=PENDING_LOCK_NATIVE ([^\n]*)", text)
    ]
    if pending_after_outer:
        assert len(children) == 7 * expected_records
        assert len(pending) == len(begins)
    else:
        assert not children and not pending
    for record, events in checkpoints.items():
        assert len(events) == 3 - int(after_outer), events
        task = events[0][1]["task"]
        value = record + 1
        if after_outer:
            value = ((value * 17) ^ value) & ((1 << 64) - 1)
        for phase, (_, row) in enumerate(events, start=int(after_outer)):
            value = ((value * 17) ^ (record + phase + 1)) & ((1 << 64) - 1)
            expect(row, phase=phase, task=task, mutex=int(mutex), irq=0, valid=1)
            assert int(row["value"], 16) == value, row
            assert int(row["waiter"], 16), row
            count = int(row["preempt"])
            assert (count == 0) == (mutex or phase == 2), row
        acks = [(position, row) for position, row in all_acks if row["task"] == task]
        owned = [item for item in children if int(item[1]["record"]) == record]
        if pending_after_outer:
            assert len(owned) == 7
            addresses = [row["lock"] for _, row in owned]
            assert len(set(addresses + [outer, inner])) == 9
            for index, (at, row) in enumerate(owned):
                expect(row, task=task, mutex=int(mutex), index=index, valid=1)
                assert int(row["lock"], 16) and at < events[0][0]
                if mutex:
                    expect(row, preempt=0)
                    expected_owner = events[0][1]["waiter" if index == 6 else "b"]
                    assert row["owner"] == expected_owner and int(expected_owner, 16)
                else:
                    assert int(row["word"], 16) & 0xFF in (1, 3)
                    expect(row, preempt=2 if task in by_task else 8)
            if not mutex:
                expect(events[0][1], preempt=2 if task in by_task else 8)
        if task not in by_task:
            assert not acks, "native-only request sent a borrowed unlock"
            continue
        borrowed_tasks.add(task)
        begin_at, begin = by_task[task]
        expect(
            begin,
            outer=outer,
            held=8 if pending_after_outer else 2,
            mutex=int(mutex),
            ip=probe,
        )
        expect(begin, outer_released=int(after_outer), remaining=expected_acks)
        assert len(acks) == expected_acks, acks
        expect(acks[-1][1], lock=inner, mutex=int(mutex), last_spin=int(not mutex))
        assert events[-2][0] < acks[-1][0] < events[-1][0]
        if after_outer:
            assert begin_at < events[0][0]
        else:
            expect(acks[0][1], lock=outer, mutex=int(mutex), last_spin=0)
            assert begin_at < events[0][0] < acks[0][0] < events[1][0]
        if pending_after_outer:
            failures = [item for item in pending if item[1]["task"] == task]
            assert len(failures) == 1
            at, error = failures[0]
            expect(error, error=-7, mutex=int(mutex), outer_released=1)
            assert int(error["return"], 16)
            for source, dest in (
                ("entry", "entry"),
                ("target", "ip"),
                ("sp", "sp"),
                ("staged_ip", "ip"),
                ("staged_sp", "sp"),
            ):
                assert int(error[source], 16) == int(begin[dest], 16)
            assert at < begin_at < owned[0][0]
            expected_locks = [row["lock"] for _, row in reversed(owned[:6])] + [inner]
            previous = events[0][0]
            for index, (ack_at, ack) in enumerate(acks):
                expect(
                    ack,
                    lock=expected_locks[index],
                    mutex=int(mutex),
                    last_spin=int(index == 6 and not mutex),
                )
                assert previous < ack_at < events[-1][0]
                previous = ack_at
        before, middle = events[0][1], events[-2][1]
        a_key, b_key = ("a", "b") if mutex else ("a_owner", "b_owner")
        assert before[b_key] == middle[b_key]
        assert int(before[b_key], 16) and before[b_key] != before["waiter"]
        release = [item for item in releases if item[1]["task"] == task]
        assert len(release) == 1
        release_at, row = release[0]
        expect(
            row,
            outer=outer,
            owner_task=before[b_key],
            remaining=expected_acks if after_outer else 1,
        )
        assert row["owner"] != task and row["next_task"] != task
        assert middle[a_key] != middle[b_key], "A is still held by B's executor"
        if after_outer:
            assert release_at < begin_at
            if pending_after_outer:
                assert release_at < failures[0][0]
        else:
            assert before[a_key] == before[b_key]
            assert events[0][0] < release_at < acks[0][0]
        if not mutex:
            assert before["preempt"] == middle["preempt"]
            assert before["cpu"] == middle["cpu"]
            for row in (before, middle):
                assert int(row["b"], 16) & 0xFF in (1, 3), row
            if not after_outer:
                assert int(before["a"], 16) & 0xFF in (1, 3), before
            # A may already have a new owner. Never require its old private
            # marker after publication; B's owner and the waiter pin stay fixed.
    assert borrowed_tasks == set(by_task), "unobserved native continuation"
    assert len(all_acks) == expected_acks * len(begins)
    stats = rows("kd_native stats")
    assert len(stats) == 1
    expect(
        stats[0][1], started=len(begins), completed=len(begins), unlocks=len(all_acks)
    )
    stats = rows("kd_ooo stats")
    assert len(stats) == 1
    expect(stats[0][1], checked=expected_records, failures=0)
    witnesses = rows("kd_ooo dependency" if mutex else "kd_ooo spin dependency")
    assert not rows("kd_ooo spin dependency" if mutex else "kd_ooo dependency")
    if dependency:
        assert pending_after_outer and dependency in (1, 2)
        assert len(witnesses) == len(begins) == 1
        at, row = witnesses[0]
        release_at, release = releases[0]
        expect(row, kind=dependency, outer=outer, inner=inner, valid=1, prefix=1)
        if mutex:
            expect(row, b=release["owner_task"])
            assert row["a"] == row["c"] == row["owner_task"] != row["b"]
        else:
            expect(row, b_owner=release["owner_task"], preempt=2, irq=0)
            assert row["owner_task"] != row["b_owner"] != row["waiter"]
            for key in ("a_word", "b_word", "c_word"):
                assert int(row[key], 16) & 0xFF in (1, 3), row
            if dependency == 1:
                expect(row, a_owner=row["owner_task"])
        assert row["owner_task"] != row["waiter"]
        assert row["task"] != row["waiter_pid"] == release["task"]
        child = next(item[1] for item in children if item[1]["index"] == "6")
        assert row["child"] == child["lock"]
        assert release_at < at < children[0][0] < all_acks[-1][0]
        if dependency == 1:
            assert row["task"] == release["next_task"]
            expect(row, comm="klock_test")
        else:
            assert row["task"] != release["next_task"]
            expect(row, comm="kd_native")
    else:
        assert not witnesses
    return len(begins)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("kind", choices=("spin", "mutex"))
    parser.add_argument("records", type=int)
    parser.add_argument("outer")
    parser.add_argument("inner")
    parser.add_argument("probe")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--after-outer", action="store_true")
    group.add_argument("--pending-after-outer", action="store_true")
    parser.add_argument("--dependency", type=int, choices=(1, 2), default=0)
    args = parser.parse_args()
    count = validate(
        args.log.read_text(),
        args.kind == "mutex",
        args.records,
        args.outer,
        args.inner,
        args.probe,
        args.after_outer,
        args.pending_after_outer,
        args.dependency,
    )
    print(
        f"[PASS] native OOO: {count} JIT continuations, "
        f"{'remaining-seven' if args.pending_after_outer else 'B-only' if args.after_outer else 'A/B'} "
        "waiter ACKs and exact records"
    )

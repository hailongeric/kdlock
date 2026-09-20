"""Offline multi-frame validation; protocol details live in adjacent components."""
import argparse
import json
import re
import sys
from pathlib import Path
from mutex_shadow_protocol import validate_shadow_pool

from mutex_parallel_events import (
    rows_in, validate_renamed_waiters, validate_native_peers,
)
from mutex_parallel_signals import (
    verified_client, signal_native_peers, validate_peer_signals, waiter_hold, signal_original_waiters, validate_waiter_signals,
)
from mutex_parallel_pools import (
    validate_code_pool, retired_reload,
)

def validate(
    text,
    published,
    probe,
    first,
    shared_cpu=False,
    after=None,
    pressure=False,
    reload=None,
    code_pool=None,
    native_peers=False,
    shadow_pool=None,
):
    assert first in (0, 1)
    assert not shared_cpu or first == 1
    assert not pressure or shared_cpu
    native_count = 2 - int(shared_cpu)
    # Validate replacement first, then isolate its two native arrivals. A
    # combined capacity/lifetime gate still has only two old JIT frames.
    if reload is not None:
        assert not shared_cpu and not pressure
        text = retired_reload(text, published, first, reload)
    else:
        assert "kd_source reload:" not in text, "unvalidated source replacement"
    capacity = (
        validate_code_pool(text, code_pool, published)
        if code_pool is not None
        else None
    )
    if code_pool is not None:
        assert not shared_cpu and not pressure
    else:
        assert not rows_in(text, "kd_parallel code record"), (
            "unvalidated code-pool workload"
        )
    if native_peers:
        assert not shared_cpu and not pressure
        peers = validate_native_peers(text, first)
        routing = validate_renamed_waiters(text)
    else:
        assert "kd_parallel peer " not in text, "unvalidated native peers"
        assert not rows_in(text, "kd_parallel routed native")
        assert not rows_in(text, "kd_resume rename")
        peers = None
        routing = None
    if shadow_pool is not None:
        assert not shared_cpu and not pressure and code_pool is not None
        shadows = validate_shadow_pool(text, shadow_pool)
    else:
        assert "kd_parallel shadow " not in text, "unvalidated shadow-table pressure"
        shadows = None

    def rows(label):
        return rows_in(text, label)

    def expect(row, **values):
        assert all(row.get(key) == str(value) for key, value in values.items()), (
            row,
            values,
        )

    def number(row, key, base=10):
        assert key in row, (key, row)
        return int(row[key], base)

    def lanes(label):
        items = rows(label)
        assert len(items) == 2, (label, items)
        result = {number(row, "lane"): (at, row) for at, row in items}
        assert set(result) == {0, 1}, (label, result)
        return result

    assert len(published) == 2 and all(item["kind"] == 2 for item in published)
    entries = {item["entry"] for item in published}
    assert len(entries) == len({item["code"] for item in published}) == 2
    assert all(item["entry"] and item["code"] for item in published)
    assert probe and not rows("kd_parallel error")
    assert "reason=PENDING_LOCK_NATIVE" not in text
    assert not rows("kd_mutex outer release")
    arrivals, resumes, done = (
        lanes(f"kd_parallel {label}") for label in ("arrive", "resume", "done")
    )
    begins, bodies, acks, completes = (
        rows(label)
        for label in (
            "kd_native begin",
            "JIT body witness",
            "kd_native ack",
            "kd_native complete",
        )
    )
    assert len(begins) == len(bodies) == len(completes) == native_count
    assert len(acks) == 2 * native_count
    executed = {number(row, "entry", 16) for _, row in begins}
    assert len(executed) == native_count and executed <= entries
    if after is not None:
        # Cross-check the device state against the actual body/lock witnesses;
        # count-only checks could accept the wrong entry remaining NORMAL.
        assert len(after) == 2 and {item["entry"] for item in after} == entries
        before = {item["entry"]: item for item in published}
        for item in after:
            assert item["code"] == before[item["entry"]]["code"]
            assert item["status"] == int(item["entry"] in executed)
            if item["status"] == 1:
                assert item["target"] == probe
    # Distinct live tasks, physical owners, records and mutex pairs rule out a
    # second log referring to the first frame or a waiter unlocking as owner.
    assert len({row["task"] for _, row in arrivals.values()}) == 2
    assert len({row["record"] for _, row in arrivals.values()}) == 2
    assert len(
        {row[key] for _, row in arrivals.values() for key in ("waiter", "owner")}
    ) == 4 - int(shared_cpu)
    assert (
        len({row[key] for _, row in arrivals.values() for key in ("outer", "inner")})
        == 4
    )
    for lane, (arrival_at, arrival) in arrivals.items():
        task = arrival["task"]
        own_begins = [item for item in begins if item[1]["task"] == task]
        own_bodies = [item for item in bodies if item[1]["lock"] == arrival["outer"]]
        own_completes = [item for item in completes if item[1]["task"] == task]
        own_acks = [item for item in acks if item[1]["task"] == task]
        resume_at, resume = resumes[lane]
        done_at, final = done[lane]
        expect(
            arrival,
            before=1,
            held=1,
            called=0,
            after=0,
            cpu=1 if pressure and lane else lane * 4 + 2,
            valid=1,
        )
        for key in ("waiter", "owner", "outer", "inner", "record"):
            assert number(arrival, key, 16)
        prefix = (lane * 8 + 3) * 3 + 17
        assert number(arrival, "value", 16) == prefix
        expect(
            resume,
            task=task,
            owner=arrival["owner"],
            arrived=3,
            done=0 if lane == first else 1 << first,
            valid=1,
        )
        expect(
            final,
            task=task,
            waiter=arrival["waiter"],
            owner=arrival["owner"],
            record=arrival["record"],
            before=1,
            held=1,
            called=1,
            after=1,
            valid=1,
        )
        assert number(final, "value", 16) == prefix ^ 0x5A5A
        assert arrival_at < resume_at < done_at
        if shared_cpu and lane == 1:
            # This waiter never borrowed locks or entered generated code. Its
            # own native mutex owner, not a fabricated ACK, authorizes B/A.
            assert not (own_begins or own_bodies or own_completes or own_acks)
            assert arrival["owner"] == arrival["waiter"]
        else:
            ((begin_at, begin),) = own_begins
            ((body_at, body),) = own_bodies
            ((complete_at, complete),) = own_completes
            expect(
                begin,
                outer=arrival["outer"],
                ip=f"{probe:x}",
                held=2,
                mutex=1,
                cpu=lane * 4 + 1,
                outer_released=0,
                remaining=2,
            )
            assert number(begin, "sp", 16)
            expect(body, entry=begin["entry"], lock=begin["outer"], body=1)
            expect(complete, outer=arrival["outer"], mutex=1)
            assert arrival["owner"] != arrival["waiter"]
            assert len(own_acks) == 2
            for (_, ack), key in zip(own_acks, ("inner", "outer")):
                expect(ack, lock=arrival[key], mutex=1, last_spin=0)
            assert body_at < begin_at < arrival_at
            assert resume_at < own_acks[0][0] < complete_at < own_acks[1][0] < done_at
    # Arrival is inside the native callee while both A/B owners still wait.
    # The first final ACK must precede the second retained-owner observation.
    assert max(at for at, _ in arrivals.values()) < resumes[first][0]
    assert done[first][0] < resumes[1 - first][0] < done[1 - first][0]
    refused, contenders = rows("mutex JIT context busy"), rows("kd_parallel contender")
    if shared_cpu:
        ((refusal_at, refusal),) = refused
        ((contender_at, contender),) = contenders
        expect(
            refusal,
            task=contender["task"],
            waiter=arrivals[1][1]["task"],
            lock=arrivals[1][1]["outer"],
            cpu=1,
        )
        expect(contender, cpu=1, valid=1)
        assert {number(refusal, "entry", 16)} == entries - executed
        assert contender["task"] not in {r["task"] for _, r in arrivals.values()}
        assert number(contender, "owner", 16)
        assert contender["owner"] not in {
            row[key] for _, row in arrivals.values() for key in ("waiter", "owner")
        }
        assert arrivals[0][0] < refusal_at < contender_at < arrivals[1][0]
    else:
        assert not refused and not contenders

    fallbacks = rows("mutex node fallback")
    task_fallbacks = rows("mutex task fallback")
    pressure_done = rows("kd_parallel pressure done")
    if pressure:
        ((fallback_at, fallback),) = fallbacks
        ((task_at, task_fallback),) = task_fallbacks
        assert len(pressure_done) == 2
        finishes = {number(row, "role"): (at, row) for at, row in pressure_done}
        assert set(finishes) == {5, 6}
        expect(fallback, slots="f")
        assert arrivals[0][0] < fallback_at < task_at < refused[0][0]
        for role, refusal_at, refusal in (
            (5, fallback_at, fallback),
            (6, task_at, task_fallback),
        ):
            finish_at, final = finishes[role]
            expect(refusal, task=final["task"], lock=arrivals[1][1]["outer"], cpu=1)
            assert {number(refusal, "entry", 16)} == entries - executed
            expect(
                final,
                owner=final["waiter"],
                outer=arrivals[1][1]["outer"],
                inner=arrivals[1][1]["inner"],
                before=1,
                held=1,
                called=1,
                after=1,
                cpu=1,
                valid=1,
            )
            assert number(final, "value", 16) == ((9 + role) * 3 + 17) ^ 0x5A5A
            assert number(final, "record", 16) and number(final, "waiter", 16)
            assert final["record"] not in {r["record"] for _, r in arrivals.values()}
            assert final["task"] not in {
                *(r["task"] for _, r in arrivals.values()),
                contenders[0][1]["task"],
            }
            assert final["owner"] not in {
                *(r[k] for _, r in arrivals.values() for k in ("waiter", "owner")),
                contenders[0][1]["owner"],
            }
            # Both failed new requests must finish B/A themselves while the
            # old frame still retains A0/B0. A refusal log or aggregate final
            # count cannot substitute for the completed caller's exact record.
            assert refusal_at < finish_at < resumes[0][0]
        for key in ("task", "record", "owner", "waiter"):
            assert len({row[key] for _, row in pressure_done}) == 2
    else:
        assert not fallbacks and not task_fallbacks and not pressure_done
    for lane, (_, row) in lanes("kd_parallel lane").items():
        count = 12004 + 2 * int(pressure and lane == 1)
        digest = 0
        for sequence in range(1, count + 1):
            digest = (digest * 33 + sequence) & ((1 << 64) - 1)
        expect(row, sequence=count, claimed=111 if pressure and lane else 15, a=0, b=0)
        assert number(row, "digest", 16) == digest
    for label, expected in (
        (
            "kd_parallel stats",
            {
                "first": first,
                "shared_cpu": int(shared_cpu),
                "pressure": int(pressure),
                "pressure_done": 3 * int(pressure),
                "arrived": 3,
                "done": 3,
                "failures": 0,
            },
        ),
        (
            "kd_native stats",
            {
                "started": native_count,
                "completed": native_count,
                "unlocks": 2 * native_count,
            },
        ),
        (
            "kd_mutex stats",
            {"context_busy": int(shared_cpu), "node_overflow": int(pressure)},
        ),
        ("kd_mutex tasks", {"active_tasks": 0, "task_alloc_failure": int(pressure)}),
    ):
        (item,) = rows(label)
        expect(item[1], **expected)
    if shared_cpu:
        assert number(rows("kd_mutex stats")[0][1], "multi_slot") >= 1
    assert re.search(r"kd_exec invariant_failures=0\b", text)
    return {
        "first": first,
        "shared_cpu": bool(shared_cpu),
        "pressure": bool(pressure),
        "jit_bodies": native_count,
        "native_frames": native_count,
        "overlapping_native_frames": 0 if shared_cpu else 2,
        "context_refusals": int(shared_cpu),
        "native_node_fallbacks": int(pressure),
        "native_task_fallbacks": int(pressure),
        "owner_acks": 2 * native_count,
        "records": 6 + 2 * int(pressure),
        "transitions": 24008 + 2 * int(pressure),
        "reloaded_native_records": 6 if reload is not None else 0,
        "reloaded_native_transitions": 6 if reload is not None else 0,
        "code_pool": capacity,
        "native_peers": peers,
        "native_routing": routing,
        "shadow_pool": shadows,
    }

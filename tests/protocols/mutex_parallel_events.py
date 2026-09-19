"""Multi-frame events protocol; keep per-role identity and exactly-once checks.

Private implementation of mutex_parallel_protocol. Moving this code does not
change signal authorization, real owner/ACK ordering or evidence acceptance.
"""
import re

def rows_in(text, label):
    return [
        (match.start(), dict(re.findall(r"(\w+)=(\w+)", match[1])))
        for match in re.finditer(re.escape(label) + r": ([^\n]*)", text)
    ]


def validate_renamed_waiters(text):
    """Require a native C unlock between renaming and the borrowed B/A ACKs.

    Matching only aggregate reroutes could hide restored target eligibility or
    a wrong-task unlock. These observations stay inside the original two frames.
    """
    renames = rows_in(text, "kd_resume rename")
    controls = rows_in(text, "kd_parallel routed native")
    arrivals = rows_in(text, "kd_parallel arrive")
    assert len(renames) == 4 and len(controls) == len(arrivals) == 2
    assert {r["lane"] for _, r in controls} == {"0", "1"}
    locks = {r[k] for _, r in arrivals for k in ("outer", "inner")}
    assert len({r["local"] for _, r in controls}) == 2
    assert not locks.intersection(r["local"] for _, r in controls)
    assert {r["task"] for _, r in renames} == {r["task"] for _, r in arrivals}
    for arrival_at, arrival in arrivals:
        task, lane = arrival["task"], arrival["lane"]
        (renamed_at, renamed), (restored_at, restored) = [
            item for item in renames if item[1]["task"] == task
        ]
        ((control_at, control),) = [
            item for item in controls if item[1]["lane"] == lane
        ]
        for row, old, new in (
            (renamed, "klock_test", "kd_renamed"),
            (restored, "kd_renamed", "klock_test"),
        ):
            assert row["old"] == old and row["new"] == new
            assert row["cpu"] == arrival["cpu"] and row["valid"] == "1"
            assert all(
                row[k] == "0"
                for k in ("preempt_before", "preempt_after", "irq_before", "irq_after")
            )
        assert all(
            control[k] == arrival[k]
            for k in ("task", "waiter", "owner", "outer", "inner")
        )
        assert control["local_owner"] == arrival["waiter"]
        assert control["owner"] != control["local_owner"]
        assert int(control["local"], 16) and control["after_owner"] == "0"
        assert control["acquired"] == control["released"] == control["valid"] == "1"
        assert control["comm"] == arrival["comm"] == "kd_renamed"
        ((begin_at, _),) = [
            item for item in rows_in(text, "kd_native begin") if item[1]["task"] == task
        ]
        ((resume_at, resume),) = [
            item
            for item in rows_in(text, "kd_parallel resume")
            if item[1]["task"] == task
        ]
        ((done_at, done),) = [
            item
            for item in rows_in(text, "kd_parallel done")
            if item[1]["task"] == task
        ]
        acks = [
            item for item in rows_in(text, "kd_native ack") if item[1]["task"] == task
        ]
        assert len(acks) == 2 and [r["lock"] for _, r in acks] == [
            arrival["inner"],
            arrival["outer"],
        ]
        assert resume["comm"] == done["comm"] == "kd_renamed"
        assert begin_at < renamed_at < arrival_at < resume_at
        assert max(at for at, _ in arrivals) < control_at < resume_at
        assert resume_at < acks[0][0] < acks[1][0] < done_at < restored_at
    assert max(at for at, _ in controls) < min(
        at for at, _ in rows_in(text, "kd_parallel peer try")
    )
    capacity = rows_in(text, "kd_parallel code record")
    assert not capacity or max(at for at, _ in controls) < min(at for at, _ in capacity)
    return {
        "renamed_waiters": 2,
        "native_acquisitions": 2,
        "native_unlocks": 2,
        "restored_after_acks": 2,
    }


def validate_native_peers(text, first):
    """Match actual Linux B waiters to two retained frames, not kdlock ACKs.

    Both peers cancel an interruptible wait, return to userspace and requeue
    before either old suffix. The first B peer must
    acquire/release while the other frame still retains B; the second follows
    that frame's later resume. Neither peer may become a generated executor.
    """

    def lanes(label):
        rows = rows_in(text, "kd_parallel " + label)
        result = {int(row["lane"]): (at, row) for at, row in rows}
        assert len(rows) == len(result) == 2 and set(result) == {0, 1}
        return result

    def attempts(label):
        rows = rows_in(text, "kd_parallel " + label)
        result = {(int(r["lane"]), int(r["attempt"])): (at, r) for at, r in rows}
        assert len(rows) == len(result) == 4
        assert set(result) == {(lane, attempt) for lane in (0, 1) for attempt in (1, 2)}
        return result

    arrivals, resumes, done, cancelled, acquired, released = (
        lanes(label)
        for label in (
            "arrive",
            "resume",
            "done",
            "peer cancelled",
            "peer acquired",
            "peer released",
        )
    )
    tries, queued = attempts("peer try"), attempts("peer queued")
    assert text.count("kd_parallel peer ") == 15
    tasks = {r["task"] for _, r in tries.values()}
    waiters = {r["waiter"] for _, r in tries.values()}
    assert len(tasks) == len(waiters) == 2
    assert tasks.isdisjoint(r["task"] for _, r in arrivals.values())
    assert waiters.isdisjoint(
        r[key] for _, r in arrivals.values() for key in ("waiter", "owner")
    )
    for lane in (0, 1):
        _, old = arrivals[lane]
        ta, tr = tries[lane, 1]
        qa, q = queued[lane, 1]
        ca, c = cancelled[lane]
        retry_at, retry = tries[lane, 2]
        requeue_at, requeue = queued[lane, 2]
        aa, a = acquired[lane]
        ra, r = released[lane]
        assert max(at for at, _ in arrivals.values()) < ta < qa < resumes[first][0]
        assert resumes[lane][0] < aa < ra and qa < aa
        assert all(tr[k] == old[v] for k, v in (("lock", "inner"), ("owner", "owner")))
        assert tr["comm"] == "kd_native" and tr["result"] == "0"
        assert int(tr["waiter"], 16) and int(tr["task"]) > 0
        assert all(q[k] == tr[k] for k in ("task", "waiter", "lock", "owner"))
        assert q["queued"] == q["matched"] == "1"
        assert (
            max(queued[i, 1][0] for i in (0, 1))
            < ca
            < retry_at
            < requeue_at
            < resumes[first][0]
        )
        assert all(c[k] == tr[k] for k in ("task", "waiter", "lock", "owner"))
        assert c["other_owner"] == arrivals[1 - lane][1]["owner"]
        assert {
            k: c[k]
            for k in (
                "error",
                "pending",
                "fatal",
                "queued",
                "matched",
                "cancelled",
                "acquired",
                "released",
                "valid",
            )
        } == {
            "error": "4",
            "pending": "1",
            "fatal": "0",
            "queued": "0",
            "matched": "0",
            "cancelled": "1",
            "acquired": "0",
            "released": "0",
            "valid": "1",
        }
        assert retry == dict(tr, attempt="2") and requeue == dict(q, attempt="2")
        assert all(a[k] == tr[k] for k in ("task", "waiter", "lock"))
        assert a["owner"] == a["waiter"]
        assert a["other"] == arrivals[1 - lane][1]["inner"]
        assert r["task"] == tr["task"] and r["value"] == a["value"]
        assert int(r["value"], 16) == ((0x700 + lane) * 33 + 17) ^ 0x5A5A
        assert r["acquired"] == r["released"] == "1"
        assert all(row["valid"] == "1" for row in (tr, q, a, r))
        if lane == first:
            assert a["other_owner"] == arrivals[1 - lane][1]["owner"]
            assert a["cross_try"] == "0" and ra < resumes[1 - lane][0]
        else:
            assert a["cross_try"] == "2"
            assert done[first][0] < aa and released[first][0] < aa
    ((_, stats),) = rows_in(text, "kd_parallel peer stats")
    assert stats == {
        "completed": "3",
        "acquired": "2",
        "released": "2",
        "cancelled": "2",
        "valid": "1",
    }
    assert not any(
        r["task"] in tasks
        for label in ("kd_native begin", "kd_native ack", "kd_native complete")
        for _, r in rows_in(text, label)
    )
    return {
        "failed_tries": 5,
        "queued": 4,
        "cancelled": 2,
        "acquired": 2,
        "released": 2,
    }

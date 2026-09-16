# Corrupt/partial log and client-protocol inputs must fail the signal oracle.
# Real signal delivery and Linux mutex exclusion belong to the live driver.
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mutex_signal_protocol import (
    Entry,
    trigger_race,
    validate,
    validate_call_quota,
    validate_nested_schedule,
    validate_shared_b,
    wait_ready,
)
from native_waiter_signal_protocol import validate as validate_waiter_signal
from native_waiter_signal_protocol import validate_pending_mutex


def fixture(probe):
    identities = {
        "probe": probe,
        "comm": "kd_native",
        "owner_tasks": [10],
        "waiter_tasks": [20],
        "native_pids": [30, 40],
    }
    first = "cancel=0 survivor=-1" if probe & 1 else "cancel=-1 survivor=0"
    both = "cancel=0 survivor=1" if probe & 1 else "cancel=1 survivor=0"
    rows = [
        "kd_native begin: task=20 outer=abcd entry=1234 ip=5678 held=1 mutex=1",
        "kd_signal borrowed: waiter=20 task=2222 owner_pid=10 owner=1111 lock=abcd",
        "kd_signal arrive: role=0 task=30 comm=kd_native",
        f"kd_signal queue: count=1 {first} owner=1111 waiter=20",
        "kd_signal arrive: role=1 task=40 comm=kd_native",
        f"kd_signal queue: count=2 {both} owner=1111 waiter=20",
    ]
    if probe >= 3:
        rows.append(
            "kd_signal nonfatal: cancel=30 checks=10 pending=1 fatal=0 queued=2 owner=1111"
        )
    rows += [
        "kd_signal result: role=0 task=30 ret=-4 entered=0 unlocked=0",
        "kd_signal queue: count=1 cancel=-1 survivor=0 owner=1111 waiter=20",
        "kd_signal cancelled: cancel=30 waiter=20 ret=-4 owner=1111 entered=0 unlocked=0",
        "kd_native ack: task=20 lock=abcd mutex=1 last_spin=0",
        "kd_signal result: role=1 task=40 ret=0 entered=1 unlocked=1",
        f"kd_signal stats: probe={probe} phase=6 failures=0 nonfatal={10 if probe >= 3 else 0} owner=0 word=0 queued=0",
        "kd_native stats: started=1 completed=1 unlocks=1",
    ]
    return "\n".join(rows), identities


def race_fixture(probe, acquired, handoff):
    text, identities = fixture(probe)
    identities.update(
        race=True,
        handoff=handoff,
        expect="acquired" if acquired else "cancelled",
        trigger={
            "signal": {
                "before_ns": 100,
                "after_ns": 120,
                "pid": 30,
                "signum": 9 if probe >= 3 else 10,
            },
            "release": {"before_ns": 110, "after_ns": 130, "written": 2},
        },
        exitcodes={
            name: -9 if probe >= 3 and name == "native-0" else 0
            for name in ("holder", "owner", "waiter", "tail", "native-0", "native-1")
        },
    )
    rows = text.splitlines()
    before = rows[: next(i for i, row in enumerate(rows) if "kd_signal result:" in row)]
    word = "1113" if handoff else "1111"
    if handoff:
        before.append(
            f"kd_signal handoff: first={30 if probe & 1 else 40} owner=1111 word={word} queued=2"
        )
    before += [
        f"kd_signal ready: waiter=20 owner=1111 handoff={int(handoff)}",
        f"kd_signal gate: task=10 owner=1111 word={word} queued=2",
        f"kd_signal unlock: done=0 task=10 owner=1111 word={word} queued=2 ns=140",
        f"kd_signal result: role=0 task=30 ret={0 if acquired else -4} entered={int(acquired)} unlocked={int(acquired)} ns=150 pending=1 fatal={int(probe >= 3)} self=3330 owner={'3330' if acquired else '1111'}",
        "kd_signal unlock: done=1 task=10 owner=4440 word=4441 queued=0 ns=170",
        "kd_signal result: role=1 task=40 ret=0 entered=1 unlocked=1 ns=160 pending=0 fatal=0 self=4440 owner=4440",
        # ACK publication permits the owner to continue before its log is printed.
        "kd_native ack: task=20 lock=abcd mutex=1 last_spin=0",
        f"kd_signal stats: probe={probe} phase=9 failures=0 nonfatal={10 if probe >= 3 else 0} owner=0 word=0 queued=0",
        "kd_native stats: started=1 completed=1 unlocks=1",
    ]
    return "\n".join(before).replace("owner=1111", "owner=1110"), identities


def nested_schedule_fixture():
    """Distinct task packets let mutations separate waiter, executor and owner."""
    cpus = (1, 0, 1, 0, 0, 1, 1)
    roles = [
        f"role={role} task={20 + role} self={0x1000 + role * 16:x} "
        f"cpu={cpu} preempt=0 irq=0"
        for role, cpu in enumerate(cpus)
    ]
    text = "\n".join(
        [f"kd_nested mutex role: {row}" for row in roles]
        + [
            "JIT body witness: entry=cafe lock=aaaa body=1",
            "kd_nested mutex blocked: holder=21 b_owner=1010 executor=24 "
            "a_owner=1040 cpu=0 executor_cpu=0 a=aaaa b=bbbb queued=1 valid=1",
        ]
        + [f"kd_nested mutex done: {row}" for row in roles]
        + ["kd_native stats: started=0 completed=0 unlocks=0"]
    )
    publication = {"status": 0, "entry": "0xcafe", "code": "0x8000"}
    places = "\n".join(f"{role}\t{cpu}" for role, cpu in enumerate(cpus))
    statuses = "\n".join(f"{role}\t0" for role in range(7))
    return text, publication, places, statuses


def shared_b_fixture():
    """No copied lock model: these records exercise only the evidence parser.

    A0's waiter is distinct from the retained owner, A1 executor and peer. Live
    tests must produce these observations from the actual Linux wait list.
    """
    cpus = {**dict(enumerate(range(8))), 10: 8}
    roles = {
        role: f"role={role} task={20 + role} self={0x1000 + role * 16:x} "
        f"cpu={cpu} preempt=0 irq=0 comm={'kd_native' if role == 10 else 'klock_test'}"
        for role, cpu in cpus.items()
    }
    retained = (
        "task=22 self=1020 cpu=2 a0=1010 a1=1050 b=1010 "
        "outer0=aaaa outer1=cccc inner=bbbb executor=25 peer=30 queued=2 "
        "before=12002 held=12001 after=12001 sequence=24003 preempt=0 irq=0 valid=1"
    )
    rows = [f"kd_shared role: {row}" for row in roles.values()] + [
        "JIT body witness: entry=cafe lock=aaaa body=1",
        "kd_native begin: task=22 outer=aaaa entry=cafe ip=1234 sp=5555 held=2 mutex=1 cpu=1 outer_released=0 remaining=2",
        "JIT body witness: entry=beef lock=cccc body=1",
        f"kd_shared retained: phase=0 {retained}",
        f"kd_shared retained: phase=1 {retained}",
        # Physical unlock precedes the ACK log; the new native owner may
        # legitimately report first. Do not make logging a fake lock barrier.
        "kd_shared peer: task=30 self=10a0 owner=10a0 lock=bbbb sequence=24005 comm=kd_native",
        "kd_native ack: task=22 lock=bbbb mutex=1 last_spin=0",
        "kd_native ack: task=22 lock=aaaa mutex=1 last_spin=0",
    ] + [f"kd_shared done: {row}" for row in roles.values()]
    for lane in range(2):
        value, token = 0, 0x12340001 + lane * 0x101
        for _ in range(12002):
            value = ((value + token) & ((1 << 64) - 1)) ^ (token << 1)
        rows.append(
            f"kd_shared record: lane={lane} lock={'cccc' if lane else 'aaaa'} "
            f"owner=0 visits=12005 before=12002 held=12002 after=12002 value={value:x} sequence={24003 + lane}"
        )
    rows += [
        "kd_shared stats: claimed=4ff observed=1 peer_sequence=24005 owner=0 failures=0",
        "kd_native stats: started=1 completed=1 unlocks=2",
        "kd_mutex stats: jit_success=1 jit_resume=1 nested_queued=1 nested_jit=1",
    ]
    publication = [
        {"entry": entry, "status": 0, "code": code}
        for entry, code in (("0xcafe", "0x8000"), ("0xbeef", "0x9000"))
    ]
    return (
        "\n".join(rows), publication,
        "\n".join(f"{role}\t{cpu}" for role, cpu in cpus.items()),
        "\n".join(f"{role}\t0" for role in cpus), "1234",
    )


class SignalOracleTests(unittest.TestCase):
    def test_nested_executor_and_b_holder_share_cpu_through_jit(self):
        result = validate_nested_schedule(*nested_schedule_fixture())
        self.assertEqual(result["executor"], 24)
        self.assertEqual(result["holder"], 21)
        self.assertEqual(result["jit_bodies"], 1)
        self.assertEqual(result["native_frames"], 0)
        shared = validate_shared_b(*shared_b_fixture())
        self.assertEqual(shared["jit_bodies"], 2)
        self.assertEqual(shared["owner_acks"], 2)
        self.assertEqual(shared["b_sequence"], 24005)

    def test_nested_schedule_requires_each_ordered_kernel_witness(self):
        text, *metadata = nested_schedule_fixture()
        for line in text.splitlines():
            for damaged in (
                text.replace(line, ""),
                text.replace(line, line + "\n" + line),
            ):
                with self.subTest(line=line), self.assertRaises(AssertionError):
                    validate_nested_schedule(damaged, *metadata)
        lines = text.splitlines()
        for prefix in ("JIT body witness:", "kd_nested mutex blocked:"):
            selected = next(line for line in lines if line.startswith(prefix))
            reordered = [line for line in lines if line != selected] + [selected]
            with self.subTest(prefix=prefix), self.assertRaises(AssertionError):
                validate_nested_schedule("\n".join(reordered), *metadata)
        text, *metadata = shared_b_fixture()
        for line in text.splitlines():
            for damaged in (text.replace(line, ""), text.replace(line, line + "\n" + line)):
                with self.subTest(shared=line), self.assertRaises(AssertionError):
                    validate_shared_b(damaged, *metadata)
        for line in (r for r in text.splitlines() if r.startswith("kd_shared retained:")):
            with self.assertRaises(AssertionError):
                validate_shared_b(text.replace(line, "") + "\n" + line, *metadata)

    def test_nested_schedule_rejects_wrong_identity_state_or_selection(self):
        text, publication, places, statuses = nested_schedule_fixture()
        for before, after in (
            ("executor=24", "executor=20"),
            ("holder=21", "holder=24"),
            ("a_owner=1040", "a_owner=1000"),
            ("b_owner=1010", "b_owner=1040"),
            ("executor_cpu=0", "executor_cpu=1"),
            ("a=aaaa", "a=bbbb"),
            ("queued=1", "queued=0"),
            ("valid=1", "valid=0"),
            ("body=1", "body=0"),
            ("entry=cafe", "entry=beef"),
            ("lock=aaaa", "lock=bbbb"),
            ("preempt=0", "preempt=1"),
            ("irq=0", "irq=1"),
            ("started=0", "started=1"),
        ):
            with self.subTest(field=before), self.assertRaises(AssertionError):
                validate_nested_schedule(
                    text.replace(before, after, 1), publication, places, statuses
                )
        for key, value in (("status", -1), ("entry", "0xbeef"), ("code", "0x0")):
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_nested_schedule(
                    text, {**publication, key: value}, places, statuses
                )
        for bad_places, bad_statuses in (
            (places.replace("0\t1", "0\t0"), statuses),
            (places + "\n0\t1", statuses),
            (places, statuses.replace("0\t0", "0\t137")),
            (places, statuses + "\n0\t0"),
        ):
            with self.assertRaises(AssertionError):
                validate_nested_schedule(text, publication, bad_places, bad_statuses)
        text, pubs, places, statuses, probe = shared_b_fixture()
        for before, after in (
            ("a0=1010", "a0=1020"), ("a1=1050", "a1=1060"),
            ("b=1010", "b=1050"), ("executor=25", "executor=26"),
            ("peer=30", "peer=22"), ("queued=2", "queued=1"),
            ("before=12002 held=12001", "before=12002 held=12002"),
            ("outer1=cccc", "outer1=aaaa"), ("phase=1", "phase=0"),
            ("ip=1234", "ip=5678"), ("sp=5555", "sp=0"),
            ("remaining=2", "remaining=1"), ("body=1", "body=0"),
            ("entry=cafe", "entry=abcd"), ("visits=12005", "visits=12006"),
            ("unlock", "missing_unlock"), ("nested_jit=1", "nested_jit=0"),
            ("comm=kd_native", "comm=klock_test"),
            ("preempt=0", "preempt=1"), ("failures=0", "failures=1"),
        ):
            with self.subTest(shared=before), self.assertRaises((AssertionError, KeyError)):
                validate_shared_b(text.replace(before, after, 1), pubs, places, statuses, probe)
        for bad_pubs, bad_places, bad_statuses in (
            ([{**pubs[0], "status": -1}, pubs[1]], places, statuses),
            ([pubs[0], pubs[0]], places, statuses),
            (pubs, places.replace("10\t8", "10\t7"), statuses),
            (pubs, places, statuses.replace("10\t0", "10\t137")),
        ):
            with self.assertRaises(AssertionError):
                validate_shared_b(text, bad_pubs, bad_places, bad_statuses, probe)

    def test_ready_waits_for_matching_kernel_publication(self):
        def entry(status, rip=0x1234, tgid=42):
            return Entry(
                status=status, pid=0, tgid=tgid, lock_kind=2, rip=rip, code=0x8000
            )

        with (
            patch(
                "mutex_signal_protocol.entries",
                side_effect=[
                    [entry(0, rip=0x5678)],
                    [entry(0, tgid=99)],
                    [entry(-1)],
                    [entry(0)],
                ],
            ) as read,
            patch("mutex_signal_protocol.time.sleep") as sleep,
        ):
            result = wait_ready("/tmp/0x1234/42/asm")
            self.assertEqual(result["entry"], "0x1234")
            self.assertEqual(result["status"], 0)
            self.assertEqual(read.call_count, 4)
            self.assertEqual(sleep.call_count, 3)
        for snapshot in ([], [entry(-1)], [entry(-3)], [entry(0), entry(0)]):
            with (
                self.subTest(snapshot=snapshot),
                patch("mutex_signal_protocol.entries", return_value=snapshot),
                self.assertRaises(AssertionError),
            ):
                wait_ready("/tmp/0x1234/42/asm", timeout=0)

    def test_all_four_valid_histories(self):
        for probe in range(1, 5):
            with self.subTest(probe=probe):
                text, identities = fixture(probe)
                validate(text, identities, "5678")

    def test_publication_checks_the_requested_spin_or_mutex_kind(self):
        for kind in (1, 2):
            published = Entry(
                status=0, pid=0, tgid=42, lock_kind=kind, rip=0x1234, code=0x8000
            )
            with patch("mutex_signal_protocol.entries", return_value=[published]):
                self.assertEqual(
                    wait_ready("/tmp/0x1234/42/asm", lock_kind=kind)["status"], 0
                )
                with self.assertRaises(AssertionError):
                    wait_ready("/tmp/0x1234/42/asm", lock_kind=3 - kind)

    def test_corrupted_histories_are_not_success(self):
        text, identities = fixture(3)
        for old, new in (
            ("task=2222", "task=1111"),
            ("owner_pid=10", "owner_pid=99"),
            ("kd_native begin:", "missing begin:"),
            ("ip=5678", "ip=8765"),
            ("ret=-4", "ret=0"),
            ("cancel=0 survivor=1", "cancel=1 survivor=0"),
            ("pending=1 fatal=0", "pending=1 fatal=1"),
            ("checks=10", "checks=1"),
            ("kd_signal nonfatal:", "missing nonfatal:"),
            ("ret=0 entered=1 unlocked=1", "ret=0 entered=0 unlocked=0"),
            ("word=0", "word=1"),
            ("completed=1", "completed=0"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(text.replace(old, new), identities, "5678")

    def test_duplicate_ack_and_early_survivor_are_rejected(self):
        text, identities = fixture(1)
        ack = "kd_native ack: task=20 lock=abcd mutex=1 last_spin=0"
        with self.assertRaises(AssertionError):
            validate(text + "\n" + ack, identities, "5678")
        survivor = "kd_signal result: role=1 task=40 ret=0 entered=1 unlocked=1"
        with self.assertRaises(AssertionError):
            validate(survivor + "\n" + text.replace(survivor, ""), identities, "5678")

    def test_race_accepts_both_legal_returns(self):
        for probe in range(1, 5):
            for acquired in (False, True):
                for handoff in (False, True):
                    with self.subTest(probe=probe, acquired=acquired, handoff=handoff):
                        text, identities = race_fixture(probe, acquired, handoff)
                        self.assertEqual(
                            validate(text, identities, "5678"), int(acquired)
                        )

    def test_race_rejects_missing_or_inconsistent_evidence(self):
        text, identities = race_fixture(3, True, True)
        for old, new in (
            ("kd_signal gate:", "missing gate:"),
            ("kd_signal unlock: done=0", "missing unlock: done=0"),
            ("kd_signal handoff:", "missing handoff:"),
            ("word=1113", "word=1111"),
            ("first=30", "first=40"),
            ("ret=0 entered=1", "ret=-4 entered=1"),
            ("ret=0 entered=1", "ret=0 entered=0"),
            ("self=3330 owner=3330", "self=3330 owner=4440"),
            ("ns=150", "ns=90"),
            ("ns=170", "ns=130"),
            ("phase=9", "phase=8"),
            ("completed=1", "completed=0"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(text.replace(old, new), identities, "5678")
        for key, value in (("expect", "cancelled"), ("handoff", False)):
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate(text, {**identities, key: value}, "5678")
        identities["exitcodes"]["native-0"] = 0
        with self.assertRaises(AssertionError):
            validate(text, identities, "5678")

    def test_race_allows_cancel_before_physical_unlock(self):
        text, identities = race_fixture(1, False, False)
        text = text.replace("ns=150", "ns=125")
        self.assertEqual(validate(text, identities, "5678"), 0)
        text = text.replace("pending=1 fatal=0", "pending=0 fatal=0")
        with self.assertRaises(AssertionError):
            validate(text, identities, "5678")


def waiter_signal_fixture(signum):
    """Synthetic logs only: the live kernel test supplies actual signal evidence."""
    fatal = int(signum == 9)
    value = (12002 * 3 + 17) ^ 0x5A5A
    text = "\n".join(
        [
            "JIT body witness: entry=1234 lock=abcd body=1",
            "[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE entry=0x1234 target=0x5678 sp=0x8000 return=0x6000 staged_ip=0x5678 staged_sp=0x8000 mutex=1 error=-7 outer_released=0 task=20",
            "kd_native begin: task=20 outer=abcd entry=1234 ip=5678 sp=8000 held=1 mutex=1 cpu=3 outer_released=0 remaining=1",
            "kd_pending mutex blocked: task=20 waiter=2220 a_owner=1110 b_owner=3330 queued=1 valid=1 holder_comm=kd_native",
            f"kd_waiter signal queued: task=20 signal={signum} samples=128 pending=1 fatal={fatal} queued=1 a_owner=1110 b_owner=3330 before=1 called=0 after=0",
            "kd_pending mutex acquired: task=20 waiter=2220 a_owner=1110 b_owner=2220 preserved=1",
            f"kd_waiter signal acquired: task=20 signal={signum} pending=1 fatal={fatal}",
            "kd_native complete: task=20 outer=abcd mutex=1",
            "kd_native ack: task=20 lock=abcd mutex=1 last_spin=0",
            f"kd_waiter signal complete: task=20 signal={signum} pending=1 fatal={fatal} before=1 called=1 after=1 record=12001 value={value:x}",
            f"kd_waiter signal stats: signal={signum} delivered=1 samples=128 acquired=1 completed=1 failures=0 api=0 cancelled=0 held_ack=0 race=0 phase=0",
            "kd_native stats: started=1 completed=1 unlocks=1",
            "kd_mutex tasks: active_tasks=0 task_alloc_failure=0 task_reroutes=0",
        ]
    )
    client = f"pending client enter: pid=20 signal={signum}\n"
    if not fatal:
        client += "pending client return: pid=20 signal=10 ret=0 errno=0 signals=1\n"
    statuses = "\n".join(
        f"{role}\t{137 if fatal and role == 0 else 0}" for role in range(7)
    )
    return text, client, statuses


def waiter_cancel_fixture(api):
    """Model evidence from a direct native API miss, never a PENDING injection."""
    signum = 10 if api == 1 else 9
    fatal = int(signum == 9)
    text, client, statuses = waiter_signal_fixture(signum)
    lines = [
        line
        for line in text.splitlines()
        if not line.startswith(
            (
                "[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE",
                "kd_waiter signal queued:",
                "kd_pending mutex acquired:",
                "kd_waiter signal acquired:",
            )
        )
    ]
    blocked = next(
        i for i, line in enumerate(lines) if "kd_pending mutex blocked:" in line
    )
    lines[blocked + 1 : blocked + 1] = [
        f"kd_waiter signal sent: task=20 signal={signum} api={api} a_owner=1110 b_owner=3330",
        f"kd_waiter signal cancelled: task=20 signal={signum} api={api} ret=-4 pending=1 fatal={fatal} queued=0 a_owner=1110 b_owner=3330 before=1 called=1 after=1 record=12001 value={((12002 * 3 + 17) ^ 0x5A5A):x}",
    ]
    complete = next(
        i for i, line in enumerate(lines) if "kd_waiter signal complete:" in line
    )
    lines.insert(
        complete + 1,
        f"kd_waiter signal held-after-ack: task=20 api={api} b_owner=3330 completed=1",
    )
    text = "\n".join(lines).replace("samples=128 acquired=1", "samples=0 acquired=0")
    text = text.replace(
        "api=0 cancelled=0 held_ack=0", f"api={api} cancelled=1 held_ack=1"
    )
    publication = [
        {
            "entry": "0x1234",
            "target": "0x5678",
            "code": "0x9000",
            "pid": 0,
            "tgid": 42,
            "kind": 2,
            "status": 1,
        }
    ]
    return [text, client, statuses, signum, api, 0x5678, publication]


def waiter_race_fixture(api, acquired):
    """The native return and real owner-release bracket select the legal suffix."""
    args = waiter_cancel_fixture(api)
    signum, fatal = args[3], int(api == 2)
    original = args[0].splitlines()
    # Keep only JIT entry, native continuation and the real B queue witness;
    # this race uses pidfd delivery, not the forced test's kernel send event.
    rows = original[:3]
    rows += [
        f"kd_waiter race ready: task=20 signal={signum} api={api} a_owner=1110 b_owner=3330 owner_task=30",
        "kd_waiter race unlock: done=0 task=30 waiter=20 owner=3330 ns=180",
    ]
    if acquired:
        rows.append(
            "kd_pending mutex acquired: task=20 waiter=2220 a_owner=1110 b_owner=2220 preserved=1"
        )
    rows.append(
        f"kd_waiter race result: task=20 api={api} ret={0 if acquired else -4} waiter=2220 a_owner=1110 b_owner={'2220' if acquired else '3330'} pending=1 fatal={fatal} queued=0 before=1 called=0 after=0 record=12001 value={12002 * 3:x} ns=210"
    )
    if acquired:
        rows.append(
            f"kd_waiter signal acquired: task=20 signal={signum} pending=1 fatal={fatal}"
        )
    else:
        rows += [row for row in original if "kd_waiter signal cancelled:" in row]
    rows.append("kd_waiter race unlock: done=1 task=30 waiter=20 owner=4440 ns=250")
    rows += [
        row
        for row in original
        if row.startswith(
            (
                "kd_native complete:",
                "kd_native ack:",
                "kd_waiter signal complete:",
                "kd_waiter signal stats:",
                "kd_native stats:",
                "kd_mutex tasks:",
            )
        )
    ]
    args[0] = (
        "\n".join(rows)
        .replace("delivered=1", "delivered=0")
        .replace("samples=0 acquired=0", f"samples=0 acquired={int(acquired)}")
        .replace(
            "cancelled=1 held_ack=1 race=0 phase=0",
            f"cancelled={int(not acquired)} held_ack=0 race=1 phase=3",
        )
    )
    if api == 1:
        args[1] = args[1].replace(
            "pending client return:",
            "pending client ioctl: pid=20 signal=10 ret=0 errno=0 signals=0\npending client return:",
        )
    args += [
        {
            "pid": 20,
            "signal": signum,
            "offset_us": 0,
            "trigger": {
                "signal": {
                    "cpu": 7,
                    "pid": 20,
                    "signum": signum,
                    "pidfd": 1,
                    "before_ns": 150,
                    "after_ns": 200,
                },
                "release": {"cpu": 9, "written": 2, "before_ns": 100, "after_ns": 190},
            },
        },
        "either",
    ]
    return args


def pending_shared_fixture():
    """Extend the existing pending packet fixture, not a copied lock model."""
    text, _, statuses = waiter_signal_fixture(10)
    text = "\n".join(
        line for line in text.splitlines() if not line.startswith("kd_waiter signal")
    )
    text = text.replace("mutex=1 cpu=3", "mutex=1 cpu=4")
    text = text.replace("preserved=1", "preserved=1 cpu=4 preempt=0 irq=0")
    cpus = {role: 4 if role in (0, 4, 6) else role for role in range(7)}
    tasks = {0: (20, "2220"), 1: (30, "3330"), 4: (10, "1110")}
    roles = []
    for role, cpu in cpus.items():
        pid, pointer = tasks.get(role, (100 + role, f"{0x4000 + role * 16:x}"))
        roles.append(
            f"kd_pending mutex role: role={role} task={pid} self={pointer} cpu={cpu} preempt=0 irq=0"
        )
    complete = f"kd_pending mutex complete: task=20 waiter=2220 cpu=4 preempt=0 irq=0 record=12001 before=1 called=1 after=1 value={((12002 * 3 + 17) ^ 0x5A5A):x} valid=1"
    text = (
        "\n".join(roles)
        + "\n"
        + text.replace("kd_native stats:", complete + "\nkd_native stats:")
    )
    return text, "\n".join(f"{role}\t{cpu}" for role, cpu in cpus.items()), statuses


class NativeWaiterSignalTests(unittest.TestCase):
    """Missing or contradictory evidence must not turn a killed client green."""

    def test_pending_waiter_can_share_its_owners_cpu(self):
        text, placements, statuses = pending_shared_fixture()
        result = validate_pending_mutex(text, True, placements, statuses)
        self.assertEqual(
            result,
            {
                "task": 20,
                "native_frames": 1,
                "acks": 1,
                "shared_cpu": True,
                "cpu": 4,
                "owner_task": 10,
                "record": 12001,
            },
        )
        # Ordinary pending-B/signal cases keep their separate placement and
        # signal contracts; they do not implicitly opt into this CPU schedule.
        ordinary, _, _ = waiter_signal_fixture(10)
        self.assertFalse(validate_pending_mutex(ordinary)["shared_cpu"])
        with self.assertRaises(AssertionError):
            validate_pending_mutex(ordinary, True, placements, statuses)

    def test_shared_cpu_requires_real_identities_packet_and_final_ack(self):
        text, placements, statuses = pending_shared_fixture()
        for line in text.splitlines():
            if line.startswith("kd_mutex tasks:"):
                continue
            for damaged in (
                text.replace(line, ""),
                text.replace(line, line + "\n" + line),
            ):
                with (
                    self.subTest(line=line),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    validate_pending_mutex(damaged, True, placements, statuses)
        for before, after in (
            ("self=1110", "self=2220"),
            ("role=6", "role=4"),
            ("task=20", "task=21"),
            ("cpu=4", "cpu=0"),
            ("preempt=0", "preempt=1"),
            ("irq=0", "irq=1"),
            ("a_owner=1110", "a_owner=2220"),
            ("b_owner=3330", "b_owner=2220"),
            ("staged_sp=0x8000", "staged_sp=0x8008"),
            ("staged_ip=0x5678", "staged_ip=0x6000"),
            ("record=12001", "record=12002"),
            ("called=1", "called=2"),
            ("preserved=1", "preserved=0"),
            ("remaining=1", "remaining=0"),
        ):
            with self.subTest(field=before), self.assertRaises(AssertionError):
                validate_pending_mutex(
                    text.replace(before, after, 1), True, placements, statuses
                )
        lines = text.splitlines()
        complete = next(
            line for line in lines if line.startswith("kd_pending mutex complete:")
        )
        lines.remove(complete)
        lines.insert(
            next(
                i for i, line in enumerate(lines) if line.startswith("kd_native ack:")
            ),
            complete,
        )
        with self.assertRaises(AssertionError):
            validate_pending_mutex("\n".join(lines), True, placements, statuses)
        for wrong_places, wrong_statuses in (
            (placements.replace("0\t4", "0\t0"), statuses),
            (placements + "\n0\t4", statuses),
            (placements, statuses.replace("0\t0", "0\t137")),
            (placements, statuses + "\n0\t0"),
        ):
            with self.assertRaises(AssertionError):
                validate_pending_mutex(text, True, wrong_places, wrong_statuses)

    def test_nonfatal_and_fatal_completion(self):
        for signum in (9, 10):
            with self.subTest(signum=signum):
                result = validate_waiter_signal(*waiter_signal_fixture(signum), signum)
                self.assertTrue(result["jit"])
                self.assertEqual(result["fatal_exit"], signum == 9)

    def test_each_kernel_witness_is_required(self):
        for signum in (9, 10):
            text, client, statuses = waiter_signal_fixture(signum)
            lines = text.splitlines()
            for index in range(len(lines)):
                with (
                    self.subTest(signum=signum, line=index),
                    self.assertRaises(AssertionError),
                ):
                    validate_waiter_signal(
                        "\n".join(lines[:index] + lines[index + 1 :]),
                        client,
                        statuses,
                        signum,
                    )

    def test_rejects_wrong_task_state_ownership_and_side_effects(self):
        text, client, statuses = waiter_signal_fixture(9)
        corruptions = (
            ("task=20", "task=21"),
            ("body=1", "body=0"),
            ("entry=1234", "entry=4321"),
            ("samples=128", "samples=127"),
            ("pending=1", "pending=0"),
            ("fatal=1", "fatal=0"),
            ("a_owner=1110", "a_owner=2220"),
            ("b_owner=3330", "b_owner=2220"),
            ("preserved=1", "preserved=0"),
            ("staged_sp=0x8000", "staged_sp=0x8008"),
            ("before=1", "before=2"),
            ("after=1", "after=0"),
            ("record=12001", "record=12000"),
            ("unlocks=1", "unlocks=0"),
            ("active_tasks=0", "active_tasks=1"),
            ("task_alloc_failure=0", "task_alloc_failure=1"),
        )
        for before, after in corruptions:
            with self.subTest(before=before), self.assertRaises(AssertionError):
                validate_waiter_signal(
                    text.replace(before, after, 1), client, statuses, 9
                )

    def test_ack_must_precede_native_suffix_return(self):
        text, client, statuses = waiter_signal_fixture(10)
        lines = text.splitlines()
        lines[8], lines[9] = lines[9], lines[8]
        with self.assertRaises(AssertionError):
            validate_waiter_signal("\n".join(lines), client, statuses, 10)

    def test_exit_status_and_client_identity_are_required(self):
        for signum in (9, 10):
            text, client, statuses = waiter_signal_fixture(signum)
            for bad_client, bad_statuses in (
                (client.replace("pid=20", "pid=21"), statuses),
                (client + client, statuses),
                (client, statuses + "\n0\t0"),
                (client, statuses.replace("1\t0", "1\t137")),
                (
                    client,
                    statuses.replace("0\t137", "0\t0")
                    if signum == 9
                    else statuses.replace("0\t0", "0\t137"),
                ),
            ):
                with self.subTest(signum=signum), self.assertRaises(AssertionError):
                    validate_waiter_signal(text, bad_client, bad_statuses, signum)

    def test_fatal_cannot_return_and_nonfatal_cannot_retry(self):
        text, client, statuses = waiter_signal_fixture(9)
        with self.assertRaises(AssertionError):
            validate_waiter_signal(
                text,
                client
                + "pending client return: pid=20 signal=9 ret=0 errno=0 signals=0\n",
                statuses,
                9,
            )
        text, client, statuses = waiter_signal_fixture(10)
        with self.assertRaises(AssertionError):
            validate_waiter_signal(
                text, client.replace("ret=0 errno=0", "ret=-1 errno=4"), statuses, 10
            )


class NativeWaiterCancelTests(unittest.TestCase):
    """Real cancellation must retain A's suffix/ACK while never acquiring B."""

    def test_both_cancellable_native_apis(self):
        for api in (1, 2):
            with self.subTest(api=api):
                result = validate_waiter_signal(*waiter_cancel_fixture(api))
                self.assertTrue(result["jit"] and result["cancelled"])
                self.assertEqual(result["api"], api)
                self.assertEqual(result["owner_acks"], 1)

    def test_every_kernel_event_remains_required(self):
        for api in (1, 2):
            args = waiter_cancel_fixture(api)
            lines = args[0].splitlines()
            for index in range(len(lines)):
                with (
                    self.subTest(api=api, line=index),
                    self.assertRaises(AssertionError),
                ):
                    validate_waiter_signal(
                        "\n".join(lines[:index] + lines[index + 1 :]), *args[1:]
                    )

    def test_requires_exact_ordinary_miss_publication(self):
        for field, bad in (
            ("target", "0x6789"),
            ("code", "0x0"),
            ("kind", 1),
            ("status", -1),
            ("status", 0),
            ("status", -3),
            ("pid", 20),
            ("tgid", 0),
            ("entry", "0x9999"),
        ):
            args = waiter_cancel_fixture(1)
            args[-1][0][field] = bad
            with (
                self.subTest(field=field, value=bad),
                self.assertRaises(AssertionError),
            ):
                validate_waiter_signal(*args)
        for position, bad in ((5, None), (5, 0x6789), (6, None), (6, [])):
            args = waiter_cancel_fixture(2)
            args[position] = bad
            with self.subTest(position=position), self.assertRaises(AssertionError):
                validate_waiter_signal(*args)
        args = waiter_cancel_fixture(2)
        args[-1] *= 2
        with self.assertRaises(AssertionError):
            validate_waiter_signal(*args)

    def test_cancellation_cannot_be_an_acquisition_or_pending_injection(self):
        args = waiter_cancel_fixture(1)
        for event in (
            "kd_pending mutex acquired: task=20 preserved=1",
            "kd_waiter signal acquired: task=20 signal=10 pending=1 fatal=0",
            "[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE task=20",
            "JIT body witness: entry=1234 lock=abcd body=1",
        ):
            with self.subTest(event=event), self.assertRaises(AssertionError):
                validate_waiter_signal(args[0] + "\n" + event, *args[1:])
        for old, new in (
            ("ret=-4", "ret=0"),
            ("pending=1", "pending=0"),
            ("queued=0", "queued=1"),
            ("a_owner=1110", "a_owner=2220"),
            ("record=12001", "record=12000"),
            ("called=1", "called=2"),
            ("acquired=0", "acquired=1"),
            ("held_ack=1", "held_ack=0"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate_waiter_signal(args[0].replace(old, new, 1), *args[1:])

    def test_owner_and_client_cannot_skip_the_final_ack(self):
        args = waiter_cancel_fixture(2)
        lines = args[0].splitlines()
        ack = next(i for i, line in enumerate(lines) if "kd_native ack:" in line)
        held = next(i for i, line in enumerate(lines) if "held-after-ack:" in line)
        lines[ack], lines[held] = lines[held], lines[ack]
        with self.assertRaises(AssertionError):
            validate_waiter_signal("\n".join(lines), *args[1:])
        args[1] += "pending client return: pid=20 signal=9 ret=0 errno=0 signals=0\n"
        with self.assertRaises(AssertionError):
            validate_waiter_signal(*args)


class NativeWaiterRaceTests(unittest.TestCase):
    """Neither a scheduling bias nor a killed client proves native cancellation."""

    def test_both_apis_and_real_returns(self):
        for api in (1, 2):
            for acquired in (False, True):
                with self.subTest(api=api, acquired=acquired):
                    result = validate_waiter_signal(*waiter_race_fixture(api, acquired))
                    self.assertTrue(result["jit"] and result["race"])
                    self.assertEqual(result["cancelled"], not acquired)
                    self.assertEqual(result["owner_acks"], 1)

    def test_bias_cannot_substitute_for_the_return(self):
        for acquired in (False, True):
            args = waiter_race_fixture(1, acquired)
            for bias in (-50000, 50000):
                args[-2]["offset_us"] = bias
                validate_waiter_signal(*args)
            args[-1] = "acquired" if acquired else "cancelled"
            validate_waiter_signal(*args)
            args[-1] = "cancelled" if acquired else "acquired"
            with self.assertRaises(AssertionError):
                validate_waiter_signal(*args)

    def test_every_kernel_event_is_required(self):
        for acquired in (False, True):
            args = waiter_race_fixture(2, acquired)
            lines = args[0].splitlines()
            for index in range(len(lines)):
                with (
                    self.subTest(acquired=acquired, index=index),
                    self.assertRaises(AssertionError),
                ):
                    validate_waiter_signal(
                        "\n".join(lines[:index] + lines[index + 1 :]), *args[1:]
                    )

    def test_corrupt_return_owner_or_packet_is_rejected(self):
        for acquired in (False, True):
            args = waiter_race_fixture(1, acquired)
            for old, new in (
                ("a_owner=1110", "a_owner=2220"),
                ("ip=5678", "ip=9999"),
                ("body=1", "body=0"),
                ("owner_task=30", "owner_task=20"),
                ("done=0", "done=1"),
                ("ns=210", "ns=50"),
                ("phase=3", "phase=2"),
                ("held_ack=0", "held_ack=1"),
                ("before=1 called=0", "before=2 called=0"),
                ("ret=0" if acquired else "ret=-4", "ret=-22"),
            ):
                with (
                    self.subTest(acquired=acquired, old=old),
                    self.assertRaises(AssertionError),
                ):
                    validate_waiter_signal(args[0].replace(old, new, 1), *args[1:])
            for event in (
                "[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE task=20",
                "kd_waiter signal sent: task=20",
                "kd_waiter signal held-after-ack: task=20",
                "JIT body witness: entry=1234 lock=abcd body=1",
            ):
                with (
                    self.subTest(acquired=acquired, event=event),
                    self.assertRaises(AssertionError),
                ):
                    validate_waiter_signal(args[0] + "\n" + event, *args[1:])

    def test_pidfd_trigger_and_syscall_windows_remain_required(self):
        for path, value in (
            (("pid",), 99),
            (("signal",), 9),
            (("offset_us",), 50001),
            (("trigger", "signal", "pidfd"), 0),
            (("trigger", "signal", "pid"), 30),
            (("trigger", "signal", "signum"), 9),
            (("trigger", "signal", "cpu"), 9),
            (("trigger", "signal", "after_ns"), 100),
            (("trigger", "release", "written"), 0),
            (("trigger", "release", "before_ns"), 181),
        ):
            args = waiter_race_fixture(1, False)
            item = args[-2]
            for key in path[:-1]:
                item = item[key]
            item[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(AssertionError):
                validate_waiter_signal(*args)
        args = waiter_race_fixture(1, True)
        args[-2] = None
        with self.assertRaises(AssertionError):
            validate_waiter_signal(*args)

    def test_ack_can_precede_later_owner_logs(self):
        for acquired in (False, True):
            args = waiter_race_fixture(2, acquired)
            lines = args[0].splitlines()
            moved = [
                row
                for row in lines
                if row.startswith("kd_waiter race unlock:")
                and (not acquired or "done=1" in row)
            ]
            lines = [row for row in lines if row not in moved]
            insertion = next(
                i for i, row in enumerate(lines) if "kd_waiter signal stats:" in row
            )
            lines[insertion:insertion] = moved
            args[0] = "\n".join(lines)
            if not acquired:
                args[0] = (
                    args[0].replace("ns=180", "ns=300").replace("ns=250", "ns=350")
                )
            validate_waiter_signal(*args)

    def test_acquisition_can_beat_signal_but_client_must_observe_it(self):
        args = waiter_race_fixture(1, True)
        args[0] = args[0].replace("pending=1", "pending=0")
        validate_waiter_signal(*args)
        args[1] = args[1].replace("signals=1", "signals=0")
        with self.assertRaises(AssertionError):
            validate_waiter_signal(*args)
        args = waiter_race_fixture(2, True)
        args[1] += "pending client ioctl: pid=20 signal=9 ret=0 errno=0 signals=0\n"
        validate_waiter_signal(*args)
        args[1] += "pending client return: pid=20 signal=9 ret=0 errno=0 signals=0\n"
        with self.assertRaises(AssertionError):
            validate_waiter_signal(*args)

    def test_shared_trigger_preserves_the_legacy_gate(self):
        # File/syscall substitutes check controller routing, not real lock races.
        with tempfile.TemporaryDirectory() as directory:
            params = Path(directory)
            for name in ("mutex_signal_release", "native_waiter_release"):
                (params / name).write_text("0\n")
            with (
                patch("mutex_signal_protocol.PARAMS", params),
                patch("mutex_signal_protocol.os.sched_setaffinity"),
                patch("mutex_signal_protocol.os.kill") as kill,
                patch("mutex_signal_protocol.signal.pidfd_send_signal") as send,
            ):
                trigger_race(42, 10, (7, 8, 9), 0)
                kill.assert_called_once_with(42, 10)
                send.assert_not_called()
                self.assertEqual((params / "mutex_signal_release").read_text(), "1\n")
                self.assertEqual((params / "native_waiter_release").read_text(), "0\n")
                result = trigger_race(
                    42,
                    10,
                    (7, 8, 9),
                    0,
                    release_parameter="native_waiter_release",
                    pidfd=99,
                )
                send.assert_called_once_with(99, 10, None, 0)
                self.assertEqual(kill.call_count, 1)
                self.assertEqual(result["signal"]["pidfd"], 1)
                self.assertEqual(result["release"]["written"], 2)
                self.assertEqual((params / "native_waiter_release").read_text(), "1\n")


def call_quota_fixture():
    # Synthetic logs exercise the oracle, not a kernel/clock implementation.
    before = "JIT body witness: entry=1000 lock=8000 body=1\n" * 2
    lines = []
    for task in (20, 21):
        lines += [
            "JIT body witness: entry=1000 lock=8000 body=1",
            f"[KD_JIT][WARN] reason=CALL_LIMIT_NATIVE entry=0x1000 ip=0x2000 sp=0x9000 return=0x1005 lock=0x8000 task={task} hostcall=1",
            f"kd_native begin: task={task} outer=8000 entry=1000 ip=2000 sp=9000 held=1 mutex=1 cpu=0 outer_released=0 remaining=1",
            f"kd_native complete: task={task} outer=8000 mutex=1",
            f"kd_native ack: task={task} lock=8000 mutex=1 last_spin=0",
            f"kd_hostcall quota done: task={task} repeats=17 cpu=1 preempt=0 irq=0",
        ]
    lines += [
        f"kd_hostcall quota done: task={task} repeats=17 cpu=0 preempt=0 irq=0"
        for task in (22, 23, 24)
    ]
    lines += [
        "kd_native stats: started=2 completed=2 unlocks=2",
        "kd_mutex stats: jit_success=2 jit_resume=2",
        "kd_hostcall stats: exits=38 executed=36 resumed=36 rejected=0 failed=0 limit=2",
    ]
    publication = dict(
        entry="0x1000", code="0x3000", tgid=0, pid=0, status=0, observed_ns=1
    )
    assembly = (
        "/* KD_HOSTCALL id=1 symbol=ktime_get */\nloc_2000:\nloc_1005:\n"
        "/* KD_HOSTCALL id=3 symbol=int_sqrt */\nloc_2100:\n"
    )
    return [
        before + "\n".join(lines),
        before,
        publication,
        dict(publication, observed_ns=2),
        assembly,
        "holder\t0\nwaiters\t0\n",
    ]


class CallQuotaTests(unittest.TestCase):
    def test_normal_returns_and_quota_suffixes_are_distinct(self):
        result = validate_call_quota(*call_quota_fixture())
        self.assertEqual(result["normal_jit"], 2)
        self.assertEqual(result["quota_native"], 2)
        self.assertEqual(result["quota_callers"], 5)
        self.assertEqual(result["jit_bodies"], 4)
        self.assertEqual(result["hostcall_executed"], 36)

    def test_packet_publication_and_ack_corruption_is_rejected(self):
        for old, new in (
            ("reason=CALL_LIMIT_NATIVE", "reason=HOSTCALL_LIMIT"),
            ("ip=0x2000", "ip=0x3000"),
            ("return=0x1005", "return=0x1006"),
            ("sp=9000", "sp=9008"),
            ("entry=1000 ip=2000", "entry=1001 ip=2000"),
            ("held=1", "held=2"),
            ("outer_released=0", "outer_released=1"),
            ("remaining=1", "remaining=0"),
            ("hostcall=1", "hostcall=0"),
            ("task=20 lock=8000", "task=21 lock=8000"),
            ("last_spin=0", "last_spin=1"),
            ("repeats=17", "repeats=16"),
            ("preempt=0", "preempt=1"),
            ("unlocks=2", "unlocks=3"),
            ("jit_resume=2", "jit_resume=1"),
            ("resumed=36", "resumed=35"),
            ("exits=38", "exits=36"),
            ("executed=36", "executed=34"),
            ("limit=2", "limit=0"),
        ):
            args = call_quota_fixture()
            args[0] = args[0].replace(old, new, 1)
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate_call_quota(*args)
        for tag in (
            "CALL_LIMIT_NATIVE",
            "kd_native begin:",
            "kd_native ack:",
            "kd_native complete:",
            "kd_hostcall quota done:",
        ):
            for duplicate in (False, True):
                args = call_quota_fixture()
                line = next(line for line in args[0].splitlines() if tag in line)
                args[0] = (
                    args[0] + "\n" + line
                    if duplicate
                    else args[0].replace(line + "\n", "", 1)
                )
                with (
                    self.subTest(tag=tag, duplicate=duplicate),
                    self.assertRaises(AssertionError),
                ):
                    validate_call_quota(*args)
        for key, value in (
            ("status", -1),
            ("code", "0x4000"),
            ("entry", "0x1001"),
            ("tgid", 1),
            ("pid", 1),
            ("observed_ns", 1),
        ):
            args = call_quota_fixture()
            args[3][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_call_quota(*args)
        for index, value in (
            (1, ""),
            (4, "loc_2000:\n"),
            (
                4,
                "/* KD_HOSTCALL id=1 symbol=ktime_get */\nloc_2000:\nloc_1005:\n",
            ),
            (
                4,
                "/* KD_HOSTCALL id=1 symbol=ktime_get */\nloc_2000:\nloc_1005:\n"
                "/* KD_HOSTCALL id=3 symbol=int_sqrt */\nloc_2000:\n",
            ),
            (5, "holder\t0\nwaiters\t124\n"),
        ):
            args = call_quota_fixture()
            args[index] = value
            with self.subTest(index=index), self.assertRaises(AssertionError):
                validate_call_quota(*args)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# Corrupt/partial log and client-protocol inputs must fail the signal oracle.
# Real signal delivery and Linux mutex exclusion belong to the live driver.
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutex_signal_protocol import Entry, trigger_race, validate, wait_ready
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


class SignalOracleTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

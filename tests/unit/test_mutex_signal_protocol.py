import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutex_signal_protocol import Entry, validate, wait_ready


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


if __name__ == "__main__":
    unittest.main(verbosity=2)

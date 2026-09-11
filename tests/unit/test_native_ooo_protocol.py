# Validate A-before-B native completion records against deliberately bad logs.
# Ordering in this fixture is an oracle input, not a concurrent execution proof.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_ooo_protocol import validate


def fixture(mutex, after_outer=False, pending=False, record=0, delegated=True):
    after_outer |= pending
    task = 20 + record
    waiter = f"{0x2222 + record * 0x100:x}"
    owner = "1111" if delegated else waiter
    pin = (2 if delegated else 8) if pending else 1
    acks = 7 if pending else 2 - int(after_outer)
    release = (
        f"kd_{'mutex' if mutex else 'spin'} outer release: task={task} owner=10 owner_task={owner} "
        f"outer=aa next_task=30 remaining={7 if pending else 1}"
    )
    rows = (
        [
            (
                f"kd_native begin: task={task} outer=aa held={8 if pending else 2} "
                f"mutex={int(mutex)} ip=ff entry=abcd sp=1000 "
                f"outer_released={int(after_outer)} remaining={acks}"
            )
        ]
        if delegated
        else []
    )
    if pending:
        if delegated:
            rows.insert(
                0,
                "[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE "
                f"entry=0xabcd target=0xff sp=0x1000 return=0x1008 "
                f"staged_ip=0xff staged_sp=0x1000 mutex={int(mutex)} "
                f"error=-7 outer_released=1 task={task}",
            )
        for index in range(7):
            child_owner = waiter if index == 6 else owner
            rows.append(
                f"kd_ooo pending lock: record={record} task={task} "
                f"mutex={int(mutex)} index={index} lock={0x100 + index:x} "
                f"owner={child_owner if mutex else '0'} word=1 "
                f"preempt={0 if mutex else pin} valid=1"
            )
    if delegated and after_outer:
        rows.insert(0, release)
    value = record + 1
    for phase in range(3):
        value = value * 17 ^ (record + phase + 1)
        if after_outer and not phase:
            continue
        if delegated and phase > int(after_outer):
            if phase == 1:
                rows.append(release)
            if pending:
                for index in reversed(range(6)):
                    rows.append(
                        f"kd_native ack: task={task} lock={0x100 + index:x} "
                        f"mutex={int(mutex)} last_spin=0"
                    )
            rows.append(
                f"kd_native ack: task={task} lock={'aa' if phase == 1 else 'bb'} "
                f"mutex={int(mutex)} last_spin={int(phase == 2 and not mutex)}"
            )
        rows.append(
            f"kd_ooo checkpoint: record={record} task={task} waiter={waiter} phase={phase} "
            f"mutex={int(mutex)} cpu=1 preempt={pin if not mutex and phase < 2 else 0} "
            f"irq=0 a={(owner if mutex else '3') if phase == 0 else '0'} b={owner if mutex else '1'} "
            f"a_private={3 if phase == 0 else 0} b_private=1 "
            f"a_owner={owner if phase == 0 else '0'} b_owner={owner} value={value:x} valid=1"
        )
    rows += [
        f"kd_native stats: started={int(delegated)} completed={int(delegated)} unlocks={acks if delegated else 0}",
        "kd_ooo stats: checked=1 failures=0",
    ]
    return "\n".join(rows)


class NativeOOOProtocolTests(unittest.TestCase):
    def check(self, text, mutex, after_outer=False):
        return validate(text, mutex, 1, "aa", "bb", "ff", after_outer)

    def test_pending_after_outer_borrowed_and_native_ownership(self):
        for mutex in (False, True):
            text = fixture(mutex, pending=True)
            with self.subTest(mutex=mutex):
                self.assertEqual(
                    validate(
                        text, mutex, 1, "aa", "bb", "ff", pending_after_outer=True
                    ),
                    1,
                )
                native = fixture(mutex, pending=True, record=1, delegated=False)
                combined = "\n".join(
                    line
                    for line in (text + "\n" + native).splitlines()
                    if "stats:" not in line
                )
                combined += "\nkd_native stats: started=1 completed=1 unlocks=7"
                combined += "\nkd_ooo stats: checked=2 failures=0"
                self.assertEqual(
                    validate(
                        combined, mutex, 2, "aa", "bb", "ff", pending_after_outer=True
                    ),
                    1,
                )

    def test_pending_after_outer_corrupted_call_ledger_and_unlocks(self):
        for mutex in (False, True):
            text = fixture(mutex, pending=True)
            mutations = (
                text.replace("held=8", "held=7"),
                text.replace("remaining=7", "remaining=8"),
                text.replace("error=-7", "error=-5"),
                text.replace("reason=PENDING_LOCK_NATIVE", "reason=MISSING"),
                text.replace("staged_ip=0xff", "staged_ip=0xfe"),
                text.replace("staged_sp=0x1000", "staged_sp=0x1008"),
                text.replace("outer_released=1", "outer_released=0", 1),
                text.replace("return=0x1008", "return=0x0"),
                text.replace("index=0", "index=1"),
                text.replace("kd_ooo pending lock:", "missing child:", 1),
                text.replace("lock=105 mutex", "lock=106 mutex"),
                text.replace("kd_native ack:", "missing ack:", 1),
                text
                + f"\nkd_native ack: task=20 lock=aa mutex={int(mutex)} last_spin=0",
                text.replace("value=112", "value=113"),
                text.replace("owner=1111", "owner=2222", 1)
                if mutex
                else text.replace("word=1", "word=0", 1),
                text.replace("owner=2222", "owner=1111")
                if mutex
                else text.replace("preempt=2", "preempt=1", 1),
            )
            for bad in mutations:
                with (
                    self.subTest(mutex=mutex, bad=bad),
                    self.assertRaises(AssertionError),
                ):
                    validate(bad, mutex, 1, "aa", "bb", "ff", pending_after_outer=True)

    def test_after_outer_b_only_ack_and_jit_prefix(self):
        for mutex in (False, True):
            text = fixture(mutex, True)
            with self.subTest(mutex=mutex):
                self.assertEqual(self.check(text, mutex, True), 1)
            for bad in (
                text.replace("outer_released=1", "outer_released=0"),
                text.replace("remaining=1", "remaining=2"),
                text.replace("lock=bb", "lock=aa"),
                text.replace("value=112", "value=113"),
                text.replace("a_owner=0", "a_owner=1111", 1)
                if not mutex
                else text.replace("a=0 b=1111", "a=1111 b=1111", 1),
                text.replace("kd_native ack:", "missing ack:"),
                text
                + f"\nkd_native ack: task=20 lock=aa mutex={int(mutex)} last_spin=0",
                text.replace("b=1111", "b=2222")
                if mutex
                else text.replace("last_spin=1", "last_spin=0"),
            ):
                with (
                    self.subTest(mutex=mutex, bad=bad),
                    self.assertRaises(AssertionError),
                ):
                    self.check(bad, mutex, True)

    def test_both_backends_and_postpublication_executor_log(self):
        for mutex in (False, True):
            with self.subTest(mutex=mutex):
                self.assertEqual(self.check(fixture(mutex), mutex), 1)
                self.assertEqual(
                    self.check(fixture(mutex) + "\nkd_native complete: task=20", mutex),
                    1,
                )

    def test_wrong_order_missing_duplicate_and_unobserved_requests(self):
        text = fixture(False)
        for bad in (
            text.replace("lock=aa", "lock=bb"),
            text.replace("kd_native ack:", "missing ack:", 1),
            text + "\nkd_native ack: task=20 lock=bb mutex=0 last_spin=1",
            text.replace("phase=1", "phase=0"),
            text.replace("record=0", "record=1", 1),
            text.replace("task=20 outer", "task=21 outer"),
            text.replace("held=2", "held=1"),
        ):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                self.check(bad, False)

    def test_premature_pin_release_context_and_side_effect_corruption(self):
        text = fixture(False)
        for bad in (
            text.replace("preempt=1", "preempt=0", 1),
            text.replace("last_spin=0", "last_spin=1", 1),
            text.replace("value=10", "value=11"),
            text.replace("a=3", "a=0"),
            text.replace("b=1", "b=0"),
            text.replace("irq=0", "irq=1", 1),
            text.replace("failures=0", "failures=1"),
        ):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                self.check(bad, False)

    def test_owner_is_not_transplanted_or_released_early(self):
        for mutex in (False, True):
            text = fixture(mutex)
            a, b = ("a", "b") if mutex else ("a_owner", "b_owner")
            for bad in (
                text.replace(f"{a}=1111 {b}=1111", f"{a}=2222 {b}=2222"),
                text.replace(f"{a}=1111", f"{a}=0", 1),
                text.replace(f"{b}=1111", f"{b}=3333", 1),
            ):
                with (
                    self.subTest(mutex=mutex, bad=bad),
                    self.assertRaises(AssertionError),
                ):
                    self.check(bad, mutex)

    def test_outer_release_identity_order_and_exactly_once(self):
        for mutex in (False, True):
            for after_outer in (False, True):
                text = fixture(mutex, after_outer)
                release = next(
                    line for line in text.splitlines() if "outer release:" in line
                )
                a, b = ("a", "b") if mutex else ("a_owner", "b_owner")
                for bad in (
                    text.replace("outer release:", "missing release:"),
                    text + "\n" + release,
                    text.replace("owner_task=1111", "owner_task=3333"),
                    text.replace("remaining=1", "remaining=0"),
                    text.replace(f"{a}=0 {b}=1111", f"{a}=1111 {b}=1111"),
                    text.replace(release, "") + "\n" + release,
                ):
                    with (
                        self.subTest(mutex=mutex, after_outer=after_outer, bad=bad),
                        self.assertRaises(AssertionError),
                    ):
                        self.check(bad, mutex, after_outer)

    def test_spin_released_outer_may_have_a_new_owner(self):
        text = fixture(False, True)
        text = text.replace("a=0 b=1", "a=40103 b=1", 1)
        text = text.replace("a_private=0", "a_private=80003", 1)
        text = text.replace("a_owner=0", "a_owner=3333", 1)
        self.assertEqual(self.check(text, False, True), 1)

    def test_spin_independent_dependency_progress_and_corruption(self):
        for kind in (1, 2):
            task = 30 if kind == 1 else 40
            text = fixture(False, pending=True)
            witness = (
                f"kd_ooo spin dependency: kind={kind} task={task} owner_task=3333 "
                "waiter=2222 waiter_pid=20 outer=aa inner=bb child=106 "
                "a_word=3 b_word=1 c_word=1 a_owner=3333 b_owner=1111 "
                f"preempt=2 irq=0 prefix=1 valid=1 comm={'klock_test' if kind == 1 else 'kd_native'}"
            )
            text = text.replace(
                "kd_ooo pending lock:", witness + "\nkd_ooo pending lock:", 1
            )

            def check(log, kind=kind):
                return validate(
                    log,
                    False,
                    1,
                    "aa",
                    "bb",
                    "ff",
                    pending_after_outer=True,
                    dependency=kind,
                )

            self.assertEqual(check(text), 1)
            for bad in (
                text.replace(witness, ""),
                text + "\n" + witness,
                text.replace("c_word=1", "c_word=0"),
                text.replace("b_owner=1111", "b_owner=3333", 1),
                text.replace("prefix=1", "prefix=0"),
                text.replace("child=106", "child=105"),
                text.replace("waiter_pid=20", "waiter_pid=30"),
                text.replace("next_task=30", "next_task=40"),
                text.replace("preempt=2 irq=0 prefix", "preempt=1 irq=0 prefix"),
                witness + "\n" + text.replace(witness, ""),
                text.replace(witness, "") + "\n" + witness,
            ):
                with (
                    self.subTest(kind=kind, bad=bad),
                    self.assertRaises(AssertionError),
                ):
                    check(bad)

    def test_independent_dependency_owner_progress_and_corruption(self):
        for kind in (1, 2):
            task = 30 if kind == 1 else 40
            text = fixture(True, pending=True)
            witness = (
                f"kd_ooo dependency: kind={kind} task={task} owner_task=3333 "
                "waiter=2222 waiter_pid=20 outer=aa inner=bb child=106 "
                "a=3333 b=1111 c=3333 prefix=1 valid=1 "
                f"comm={'klock_test' if kind == 1 else 'kd_native'}"
            )
            text = text.replace(
                "kd_ooo pending lock:", witness + "\nkd_ooo pending lock:", 1
            )

            def check(log, kind=kind):
                return validate(
                    log,
                    True,
                    1,
                    "aa",
                    "bb",
                    "ff",
                    pending_after_outer=True,
                    dependency=kind,
                )

            self.assertEqual(check(text), 1)
            for bad in (
                text.replace(witness, ""),
                text + "\n" + witness,
                text.replace("c=3333", "c=1111"),
                text.replace("prefix=1", "prefix=0"),
                text.replace("child=106", "child=105"),
                text.replace("waiter_pid=20", "waiter_pid=30"),
                witness + "\n" + text.replace(witness, ""),
                text.replace(witness, "") + "\n" + witness,
                text.replace("next_task=30", "next_task=40"),
                text.replace("a=3333 b=1111 c=3333", "a=3333 b=3333 c=3333"),
            ):
                with (
                    self.subTest(kind=kind, bad=bad),
                    self.assertRaises(AssertionError),
                ):
                    check(bad)


if __name__ == "__main__":
    unittest.main()

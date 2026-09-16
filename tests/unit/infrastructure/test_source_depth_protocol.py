"""Mutate dependency observations, not frames or generated-code execution.

The live depth workload supplies CALL misses, real capacity exits and records.
These fixtures prevent its new source oracle accepting a loader ref as a pin.
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from source_depth_protocol import HELPER, MAIN, validate, validate_learning

ENTRY = 0x1100


def fixture(count=1, writers=1, status=0, main_refs=1, helper_refs=1):
    modules = {
        MAIN: {
            "text_start": 0x1000,
            "text_end": 0x2000,
            "callee": 0x1800,
            "sha256": "a" * 64,
            "refcnt": main_refs,
            "holders": [],
        },
        HELPER: {
            "text_start": 0x3000,
            "text_end": 0x4000,
            "callee": 0x3010,
            "sha256": "b" * 64,
            "refcnt": helper_refs,
            "holders": [MAIN] if main_refs is not None else [],
        },
    }
    for name in (MAIN, HELPER):
        if modules[name]["refcnt"] is None:
            modules[name] = None
    return {
        "info": {
            "state": 2 if status == -3 else 0,
            "modules": count,
            "writers": writers,
            "frames": 0,
        },
        "modules": modules,
        "registry": [
            {
                "entry": ENTRY,
                "code": 0x5000,
                "kind": 2,
                "tgid": 71,
                "status": status,
                "target": 0x3010 if count == 2 or status == -3 else 0,
            }
        ],
    }


class SourceDepthTests(unittest.TestCase):
    def test_loader_and_source_refs_follow_every_phase(self):
        root = fixture()
        for phase, args, target in (
            ("root", (), 0),
            ("local-miss", (1, 1, 1, 1, 1), 0x1800),
            ("local-ready", (1, 1, 0, 1, 1), 0x1800),
            ("foreign-miss", (2, 1, 1, 1, 2), 0x3010),
            ("ready", (2, 0, 0, 1, 2), 0x3010),
            ("drained", (2, 0, 0, 1, 2), 0x3010),
            ("retired", (0, 0, -3, 0, 1), 0x3010),
            ("detached", (0, 0, -3, None, 0), 0x3010),
            ("unloaded", (0, 0, -3, None, None), 0x3010),
        ):
            with self.subTest(phase=phase):
                observation = fixture(*args)
                observation["registry"][0]["target"] = target
                validate(phase, observation, ENTRY, root)

    def test_loader_reference_cannot_substitute_for_a_second_pin(self):
        for count, refs in ((1, 2), (2, 1), (2, 3), (3, 2)):
            with (
                self.subTest(count=count, refs=refs),
                self.assertRaises(AssertionError),
            ):
                validate("ready", fixture(count, 0, 0, 1, refs), ENTRY, fixture())

    def test_early_pin_cannot_be_attributed_to_the_later_call_miss(self):
        with self.assertRaises(AssertionError):
            validate("root", fixture(2, 1, 0, 1, 2), ENTRY)

    def test_local_learning_cannot_borrow_the_foreign_pin_or_target(self):
        for phase, status in (("local-miss", 1), ("local-ready", 0)):
            good = fixture(status=status)
            good["registry"][0]["target"] = 0x1800
            validate(phase, good, ENTRY, fixture())
            for field, value in (("modules", 2), ("writers", 0)):
                bad = copy.deepcopy(good)
                bad["info"][field] = value
                with (
                    self.subTest(phase=phase, field=field),
                    self.assertRaises(AssertionError),
                ):
                    validate(phase, bad, ENTRY, fixture())
            good["registry"][0]["target"] = 0x3010
            with self.assertRaises(AssertionError):
                validate(phase, good, ENTRY, fixture())

    def test_learning_wave_needs_its_own_body_target_record_and_ack(self):
        # Synthetic log mutations validate the observer, not kernel execution.
        before = "previous-wave\n"
        wave = (
            "JIT body witness: entry=1100 lock=7000 body=1\n"
            "kd_native begin: task=71 outer=7000 entry=1100 ip=1800 sp=9000 "
            "held=1 mutex=1 cpu=0 outer_released=0 remaining=1\n"
            "kd_depth mutex: task=71 retained=0 children=8 valid=1 record=12003\n"
            "kd_native complete: task=71 outer=7000 mutex=1\n"
            "kd_native ack: task=71 lock=7000 mutex=1 last_spin=0\n"
        )
        validate_learning(before, before + wave, ENTRY, 0x1800)
        for altered in (
            "",
            wave.replace("ip=1800", "ip=3010"),
            wave.replace("body=1", "body=0"),
            wave.replace("held=1", "held=8"),
            wave.replace("entry=1100", "entry=1101"),
            wave.replace("retained=0", "retained=7"),
            wave.replace("valid=1", "valid=0"),
            wave.replace("kd_native ack:", "missing:"),
            wave.replace("kd_native complete:", "missing:"),
            wave + "reason=PENDING_LOCK_NATIVE\n",
            wave + wave,
        ):
            with self.subTest(altered=altered), self.assertRaises(AssertionError):
                validate_learning(before, before + altered, ENTRY, 0x1800)
        with self.assertRaises(AssertionError):
            validate_learning(before, wave, ENTRY, 0x1800)

    def test_busy_or_closed_snapshot_is_not_a_joined_open_wave(self):
        for key, value in (("frames", 1), ("writers", 1), ("state", 1), ("state", 2)):
            observation = fixture(2, 0, 0, 1, 2)
            observation["info"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                validate("drained", observation, ENTRY, fixture())

    def test_source_identity_and_native_holder_are_required(self):
        for name in (MAIN, HELPER):
            for key, value in (
                ("sha256", "c" * 64),
                ("callee", 0x1801),
                ("text_end", 0x8000),
                ("holders", ["unexpected"]),
                ("refcnt", 7),
            ):
                bad = fixture(2, 0, 0, 1, 2)
                bad["modules"][name][key] = value
                with (
                    self.subTest(name=name, key=key),
                    self.assertRaises(AssertionError),
                ):
                    validate("ready", bad, ENTRY, fixture())
        bad = fixture()
        bad["modules"][HELPER] = copy.deepcopy(bad["modules"][MAIN])
        bad["modules"][HELPER]["holders"] = [MAIN]
        with self.assertRaises(AssertionError):
            validate("root", bad, ENTRY)

    def test_wrong_registry_or_call_target_cannot_pass(self):
        for key, value in (
            ("entry", ENTRY + 1),
            ("code", 0),
            ("code", 0x6000),
            ("kind", 1),
            ("tgid", 72),
            ("status", -3),
            ("target", 0x1800),
        ):
            bad = fixture(2, 1, 1, 1, 2)
            bad["registry"][0]["target"] = 0x3010
            bad["registry"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                validate("foreign-miss", bad, ENTRY, fixture())
        for rows in ([], fixture()["registry"] * 2):
            bad = fixture()
            bad["registry"] = rows
            with self.assertRaises(ValueError):
                validate("root", bad, ENTRY)

    def test_retirement_releases_pins_but_not_the_loader_reference(self):
        for main, helper in ((1, 1), (0, 2), (0, 0), (None, 1)):
            with (
                self.subTest(main=main, helper=helper),
                self.assertRaises(AssertionError),
            ):
                validate("retired", fixture(0, 0, -3, main, helper), ENTRY, fixture())
        bad = fixture(0, 0, -3, 0, 1)
        bad["registry"][0]["status"] = 0
        with self.assertRaises(AssertionError):
            validate("retired", bad, ENTRY, fixture())

    def test_last_unloads_must_preserve_terminal_entry(self):
        with self.assertRaises(AssertionError):
            validate("detached", fixture(0, 0, -3, None, 1), ENTRY, fixture())
        with self.assertRaises(AssertionError):
            validate("unloaded", fixture(0, 0, -3, None, 0), ENTRY, fixture())
        bad = fixture(0, 0, -3, None, None)
        bad["registry"][0]["status"] = 0
        with self.assertRaises(AssertionError):
            validate("unloaded", bad, ENTRY, fixture())


if __name__ == "__main__":
    unittest.main()

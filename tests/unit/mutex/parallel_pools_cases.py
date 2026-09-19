"""Private TestCases collected by test_mutex_parallel_protocol."""
import copy
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mutex_parallel_protocol import validate

from parallel_fixtures import PUBLISHED, reloaded_fixture, code_pool_fixture, shadow_fixture

class CodePoolTests(unittest.TestCase):
    def test_capacity_then_retirement_does_not_count_reloaded_arrivals(self):
        for first in (0, 1):
            text, evidence = code_pool_fixture(first)
            reloaded, metadata = reloaded_fixture(first)
            interval = reloaded[reloaded.index("kd_source reload: phase=begin") :]
            result = validate(
                text + "\n" + interval,
                PUBLISHED,
                0xFF,
                first,
                reload=metadata,
                code_pool=evidence,
            )
            self.assertEqual(result["code_pool"]["native_queue_records"], 3)
            self.assertEqual(result["reloaded_native_records"], 6)
            # A replacement interval cannot hide an extra capacity record.
            bad = interval.replace(
                "kd_source reload: phase=end",
                "kd_parallel code record: role=4\nkd_source reload: phase=end",
            )
            with self.assertRaises(AssertionError):
                validate(
                    text + "\n" + bad,
                    PUBLISHED,
                    0xFF,
                    first,
                    reload=metadata,
                    code_pool=evidence,
                )

    def test_capacity_and_queue_preserve_both_original_ack_orders(self):
        for first in (0, 1):
            text, evidence = code_pool_fixture(first)
            result = validate(text, PUBLISHED, 0xFF, first, code_pool=evidence)
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(
                result["code_pool"],
                {
                    "allocated_blocks": 64,
                    "cold_sites": 64,
                    "missing_sites": 3,
                    "native_queue_records": 3,
                    "pre_wrapper_refusals": 1,
                },
            )

    def test_pool_count_does_not_replace_identity_or_live_frame_evidence(self):
        text, evidence = code_pool_fixture()
        for variant in range(11):
            bad = copy.deepcopy(evidence)
            full = bad["snapshots"]["filled"]["registry"]
            if variant == 0:
                full.pop()
            elif variant == 1:
                full[-1]["code"] = full[0]["code"]
            elif variant == 2:
                full[0]["code"] += 1
            elif variant == 3:
                full[-1]["status"] = 0
            elif variant == 4:
                full[-1]["entry"] = bad["sites"]["63"]["entry"]
            elif variant == 5:
                bad["snapshots"]["drained"]["source"]["frames"] = 0
            elif variant == 6:
                bad["snapshots"]["held"]["source"]["state"] = 1
            elif variant == 7:
                bad["snapshots"]["filled"]["source"]["writers"] = 1
            elif variant == 8:
                bad["sites"]["63"] = bad["sites"]["62"]
            elif variant == 9:
                bad["lock"] += 1
            else:
                bad["module_sha256"] = ""
            with self.subTest(variant=variant), self.assertRaises(AssertionError):
                validate(text, PUBLISHED, 0xFF, 0, code_pool=bad)

    def test_fallback_records_and_loaded_sites_are_required(self):
        text, evidence = code_pool_fixture()
        for old, new in (
            ("ready: 64/64", "ready: 32/64"),
            ("pool exhausted entry=17b0", "pool exhausted entry=0000"),
            ("fn=17e0", "fn=17c0"),
            ("waiters=3", "waiters=0"),
            ("task=103 waiter=104", "task=103 waiter=105"),
            ("cpu=9", "cpu=1"),
            ("owner=ee03", "owner=20"),
            ("updates=1", "updates=2"),
            ("value=18a", "value=18b"),
            ("filled=64", "filled=63"),
            ("updates=12067", "updates=12068"),
        ):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(
                    text.replace(old, new, 1), PUBLISHED, 0xFF, 0, code_pool=evidence
                )
        for label in (
            "kd_parallel code queued:",
            "mutex JIT not ready:",
            "kd_parallel code record: role=4",
            "kd_native ack:",
        ):
            line = next(line for line in text.splitlines() if line.startswith(label))
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                with (
                    self.subTest(label=label),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    validate(bad, PUBLISHED, 0xFF, 0, code_pool=evidence)

    def test_completed_old_frames_cannot_fake_concurrent_pressure(self):
        text, evidence = code_pool_fixture()
        line = next(
            line
            for line in text.splitlines()
            if line.startswith("kd_parallel code record: role=5")
        )
        with self.assertRaises(AssertionError):
            validate(
                text.replace(line, "", 1) + "\n" + line,
                PUBLISHED,
                0xFF,
                0,
                code_pool=evidence,
            )
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0)
        with self.assertRaises(AssertionError):
            validate(
                text + "\nJIT body witness: entry=17f0 lock=c00 body=1",
                PUBLISHED,
                0xFF,
                0,
                code_pool=evidence,
            )


class ShadowPoolTests(unittest.TestCase):
    def check(self, text, code, evidence, first=0, **kwargs):
        return validate(
            text,
            PUBLISHED,
            0xFF,
            first,
            code_pool=code,
            native_peers=True,
            shadow_pool=evidence,
            **kwargs,
        )

    def rejects(self, text, code, evidence, **kwargs):
        with self.assertRaises((AssertionError, ValueError, KeyError)):
            self.check(text, code, evidence, **kwargs)

    def test_shadow_full_preserves_both_frame_peer_retirement_orders(self):
        for first in (0, 1):
            text, code, evidence = shadow_fixture(first)
            native, metadata = reloaded_fixture(first)
            native = native[native.index("kd_source reload: phase=begin") :]
            result = self.check(
                text + "\n" + native, code, evidence, first, reload=metadata
            )
            self.assertEqual(
                result["shadow_pool"],
                {
                    "allocated_shadows": 1024,
                    "previous_shadows": 5,
                    "new_shadows": 1019,
                    "filler_records": 1025,
                    "native_queue_records": 3,
                    "target_refusals": 8,
                },
            )
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(result["reloaded_native_records"], 6)
            self.assertEqual(result["native_peers"]["queued"], 4)
            self.assertEqual(result["code_pool"]["allocated_blocks"], 64)

    def test_counts_require_real_membership_identity_and_live_frames(self):
        text, code, evidence = shadow_fixture()
        for phase in evidence["snapshots"]:
            for key, value in (
                ("allocated", 0),
                ("allocated", 1023),
                ("frames", 1),
                ("state", 2),
            ):
                bad = copy.deepcopy(evidence)
                if key == "allocated":
                    bad["snapshots"][phase][key] = value
                else:
                    bad["snapshots"][phase]["source"][key] = value
                # Prepare can be any observed positive count no greater than
                # the held snapshot; the exact allocation delta is checked later.
                with self.subTest(phase=phase, key=key, value=value):
                    self.rejects(text, code, bad)
        for key, value in (
            ("base", 1),
            ("stride", 1),
            ("count", 1024),
            ("entry", 1),
            ("module_sha256", ""),
        ):
            self.rejects(text, code, {**evidence, key: value})

    def test_owner_packets_queue_and_each_refusal_are_not_optional(self):
        text, code, evidence = shadow_fixture()
        for label in (
            "kd_parallel shadow layout:",
            "kd_hotlock selftest promote:",
            "kd_parallel shadow record: role=0",
            "kd_parallel shadow record: role=2",
            "mutex shadow fallback:",
            "kd_parallel shadow queued:",
        ):
            row = next(line for line in text.splitlines() if line.startswith(label))
            self.rejects(text.replace(row, "", 1), code, evidence)
            self.rejects(text + "\n" + row, code, evidence)
        prefix = "kd_parallel shadow record: role=2"
        row = next(line for line in text.splitlines() if line.startswith(prefix))
        for key, value in (
            ("role", "1"),
            ("index", "0"),
            ("task", "20"),
            ("owner", "20"),
            ("lock", "a0"),
            ("registered", "1"),
            ("updates", "2"),
            ("value", "0"),
            ("valid", "0"),
        ):
            replacement = re.sub(rf"\b{key}=\w+", f"{key}={value}", row)
            self.rejects(text.replace(row, replacement), code, evidence)
        for old, new in (
            ("count=2 matched=3", "count=2 matched=1"),
            ("entry=8888", "entry=8889"),
            ("registered=0 updates=1", "registered=1 updates=1"),
        ):
            self.rejects(text.replace(old, new, 1), code, evidence)

    def test_pressure_must_not_be_after_old_frames_or_hidden_in_reload(self):
        text, code, evidence = shadow_fixture()
        row = next(
            line
            for line in text.splitlines()
            if line.startswith("kd_parallel shadow record: role=3")
        )
        self.rejects(text.replace(row, "", 1) + "\n" + row, code, evidence)
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0, code_pool=code, native_peers=True)
        native, metadata = reloaded_fixture(0)
        interval = native[native.index("kd_source reload: phase=begin") :]
        for label in ("layout", "record", "queued"):
            bad = interval.replace(
                "kd_source reload: phase=end",
                f"kd_parallel shadow {label}: role=0\nkd_source reload: phase=end",
            )
            self.rejects(text + "\n" + bad, code, evidence, reload=metadata)

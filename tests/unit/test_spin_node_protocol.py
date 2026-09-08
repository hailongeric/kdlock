"""Corrupt-log tests for the live reservation observer, run in the guest."""

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from spin_node_protocol import FIELDS, validate


def fixture(depth=2):
    rows = [dict.fromkeys(sorted(FIELDS), 0) for _ in range(10)]
    for cpu, row in enumerate(rows):
        row["cpu"] = cpu
        if cpu <= depth:
            row.update(
                native=1, combiner=1, peak=1, peak_task=100 + cpu, peak_preempt=1
            )
    rows[0].update(virtual=depth - 1, combiner=depth, poll=3)
    return rows, {"online_cpus": list(range(10)), "depth": depth}


def render(rows, **summary):
    def line(prefix, fields):
        return (
            prefix + " " + " ".join(f"{key}={value}" for key, value in fields.items())
        )

    summary = {"cpus": len(rows), "capacity": 4, "record_bytes": 128, **summary}
    return "\n".join(
        [line("[1.0] kd_node trace:", row) for row in rows]
        + [line("[1.0] kd_node summary:", summary)]
    )


class NodeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.placement = fixture()
        self.profile = {"enabled": True, "kind": "physical"}

    def check(self, rows=None, **summary):
        return validate(
            render(self.rows if rows is None else rows, **summary),
            self.placement,
            self.profile,
        )

    def test_positive_physical_depths(self):
        for depth in range(1, 9):
            with self.subTest(depth=depth):
                self.rows, self.placement = fixture(depth)
                result = self.check()
                self.assertEqual(result["peak"], 1)
                self.assertEqual(result["native"], depth + 1)
                self.assertEqual(result["virtual"], depth - 1)
                self.assertEqual(result["combiner"], 2 * depth)

    def test_remote_requires_virtual_and_poll(self):
        self.profile["kind"] = "remote"
        self.assertTrue(self.check()["enabled"])
        for field in ("virtual", "poll"):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = 0
            if field == "virtual":
                rows[0]["combiner"] -= 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.check(rows)

    def test_disabled_requires_absence(self):
        self.profile["enabled"] = False
        self.assertEqual(validate("ordinary log", {}, self.profile), {"enabled": False})
        for log in (render(self.rows), render(self.rows).splitlines()[0]):
            with self.subTest(log=log), self.assertRaises(AssertionError):
                validate(log, self.placement, self.profile)

    def test_record_shape_and_summary(self):
        log = render(self.rows)
        bad_logs = [
            "",
            "\n".join(log.splitlines()[:-1]),
            log + "\n" + log.splitlines()[-1],
            log + "\n" + log.splitlines()[0],
            log.replace("native=1", "native=1 native=1", 1),
            log.replace("native=1", "unknown=1", 1),
            log.replace("native=1", "native=1junk", 1),
            log.replace("native=1", "", 1),
        ]
        for bad in bad_logs:
            with self.subTest(log=bad), self.assertRaises(AssertionError):
                validate(bad, self.placement, self.profile)
        for summary in ({"cpus": 9}, {"capacity": 5}, {"record_bytes": 136}):
            with self.subTest(summary=summary), self.assertRaises(AssertionError):
                self.check(**summary)

    def test_cpu_coverage_and_per_cpu_balance(self):
        variants = [self.rows[:-1]]
        duplicate = copy.deepcopy(self.rows)
        duplicate[-1]["cpu"] = 0
        variants.append(duplicate)
        crossed = copy.deepcopy(self.rows)
        crossed[0]["combiner"] -= 1
        crossed[1]["combiner"] += 1
        variants.append(crossed)
        absent = copy.deepcopy(self.rows)
        absent[1].update(native=0, combiner=0, peak=0, peak_task=0, peak_preempt=0)
        variants.append(absent)
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(AssertionError):
                self.check(rows)

    def test_invalid_counters_and_context(self):
        changes = {
            "native": -1,
            "virtual": -1,
            "live": 1,
            "actual": 1,
            "peak": 2,
            "peak_task": 0,
            "peak_preempt": 256,
            "peak_irq": 1,
            "native_full": 1,
            "virtual_full": 1,
            "context_missing": 1,
            "prepare_cancel": 1,
            **{key: 1 for key in FIELDS if key.startswith("first_")},
        }
        for field, value in changes.items():
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            if field == "prepare_cancel":
                rows[0]["combiner"] -= 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.check(rows)
        for field in ("peak", "peak_task", "peak_preempt", "peak_irq", "poll"):
            rows = copy.deepcopy(self.rows)
            rows[-1][field] = 1
            with self.subTest(inactive=field), self.assertRaises(AssertionError):
                self.check(rows)

    def test_profile_types_and_depth(self):
        for profile in (
            {},
            {"enabled": 1, "kind": "physical"},
            {"enabled": True, "kind": "unknown"},
            {"enabled": True, "kind": "physical", "extra": 0},
        ):
            with self.subTest(profile=profile), self.assertRaises(AssertionError):
                validate(render(self.rows), self.placement, profile)
        for depth in (0, 9, True):
            self.placement["depth"] = depth
            with self.subTest(depth=depth), self.assertRaises(AssertionError):
                self.check()

    def test_profile_cli_and_invalid_driver_switches(self):
        script = str(ROOT / "tests/spin_node_protocol.py")
        for enabled in ("0", "1"):
            for kind in ("physical", "remote"):
                result = subprocess.run(
                    [sys.executable, script, "profile", enabled, kind],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(
                    json.loads(result.stdout), {"enabled": enabled == "1", "kind": kind}
                )
        for test, variable in (
            ("test_14_spin_frame_depth.sh", "KD_CHAIN_TRACE_NODES"),
            ("test_21_remote_depth.sh", "KD_DEEP_TRACE_NODES"),
        ):
            result = subprocess.run(
                ["env", f"{variable}=2", "bash", str(ROOT / "tests" / test)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Evidence:", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

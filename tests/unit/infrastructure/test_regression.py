"""Protect selection and stop boundaries without loading a kernel module.

The module case and direct runner provide current live evidence. These fixtures
protect explicit scope, stop boundaries and offline evidence integrity.
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import regression as r
from unit import run as unit_runner


class UnitSelectionTests(unittest.TestCase):
    """Grouping must preserve explicit selection without triggering a sweep."""

    def test_basename_and_group_path_select_the_same_driver(self):
        expected = unit_runner.ROOT / "infrastructure/test_regression.py"
        self.assertEqual(unit_runner.select("test_regression.py"), expected)
        self.assertEqual(unit_runner.select("infrastructure/test_regression.py"), expected)
        for invalid in ("missing.py", "../regression.py", "run.py"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                unit_runner.select(invalid)

    def test_ambiguous_basename_requires_a_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for group in ("one", "two"):
                (root / group).mkdir()
                (root / group / "test_example.py").touch()
            with patch.object(unit_runner, "ROOT", root):
                with self.assertRaises(ValueError):
                    unit_runner.select("test_example.py")
                self.assertEqual(unit_runner.select("one/test_example.py"),
                                 root / "one/test_example.py")

    def test_list_does_not_execute_and_selection_forwards_arguments(self):
        with patch.object(unit_runner.runpy, "run_path") as execute:
            for args in ([], ["--list"]):
                with patch.object(sys, "argv", ["run.py", *args]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        unit_runner.main()
            execute.assert_not_called()
            with patch.object(sys, "argv", ["run.py", "test_regression.py", "-v"]):
                unit_runner.main()
                selected = str(unit_runner.ROOT / "infrastructure/test_regression.py")
                self.assertEqual(sys.argv, [selected, "-v"])
                execute.assert_called_once_with(selected, run_name="__main__")


class SelectionTests(unittest.TestCase):
    def test_catalog_contains_only_current_module_case(self):
        self.assertEqual(set(r.CASES), {"module"})
        self.assertEqual(r.select(["baseline"], ["module"]), [r.CASES["module"]])
        self.assertTrue((r.ROOT / "tests" / r.CASES["module"].script).is_file())
        with self.assertRaises(KeyError):
            r.select([], ["virtual-ticket-refusal"])

    def test_preview_never_runs_guest(self):
        with patch.object(r, "check_idle") as idle, patch.object(r, "run") as execute:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(r.main(["--case", "module", "--dry-run"]), 0)
                self.assertEqual(r.main([]), 0)
            idle.assert_not_called()
            execute.assert_not_called()


from regression_boundary_cases import BoundaryTests
from regression_evidence_cases import EvidenceTests

if __name__ == "__main__":
    unittest.main()

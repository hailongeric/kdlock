import contextlib
import io
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_context_spills as audit


class ContextSpillAuditTests(unittest.TestCase):
    def test_unique_cases_and_concrete_witnesses(self):
        self.assertEqual(len({case.name for case in audit.CASES}), len(audit.CASES))
        for case in audit.CASES:
            with self.subTest(case=case.name):
                _, accesses = audit.witness(case)
                self.assertEqual(bool(accesses), case.sensitive)

    def test_partial_alias_write_really_constructs_sensitive_value(self):
        case = next(
            case
            for case in audit.CASES
            if case.name == "may-alias-partial-write-constructs-address"
        )
        _, accesses = audit.witness(case)
        self.assertEqual(accesses[-1]["address"], "0x3000")
        self.assertEqual(accesses[-1]["instruction"], "LODSQ")

    def test_return_slot_is_written_by_call_and_reloaded_after_ret(self):
        case = next(case for case in audit.CASES if case.name == "call-return-slot")
        inputs, accesses = audit.witness(case)
        self.assertEqual(inputs["RSP"], 0x8000)
        self.assertEqual(accesses[-1]["rip"], "0x1010")
        self.assertEqual(accesses[-1]["address"], "0x3000")
        self.assertEqual(accesses[-1]["instruction"], "MOV        RDI, QWORD PTR [RAX]")

    def test_direct_call_argument_and_return_witnesses(self):
        expected_rips = {
            "direct-call-argument": "0x1044",
            "direct-call-return-register": "0x1009",
        }
        for case in audit.CASES:
            if not case.name.startswith("direct-call-"):
                continue
            with self.subTest(case=case.name):
                _, accesses = audit.witness(case)
                if case.sensitive:
                    self.assertEqual(accesses[-1]["address"], "0x3008")
                    self.assertEqual(accesses[-1]["rip"], expected_rips[case.name])
                else:
                    self.assertEqual(accesses, [])
                self.assertTrue(audit.audit(case)["ok"])

    def test_wrong_reference_expectation_is_not_a_policy_failure(self):
        with self.assertRaisesRegex(ValueError, "disagrees"):
            audit.witness(audit.Case("invalid", "90c3"))

    def test_nonidentity_rmw_really_constructs_sensitive_address(self):
        case = next(
            case
            for case in audit.CASES
            if case.name == "rmw-constructs-sensitive-address"
        )
        inputs, accesses = audit.witness(case)
        self.assertEqual(inputs["RDI"], 0x8400)
        self.assertEqual(accesses[-1]["rip"], "0x1024")
        self.assertEqual(accesses[-1]["address"], "0x3000")
        self.assertTrue(audit.audit(case)["ok"])
        self.assertEqual(case.raw.count("48830710"), 1)
        without_add = replace(
            case,
            name="rmw-without-sensitive-increment",
            raw=case.raw.replace("48830710", "48830700"),
            sensitive=False,
        )
        self.assertTrue(audit.audit(without_add)["ok"])

    def test_identity_write_witnesses_cover_alias_and_disjoint_inputs(self):
        for case in audit.CASES:
            if not case.name.startswith("identity-write-"):
                continue
            for address in (0x8200, 0x8300, 0x83FF, 0x8400, 0x8401):
                with self.subTest(case=case.name, address=address):
                    _, accesses = audit.witness(
                        replace(case, registers={"RDI": address})
                    )
                    self.assertEqual(bool(accesses), case.sensitive)
                    if case.sensitive:
                        self.assertEqual(accesses[-1]["address"], "0x3000")

    def test_gap_is_reported_without_enshrining_current_bug(self):
        result = audit.audit(audit.CASES[0], lambda *a, **k: (b"JIT", "", 0))
        self.assertFalse(result["ok"])
        self.assertEqual(result["expected_status"], 2)
        self.assertEqual(result["actual_status"], 0)

    def test_refusal_requires_status_no_image_and_diagnostic(self):
        for response, valid in (
            ((b"", "CONTEXT_NATIVE_ONLY", 2), True),
            ((b"stale image", "CONTEXT_NATIVE_ONLY", 2), False),
            ((b"", "", 2), False),
            ((b"", "CONTEXT_NATIVE_ONLY", 1), False),
        ):
            with self.subTest(response=response):
                result = audit.audit(
                    audit.CASES[0], lambda *a, response=response, **k: response
                )
                self.assertEqual(result["ok"], valid)

    def test_safe_control_requires_success_and_an_image(self):
        for response, valid in (
            ((b"JIT", "", 0), True),
            ((b"", "", 0), False),
            ((b"", "CONTEXT_NATIVE_ONLY", 2), False),
        ):
            with self.subTest(response=response):
                result = audit.audit(
                    next(case for case in audit.CASES if not case.sensitive),
                    lambda *a, response=response, **k: response,
                )
                self.assertEqual(result["ok"], valid)

    def test_cli_reports_gap_and_tool_failure_separately(self):
        for payload, status in (({"ok": False}, 1), ({"ok": True}, 0)):
            with (
                patch.object(audit, "audit", return_value=payload),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(audit.main(["--case", audit.CASES[0].name]), status)
            self.assertEqual(json.loads(output.getvalue())["ok"], status == 0)
        with (
            patch.object(audit, "audit", side_effect=ValueError("broken fixture")),
            contextlib.redirect_stderr(io.StringIO()) as output,
        ):
            self.assertEqual(audit.main(["--case", audit.CASES[0].name]), 2)
        self.assertIn("broken fixture", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()

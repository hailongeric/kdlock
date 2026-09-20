"""Private test cases loaded by test_regression, not an extra test entry."""
import contextlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import regression as r
import verify_evidence as verifier


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name)
        # Mock only the runner's environment; never bypass a live script's
        # oracle or claim these subprocess fixtures executed translated code.
        for name, value in (("source_hashes", {}), ("check_idle", None)):
            helper = patch.object(r, name, return_value=value)
            setattr(self, name, helper.start())
            self.addCleanup(helper.stop)
        for name, value in (("call", 0), ("check_output", "clean\n")):
            helper = patch.object(r.subprocess, name, return_value=value)
            setattr(self, name, helper.start())
            self.addCleanup(helper.stop)
        root = patch.object(r, "ROOT", self.out / "source")
        root.start()
        self.addCleanup(root.stop)
        environment = patch.object(r.evidence, "environment")
        self.environment = environment.start()
        self.addCleanup(environment.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        # Boundary fixtures need two cases, not the live scope's growing list.
        self.cases = [r.Case("fixture-0", "unused-0.sh"),
                      r.Case("fixture-1", "unused-1.sh")]

    def test_two_successful_cases_and_evidence(self):
        self.assertEqual(r.run(self.cases, self.out, 60), 0)
        self.assertEqual(self.call.call_count, 2)
        for case in self.cases:
            for name in (
                "accepted",
                "exit-status",
                "dmesg.log",
                "artifacts.tar.gz",
                "protocol.tar.gz",
                "post-case-builds.tar.gz",
                "evidence.json",
                "result.json",
            ):
                self.assertTrue((self.out / case.name / name).exists())
            result = json.loads((self.out / case.name / "result.json").read_text())
            self.assertTrue(result["accepted"] and result["evidence_complete"])
        self.assertTrue((self.out / "source.tar.gz").is_file())
        self.assertEqual(self.check_idle.call_count, 4)
        command = self.call.call_args.args[0]
        self.assertEqual(command[:3], ["timeout", "--kill-after=5s", "60s"])
        args = self.environment.call_args.args
        self.assertEqual((args[0], args[2]), (self.out, r.ROOT))
        self.assertEqual(args[1], r.child_environment())

    def test_environment_failure_stops_before_any_workload(self):
        # Missing provenance must not be accepted as a passed/skipped workload.
        self.environment.side_effect = RuntimeError("environment capture failed")
        with self.assertRaisesRegex(RuntimeError, "environment capture failed"):
            r.run(self.cases, self.out, 60)
        self.call.assert_not_called()
        self.assertTrue((self.out / "source.tar.gz").is_file())
        self.assertFalse((self.out / self.cases[0].name).exists())

    def test_script_failure_and_timeout_stop_before_second_case(self):
        for status in (1, 124, 137):
            out = self.out / str(status)
            out.mkdir()
            self.call.reset_mock()
            self.call.return_value = status
            self.assertEqual(r.run(self.cases, out, 60), 1)
            self.call.assert_called_once()
            self.assertFalse((out / self.cases[0].name / "accepted").exists())
            self.assertFalse((out / self.cases[1].name).exists())
            result = json.loads((out / self.cases[0].name / "result.json").read_text())
            self.assertEqual(result["script_exit"], status)
            self.assertTrue(result["drained"] and result["evidence_complete"])
            self.assertFalse(result["accepted"])

    def test_zero_exit_with_kernel_fault_is_not_accepted(self):
        self.check_output.return_value = "BUG: fixture kernel fault"
        self.assertEqual(r.run(self.cases, self.out, 60), 1)
        self.call.assert_called_once()
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())

    def test_incomplete_drain_stops_without_unloading(self):
        self.check_idle.side_effect = [None, RuntimeError("still active")]
        with patch.object(r.evidence, "collect_case") as capture:
            self.assertEqual(r.run(self.cases, self.out, 60), 1)
            capture.assert_not_called()
        self.call.assert_called_once()
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())
        result = json.loads((self.out / self.cases[0].name / "result.json").read_text())
        self.assertFalse(result["drained"] or result["evidence_complete"])
        self.assertIn("still active", result["errors"][0])

    def test_source_changes_invalidate_current_result(self):
        self.source_hashes.side_effect = [{}, {}, {"changed.c": "new"}]
        self.assertEqual(r.run(self.cases, self.out, 60), 1)
        self.call.assert_called_once()
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())
        result = json.loads((self.out / self.cases[0].name / "result.json").read_text())
        self.assertFalse(result["source_unchanged"])
        self.assertIn("source changed during", result["errors"][0])

    def test_capture_error_or_missing_dmesg_never_creates_acceptance(self):
        for failure in ("archive", "dmesg"):
            out = self.out / failure
            out.mkdir()
            target = r.evidence if failure == "archive" else r.subprocess
            method = "collect_case" if failure == "archive" else "check_output"
            self.call.reset_mock()
            with patch.object(target, method, side_effect=OSError(failure)):
                self.assertEqual(r.run(self.cases, out, 60), 1)
            self.call.assert_called_once()
            result = json.loads((out / self.cases[0].name / "result.json").read_text())
            self.assertFalse(result["accepted"])
            self.assertTrue(result["errors"])
            self.assertFalse((out / self.cases[1].name).exists())

    def test_failed_oracle_still_retains_generated_bytes(self):
        # Failure evidence must survive the next manual cleanup, without
        # turning that retained image into an accepted or executed JIT result.
        image = r.ROOT / "daemon/0x123/asm/jit.bin"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"captured generated bytes")
        self.call.return_value = 17
        self.assertEqual(r.run(self.cases, self.out, 60), 1)
        path = self.out / self.cases[0].name / "artifacts.tar.gz"
        with tarfile.open(path) as archive:
            self.assertEqual(
                archive.extractfile("daemon/0x123/asm/jit.bin").read(),
                image.read_bytes(),
            )
        self.assertFalse((self.out / self.cases[0].name / "accepted").exists())

    def test_stop_marker_does_not_interrupt_current_case(self):
        def finish(*args, **kwargs):
            (self.out / "STOP").touch()
            return 0

        self.call.side_effect = finish
        self.assertEqual(r.run(self.cases, self.out, 60), 93)
        self.call.assert_called_once()
        self.assertTrue((self.out / self.cases[0].name / "accepted").exists())
        self.assertFalse((self.out / self.cases[1].name).exists())

    def offline_run(self, status=0):
        # Reuse the real collector and existing substituted runner, not a
        # handwritten archive layout or any native/JIT execution claim.
        # Real captures live outside the checkout. Keep this fixture's source
        # separate too, so an extra case directory is not silently tolerated.
        source_directory = tempfile.TemporaryDirectory(prefix="kdlock-offline-source-")
        self.addCleanup(source_directory.cleanup)
        root = patch.object(r, "ROOT", Path(source_directory.name))
        root.start()
        self.addCleanup(root.stop)
        source = r.ROOT / "fixture.c"
        source.write_bytes(b"frozen fixture, never compiled\n")
        self.source_hashes.return_value = {
            "fixture.c": r.evidence.digest(source.read_bytes())
        }

        def environment(out, *args):
            notes = b"fixture boot notes"
            (out / "kernel.notes").write_bytes(notes)
            r.evidence.write_json(
                out / "environment.json",
                {"errors": {}, "kernel_notes_sha256": r.evidence.digest(notes)},
            )

        self.environment.side_effect = environment
        self.call.return_value = status
        return r.run(self.cases, self.out, 60)

    def test_offline_verification_uses_archived_bytes_and_never_runs_payloads(self):
        self.assertEqual(self.offline_run(), 0)
        (r.ROOT / "fixture.c").write_text("current checkout differs from old capture")
        for operation in (self.call, self.check_output, self.check_idle):
            operation.reset_mock()
        before = {p: p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        report = verifier.verify_run(self.out)
        self.assertTrue(report["all_recorded_accepted"])
        self.assertEqual(report["source_files"], 1)
        self.assertEqual(report["unrecorded_cases"], [])
        self.assertEqual(
            [c["name"] for c in report["cases"]], [c.name for c in self.cases]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(verifier.main([str(self.out)]), 0)
        self.assertEqual(json.loads(output.getvalue()), report)
        for operation in (self.call, self.check_output, self.check_idle):
            operation.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_offline_recorded_failure_and_unrecorded_cases_never_pass(self):
        self.assertEqual(self.offline_run(17), 1)
        report = verifier.verify_run(self.out)
        self.assertFalse(report["all_recorded_accepted"])
        self.assertFalse(report["cases"][0]["recorded_accepted"])
        self.assertEqual(report["unrecorded_cases"], [self.cases[1].name])
        self.assertEqual(verifier.main([str(self.out)]), 1)
        # No result is not proof of process termination or even of nonexecution.
        (self.out / self.cases[1].name).mkdir()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(verifier.main([str(self.out)]), 2)

    def test_offline_rejects_inconsistent_manifests_status_logs_and_links(self):
        self.assertEqual(self.offline_run(), 0)
        case = self.out / self.cases[0].name
        result = json.loads((case / "result.json").read_text())
        changes = [
            (self.out / "source.json", b"{}"),
            (self.out / "source.tar.gz", b"corrupted archive"),
            (self.out / "kernel.notes", b"different boot"),
            (self.out / "environment.json", b'{"errors":{},"errors":{"lost":"probe"}}'),
            (self.out / "results.tsv", b"duplicate\t0\nduplicate\t0\n"),
            (case / "exit-status", b"17\n"),
            (case / "dmesg.log", b"BUG: not recorded in the result\n"),
            (case / "accepted", b"not an empty marker"),
            (case / "result.json", json.dumps(result | {"accepted": 1}).encode()),
            (
                case / "result.json",
                json.dumps(result | {"errors": ["lost evidence"]}).encode(),
            ),
        ]
        for path, data in changes:
            old = path.read_bytes()
            with self.subTest(path=path, data=data[:40]):
                try:
                    path.write_bytes(data)
                    with self.assertRaises((RuntimeError, ValueError)):
                        verifier.verify_run(self.out)
                finally:
                    path.write_bytes(old)
        path = case / "protocol.tar.gz"
        old = path.read_bytes()
        path.unlink()
        with self.assertRaises(OSError):
            verifier.verify_run(self.out)
        path.symlink_to(self.out / "source.tar.gz")
        with self.assertRaises(RuntimeError):
            verifier.verify_run(self.out)
        path.unlink()
        path.write_bytes(old)
        extra = self.out / "unselected-case"
        extra.mkdir()
        with self.assertRaisesRegex(RuntimeError, "unselected"):
            verifier.verify_run(self.out)

    def test_offline_archive_members_need_exact_hashes_and_safe_unique_names(self):
        self.assertEqual(self.offline_run(), 0)
        case = self.out / self.cases[0].name
        manifest = json.loads((case / "evidence.json").read_text())
        name, payload = "daemon/0x1/asm/jit.bin", b"never execute these bytes"
        for damage in (
            "duplicate",
            "link",
            "device",
            "traversal",
            "missing",
            "extra",
            "hash",
        ):
            # Update the outer hash too, to exercise member validation rather
            # than stopping at the compressed-file checksum every time.
            with self.subTest(damage=damage):
                path = case / "artifacts.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    info = tarfile.TarInfo(
                        "../outside" if damage == "traversal" else name
                    )
                    info.size = len(payload)
                    if damage == "link":
                        info.type, info.linkname, info.size = (
                            tarfile.SYMTYPE,
                            "/etc/shadow",
                            0,
                        )
                    elif damage == "device":
                        info.type, info.size = tarfile.CHRTYPE, 0
                    if damage != "missing":
                        archive.addfile(info, io.BytesIO(payload))
                    if damage == "duplicate":
                        archive.addfile(info, io.BytesIO(payload))
                manifest["archives"]["artifacts"] = {
                    "sha256": r.evidence.digest(path.read_bytes()),
                    "files": {}
                    if damage == "extra"
                    else {
                        name: "0" * 64
                        if damage == "hash"
                        else r.evidence.digest(payload)
                    },
                }
                r.evidence.write_json(case / "evidence.json", manifest)
                expected = {
                    "duplicate": "duplicate archive member",
                    "link": "unsafe archive member",
                    "device": "unsafe archive member",
                    "traversal": "unsafe archive member",
                    "missing": "hashes/membership mismatch",
                    "extra": "unlisted archive member",
                    "hash": "hashes/membership mismatch",
                }
                with self.assertRaisesRegex(RuntimeError, expected[damage]):
                    verifier.verify_run(self.out)
        self.assertFalse((self.out / "outside").exists())

    def test_offline_read_limits_and_cross_file_mutation_are_not_silent(self):
        self.assertEqual(self.offline_run(), 0)
        for limit in ("MAX_METADATA", "MAX_ARCHIVE", "MAX_EXPANDED", "MAX_MEMBERS"):
            with (
                self.subTest(limit=limit),
                patch.object(verifier, limit, 0),
                self.assertRaisesRegex(RuntimeError, "limit"),
            ):
                verifier.verify_run(self.out)
        original = verifier.Snapshot.archive

        def mutate(snapshot, path, record):
            value = original(snapshot, path, record)
            if path.name == "protocol.tar.gz":
                # Keep JSON valid; only the end-of-inspection identity check
                # can detect a previously read file changing in this schedule.
                env = self.out / "environment.json"
                env.write_bytes(env.read_bytes() + b"\n")
            return value

        with (
            patch.object(verifier.Snapshot, "archive", mutate),
            self.assertRaisesRegex(RuntimeError, "changed file"),
        ):
            verifier.verify_run(self.out)

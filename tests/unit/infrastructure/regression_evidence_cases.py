"""Private test cases loaded by test_regression, not an extra test entry."""
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import regression as r


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="kdlock-evidence-", dir="/tmp")
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.root = self.base / "checkout"
        self.out = self.base / "run"
        self.case = self.out / "case"
        self.root.mkdir()
        self.case.mkdir(parents=True)
        (self.case / "output.log").write_text("")

    def collect(self, text=""):
        (self.case / "output.log").write_text(text)
        return r.evidence.collect_case(self.root, self.out, self.case)

    def test_source_archive_contains_exact_bytes_and_rejects_changed_inputs(self):
        path = self.root / "fixture.c"
        path.write_bytes(b"source\n")
        frozen = {"fixture.c": r.evidence.digest(path.read_bytes())}
        r.evidence.freeze_source(self.root, self.out, frozen)
        with tarfile.open(self.out / "source.tar.gz") as archive:
            self.assertEqual(archive.extractfile("fixture.c").read(), b"source\n")
        other = self.base / "changed"
        other.mkdir()
        path.write_bytes(b"edited\n")
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            r.evidence.freeze_source(self.root, other, frozen)
        self.assertFalse((other / "source.tar.gz").exists())
        self.assertTrue((other / "source.tar.gz.partial").exists())

    def test_protocol_tree_and_log_declarations_are_deduplicated(self):
        protocol = self.base / "protocol"
        protocol.mkdir()
        nested = protocol / "writer"
        nested.mkdir()
        (nested / "result.json").write_text('{"closed": true}\n')
        daemon = protocol / "daemon.log"
        daemon.write_text("translation finished\n")
        result = self.collect(
            f"  [INFO] Evidence: {protocol}\nEvidence: {protocol}\n"
            f"Evidence: {nested}\n  [INFO] Evidence file: {daemon}\n"
        )
        self.assertEqual(result["directories"], [str(protocol)])
        self.assertEqual(result["files"], [])
        with tarfile.open(self.case / "protocol.tar.gz") as archive:
            self.assertEqual(len(archive.getmembers()), 2)
            self.assertEqual(
                archive.extractfile(str(daemon.relative_to(Path("/tmp")))).read(),
                b"translation finished\n",
            )

    def test_standalone_log_and_post_case_build_bytes_are_preserved(self):
        log = self.base / "daemon.log"
        log.write_text("not a JIT execution witness\n")
        binary = self.root / "daemon/daemon"
        binary.parent.mkdir()
        binary.write_bytes(b"post-case build, not loaded identity")
        result = self.collect(f"Evidence file: {log}\nEvidence file: {log}\n")
        self.assertEqual(result["files"], [str(log)])
        builds = result["archives"]["post-case-builds"]
        self.assertEqual(
            builds["files"], {"daemon/daemon": r.evidence.digest(binary.read_bytes())}
        )
        self.assertEqual(
            builds["sha256"],
            r.evidence.digest((self.case / "post-case-builds.tar.gz").read_bytes()),
        )

    def test_protocol_symlinks_are_metadata_never_followed_or_extracted(self):
        protocol = self.base / "protocol"
        protocol.mkdir()
        link = protocol / "compiler.py"
        target = self.base / "outside.py"
        target.write_text("must not be read through the protocol link\n")
        link.symlink_to(target)
        # A dangling link and a directory link are also non-payload metadata.
        (protocol / "missing").symlink_to(self.base / "missing-target")
        (protocol / "outside-dir").symlink_to(self.root, target_is_directory=True)
        result = self.collect(f"Evidence: {protocol}\n")
        self.assertEqual(len(result["symlinks"]), 3)
        self.assertEqual(
            result["symlinks"][str(link.relative_to(Path("/tmp")))], str(target)
        )
        with tarfile.open(self.case / "protocol.tar.gz") as archive:
            self.assertEqual(archive.getmembers(), [])
        self.assertNotIn("must not be read", (self.case / "evidence.json").read_text())

    def test_invalid_or_recursive_declared_paths_are_refused(self):
        for path in (
            "/etc/passwd",
            "/tmp/unrelated.log",
            "/tmp/kdlock-x/../secret",
            str(self.case),
            str(self.out),
            str(self.base),
        ):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                r.evidence.declared_paths(f"Evidence: {path}\n", self.out)

    def test_missing_declared_directory_and_file_are_errors(self):
        for kind in ("", " file"):
            with self.subTest(kind=kind), self.assertRaises((RuntimeError, OSError)):
                self.collect(f"Evidence{kind}: {self.base / 'missing'}\n")
            for path in self.case.glob("*.gz*"):
                path.unlink()
        self.assertFalse((self.case / "evidence.json").exists())

    def test_symlinks_and_special_files_are_not_archived(self):
        regular = self.base / "plain"
        regular.write_text("payload")
        for kind in ("file-link", "directory-link", "fifo"):
            target = self.base / kind
            if kind == "file-link":
                target.symlink_to(regular)
            elif kind == "directory-link":
                target.symlink_to(self.root, target_is_directory=True)
            else:
                os.mkfifo(target)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                r.evidence.tree_files(self.base)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                r.evidence.regular_bytes(target)
            target.unlink()

    def test_late_same_name_log_mutation_invalidates_capture(self):
        protocol = self.base / "protocol"
        protocol.mkdir()
        log = protocol / "role.log"
        log.write_text("original\n")
        real_archive = r.evidence.archive_files

        def mutate(destination, files, expected=None):
            result = real_archive(destination, files, expected)
            if destination.name == "protocol.tar.gz":
                log.write_text("late writer\n")
            return result

        with (
            patch.object(r.evidence, "archive_files", side_effect=mutate),
            self.assertRaisesRegex(RuntimeError, "evidence changed after"),
        ):
            self.collect(f"Evidence: {protocol}\n")
        self.assertFalse((self.case / "evidence.json").exists())

    def test_environment_retains_boot_dependencies_and_only_build_environment(self):
        # Reuse the real read-only guest capture; it is neither a build nor a
        # translated-code execution, and must never dump unrelated env secrets.
        env = r.child_environment()
        env["UNRELATED_TOKEN"] = "do not archive this value"
        env["CFLAGS"] = "-O1 -g"
        r.evidence.environment(self.out, env, r.ROOT)
        record = json.loads((self.out / "environment.json").read_text())
        self.assertEqual(record["uname"]["release"], os.uname().release)
        self.assertEqual(
            record["kernel_notes_sha256"],
            r.evidence.digest((self.out / "kernel.notes").read_bytes()),
        )
        self.assertTrue(record["online_cpus"])
        self.assertEqual(record["stage"], "before_cases")
        self.assertEqual(record["cwd"], str(r.ROOT))
        self.assertIn("preempt", record["runtime_settings"])
        self.assertFalse(record["errors"])
        self.assertIn("filesystems", record["mount"])
        self.assertEqual(record["build_environment"]["CFLAGS"], "-O1 -g")
        self.assertEqual(record["build_environment"]["LC_ALL"], "C")
        self.assertNotIn("UNRELATED_TOKEN", record["build_environment"])
        self.assertNotIn("do not archive this value", json.dumps(record))
        self.assertEqual(
            set(record["python"]["packages"]),
            {"miasm", "pyelftools", "future", "pyparsing"},
        )
        for name, probe in record["tools"].items():
            with self.subTest(tool=name):
                self.assertEqual(probe["returncode"], 0)
                self.assertNotIn("error", probe)
                self.assertEqual(
                    probe["sha256"],
                    r.evidence.digest(Path(probe["resolved"]).read_bytes()),
                )

    def test_probe_preserves_selected_path_and_bounds_failures(self):
        # Hash the target, but preserve the path used to launch a venv/tool.
        tools = self.root / "bin"
        tools.mkdir()
        binary = tools / "python-real"
        binary.write_bytes(b"fixture only: never executed")
        binary.chmod(0o755)
        link = tools / "python3"
        link.symlink_to(binary)
        env = {"PATH": "bin"}
        command = ["python3", "--version"]
        with patch.object(r.evidence.subprocess, "run") as launch:
            launch.return_value = subprocess.CompletedProcess(command, 0, "v\n", "")
            probe = r.evidence.command_observation(command, env, self.root)
            self.assertNotIn("error", probe)
            self.assertEqual(probe["resolved"], str(binary))
            self.assertEqual(launch.call_args.args[0], [str(link), "--version"])
            self.assertEqual(launch.call_args.kwargs["timeout"], 10)
            self.assertEqual(launch.call_args.kwargs["cwd"], self.root)
            for failure in (
                OSError("unavailable"),
                subprocess.TimeoutExpired(command, 10),
            ):
                launch.side_effect = failure
                probe = r.evidence.command_observation(command, env, self.root)
                self.assertIn("error", probe)
            launch.side_effect = None
            launch.return_value = subprocess.CompletedProcess(command, 17, "", "bad")
            probe = r.evidence.command_observation(command, env, self.root)
            self.assertEqual(probe["returncode"], 17)
            self.assertEqual(probe["stderr"], "bad")
            self.assertIn("error", probe)
            launch.reset_mock()
            probe = r.evidence.command_observation(["missing"], env, self.root)
            self.assertIn("error", probe)
            launch.assert_not_called()

    def test_failed_or_malformed_environment_probe_is_retained_not_accepted(self):
        for failure in ({"error": "missing package"}, {"stdout": "not JSON"}):
            with (
                self.subTest(probe=failure),
                patch.object(
                    r.evidence,
                    "command_observation",
                    side_effect=lambda *args, record=failure: record.copy(),
                ),
                self.assertRaisesRegex(RuntimeError, "environment capture failed"),
            ):
                r.evidence.environment(self.out, r.child_environment(), r.ROOT)
            record = json.loads((self.out / "environment.json").read_text())
            self.assertIn("error", record["tools"]["python3"])
            self.assertTrue((self.out / "kernel.notes").is_file())

        # A missing debugfs observation also retains a manifest and stops; it
        # must not look like a verified runtime configuration or a clean SKIP.
        read_text = Path.read_text

        def missing_preempt(path, *args, **kwargs):
            if str(path) == "/sys/kernel/debug/sched/preempt":
                raise PermissionError("preempt observation denied")
            return read_text(path, *args, **kwargs)

        with (
            patch.object(Path, "read_text", missing_preempt),
            patch.object(
                r.evidence, "command_observation", return_value={"stdout": "{}"}
            ),
            self.assertRaisesRegex(RuntimeError, "runtime_settings.preempt"),
        ):
            r.evidence.environment(self.out, r.child_environment(), r.ROOT)
        record = json.loads((self.out / "environment.json").read_text())
        self.assertIn(
            "preempt observation denied", record["errors"]["runtime_settings.preempt"]
        )

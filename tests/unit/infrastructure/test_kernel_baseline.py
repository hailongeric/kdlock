#!/usr/bin/env python3
"""Exercise read-only baseline checks with mutations, never a running kernel."""

import hashlib
import importlib.util
import io
import json
import os
import struct
import tarfile
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "kernel_baseline", Path(__file__).resolve().parents[3] / "kernel_baseline/verify.py"
)
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def note(name=b"GNU\0", data=b"build-id", kind=3):
    return (
        struct.pack("<III", len(name), len(data), kind)
        + name
        + b"\0" * (-len(name) % 4)
        + data
        + b"\0" * (-len(data) % 4)
    )


class KernelBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kd-kernel-baseline-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"
        self.source = self.root / "source"
        self.bundle.mkdir()
        self.source.mkdir()
        (self.bundle / "guest.config").write_bytes(b"CONFIG_FIXTURE=y\n")
        (self.bundle / "guest.patch").write_bytes(b"fixture patch\n")
        (self.source / ".config").write_bytes(b"CONFIG_FIXTURE=y\n")
        (self.source / "hook.c").write_bytes(b"patched hook\n")
        (self.source / "vmlinux").write_bytes(b"fixture image\n")
        self.manifest = {
            "schema": 1,
            "bundle_files": {
                "guest.config": sha(b"CONFIG_FIXTURE=y\n"),
                "guest.patch": sha(b"fixture patch\n"),
            },
            "source_files": {"hook.c": sha(b"patched hook\n")},
            "build_files": {"vmlinux": sha(b"fixture image\n")},
        }
        self.save_manifest()

    def save_manifest(self):
        (self.bundle / "manifest.json").write_text(json.dumps(self.manifest))

    def test_scoped_check_is_read_only(self):
        before = {path: path.read_bytes() for path in self.source.iterdir()}
        self.assertEqual(
            baseline.verify(self.bundle, self.source, build=True),
            {
                "ok": True,
                "bundle_files": 2,
                "source_files": 1,
                "config": True,
                "build_files": 1,
            },
        )
        self.assertEqual(
            before, {path: path.read_bytes() for path in self.source.iterdir()}
        )

    def test_each_input_drift_fails_even_with_same_release(self):
        for path in (
            self.source / "hook.c",
            self.source / ".config",
            self.source / "vmlinux",
            self.bundle / "guest.patch",
            self.bundle / "guest.config",
        ):
            with self.subTest(path=path):
                saved = path.read_bytes()
                path.write_bytes(saved + b"changed")
                with self.assertRaisesRegex(baseline.BaselineError, "SHA256 mismatch"):
                    baseline.verify(self.bundle, self.source, build=True)
                path.write_bytes(saved)

    def test_missing_symlink_and_escaping_paths_fail(self):
        path = self.source / "hook.c"
        path.unlink()
        with self.assertRaisesRegex(baseline.BaselineError, "missing"):
            baseline.verify(self.bundle, self.source)
        path.symlink_to(self.bundle / "guest.config")
        with self.assertRaisesRegex(baseline.BaselineError, "escapes"):
            baseline.verify(self.bundle, self.source)
        path.unlink()
        path.symlink_to(".config")
        with self.assertRaisesRegex(baseline.BaselineError, "non-regular"):
            baseline.verify(self.bundle, self.source)
        for name in ("../hook.c", "/hook.c", "a//b", ".", "", None):
            with self.subTest(name=name), self.assertRaises(baseline.BaselineError):
                baseline.relative_path(name)

    def test_malformed_manifest_fails(self):
        for field, value in (
            ("schema", 2),
            ("schema", True),
            ("schema", 1.0),
            ("source_files", {}),
            ("source_files", {"hook.c": "invalid digest"}),
        ):
            old = self.manifest[field]
            self.manifest[field] = value
            self.save_manifest()
            with self.assertRaises(baseline.BaselineError):
                baseline.verify(self.bundle, self.source)
            self.manifest[field] = old
        for value in ([], None, 1, True):
            (self.bundle / "manifest.json").write_text(json.dumps(value))
            with self.assertRaises(baseline.BaselineError):
                baseline.verify(self.bundle, self.source)

    def test_raw_notes_padding_and_unrelated_notes(self):
        self.assertEqual(
            baseline.note_build_id(note(b"Xen\0", b"x", 3) + note()), b"build-id".hex()
        )
        for data in (
            b"",
            note()[:-1],
            note() + b"x",
            note() + note(),
            note(data=b""),
            struct.pack("<III", 0xFFFFFFFF, 8, 3),
        ):
            with self.subTest(data=data), self.assertRaises(baseline.BaselineError):
                baseline.note_build_id(data)

    def test_running_identity_is_not_release_alone(self):
        uname = os.uname_result(("Linux", "fixture", "6.1.159", "#28", "x86_64"))
        expected = {
            "release": "6.1.159",
            "version": "#28",
            "machine": "x86_64",
            "build_id": b"build-id".hex(),
        }
        self.assertEqual(
            baseline.check_running(expected, uname, note()), b"build-id".hex()
        )
        with self.assertRaisesRegex(baseline.BaselineError, "Build ID"):
            baseline.check_running(expected, uname, note(data=b"another build"))
        for field in ("release", "version", "machine"):
            changed = dict(expected, **{field: "different"})
            with self.subTest(field=field), self.assertRaises(baseline.BaselineError):
                baseline.check_running(changed, uname, note())

    def archive(self, extra=()):
        path = self.root / "linux.tar.xz"
        with tarfile.open(path, "w:xz") as archive:
            for name, data in (
                ("linux/hook.c", b"original hook\n"),
                ("linux/ordinary.c", b"ordinary\n"),
                *extra,
            ):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            member = tarfile.TarInfo("linux/link.h")
            member.type = tarfile.SYMTYPE
            member.linkname = "./ordinary.c"
            archive.addfile(member)
        self.manifest["upstream"] = {
            "directory": "linux",
            "sha256": sha(path.read_bytes()),
            "entries": 3 + len(extra),
        }
        self.save_manifest()
        return path

    def prepare_full_source(self):
        (self.source / "ordinary.c").write_bytes(b"ordinary\n")
        (self.source / "link.h").symlink_to("ordinary.c")

    def test_full_archive_checks_ordinary_files_and_links(self):
        archive = self.archive()
        self.prepare_full_source()
        result = baseline.verify(self.bundle, self.source, archive=archive)
        self.assertEqual(result["upstream_members"], 3)
        ordinary = self.source / "ordinary.c"
        ordinary.write_bytes(b"hidden change\n")
        baseline.verify(self.bundle, self.source)  # Scoped checks are not full checks.
        with self.assertRaisesRegex(baseline.BaselineError, "ordinary.c"):
            baseline.verify(self.bundle, self.source, archive=archive)
        ordinary.write_bytes(b"ordinary\n")
        (self.source / "link.h").unlink()
        (self.source / "link.h").symlink_to("hook.c")
        with self.assertRaisesRegex(baseline.BaselineError, "symlink mismatch"):
            baseline.verify(self.bundle, self.source, archive=archive)

    def test_full_archive_checksum_count_and_member_validation(self):
        self.prepare_full_source()
        archive = self.archive()
        original = archive.read_bytes()
        archive.write_bytes(original + b"changed")
        with self.assertRaisesRegex(baseline.BaselineError, "SHA256 mismatch"):
            baseline.verify(self.bundle, self.source, archive=archive)
        archive.write_bytes(original)
        self.manifest["upstream"]["entries"] = 4
        self.save_manifest()
        with self.assertRaisesRegex(baseline.BaselineError, "entry count"):
            baseline.verify(self.bundle, self.source, archive=archive)
        for name in ("linux/../outside", "other/file", "linux/hook.c"):
            archive = self.archive(((name, b"x"),))
            with self.subTest(name=name), self.assertRaises(baseline.BaselineError):
                baseline.verify(self.bundle, self.source, archive=archive)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Guest checks for assembly provenance, drain gating and completed-file publication."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import assembly
import bench_session


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spin-assembly-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.archive = assembly.AssemblyArchive(self.run, self.root / "views")
        (self.run / "payload-disassembly.txt").write_text(
            "Disassembly of section .text:\n\n0000000000000000 <sc_body_1>:\n"
            "  0: call 5\n    1: R_X86_64_PLT32 _raw_spin_lock-0x4\n"
            "  5: add $0x1,%rax\n  9: ret\n\n0000000000000010 <sc_body_2>:\n"
            " 10: nop\nDisassembly of section .init.text:\n 0: ret\n")

    def session(self, name="c01-t04-r00-kdlock", *, jit=True, legacy=False):
        """A saved publication and its matching workspace, not a running JIT."""
        session = self.run / name
        folder = session / "workspace/daemon/0x1000/42/asm"
        folder.mkdir(parents=True)
        for filename, content in {"jit.bin": b"\xc3", "bin.txt": b"0: c3 ret\n",
                                  "jit.S": b"loc_1000:\nMOV             Stack_JIT_WITNESS, 1\nRET\n"}.items():
            (folder / filename).write_bytes(content)
        publication = dict(entry=dict(entry=0x1000, tgid=42, code=0x9000,
                                      lock_kind=1, status=0, pid=0),
                           source=dict(state=0, frames=0, modules=1, writers=0),
                           images={p.name: assembly.sha256(p.read_bytes())
                                   for p in folder.iterdir() if not legacy or p.name != "bin.txt"})
        record = dict(name=name, arm="kdlock", cachelines=1, threads=4, iterations=100000,
                      repeat=0, cpus=[0, 1, 2, 3], execution_status="OK", drained=True,
                      jit_status="JIT" if jit else "NO_JIT", jit_bodies=400000 if jit else 0,
                      jit_share=1.0 if jit else 0.0, published_before=publication,
                      published_after=publication, entry_range=[0x1000, 0x1100],
                      retired=dict(state=2, modules=0, frames=0, writers=0))
        (session / "session.json").write_text(json.dumps(record))
        return session, folder, record

    def test_copies_matching_entry_and_indexes_jit_and_no_jit(self):
        session, folder, _ = self.session()
        # An unrelated earlier workspace must not supply either requested file.
        other = session / "workspace/daemon/0x1/1/asm"
        other.mkdir(parents=True)
        (other / "jit.S").write_text("wrong translation")
        original = {p: p.read_bytes() for p in session.rglob("*") if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            assembly.capture_completed(self.archive, session)
        dest = self.archive.path / session.name
        for target, source in (("JIT.S", "jit.S"), ("bin.txt", "bin.txt")):
            self.assertEqual((dest / target).read_bytes(), (folder / source).read_bytes())
        native = (dest / "native.S").read_text()
        self.assertIn("_raw_spin_lock-0x4", native)
        self.assertNotIn("<sc_body_2>", native)
        self.assertIn("ELF section offsets", native)
        second, _, _ = self.session("c01-t01-r01-kdlock", jit=False)
        self.archive.capture(second)
        rows = json.loads((self.archive.path / "index.json").read_text())["sessions"]
        self.assertEqual([r["jit_status"] for r in rows], ["JIT", "NO_JIT"])
        self.assertEqual(rows[1]["jit_share"], 0)
        self.assertTrue(rows[0]["bin_txt_hashed_during_measurement"])
        for row in rows:
            for name, digest in row["sha256"].items():
                self.assertEqual(assembly.sha256((self.archive.path / row["name"] / name).read_bytes()),
                                 digest)
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        pointer = json.loads((self.run / "assembly-export.json").read_text())
        self.assertEqual(pointer["directory"], str(self.archive.path))
        self.assertFalse(list(self.archive.path.glob(".pending-*")))

    def test_native_failed_and_undrained_do_not_read_workspace(self):
        for i, (arm, status, drained) in enumerate((
                ("native", "OK", True), ("kdlock", "DATA_ERROR", True),
                ("kdlock", "TIMEOUT", False), ("kdlock", "OK", False))):
            session = self.run / f"case{i}"
            session.mkdir()
            (session / "session.json").write_text(json.dumps(dict(
                arm=arm, execution_status=status, drained=drained)))
            with self.subTest(arm=arm, status=status, drained=drained):
                self.assertIsNone(self.archive.capture(session))
        self.assertIsNone(self.archive.path)
        self.assertFalse(self.archive.root.exists())

    def test_missing_or_modified_publication_is_not_exported(self):
        for name in ("jit.S", "jit.bin", "bin.txt"):
            for fault in ("missing", "changed"):
                session, folder, _ = self.session(f"{name.replace('.', '-')}-{fault}")
                if fault == "missing":
                    (folder / name).unlink()
                else:
                    (folder / name).write_bytes(b"different bytes")
                with self.subTest(name=name, fault=fault), self.assertRaises(ValueError):
                    self.archive.capture(session)
        self.assertIsNone(self.archive.path)

    def test_publication_hashes_disassembly_before_export(self):
        session, folder, record = self.session()
        instance = object.__new__(bench_session.Session)
        instance.path, instance.record = session, record
        expected = record["published_before"]
        with patch.object(bench_session, "registry", return_value=[expected["entry"]]), \
                patch.object(bench_session, "status", return_value=expected["source"]):
            self.assertEqual(instance.publication(), expected)
            (folder / "bin.txt").write_text("changed disassembly")
            after = instance.publication()
            self.assertNotEqual(expected, after)
            self.assertNotEqual(expected["images"]["bin.txt"], after["images"]["bin.txt"])
            (folder / "bin.txt").unlink()
            with self.assertRaises(bench_session.Failure):
                instance.publication()

    def test_legacy_export_is_fresh_and_preserves_original_evidence(self):
        session, _, _ = self.session(legacy=True)
        (self.run / "plan.json").write_text(json.dumps([dict(name=session.name)]))
        before = {p: p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        # Exercise the saved-run CLI twice. It must create new views without
        # writing pointers into old evidence or replacing an earlier export.
        exports = []
        for _ in range(2):
            output = io.StringIO()
            cls = assembly.AssemblyArchive
            with patch.object(assembly, "AssemblyArchive",
                              side_effect=lambda run: cls(run, self.root / "views")):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(assembly.main([str(self.run)]), 0)
            exports.append(json.loads(output.getvalue())["directory"])
        self.assertNotEqual(*exports)
        row = json.loads((Path(exports[0]) / "index.json").read_text())["sessions"][0]
        self.assertFalse(row["bin_txt_hashed_during_measurement"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
        self.archive.capture(session)
        with self.assertRaises(FileExistsError):
            self.archive.capture(session)

    def test_native_symbol_must_be_unambiguous_and_paths_stay_local(self):
        for content in ("no symbols", "0 <sc_body_1>:\n1 <sc_body_1>:\n"):
            with self.assertRaises(ValueError):
                assembly.native_body(content, 1)
        for name in ("../outside", "/tmp/outside", "a/b"):
            with self.assertRaises(ValueError):
                assembly.component(name)
        with self.assertRaises(ValueError):
            self.archive.capture(self.root / "another-run/session")


if __name__ == "__main__":
    unittest.main()

"""Guest-only ELF interval, prefetch and quiescent-image evidence checks."""
import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import list_audit as audit
from bench_session import Session


class ListAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def assemble(self, name, text):
        source, binary = self.root/(name + ".S"), self.root/(name + ".o")
        source.write_text(text)
        subprocess.run(["cc", "-c", str(source), "-o", str(binary)],
                       capture_output=True, check=True, timeout=20)
        return binary

    def test_function_extent_excludes_prefetch_in_another_function(self):
        for hint in ("nop", "prefetcht0 (%rax)", "prefetchnta (%rax)", "prefetchw (%rax)"):
            binary = self.assemble("payload", f"""
.text
.type decoy,@function
decoy: prefetcht0 (%rax)
ret
.size decoy,.-decoy
.type payload,@function
payload: {hint}
ret
.size payload,.-payload
""")
            for expected in (False, True):
                valid = hint != "prefetchw (%rax)" and expected == (hint != "nop")
                if valid:
                    result = audit.functions(binary, ["payload"], expected, self.root/"source-audit")
                    self.assertEqual(bool(result["functions"]["payload"]["hints"]), expected)
                else:
                    with self.assertRaises(RuntimeError):
                        audit.functions(binary, ["payload"], expected, self.root/"source-audit")

    def test_decoder_failures_reach_session_reporting_and_cleanup(self):
        # Substitute only the file-decoder process and physical cleanup here.
        # Production Session must classify failure and attempt its drain path;
        # the live runner still has to prove actual worker/source/module drain.
        for error in (
                subprocess.CalledProcessError(1, ["objdump"], output="decoder failed"),
                subprocess.TimeoutExpired(["objdump"], 15, output=b"partial decode")):
            with self.subTest(error=type(error).__name__):
                output = self.root / type(error).__name__

                class AuditSession(Session):
                    def __init__(self):
                        self.record = dict(execution_status="PREPARING")
                        self.kmsg = os.open(os.devnull, os.O_RDONLY)
                        self.cleaned = False
                        self.saved = []

                    def prepare(self):
                        audit.inspect_bytes(b"\x90", 48, False, output)

                    def measure(self):
                        raise AssertionError("failed audit reached measurement")

                    def cleanup(self):
                        self.cleaned = True

                    def save(self):
                        self.saved.append(dict(self.record))

                session = AuditSession()
                with patch.object(audit.subprocess, "check_output", side_effect=error), \
                        self.assertRaises(audit.Failure) as caught:
                    session.execute()
                self.assertEqual(caught.exception.status, "PREPARATION_FAILED")
                self.assertFalse(caught.exception.unsafe)
                self.assertTrue(session.cleaned)
                self.assertEqual(session.saved[-1]["execution_status"], "PREPARATION_FAILED")
                self.assertIn("finished_ns", session.saved[-1])
                self.assertIn("resident-list disassembly failed", session.saved[-1]["error"])
                self.assertEqual(output.with_suffix(".bin").read_bytes(), b"\x90")
                self.assertIn(str(error), output.with_suffix(".txt").read_text())
                with self.assertRaises(OSError):
                    os.fstat(session.kmsg)

    def generated(self, hint="prefetcht0 (%rax)", abi=2, requirements=0):
        obj = self.assemble("generated", f"""
.text
/* Deliberate decoy in the header, outside the generated code interval. */
.byte 0x0f,0x18,0x08
.zero 6
.ascii "KDWB002"
.zero 9
.ascii "KDWC002"
.zero 9
.ascii "KDAB"
.byte {abi},2,{requirements}
generated_body:
{hint}
comp_syscall:
prefetcht0 (%rax)
ret
""")
        binary = self.root/"jit.bin"
        subprocess.run(["objcopy", "-O", "binary", str(obj), str(binary)],
                       check=True, capture_output=True, timeout=10)
        return obj, binary.read_bytes()

    def test_generated_scope_rejects_mismatched_upload_and_ignores_header(self):
        obj, upload = self.generated("nop")
        begin, end = audit.generated_body(obj, upload)
        result = audit.inspect_bytes(upload[begin:end], begin, False, self.root/"body")
        self.assertEqual(result["hints"], [])
        with self.assertRaises(RuntimeError):
            audit.inspect_bytes(upload[begin:end], begin, True, self.root/"body")
        with self.assertRaises(RuntimeError):
            audit.generated_body(obj, upload + b"\x90")
        extra = self.assemble("extra", """
.text
.zero 48
generated_body: nop
comp_syscall: ret
.section .rodata
.byte 1
""")
        with extra.open("rb") as stream:
            text = audit.ELFFile(stream).get_section_by_name(".text").data()
        with self.assertRaises(RuntimeError):
            audit.generated_body(extra, text)
        for bad in (b"", b"\x0f", b"\x48", b"\x0f\x18\x08\x0f"):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                audit.inspect_bytes(bad, 48, bad.startswith(b"\x0f\x18\x08"), self.root/"bad")

    def test_readback_rejects_loaded_bytes_and_registry_or_source_drift(self):
        obj, upload = self.generated()
        entry = dict(entry=4096, tgid=42, code=0xffffffffc1000000,
                     entry_abi=2, requirements=0, generation=7)
        source = dict(state=0, modules=1, frames=0, writers=0)
        folder = self.root/"workspace/daemon/0x1000/42/asm"
        folder.mkdir(parents=True)
        (folder/"jit.o").write_bytes(obj.read_bytes())
        (folder/"jit.bin").write_bytes(upload)
        publication = dict(entry=entry, source=source,
            images={name: audit.digest(folder/name) for name in ("jit.o", "jit.bin")})
        begin, end = audit.generated_body(obj, upload)
        inspected = audit.inspect_bytes(upload[begin:end], begin, True, self.root/"inspected")
        (self.root/"list-image").mkdir()
        for fault in (None, "bytes", "registry", "source", "writers", "object", "marker"):
            current = copy.deepcopy(publication)
            if fault == "object":
                current["images"]["jit.o"] = "wrong"
            (folder/"jit.bin").write_bytes(upload if fault != "marker" else
                                          upload[:25] + b"X" + upload[26:])
            states = [source, dict(source, frames=1) if fault == "source" else source]
            if fault == "writers":
                states[0] = dict(source, writers=1)
            with self.subTest(fault=fault), \
                 patch.object(audit.os, "open", return_value=7), \
                 patch.object(audit.os, "close") as closed, \
                 patch.object(audit, "inspect_bytes", return_value=copy.deepcopy(inspected)), \
                 patch.object(audit, "registry", side_effect=[[entry], [] if fault == "registry" else [entry]]), \
                 patch.object(audit, "status", side_effect=states), \
                 patch.object(audit, "read_image", return_value=upload + b"\x90" if fault == "bytes" else upload):
                if fault is None:
                    receipt = audit.capture(self.root, current, True)
                    self.assertTrue(receipt["byte_for_byte_match"])
                    self.assertEqual(receipt["loaded_sha256"], receipt["uploaded_sha256"])
                    self.assertEqual(receipt["hints"][0]["mnemonic"], "prefetcht0")
                else:
                    with self.assertRaises(RuntimeError):
                        audit.capture(self.root, current, True)
                if fault not in ("object", "marker"):
                    closed.assert_called_once_with(7)

    def test_plain_and_checked_pointer_contracts(self):
        for abi, requirements, allowed in ((1, 0, True), (3, 0, True), (1, 2, True),
                                            (2, 2, False), (2, 1, False), (1, 20, False)):
            obj, upload = self.generated(abi=abi, requirements=requirements)
            entry = dict(entry=4096, tgid=42, code=0xffffffffc1000000,
                         entry_abi=abi, requirements=requirements, generation=0)
            folder = self.root/"workspace/daemon/0x1000/42/asm"
            folder.mkdir(parents=True, exist_ok=True)
            (folder/"jit.o").write_bytes(obj.read_bytes())
            (folder/"jit.bin").write_bytes(upload)
            publication = dict(entry=entry, source=dict(state=0, modules=1, frames=0, writers=0),
                images={name: audit.digest(folder/name) for name in ("jit.o", "jit.bin")})
            with self.subTest(abi=abi, requirements=requirements), \
                 patch.object(audit.os, "open", side_effect=OSError("reached provider boundary")):
                if allowed:
                    with self.assertRaisesRegex(OSError, "reached provider boundary"):
                        audit.capture(self.root, publication, True)
                else:
                    with self.assertRaises(RuntimeError):
                        audit.capture(self.root, publication, True)


if __name__ == "__main__":
    unittest.main()

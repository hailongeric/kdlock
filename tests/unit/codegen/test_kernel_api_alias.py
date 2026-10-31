"""Guest-only exact root-alias completion and original FULL CALL lowering."""
import io
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from test_jit_diagnostics import translator
import conflict
import special_inst
from translation_image import write_entry_dispatch

ROOT = Path(__file__).resolve().parents[3]


def body():
    stream = io.StringIO()
    write_entry_dispatch(stream, 0x1000, {0x1000: None}, set(),
                         body_witness=True, root_only=True)
    stream.write("loc_1000:\nMOV RSI, R13\nMOV RCX, R12\n"
                 "MOV RDI, QWORD PTR[rip + fixture_lock]\n"
                 "MOV RDX, QWORD PTR[rip + fixture_return]\n")
    stream.write(special_inst.terminal_clobber_unlock(
        0x8000, 0x7777, conflict.block_init(), identity_target=0x7000))
    return stream.getvalue()


def main():
    here = Path(__file__).resolve().parent
    generated = body()
    with tempfile.TemporaryDirectory(prefix="kd-api-alias-") as name:
        path = Path(name)
        # Only the existing conventional wrapper-invocation shim is needed.
        helper = (here / "native_call_execution_helpers.S").read_text().split(".macro alignment_check")[0]
        (path / "invoke.S").write_text(helper + '\n.section .note.GNU-stack,"",@progbits\n')
        (path / "wrapper.S").write_text((ROOT / "include/wrapper.S").read_text() +
                                       '\n.globl kd_alias_wrapper\n.section .note.GNU-stack,"",@progbits\n')
        cc = shlex.split(os.environ.get("CC", "gcc"))
        def run(text):
            (path / "jit.S").write_text(text)
            subprocess.run(cc + ["-c", "-Dmain=kd_alias_wrapper", "-DKD_GENERATED_ENTRY_ABI=1",
                "-DKD_GENERATED_REQUIREMENTS=0", "-DKD_GENERATED_GS_INPUT=0", "-DKD_GENERATED_TASK_INPUT=0",
                "-I" + str(path), "-I" + str(ROOT / "include"), str(path / "wrapper.S"),
                "-o", str(path / "wrapper.o")], check=True, capture_output=True, text=True, timeout=30)
            subprocess.run(cc + ["-O2", "-fno-omit-frame-pointer", "-mno-red-zone", "-fno-pie", "-no-pie",
                "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "include"),
                str(here / "kernel_api_alias_fixture.c"), str(path / "invoke.S"), str(path / "wrapper.o"),
                "-o", str(path / "fixture")], check=True, capture_output=True, text=True, timeout=30)
            return subprocess.run([str(path / "fixture")], capture_output=True, text=True, timeout=10)
        result = run(generated)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout.strip())
        # Losing either distinction changes actual executed wrapper behavior:
        # no canonical identity -> rejects valid KD root; canonical FULL target
        # -> loses the Native-capable source bridge on a different object.
        for old, new in (("0x7000", "0x8000"), ("0x8000", "0x7000")):
            assert generated.count(old) == 1
            result = run(generated.replace(old, new))
            assert result.returncode == 1 and "FAIL" in result.stderr, result.stderr
    print("[PASS] 4 actual alias wrapper paths; 2 identity/continuation mutants")


if __name__ == "__main__":
    main()

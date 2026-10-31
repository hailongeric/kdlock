"""Guest-only original clobber macro + assembly tail bridge forwarding."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from test_kernel_api_binding import types, ROOT


def main():
    here = Path(__file__).resolve().parent
    overlay = ROOT / "kernel_integration/real_api/overlay"
    entry = (overlay / "kernel/locking/kd_api/bridge.S").read_text()
    with tempfile.TemporaryDirectory(prefix="kd-api-bridge-") as name:
        path = Path(name)
        for directory in ("linux", "asm"):
            (path / directory).mkdir()
        (path / "api_types.h").write_text(types())
        for header in ("kd_api_lock_types.h", "kd_api_control.h"):
            (path / "linux" / header).write_text("/* fixture types supplied before actual shell */\n")
        (path / "linux/kd_api_lock.h").write_bytes((overlay / "include/linux/kd_api_lock.h").read_bytes())
        (path / "linux/kd_api_provider.h").write_bytes((overlay / "include/linux/kd_api_provider.h").read_bytes())
        (path / "linux/linkage.h").write_text(
            '#define SYM_FUNC_START(name) .text; .globl name; .type name,@function; name:\n'
            '#define SYM_FUNC_END(name) .size name,.-name\n')
        (path / "asm/asm.h").write_text('#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)\n')
        (path / "asm/nospec-branch.h").write_text('.macro JMP_NOSPEC reg:req\n jmp *%\\reg\n.endm\n')
        targets = ".text\n.macro TARGET name, value\n.globl \\name\n.type \\name,@function\n\\name:\n"
        targets += "movq $\\value, captured(%rip)\nmovq %rdi,captured+8(%rip)\nmovq %rsi,captured+16(%rip)\n"
        targets += "movq %rdx,captured+24(%rip)\nmovq %rcx,captured+32(%rip)\nmovq %rsp,captured+40(%rip)\n"
        targets += "movq (%rsp),%rax\nmovq %rax,captured+48(%rip)\n"
        # Deliberately violate ordinary C callee-save rules; the actual source
        # shell must advertise these clobbers and preserve its live values.
        for register in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"):
            targets += f"movq $0x1234,%{register}\n"
        targets += "ret\n.size \\name,.-\\name\n.endm\n"
        for symbol, value in (("fixture_spin_lock",1),("fixture_spin_unlock",2),
                              ("fixture_mutex_lock",3),("fixture_mutex_unlock",4),
                              ("fixture_mutex_local",5),("_raw_spin_lock",10),
                              ("_raw_spin_unlock",11),("mutex_lock",12),("mutex_unlock",13)):
            targets += f"TARGET {symbol}, {value}\n"
        targets += '.section .note.GNU-stack,"",@progbits\n'
        (path / "targets.S").write_text(targets)
        cc = shlex.split(os.environ.get("CC", "gcc"))
        def run(source):
            (path / "entry.S").write_text(source + '\n.section .note.GNU-stack,"",@progbits\n')
            command = cc + ["-O2", "-fno-omit-frame-pointer", "-mno-red-zone", "-fno-pie", "-no-pie",
                "-Wall", "-Wextra", "-Werror", "-DCONFIG_KD_API_LOCKS=1", "-I" + str(path),
                str(here / "api_bridge_fixture.c"), str(path / "entry.S"), str(path / "targets.S"),
                "-o", str(path / "fixture")]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            return subprocess.run([str(path / "fixture")], capture_output=True, text=True, timeout=10)
        result = run(entry)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout.strip())
        old = "movq KD_API_OP_MUTEX_LOCAL_LOCK(%r8), %rax"
        assert entry.count(old) == 1
        result = run(entry.replace(old, "movq KD_API_OP_MUTEX_LOCK(%r8), %rax"))
        assert result.returncode == 1 and "FAIL" in result.stderr, result.stderr
    print("[PASS] 11 Native/KD tail routes; GET-only eligibility mutant")


if __name__ == "__main__":
    main()

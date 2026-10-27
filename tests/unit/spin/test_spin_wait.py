"""Guest-only x86 execution and RSP sampling of the production shadow wait."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


from source_text import read_source, without_includes
from test_exec_capacity import production
from test_spin_shadow import definition


def main():
    source = (ROOT / "kernel_module/spin/wait.inc").read_text()
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-wait-") as directory:
        path = Path(directory)
        (path / "wait_production.h").write_text(source)
        # Execute with the real node layout so moved polling bytes cannot be
        # hidden by a compact mock struct with unrelated offsets.
        (path / "wait_node.h").write_text(definition(
            (ROOT / "include/kd_spinlock.h").read_text(),
            "struct kd_spin_node {").rstrip() + ";\n")
        binary = path / "spin-wait"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-mno-red-zone", "-fno-stack-protector", "-pthread",
                "-I", str(path),
                str(ROOT / "tests/unit/spin/spin_wait_fixture.c"),
                "-o", str(binary),
            ],
            check=True, timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=15)
        types, _ = production()
        (path / "restore_types.h").write_text(
            types + without_includes((ROOT / "include/kd_image.h").read_text()))
        source = read_source(ROOT / "kernel_module/kd_spinlock.c")
        code = definition(source, "kd_spin_restore_request(struct kd_spin_continuation *execution,")
        macro_start = source.index("#define KD_SPIN_RETIRE_ASM")
        macros = source[macro_start:
                        source.index("static __attribute__((noipa, noreturn))", macro_start)]
        (path / "restore_production.h").write_text(
            "static __attribute__((noipa, used, no_caller_saved_registers)) noinline notrace void\n"
            + definition(source, "kd_spin_restore_unpin(void)")
            # The flags helper consumes its incoming regs argument through
            # the fixed %rdi ABI in assembly. Keep warnings for the fixture
            # and final restore while admitting that exact production helper.
            + '\n#pragma GCC diagnostic push\n'
            + '#pragma GCC diagnostic ignored "-Wunused-parameter"\n'
            + source[source.index("#define KD_RESTORE_REG_OPERANDS"):
                     source.index("#pragma GCC push_options", source.index("#define KD_RESTORE_REG_OPERANDS"))]
            + '\n#pragma GCC diagnostic pop\n'
            + macros + "static __attribute__((noipa, noreturn)) noinline notrace void\n" + code)
        for thunk in (None, "CONFIG_RETHUNK", "CONFIG_MITIGATION_RETHUNK"):
            binary = path / ("spin-restore-" + (thunk or "direct"))
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc")) + [
                    "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-mno-red-zone", "-mgeneral-regs-only", "-fno-stack-protector",
                    *(["-D" + thunk + "=1"] if thunk else []), "-I", str(path),
                    str(ROOT / "tests/unit/spin/spin_restore_fixture.c"),
                    "-o", str(binary),
                ], check=True, timeout=30,
            )
            subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    main()

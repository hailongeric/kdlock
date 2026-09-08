"""Exercise real code-pool registration and device bounds in guest userspace.

Allocation, executable-page permissions and userspace copies are test doubles.
The bounded hash probe, pool consumption, publication and device decisions are
extracted unchanged. This does not test kernel IRQs or live code replacement.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT
from test_spin_shadow import definition


def lookup_code():
    """Use the same production lookup in allocation and pre-body consumer tests."""
    source = (ROOT / "kernel_module/exe.c").read_text()
    code = "static struct kd_exe_info *kd_exes;\n"
    code += definition(
        (ROOT / "include/exe.h").read_text(),
        "static inline unsigned int zz_hash(unsigned int pid, unsigned long ip)",
    )
    for name in (
        "struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip)",
        "const struct kd_exe_info *kd_exe_get_slot(unsigned int index)",
        "bool kd_exe_publish_status(struct kd_exe_info *exe, int status)",
        "bool kd_exe_is_ready(unsigned int pid, unsigned long ip)",
    ):
        code += definition(source, name)
    return code


def production():
    source = (ROOT / "kernel_module/exe.c").read_text()
    # Keep production capacities, gate and service declarations. Service calls
    # are not executed; their table is needed by the real init/exit functions.
    code = "\n".join(
        line for line in source.splitlines() if line.startswith("#define KD_CODE_")
    )
    code += (
        "\n"
        + source[
            source.index("static void *kd_code_block_pool[") : source.index(
                "static const struct kd_hostcall_desc *kd_hostcall_lookup"
            )
        ]
    )
    code += lookup_code()
    for name in (
        "int kd_exe_init(void)",
        "void kd_exe_exit(void)",
        "void kd_exe_add(int pid, unsigned long rip, enum kd_exe_lock_kind kind)",
    ):
        code += definition(source, name)
    device = (ROOT / "kernel_module/sys.c").read_text()
    for name in (
        "static ssize_t kd_dev_read(struct file *file, char __user *buf, size_t count,",
        "static ssize_t kd_dev_write_locked(const char __user *buf, size_t count)",
    ):
        code += definition(device, name)
    return code


def main():
    code = production()
    # Each mutation must compile and fail an assertion. A compiler error or
    # timeout is not evidence that a resource invariant is actually observed.
    mutations = {
        "partial-publish": (
            "if (!mem) {\n\t\tkd_code_block_gate_unlock();",
            (
                "if (!mem) {\n\t\texe->status_code = KD_EXE_UNINIT;"
                "\n\t\tkd_code_block_gate_unlock();"
            ),
        ),
        "duplicate-consumes-block": (
            "if (exe->pid == pid && exe->RIP == rip) {",
            (
                "if (exe->pid == pid && exe->RIP == rip) {"
                "\n\t\tif (kd_code_block_free > 0) kd_code_block_free--;"
            ),
        ),
        "pool-stops-early": (
            "if (kd_code_block_free > 0)\n\t\tmem =",
            "if (kd_code_block_free > 1)\n\t\tmem =",
        ),
        "premature-readiness": (
            "smp_store_release(&exe->status_code, KD_EXE_UNINIT);",
            "smp_store_release(&exe->status_code, KD_EXE_NORMAL);",
        ),
        "lost-terminal-rejection": (
            "if (old == KD_EXE_NATIVE_ONLY)",
            "if (old == KD_EXE_NATIVE_ONLY && status == KD_EXE_NATIVE_ONLY)",
        ),
        "last-slot-invisible": (
            "index >= KD_MAX_EXE",
            "index >= KD_MAX_EXE - 1",
        ),
        "upload-past-end": (
            "head.offset > KD_CODE_BLOCK_SIZE",
            "head.offset > KD_CODE_BLOCK_SIZE + 1",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-exe-registry-") as tmp:
        directory = Path(tmp)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == 1, (name, code.count(before))
                candidate = code.replace(before, after)
            (directory / "registry_code.h").write_text(candidate)
            binary = directory / name
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-pthread",
                    "-I",
                    str(directory),
                    "-I",
                    str(ROOT / "include"),
                    str(ROOT / "tests/unit/exe_registry_fixture.c"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=15, check=False
            )
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name,
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                print(f"registry mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()

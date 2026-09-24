"""Guest-only geometry and rollback checks for the real spin storage allocator.

Compile production layouts, allocation/free bodies and reserve/collapse helpers.
Only allocation and CPU primitives are substitutes; no kernel code is executed.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_exec_capacity import production
from test_spin_shadow import definition


def main():
    types, _ = production()
    spin_types = (ROOT / "include/kd_spinlock.h").read_text()
    types += "\n".join(
        line for line in spin_types.splitlines()
        if line.startswith(("#define MAX_NODES ",
                            "#define KD_SPIN_CONT_BYTES ",
                            "#define KD_SPIN_WAIT_STACK_SIZE ",
                            "#define KD_SPIN_STORAGE_BYTES "))
    ) + "\n"
    types += definition(spin_types, "struct kd_spin_node {").rstrip() + ";\n"
    state = (ROOT / "kernel_module/spin/state.inc").read_text()
    types += "#define KD_SPIN_DIAG_SLOTS 32\n"
    for marker in ("enum kd_spin_diag_event {", "struct kd_spin_diag_slot {",
                   "struct kd_spin_diag_counts {", "struct kd_spin_diag_cpu {",
                   "struct kd_spin_cpu_state {"):
        types += definition(state, marker).rstrip() + ";\n"
    lifecycle = (ROOT / "kernel_module/spin/lifecycle.inc").read_text()
    code = "".join(definition(lifecycle, marker) for marker in (
        "static size_t kd_spin_continuation_offset(unsigned int cpu)",
        "static void kd_spinlock_free_percpu(void)",
        "int kd_spinlock_init(void)",
    ))
    code += read_source(ROOT / "kernel_module/spin/request.inc")
    mutations = {
        "no-colors": (
            "return ((unsigned long)cpu * 13 % colors) * L1_CACHE_BYTES;",
            "return ((unsigned long)cpu * 13 % colors) * 0;",
        ),
        "free-interior": (
            "vfree((char *)stack->wait_stack_top - KD_SPIN_STORAGE_BYTES);",
            "vfree(*per_cpu_ptr(&kd_spin_continuations, cpu));",
        ),
        "short-wait-stack": (
            "ptr->wait_stack_top = (char *)wait_stack + KD_SPIN_STORAGE_BYTES;",
            "ptr->wait_stack_top = (char *)wait_stack + KD_SPIN_CONT_BYTES;",
        ),
        # Reverting to one-line separation must fail the production guard,
        # before a module can reintroduce base-dependent adjacent-pair sharing.
        "diag-single-line-pair": (
            "atomic_t waiter_count __aligned(2 * L1_CACHE_BYTES);",
            "atomic_t waiter_count __aligned(L1_CACHE_BYTES);",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-storage-") as directory:
        path = Path(directory)
        for name, mutation in [("production", None), *mutations.items()]:
            body = code
            layout = types
            if mutation:
                before, after = mutation
                assert body.count(before) + layout.count(before) == 1
                body = body.replace(before, after, 1)
                layout = layout.replace(before, after, 1)
            (path / "spin_storage_types.h").write_text(layout)
            (path / "spin_storage_production.h").write_text(body)
            binary = path / name
            compiled = subprocess.run(
                shlex.split(os.environ.get("CC", "cc")) + [
                    "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(path),
                    str(ROOT / "tests/unit/spin/spin_storage_fixture.c"),
                    "-o", str(binary),
                ], capture_output=True, text=True, check=False, timeout=30,
            )
            if name == "diag-single-line-pair":
                assert compiled.returncode != 0 and "static assertion failed" in compiled.stderr, (
                    name, compiled.returncode, compiled.stdout, compiled.stderr,
                )
                assert "offsetof(struct kd_spin_diag_slot, waiter_count) != 2 * L1_CACHE_BYTES" in compiled.stderr
                print(f"spin storage mutation detected: {name}")
                continue
            assert compiled.returncode == 0, (name, compiled.stdout, compiled.stderr)
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True,
                check=False, timeout=15,
            )
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr,
                )
                print(f"spin storage mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()

"""Execute production residency/retirement with substituted kernel primitives.

Unlike basic module-load tests, this covers the bounded source dependency and
terminal admission protocol. It does not model hook-reader grace periods.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

from source_text import ROOT, without_includes
from test_spin_shadow import definition


def production():
    code = without_includes(read_source((ROOT / "include/kd_source.h")))
    code += without_includes(read_source((ROOT / "kernel_module/kd_source.c")))
    for path, signatures in {
        "kernel_module/exe.c": (
            "bool kd_exe_publish_status(struct kd_exe_info *exe, int status)",
            "void kd_exe_retire_all(void)",
        ),
        "kernel_module/sys.c": (
            "static struct kd_jit_caps kd_jit_capabilities(void)",
            "static int kd_dev_open(struct inode *inode, struct file *file)",
            "static int kd_dev_release(struct inode *inode, struct file *file)",
            "static long kd_dev_ioctl(struct file *file, unsigned int command,",
        ),
    }.items():
        source = read_source((ROOT / path))
        code += "\n".join(definition(source, name) for name in signatures) + "\n"
    return code


def main():
    code = production()
    mutations = {
        "duplicate-pins": (
            "for (i = 0; i < kd_sources.modules; i++)",
            "for (i = kd_sources.modules; i < kd_sources.modules; i++)",
        ),
        "early-cap": (
            "kd_sources.modules == KD_SOURCE_MAX_MODULES",
            "kd_sources.modules == KD_SOURCE_MAX_MODULES - 1",
        ),
        "coming-text": (
            "READ_ONCE(module->state) != MODULE_STATE_LIVE",
            "READ_ONCE(module->state) == MODULE_STATE_GOING",
        ),
        "kernel-init-text": (
            "(address >= kd_init_start && address < kd_init_end)",
            "false",
        ),
        "busy-writer-ignored": (
            "if (kd_source_frame_count() || kd_sources.writers)",
            "if (kd_source_frame_count())",
        ),
        "busy-frame-ignored": (
            "if (kd_source_frame_count() || kd_sources.writers)",
            "if (kd_sources.writers)",
        ),
        "stale-entry": ("kd_exe_retire_all();", "(void)kd_exe_retire_all;"),
        "writer-after-close": (
            "kd_sources.state == KD_SOURCE_OPEN &&\n\t     kd_sources.writers",
            "kd_sources.state != KD_SOURCE_RETIRED &&\n\t     kd_sources.writers",
        ),
        "frame-leak": (
            "atomic64_dec_return(&kd_source_frame_gate)",
            "atomic64_read(&kd_source_frame_gate)",
        ),
        "frame-after-close": (
            "(old & KD_SOURCE_FRAME_CLOSED) ||",
            "false ||",
        ),
        "wrong-stack-capability": (
            ".mutex_stack_bytes = KD_JIT_MUTEX_STACK_BYTES,",
            ".mutex_stack_bytes = KD_JIT_MUTEX_STACK_BYTES + 8,",
        ),
        "missing-stack-feature": (
            ".features = KD_JIT_CAP_MUTEX_STACK,",
            ".features = 0,",
        ),
        "wrong-module-arena": (
            "caps.percpu_module_bytes = PERCPU_MODULE_RESERVE;",
            "caps.percpu_module_bytes = PERCPU_MODULE_RESERVE + 4;",
        ),
        "missing-module-feature": (
            "caps.features |= KD_JIT_CAP_PERCPU_MODULE;",
            "(void)caps.features;",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-source-unit-") as tmp:
        directory = Path(tmp)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == 1, (name, code.count(before))
                candidate = code.replace(before, after)
            (directory / "source_production.h").write_text(candidate)
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
                    str(ROOT / "tests/unit/infrastructure/source_lifetime_fixture.c"),
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
                print(f"source lifetime mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()

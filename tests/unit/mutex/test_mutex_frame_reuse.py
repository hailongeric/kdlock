"""Guest-only checks of production mutex retired-frame reuse boundaries.

The fixture substitutes CPU context, source admission and Linux ownership. It
does not execute JIT or model scheduler/ACK concurrency; the live checks do so.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    types = definition(read_source(ROOT / "include/kd_regs.h"),
                       "struct kd_regs {").rstrip() + ";\n"
    types += definition(read_source(ROOT / "include/kd_spin_entry.h"),
                        "struct kd_spin_ref {").rstrip() + ";\n"
    for name in ("exe_info", "kd_call", "kd_exec", "kd_mutex"):
        types += without_includes(read_source(ROOT / f"include/{name}.h")) + "\n"
    source = read_source(ROOT / "kernel_module/kd_exec.c")
    push = definition(source, "struct kd_exec_frame *kd_exec_frame_push_mutex_batch(")
    rebind = definition(source, "struct kd_exec_frame *kd_exec_frame_rebind_mutex_batch(")
    retire = definition(source, "int kd_exec_frame_retire_mutex_batch(struct kd_exec_frame *frame,")
    variants = {
        "production": rebind,
        "closed-admission": rebind.replace("!kd_source_is_open()", "false"),
        "complex-token": rebind.replace("retired->complex_ready ||", ""),
        "wrong-slot": rebind.replace("retired != &ctx->frames[0] ||", ""),
        "occupied-context": rebind.replace("ctx->depth ||", ""),
        "wrong-lock": rebind.replace("retired->jit_lock_node[0] != lock ||", ""),
        "released-hook": rebind.replace("hook->released ||", ""),
        "missing-completion": rebind.replace("!retired->completion_seen ||", ""),
        "old-packet": rebind.replace("retired->borrowed_regs = regs;", ""),
    }
    with tempfile.TemporaryDirectory(prefix="kd-mutex-frame-reuse-") as directory:
        path = Path(directory)
        (path / "types.h").write_text(types)
        for name, candidate in variants.items():
            assert name == "production" or candidate != rebind, name
            (path / "production.h").write_text(push + "\n" + candidate + "\n" + retire)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I" + str(path),
                str(ROOT / "tests/unit/mutex/mutex_frame_reuse_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if name == "production":
                assert result.returncode == 0, (result.stdout, result.stderr)
                print(result.stdout, end="")
            else:
                assert result.returncode == 1 and "FAIL frame reuse" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print("frame reuse mutation detected:", name)


if __name__ == "__main__":
    main()

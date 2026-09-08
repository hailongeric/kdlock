"""Guest-only extraction of production frame allocation, not an IRQ/ABI model."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def production():
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (kernel / "arch/x86/include/asm/ptrace.h").read_text()
    ptrace = ptrace.split("#else /* __i386__ */", 1)[1]
    types = definition(ptrace, "struct pt_regs {").rstrip() + ";\n"
    types += (
        definition(
            (ROOT / "include/kd_spin_entry.h").read_text(), "struct kd_spin_ref {"
        ).rstrip()
        + ";\n"
    )
    for name in ("include/kd_call.h", "include/kd_exec.h"):
        types += without_includes((ROOT / name).read_text()) + "\n"
    source = (ROOT / "kernel_module/kd_exec.c").read_text()
    code = "\n".join(
        definition(source, signature)
        for signature in (
            "static int kd_exec_invariant_failure(void)",
            "static bool kd_exec_frame_state_is_active(int state)",
            "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
            "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
            "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
            "static bool kd_exec_context_validate(const struct kd_exec_context *ctx)",
            "static void kd_exec_context_reset(struct kd_exec_context *ctx)",
            "static struct kd_exec_context *kd_exec_current_context(void)",
            "struct kd_exec_frame *kd_exec_current_frame(void)",
            "bool kd_exec_context_busy(void)",
            "kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,",
            "int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)",
        )
    )
    code = code.replace(
        "\nkd_exec_frame_push(", "\nstruct kd_exec_frame *\nkd_exec_frame_push("
    )
    code += "\n#define kd_exec_frame_push counted_frame_push\n"
    code += (ROOT / "tests/kernel/exec_capacity_probe.c").read_text()
    code += "\n#undef kd_exec_frame_push\n"
    return types, code


def main():
    types, code = production()
    mutations = {
        "early-refusal": (
            "ctx->depth >= KD_EXEC_MAX_NESTING",
            "ctx->depth >= KD_EXEC_MAX_NESTING - 1",
        ),
        "reject-writes-parent": (
            "ctx->depth >= KD_EXEC_MAX_NESTING",
            "(ctx->depth >= KD_EXEC_MAX_NESTING && (ctx->frames[0].regs.ax = 0, true))",
        ),
        "lost-registers": ("frame->regs = *regs;", "frame->regs.ax = regs->ax;"),
        "lost-parent": (
            "frame->parent = kd_exec_current_frame();",
            "frame->parent = NULL;",
        ),
        "stale-owner": (
            "if (!ctx->depth)\n\t\tctx->owner = NULL;",
            "/* stale owner */",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-exec-capacity-unit-") as tmp:
        path = Path(tmp)
        (path / "frame_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == 1, (name, code.count(before))
                candidate = code.replace(before, after)
            (path / "frame_code.h").write_text(candidate)
            binary = path / name
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(path),
                    str(ROOT / "tests/unit/exec_capacity_fixture.c"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=10, check=False
            )
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name,
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                print(f"capacity mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()

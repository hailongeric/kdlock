"""Guest-only production mutex node, shadow-table and hook resource tests.

Keep the real capacities, guest pt_regs and decisions. Kernel scheduling,
physical mutexes, task records, the assembly slowpath and resume trampolines
are deterministic substitutes, not proof of live concurrency or owner ACKs.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def production():
    mutex = (ROOT / "kernel_module/kd_mutex.c").read_text()
    hook = (ROOT / "kernel_module/kd_lock.c").read_text()
    # This boundary is substituted, so pin its normal owner result to the
    # actual producer. A consumer accepting other values is not equivalence.
    slowpath = definition(
        mutex, "__kd_mutex_lock_slowpath(struct kd_mutex *lock, int tail,"
    )
    assert "release:\n\tkd_mutex_waiter_exit(lock);\n\treturn 2;" in slowpath
    # These statics belong to separate production translation units. Rename
    # only the per-CPU symbol so both unchanged paths can share one fixture.
    code = "#define kd_mutex_shadows cpu_shadows\n"
    code += mutex[
        mutex.index("struct kd_mutex_shadow {") : mutex.index(
            "static inline struct kd_mutex_node *decode_tail"
        )
    ]
    code += (
        next(
            line
            for line in mutex.splitlines()
            if line.startswith("#define _Q_LOCKED_COMBINER_VAL ")
        )
        + "\n"
    )
    for marker in (
        "void kd_mutex_init(struct kd_mutex *lock)",
        "static void kd_mutex_schedule_if_needed(void)",
        "static void kd_mutex_claim_origin(struct kd_mutex *lock)",
        "static void kd_mutex_wait_and_lock(struct kd_mutex *lock)",
        "static struct kd_mutex_node *kd_mutex_reserve_node(void)",
        "static void kd_mutex_release_node(struct kd_mutex_node *node)",
    ):
        code += definition(mutex, marker)
    for marker, result in (
        ("_kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value,", "void"),
        ("_kd_mutex_unlock_checked(struct kd_mutex *lock)", "int"),
        ("_kd_mutex_unlock(struct kd_mutex *lock)", "void"),
    ):
        code += f"__attribute__((noipa)) {result}\n" + definition(mutex, marker)
    code += "#undef kd_mutex_shadows\n"
    code += hook[
        hook.index("#define KD_MUTEX_SHADOW_TABLE_SIZE ") : hook.index(
            "/* --- externs from patched kernel"
        )
    ]
    for marker in (
        "static struct kd_mutex *get_kd_mutex_shadow(struct mutex *lock)",
        "static struct kd_mutex *find_kd_mutex_shadow(struct mutex *lock)",
        "void __kd_mutex_lock(struct mutex *lock, unsigned long ret_rsp,",
        "void __kd_mutex_unlock(struct mutex *lock, unsigned long ret_rsp,",
    ):
        code += definition(hook, marker)
    return code


def main():
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (kernel / "arch/x86/include/asm/ptrace.h").read_text()
    ptrace = ptrace.split("#else /* __i386__ */", 1)[1]
    types = definition(ptrace, "struct pt_regs {").rstrip() + ";\n"
    types += without_includes((ROOT / "include/kd_mutex.h").read_text())
    code = production()
    # Compile each broken decision first, then require an explicit assertion
    # failure. A crash, compiler error, BUG-only exit or timeout is not a pass.
    mutations = {
        "missing-stack-accepted": (
            "if (!node->shadow_stack_base)",
            "if (0 && !node->shadow_stack_base)",
        ),
        "reservation-not-published": (
            "WRITE_ONCE(shadow->node_slots, slots | BIT(idx));",
            "WRITE_ONCE(shadow->node_slots, slots);",
        ),
        "release-keeps-gs": ("node->gsbase = 0;", "node->gsbase = 1;"),
        "gate-without-native-lock": (
            "\t\tkd_mutex_claim_origin(lock);\n\t\treturn;",
            "\t\treturn;",
        ),
        "resume-loses-register": (
            "resume_regs = resume_node->regs;",
            "resume_regs = resume_node->regs; resume_regs.r10 = 0;",
        ),
        "native-drops-task-record": (
            "if (native_resume)\n\t\t\tjump_to_saved_regs_in_cs(&resume_regs);",
            (
                "if (native_resume) { kd_mutex_task_put(current); "
                "jump_to_saved_regs_in_cs(&resume_regs); }"
            ),
        ),
        "unlock-allocates-shadow": (
            "kd_mtx = find_kd_mutex_shadow(lock);",
            "kd_mtx = get_kd_mutex_shadow(lock);",
        ),
        "hook-ignores-task-failure": (
            "if (!kd_mtx || !kd_mutex_task_get(current)) {",
            "if (!kd_mtx || (kd_mutex_task_get(current) && false)) {",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-mutex-resources-") as tmp:
        directory = Path(tmp)
        (directory / "mutex_resource_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == 1, (name, code.count(before))
                candidate = code.replace(before, after)
            (directory / "mutex_resource_code.h").write_text(candidate)
            binary = directory / name
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(directory),
                    "-I",
                    str(ROOT / "include"),
                    str(ROOT / "tests/unit/mutex_resources_fixture.c"),
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
                print(f"mutex resource mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()

"""Compile real spin queue-head and combiner paths with deterministic primitives.

This also compiles the real native/virtual node producers. CPU, ticket and peer
actions are substitutes, not concurrent kernel execution or live exhaustion.
"""

import argparse
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

ROOT = Path(__file__).resolve().parents[3]


def definition(source, first_line):
    # These file-scope C definitions end with an unindented closing brace.
    # Keep the original body, and fail closed if the source layout changes.
    matches = list(re.finditer(r"(?m)^" + re.escape(first_line) + r"$", source))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition starting with {first_line!r}")
    start = matches[0].start()
    end = source.index("\n}", start) + 2
    return source[start:end] + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutations", action="store_true")
    options = parser.parse_args()
    source = read_source((ROOT / "kernel_module/kd_spinlock.c"))
    spin_types = read_source((ROOT / "include/kd_spinlock.h"))
    exec_types = read_source((ROOT / "include/kd_exec.h"))
    types = "\n".join(
        line
        for line in (spin_types + exec_types).splitlines()
        if line.startswith(
            (
                "#define MAX_NODES ",
                "#define KD_SPIN_NESTED_",
                "#define KD_EXEC_MAX_LOCK_DEPTH ",
            )
        )
    )
    for header, marker in (
        ((ROOT / "include/exe_info.h").read_text(), "enum kd_entry_abi {"),
        ((ROOT / "include/exe_info.h").read_text(), "enum kd_packet_state {"),
        (exec_types, "enum kd_exec_lock_kind {"),
        (exec_types, "enum kd_request_role {"),
        (exec_types, "enum kd_exec_remote_state {"),
        (read_source((ROOT / "include/kd_call.h")), "enum kd_call_phase {"),
    ):
        types += "\n" + definition(header, marker).rstrip() + ";\n"
    results = read_source((ROOT / "include/exe.h")).splitlines()
    types += (ROOT / "include/kd_jit_batch.h").read_text()
    body = ""
    for name in ("KD_EXE_NO_RUN", "KD_EXE_RUN_ERROR", "KD_EXE_NATIVE_DONE"):
        matching = [line for line in results if line.startswith(f"#define {name} ")]
        if len(matching) != 1 or not matching[0].split()[-1].isdigit():
            raise AssertionError(f"expected one numeric definition of {name}")
        body += matching[0] + "\n"
    body += read_source(ROOT / "kernel_module/spin/request.inc")
    types += definition(source, "struct kd_spin_cpu_state {").rstrip() + ";\n"
    body += "static inline unsigned int\n" + definition(
        source, "kd_spin_lock_stack_depth(const struct kd_spin_cpu_state *ptr)"
    )
    body += definition(source, "bool kd_spin_nested_shadow_has_space(void)")
    body += definition(
        source, "static inline bool check_irq_node(struct kd_spin_node *node)"
    )
    body += (
        "#ifdef NUMA_AWARE\n"
        + definition(
            source,
            "__always_inline static void add_to_local_queue(struct kd_spin_node *node)",
        )
        + "#endif\n"
    )
    body += "static struct kd_spin_node *\n" + definition(
        source, "get_next_node(struct kd_spin_node *my_node)"
    )
    body += definition(source, "static struct kd_spin_node *kd_spin_linked_successor(struct qspinlock *word,")
    body += definition(source, "struct kd_spin_batch {").rstrip() + ";\n"
    body += definition(source, "static void kd_spin_batch_run(void *opaque)")
    # The wrapper observes recursive entry/return; it does not replace the
    # production scan, cancellation, splice or queue-head save/restore bodies.
    body += "#define run_combiner production_run_combiner\nstatic void\n"
    body += definition(
        source, "run_combiner(struct qspinlock *lock, struct kd_spin_node *curr_node,"
    )
    body += "#undef run_combiner\n"
    body += "static int\n" + definition(
        source, "__kd_spin_lock_longjmp(struct qspinlock *lock, int tail,"
    )
    body += definition(source, "struct kd_spin_native_input {").rstrip() + ";\n"
    body += definition(source, "static void kd_spin_prepare_regs(struct kd_spin_node *node)")
    body += "static int\n" + definition(
        source, "__kd_spin_lock_slowpath(struct qspinlock *lock, struct kd_spin_request *request,"
    )
    for marker in (
        "static int kd_spin_prepare_jit_node(struct kd_spin_node *node,",
        "static int kd_spin_advance_jit_node(struct kd_spin_node *node,",
        "static int kd_spin_finish_remote_node(struct kd_spin_node *node,",
        "int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,",
    ):
        body += definition(source, marker)
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-shadow-") as directory:
        path = Path(directory)
        run_environment = dict(os.environ)
        run_environment.pop("KD_NODE_MUTATION", None)
        (path / "spin_shadow_types.h").write_text(types)
        (path / "spin_request_type.h").write_text(
            definition(source, "struct kd_spin_request {").rstrip() + ";\n"
        )
        observer = read_source((ROOT / "tests/kernel/spin/spin_node_trace.c"))
        (path / "spin_node_observer.h").write_text(
            re.sub(r"^#include .*\n", "", observer, flags=re.MULTILINE)
        )
        (path / "spin_shadow_production.h").write_text(body)
        for numa in (0, 1):
            binary = path / f"spin-shadow-{numa}"
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11",
                "-O2", "-g",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-sign-compare",
                "-I",
                str(path),
                str(ROOT / "tests/unit/spin/spin_shadow_fixture.c"),
                "-o",
                str(binary),
            ]
            if numa:
                command.append("-DNUMA_AWARE")
            subprocess.run(command, check=True, timeout=30)
            result = subprocess.run([str(binary)], timeout=10, env=run_environment)
            result.check_returncode()
        if options.mutations:
            mutations = (
                (
                    "native-full-count-leak",
                    "if (unlikely(idx >= MAX_NODES)) {\n\t\tthis_cpu_ptr(&kd_spin_cpu)->node_count--;",
                    "if (unlikely(idx >= MAX_NODES)) {",
                ),
                (
                    "virtual-full-count-leak",
                    "if (unlikely(idx < 0 || idx >= MAX_NODES)) {\n\t\tthis_cpu_ptr(&kd_spin_cpu)->node_count--;",
                    "if (unlikely(idx < 0 || idx >= MAX_NODES)) {",
                ),
                (
                    "prepare-cancel-count-leak",
                    "this_cpu_ptr(&kd_spin_cpu)->node_count--;\n\t\tkd_spin_selftest_node_event(KD_NODE_PREPARE_CANCEL);",
                    "kd_spin_selftest_node_event(KD_NODE_PREPARE_CANCEL);",
                ),
                (
                    "native-resume-count-leak",
                    "if (READ_ONCE(curr_node->execution->native_resume)) {\n\t\t\tthis_cpu_ptr(&kd_spin_cpu)->node_count--;",
                    "if (READ_ONCE(curr_node->execution->native_resume)) {",
                ),
                (
                    "completed-count-leak",
                    "this_cpu_ptr(&kd_spin_cpu)->node_count--;\n\t\t\tkd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);",
                    "kd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);",
                ),
                (
                    "head-count-double-release",
                    "this_cpu_ptr(&kd_spin_cpu)->node_count--;\n\tkd_spin_selftest_node_event(KD_NODE_COMBINER_ENTER);",
                    "this_cpu_ptr(&kd_spin_cpu)->node_count -= 2;\n\tkd_spin_selftest_node_event(KD_NODE_COMBINER_ENTER);",
                ),
                (
                    "common-exit-count-leak",
                    "this_cpu_ptr(&kd_spin_cpu)->node_count--;\n\tkd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);",
                    "kd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);",
                ),
                (
                    "lost-logical-origin",
                    "frame->spin_origin = parent->spin_origin;",
                    "frame->spin_origin = (struct kd_spin_ref){ 0 };",
                ),
                (
                    "physical-task-instead-of-waiter",
                    "parent->gsbase, parent->logical_task);",
                    "parent->gsbase, current);",
                ),
            )
            # Mutate only the temporary extracted copy, never project/kernel files.
            for name, original, replacement in mutations:
                if body.count(original) != 1:
                    raise AssertionError(f"mutation anchor changed: {name}")
                (path / "spin_shadow_production.h").write_text(
                    body.replace(original, replacement)
                )
                subprocess.run(command, check=True, timeout=30)
                result = subprocess.run(
                    [str(binary)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                    env={**os.environ, "KD_NODE_MUTATION": "1"},
                )
                if result.returncode <= 0 or "FAIL " not in result.stderr:
                    raise AssertionError(f"mutation not rejected by checks: {name}")
                print(f"[PASS] mutation rejected: {name}")
    print(
        "[PASS] test_spin_shadow (production node producers, queue exits and nested lists, NUMA off/on)"
    )


if __name__ == "__main__":
    main()

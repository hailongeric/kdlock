"""Guest-only actual READY wait/claim helpers with deterministic race injection.

Cover initial spin grace, expiry arbitration, cancellation, result races and
balanced scheduling. This does not establish live scheduler or weak-memory behavior.
"""
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / "kernel_module/kd_mutex.c")
    code = without_includes(read_source(ROOT / "include/kd_mutex_state.h")) + "\n" + without_includes(read_source(ROOT / "kernel_module/mutex/pin_origin.inc")) + "\n"
    code += "\n".join(definition(source, signature) for signature in (
        "static void kd_mutex_wait_for_result(struct kd_mutex_node *node)",
        "static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,",
        "static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)",
        "static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,",
    ))
    constants = "\n".join(re.findall(
        r"^#define KD_MUTEX_(?:WAIT|PROXY_READY|PROXY_CLAIMED|QUEUE_INIT) \d+$",
        (ROOT / "include/kd_mutex.h").read_text(), re.M))
    assert len(constants.splitlines()) == 4
    constants += "\n" + "\n".join(line for line in (ROOT / "include/kd_mutex.h").read_text().splitlines()
                                  if line.startswith("#define KD_MUTEX_GATE_"))
    mutations = {
        "schedule-before-budget": ("if (budget) {", "if (false && budget) {"),
        "withdraw-without-unpin": ("\tpreempt_enable();\n\twhile ((state =", "\twhile ((state ="),
        "head-cannot-schedule": (
            "\tpreempt_enable();\n\tfor (;;) {\n\t\twhile (kd_mutex_gate_read(lock))",
            "\tfor (;;) {\n\t\twhile (kd_mutex_gate_read(lock))"),
        "rearm-withdrawn-origin": (
            "cmpxchg(&node->locked, KD_MUTEX_QUEUE_INIT, KD_MUTEX_PROXY_READY)",
            "cmpxchg(&node->locked, KD_MUTEX_WAIT, KD_MUTEX_PROXY_READY)"),
        "ignore-expiry-cas-loss": (
            "if (state == KD_MUTEX_PROXY_READY) {", "if (true) {"),
        "self-cpu-selection": (" == raw_smp_processor_id())", " == -99)"),
        "claim-without-ready": (
            "if (smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_READY)",
            "if (false && smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_READY)"),
        "withdraw-without-reservation": (
            "if (!kd_mutex_gate_try_withdraw(node->lock))", "if (false && !kd_mutex_gate_try_withdraw(node->lock))"),
        "unpin-with-reservation": (
            "kd_mutex_gate_end_withdraw(node->lock);", "(void)node;"),
    }
    with tempfile.TemporaryDirectory(prefix="kd-mutex-proxy-pin-") as directory:
        path = Path(directory)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) >= 1, name
                candidate = candidate.replace(before, after, 1)
            (path / "proxy_production.h").write_text(constants + "\n" + candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I" + directory,
                str(ROOT / "tests/unit/mutex/mutex_proxy_pin_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if mutation:
                assert result.returncode == 1 and "FAIL proxy pin" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print("proxy pin mutation detected:", name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end="")


if __name__ == "__main__":
    main()

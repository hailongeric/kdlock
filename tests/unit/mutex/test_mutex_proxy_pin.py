"""Guest-only production origin pin protocol with deterministic scheduling.

Compile the current wait/request/ACK helpers unchanged. The window selection
fixture is separate; these cases cover preemptible queue/head waiting, exact
origin pins, cancellation and reselection, including an unobserved WAIT interval.
They do not establish live scheduler, weak-memory or JIT behavior.
"""
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / "kernel_module/kd_mutex.c")
    code = "\n".join(definition(source, signature) for signature in (
        "static void kd_mutex_wait_for_result(struct kd_mutex_node *node)",
        "static bool kd_mutex_proxy_request(struct kd_mutex_node *node)",
        "static void kd_mutex_proxy_wait_pinned(struct kd_mutex_node *node)",
        "static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,",
    ))
    constants = "\n".join(re.findall(
        r"^#define KD_MUTEX_(?:WAIT|PROXY_REQUEST|PROXY_PINNED) \d+$",
        (ROOT / "include/kd_mutex.h").read_text(), re.M))
    assert len(constants.splitlines()) == 3
    mutations = {
        "queue-cannot-schedule": ("\tpreempt_enable();", "\t/* Missing enable. */"),
        "proxy-without-origin-pin": ("\t\t\tpreempt_disable();", "\t\t\t/* Missing pin. */"),
        "cancel-keeps-pin": ("\t\t\t\t\t\tpreempt_enable();", "\t\t\t\t\t\t/* Missing cancel unpin. */"),
        "reselection-without-ack": (
            "\t\t\t\t\tif (state == KD_MUTEX_PROXY_REQUEST)\n"
            "\t\t\t\t\t\tsmp_store_release(&node->locked, KD_MUTEX_PROXY_PINNED);",
            "\t\t\t\t\tif (state == KD_MUTEX_PROXY_REQUEST)\n\t\t\t\t\t\t(void)node;"),
        "skip-origin-ack": (
            "\twhile (smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_PINNED)\n\t\tcpu_relax();",
            "\t(void)node; /* No acknowledgement wait. */"),
        "self-cpu-selection": (" == raw_smp_processor_id())", " == -99)"),
        "head-cannot-schedule": (
            "\tpreempt_enable();\n\tfor (;;) {\n\t\twhile (kd_mutex_gate_read(lock))",
            "\tfor (;;) {\n\t\twhile (kd_mutex_gate_read(lock))"),
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

"""Guest-only bounded pin-window protocol with deterministic origin ACKs.

Compile production descriptors, selection, cancellation and consumption helpers.
Atomic access observers model delayed peers and slot reuse. This does not prove
live scheduler/JIT behavior or execute the enclosing combiner's body boundaries.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    header = read_source(ROOT / "include/kd_mutex.h")
    source = read_source(ROOT / "kernel_module/kd_mutex.c")
    constants = "\n".join(re.findall(
        r"^#define KD_MUTEX_(?:WAIT|PROXY_REQUEST|PROXY_PINNED|PIN_WINDOW|CUSTODY_LOCKS) \d+$",
        header, re.M))
    assert len(constants.splitlines()) == 5
    types = constants + "\n"
    types += definition(read_source(ROOT / "include/kd_mutex_types.h"),
                        "struct kd_mutex {") + ";\n"
    for marker in ("enum kd_mutex_custody_phase {", "struct kd_mutex_custody {",
                   "struct kd_mutex_osq_node {", "struct kd_mutex_node {"):
        types += definition(header, marker) + ";\n"
    abi = read_source(ROOT / "include/exe_info.h")
    for marker in ("enum kd_entry_abi {", "enum kd_packet_state {"):
        types += definition(abi, marker) + ";\n"
    types += definition(read_source(ROOT / "include/kd_exec.h"),
                        "struct kd_exec_outer_unlock {") + ";\n"
    types += definition(source, "struct kd_mutex_batch {") + ";\n"
    code = "#define MODULE_INFO(...)\n" + without_includes(read_source(ROOT / "kernel_module/mutex/pin_diag.inc")) + "\n"
    for marker in (
        "static __always_inline bool kd_mutex_proxy_request(struct kd_mutex_node *node)",
        "static __always_inline void kd_mutex_proxy_wait_pinned(struct kd_mutex_node *node)",
    ):
        code += definition(source, marker) + "\n"
    window = read_source(ROOT / "kernel_module/mutex/pin_window.inc")
    code += window
    unpin = definition(window,
        "static void kd_mutex_batch_unpin(struct kd_mutex_batch *batch, bool keep_current)")
    remove_before_wait = (
        "\t\tbatch->pins[index].node = NULL;\n"
        "\t\tbatch->nr_pins = count;\n"
        "\t\tKD_MUTEX_PIN_INC(batch, cancelled);\n"
        "\t\tsmp_store_release(&node->locked, KD_MUTEX_WAIT);")
    assert remove_before_wait in unpin
    mutations = {
        "ignore-window-bound": (
            "\t\tlimit = KD_MUTEX_PIN_WINDOW;", "\t\tlimit = batch->pin_budget;", "", 86),
        "ignore-total-budget": (
            "unsigned int i, limit = batch->pin_budget;",
            "unsigned int i, limit = KD_MUTEX_PIN_WINDOW;", "", 1),
        "ignore-duplicate-cpu": (
            "if ((batch->pins[index].node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) == cpu)",
            "if (false && (batch->pins[index].node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) == cpu)", "", 1),
        "ignore-image-boundary": (
            "READ_ONCE(next->regs.ip) != READ_ONCE(node->regs.ip), KD_MUTEX_PIN_ENTRY)", "false, KD_MUTEX_PIN_ENTRY)", "", 1),
        "ignore-numa-boundary": (
            "(batch->numa_node >= 0 && next->numa_node != batch->numa_node)", "false", "", 1),
        "ignore-deferred-terminal": (
            "(batch->deferred_head && !smp_load_acquire(&next->next))", "false", "", 1),
        "ignore-local-budget": (
            "if (left > local_left)", "if (false && left > local_left)", "", 1),
        "underflow-local-budget": (
            "counter >= KDLOCK_MUTEX_NUMA_BOUNDARY ?", "false ?", "", 1),
        "cancel-before-ack": (unpin,
            unpin.replace("\t\tKD_MUTEX_PIN_WAIT(batch, node, true);", "\t\t/* Missing ACK. */", 1), "", 1),
        "cancel-before-descriptor-removal": (unpin,
            unpin.replace(remove_before_wait,
                "\t\tsmp_store_release(&node->locked, KD_MUTEX_WAIT);\n"
                "\t\tbatch->pins[index].node = NULL;\n\t\tbatch->nr_pins = count;", 1), "", 1),
        "retain-consumed-descriptor": (
            "\tbatch->pins[index].node = NULL;\n\tbatch->nr_pins--;",
            "\tbatch->nr_pins--;", "", 1),
        "advance-by-two": (
            "batch->pin_head = (index + 1) % KD_MUTEX_PIN_WINDOW;",
            "batch->pin_head = (index + 2) % KD_MUTEX_PIN_WINDOW;", "", 86),
        "forget-ring-head": (
            "return (batch->pin_head + offset) % KD_MUTEX_PIN_WINDOW;",
            "return offset;", "", 86),
        "cancel-moves-head": (
            "\t\tbatch->nr_pins = count;",
            "\t\tbatch->nr_pins = count; batch->pin_head = (batch->pin_head + 1) % KD_MUTEX_PIN_WINDOW;", "", 86),
        "ignore-generation": (
            "READ_ONCE(node->count_seq) != batch->pins[index].generation", "false", "generation", 1),
        "ignore-lock-identity": (
            "READ_ONCE(node->counted_lock) != batch->lock ||", "false ||", "wrong-lock", 1),
    }
    with tempfile.TemporaryDirectory(prefix="kd-pin-window-") as directory:
        path = Path(directory)
        (path / "pin_window_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate, scenario, expected = code, "", 0
            if mutation:
                before, after, scenario, expected = mutation
                assert candidate.count(before) == 1, (name, candidate.count(before))
                candidate = candidate.replace(before, after, 1)
            (path / "pin_window_production.h").write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I" + directory, "-I" + str(ROOT / "include"),
                str(ROOT / "tests/unit/mutex/mutex_pin_window_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([binary, *([scenario] if scenario else [])],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == expected, (name, result)
            if mutation:
                marker = "BUG pin window:" if expected == 86 else "FAIL pin window"
                assert marker in result.stderr, (name, result)
                print("pin-window mutation detected:", name)
            else:
                print(result.stdout, end="")
                for invalid in ("generation", "wrong-lock", "odd-generation",
                                "wrong-current", "complete-unacked", "bad-head", "occupied-slot"):
                    rejected = subprocess.run([binary, invalid], capture_output=True,
                                              text=True, timeout=10)
                    assert rejected.returncode == 86 and "BUG pin window:" in rejected.stderr, (
                        invalid, rejected)
                    print("pin-window invariant retained:", invalid)


if __name__ == "__main__":
    main()

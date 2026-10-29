"""Guest-only single-current epoch claims with deterministic READY peers.

Compile production descriptors, selection, cancellation and consumption helpers. Future origins remain READY.
Atomic access observers model expiry races and slot reuse. This does not prove
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
        r"^#define KD_MUTEX_(?:WAIT|PROXY_READY|PROXY_CLAIMED|QUEUE_INIT|CLAIM_SLOTS|CUSTODY_LOCKS) \d+$",
        header, re.M))
    assert len(constants.splitlines()) == 6
    types = constants + "\n" + "\n".join(line for line in header.splitlines() if line.startswith("#define KD_MUTEX_GATE_")) + "\n"
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
    code = "#define MODULE_INFO(...)\n" + without_includes(read_source(ROOT / "kernel_module/mutex/pin_origin.inc")) + "\n" + without_includes(read_source(ROOT / "kernel_module/mutex/pin_diag.inc")) + "\n"
    for marker in (
        "static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,",
        "static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)",
    ):
        code += definition(source, marker) + "\n"
    window = read_source(ROOT / "kernel_module/mutex/pin_window.inc")
    code += window
    for marker in ("static bool kd_mutex_batch_epoch_begin(struct kd_mutex_batch *batch)",
                   "static void kd_mutex_batch_epoch_end(struct kd_mutex_batch *batch, bool keep_current)"):
        code += definition(source, marker) + "\n"
    unpin = definition(window,
        "static void kd_mutex_batch_unpin(struct kd_mutex_batch *batch, bool keep_current)")
    complete = definition(window,
        "static __always_inline void kd_mutex_batch_pin_complete(struct kd_mutex_batch *batch,")
    check = definition(window,
        "static __always_inline void kd_mutex_batch_pin_check(struct kd_mutex_batch *batch)")
    proof = definition(window,
        "static __always_inline void\nkd_mutex_batch_pin_assert(struct kd_mutex_batch *batch,")
    retained_complete = definition(window,
        "static __always_inline void\nkd_mutex_batch_pin_complete_retained(struct kd_mutex_batch *batch,")
    epoch_end = definition(source,
        "static void kd_mutex_batch_epoch_end(struct kd_mutex_batch *batch, bool keep_current)")
    mutations = {
        "claim-successor-instead": (
            "if (!kd_mutex_batch_pin_add(batch, node))",
            "if (!kd_mutex_batch_pin_add(batch, node->next))", "", 1),
        "cancel-rearms-ready": (
            "smp_store_release(&node->locked, KD_MUTEX_WAIT);",
            "smp_store_release(&node->locked, KD_MUTEX_PROXY_READY);", "", 1),
        "cancel-before-descriptor-removal": (unpin,
            unpin.replace("\tbatch->pin.node = NULL;", "\tsmp_store_release(&node->locked, KD_MUTEX_WAIT);\n\tbatch->pin.node = NULL;", 1)
                 .replace("\t/* Last access: the origin may unpin after observing this publication. */\n\tsmp_store_release(&node->locked, KD_MUTEX_WAIT);", "", 1), "", 1),
        "retain-consumed-descriptor": (complete,
            complete.replace("\tbatch->pin.node = NULL;\n", "", 1), "", 1),
        "empty-current-keeps-epoch-closed": (
            "\tkd_mutex_batch_unpin(batch, keep_current);",
            "\tif (!batch->nr_pins) return;\n\tkd_mutex_batch_unpin(batch, keep_current);", "", 1),
        "cold-exit-cancels-current": (
            "\tkd_mutex_batch_unpin(batch, keep_current);",
            "\t(void)keep_current;\n\tkd_mutex_batch_unpin(batch, false);", "", 1),
        "epoch-exit-keeps-gate-closed": (
            "\tkd_mutex_set_locked(batch->lock);",
            "\tif (false) kd_mutex_set_locked(batch->lock);", "", 1),
        "omit-cold-promotion": (
            "smp_store_release(&node->locked, KD_MUTEX_PROXY_CLAIMED);",
            "(void)node;", "", 1),
        "promote-after-epoch-open": (epoch_end,
            epoch_end.replace("\tkd_mutex_batch_unpin(batch, keep_current);\n", "", 1)
                     .replace("\tkd_mutex_set_locked(batch->lock);",
                              "\tkd_mutex_set_locked(batch->lock);\n\tkd_mutex_batch_unpin(batch, keep_current);", 1), "", 1),
        "ignore-private-epoch": (proof,
            proof.replace("!batch->proxy_epoch ||", "false ||", 1), "ready-without-epoch", 1),
        "ignore-ready-owner": (proof,
            proof.replace("!kd_mutex_delegation_owned(batch->lock, current) ||", "false ||", 1), "later-owner-combiner", 1),
        "ignore-released-epoch": (proof,
            proof.replace("batch->outer.released ||", "false ||", 1), "released-epoch", 1),
        "ignore-ready-gate": (proof,
            proof.replace("kd_mutex_gate_read(batch->lock) != KD_MUTEX_GATE_COMBINER", "false", 1), "ready-held", 1),
        "cold-completion-skips-strict-proof": (retained_complete,
            retained_complete.replace("\tkd_mutex_batch_pin_assert_retained(batch, node);\n", "", 1), "retained-open-epoch", 1),
        "ignore-generation": (check,
            check.replace("READ_ONCE(node->count_seq) != batch->pin.generation", "false", 1), "generation", 1),
        "ignore-lock-identity": (check,
            check.replace("READ_ONCE(node->counted_lock) != batch->lock ||", "false ||", 1), "wrong-lock", 1),
    }
    with tempfile.TemporaryDirectory(prefix="kd-pin-window-") as directory:
        path = Path(directory)
        (path / "pin_window_types.h").write_text(types)
        (path / "mutex_state_production.h").write_text(without_includes(read_source(ROOT / "include/kd_mutex_state.h")))
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
                                "wrong-current", "complete-unclaimed", "occupied-slot", "excess-count", "without-epoch",
                                "ready-without-epoch", "later-owner-combiner", "released-epoch", "expiry-before-promotion",
                                "ready-held", "retained-ready", "retained-open-epoch"):
                    rejected = subprocess.run([binary, invalid], capture_output=True,
                                              text=True, timeout=10)
                    assert rejected.returncode == 86 and "BUG pin window:" in rejected.stderr, (
                        invalid, rejected)
                    print("pin-window invariant retained:", invalid)


if __name__ == "__main__":
    main()

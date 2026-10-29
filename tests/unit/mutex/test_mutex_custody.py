"""Guest-only production custody/ACK tests with explicit scheduler substitutes.

Compile the real queue rejoin/retirement, role exchange, pickup, native ledger,
owner-unlock routing, transferred event and frame pop. Two host C threads model
the pinned CPUs; this is not a live kernel/JIT validation.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    mutex = read_source(ROOT / "kernel_module/kd_mutex.c")
    frame = read_source(ROOT / "kernel_module/kd_exec.c")
    header = read_source(ROOT / "include/kd_mutex.h")
    types = without_includes(read_source(ROOT / "include/kd_mutex_types.h"))
    abi = read_source(ROOT / "include/exe_info.h")
    for marker in ("enum kd_entry_abi {", "enum kd_packet_state {"):
        types += definition(abi, marker) + ";\n"
    for marker in ("enum kd_mutex_custody_phase {", "struct kd_mutex_custody {",
                   "struct kd_mutex_osq_node {", "struct kd_mutex_node {"):
        types += definition(header, marker) + ";\n"
    types += definition(read_source(ROOT / "include/kd_spin_entry.h"), "struct kd_spin_ref {") + ";\n"
    for name in ("include/kd_call.h", "include/kd_exec.h"):
        types += without_includes(read_source(ROOT / name)) + "\n"
    types += "\n".join(line for line in header.splitlines() if line.startswith("#define KD_MUTEX_") and any(word in line for word in ("WAIT", "PROXY", "PIN_WINDOW"))) + "\n"
    types += definition(mutex, "enum kd_mutex_batch_result {") + ";\n"
    types += definition(mutex, "struct kd_mutex_batch {") + ";\n"
    queue = "static struct kd_mutex_node *\n" + definition(mutex, "kd_mutex_batch_rejoin(struct kd_mutex_batch *batch, struct kd_mutex_node *next)") + "\n"
    queue += definition(mutex, "static void kd_mutex_batch_retire_current(struct kd_mutex *lock,") + "\n"
    queue += "static __always_inline unsigned int\n" + definition(mutex, "kd_mutex_batch_pin_slot(struct kd_mutex_batch *batch, unsigned int offset)") + "\n"
    for marker in ("static __always_inline void kd_mutex_proxy_wait_pinned(struct kd_mutex_node *node)",
                   "static __always_inline void kd_mutex_batch_pin_check(struct kd_mutex_batch *batch,",
                   "static void kd_mutex_batch_unpin(struct kd_mutex_batch *batch, bool keep_current)",
                   "static __always_inline void kd_mutex_batch_pin_complete(struct kd_mutex_batch *batch,"):
        queue += definition(mutex, marker) + "\n"
    code = definition(frame, "static bool kd_exec_mutex_custody_accepted(const struct kd_exec_frame *frame)") + "\n"
    code += definition(frame, "int kd_exec_frame_record_event(struct kd_exec_frame *frame,") + "\n"
    code += definition(frame, "int kd_exec_frame_pop(struct kd_exec_frame *frame, struct kd_regs *regs)") + "\n"
    code += definition(mutex, "static bool kd_mutex_try_role_swap(struct kd_mutex *lock,") + "\n"
    code += without_includes(read_source(ROOT / "kernel_module/mutex/custody.inc"))
    with tempfile.TemporaryDirectory(prefix="kd-custody-") as tmp:
        path = Path(tmp)
        (path / "custody_types.h").write_text(types)
        (path / "custody_queue.h").write_text(queue)
        variants = {
            "production": code,
            "transfer-keeps-future-pins": code.replace("\tkd_mutex_batch_unpin(batch, true);", "", 1),
            "transfer-keeps-current-descriptor": code.replace("\tkd_mutex_batch_pin_complete(batch, node);", "\tif (false) kd_mutex_batch_pin_complete(batch, node);", 1),
            "missing-pickup-ack": code.replace("!smp_load_acquire(&frame->mutex_mixed.picked_up) ||", "false ||", 1),
            "wrong-queue-custody": code.replace("node->custody.head != frame->mutex_mixed.queue.head ||", "false ||", 1),
            "miss-native-mutex": code.replace("custody->native_locks[custody->native_count++] = lock;", "(void)lock;", 1),
            "combine-with-native-lock": code.replace("!node->custody.native_count && !node->custody.native_overflow", "true", 1),
            "fake-outer-unlock": code.replace("kd_exec_frame_set_state(frame, KD_EXEC_FRAME_TRANSFERRED);",
                                               "frame->outer_unlock_seen = true; kd_exec_frame_set_state(frame, KD_EXEC_FRAME_TRANSFERRED);", 1),
        }
        cc = shlex.split(os.environ.get("CC", "cc"))
        for name, source in variants.items():
            assert name == "production" or source != code, name
            (path / "custody_production.h").write_text(source)
            binary = path / name
            subprocess.run(cc + ["-std=gnu11", "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                           "-I" + str(path), "-I" + str(ROOT / "include"),
                           str(ROOT / "tests/unit/mutex/mutex_custody_fixture.c"), "-o", str(binary)],
                           check=True, timeout=30)
            result = subprocess.run([binary], text=True, capture_output=True, timeout=15)
            if name == "production":
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout, end="")
            else:
                assert result.returncode == 1 and "FAIL custody" in result.stderr, (name, result)
                print("custody mutation detected:", name)


if __name__ == "__main__":
    main()

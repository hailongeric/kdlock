"""Guest-only actual slowpath publication and wait-entry control flow.

Release observers exercise the complete production C slowpath and versioned
count helpers. Stack switching, proxy bodies and physical acquisition are
substitutes; source checks retain both actual assembly-entry ordering contracts.
Existing custody tests cover role-C frame/source retirement and late READY.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def production():
    source = read_source(ROOT / "kernel_module/kd_mutex.c")
    header = (ROOT / "include/kd_mutex.h").read_text()
    constants = "\n".join(line for line in header.splitlines() if line.startswith((
        "#define KD_MUTEX_GATE_", "#define KD_MUTEX_WAIT ", "#define KD_MUTEX_QUEUE_INIT ",
        "#define KD_MUTEX_PROXY_READY ", "#define KD_MUTEX_PROXY_CLAIMED ",
        "#define KD_MUTEX_WAITER_PROCESSED ")))
    constants += "\n" + next(line for line in source.splitlines()
                              if line.startswith("#define KD_MUTEX_WAITER_PROCESSED "))
    constants += "\n" + definition((ROOT / "include/exe_info.h").read_text(),
                                    "enum kd_entry_abi {").rstrip() + ";\n"
    constants += "\n" + definition(source, "enum kd_mutex_batch_result {").rstrip() + ";\n"
    constants += "\n" + next(line for line in (ROOT / "include/kd_lock.h").read_text().splitlines()
                               if line.startswith("#define KD_MUTEX_OWNER_FLAGS ")) + "\n"
    code = constants + without_includes(read_source(ROOT / "include/kd_mutex_state.h"))
    code += without_includes(read_source(ROOT / "kernel_module/mutex/pin_origin.inc"))
    for marker in (
        "static __always_inline bool\nkd_mutex_combiner_owned(struct kd_mutex *lock, struct task_struct *task)",
        "static inline u32 kd_mutex_xchg_tail(struct kd_mutex *lock, u32 tail)",
        "static void kd_mutex_update_max_waiters(int active)",
        "static void kd_mutex_waiter_enter(struct kd_mutex *lock, struct kd_mutex_node *node)",
        "static void kd_mutex_waiter_exit(struct kd_mutex *lock, struct kd_mutex_node *node)",
        "static __always_inline void kd_mutex_wait_for_result(struct kd_mutex_node *node)",
        "static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,",
    ):
        code += definition(source, marker)
    code += "static __always_inline struct kd_mutex_node *\n" + definition(
        source, "kd_mutex_head_successor(struct kd_mutex *lock, struct kd_mutex_node *curr_node)")
    code += "__attribute__((noipa)) static int\n" + definition(
        source, "__kd_mutex_lock_slowpath(struct kd_mutex *lock, int tail,")
    assert "__attribute__((noipa)) noinline notrace static int\n__kd_mutex_lock_slowpath(" in source
    # These are source-order assertions, not execution of the assembly or the
    # role exchange in this fixture. Keep their live/custody gates separate.
    clobber = (ROOT / "kernel_module/mutex/clobber.inc").read_text()
    legacy = (ROOT / "kernel_module/kd_mutex.c").read_text()
    assert clobber.index('movq %c[shadow](%%rsi), %%rsp') < clobber.index('callq %P[wait]')
    assert '[wait] "i"(kd_mutex_lock_slowpath)' in clobber
    assert legacy.index('asm volatile("movq %0, %%rsp"') < legacy.index(
        'ret_val = kd_mutex_lock_slowpath(lock, cur_node);')
    wrapper = definition(source,
                         'kd_mutex_lock_slowpath(struct kd_mutex *lock, struct kd_mutex_node *curr_node)')
    assert 'return __kd_mutex_lock_slowpath(lock, curr_node->tail, curr_node);' in wrapper
    combiner = (ROOT / "kernel_module/mutex/combiner.inc").read_text()
    role_publish = combiner.index('cmpxchg(&batch.own_node->locked, KD_MUTEX_QUEUE_INIT,')
    assert combiner.rfind('kd_source_frame_put', 0, role_publish) >= 0
    assert role_publish < combiner.index('custody.ready', role_publish)
    return code


def main():
    code = production()
    mutations = {
        "ready-before-count": (
            "\tkd_mutex_waiter_enter(lock, curr_node);",
            "\tif (old_tail) smp_store_release(&curr_node->locked, KD_MUTEX_PROXY_READY);\n"
            "\tkd_mutex_waiter_enter(lock, curr_node);"),
        "ready-before-debug": (
            '\t\tmutex_debug("Mutex waiter spinning\\n");',
            '\t\tsmp_store_release(&curr_node->locked, KD_MUTEX_PROXY_READY);\n'
            '\t\tmutex_debug("Mutex waiter spinning\\n");'),
        "link-before-ready": (
            "\t\tsmp_store_release(&curr_node->locked, KD_MUTEX_PROXY_READY);",
            "\t\tsmp_store_release(&prev_node->next, curr_node);\n"
            "\t\tsmp_store_release(&curr_node->locked, KD_MUTEX_PROXY_READY);"),
        "ready-without-release": (
            "smp_store_release(&curr_node->locked, KD_MUTEX_PROXY_READY);",
            "WRITE_ONCE(curr_node->locked, KD_MUTEX_PROXY_READY);"),
        "link-without-release": (
            "smp_store_release(&prev_node->next, curr_node);",
            "WRITE_ONCE(prev_node->next, curr_node);"),
        "republish-on-wait-entry": (
            "\t\tstate = smp_load_acquire(&node->locked);",
            "\t\tWRITE_ONCE(node->locked, KD_MUTEX_PROXY_READY);\n"
            "\t\tstate = smp_load_acquire(&node->locked);"),
        "first-head-stays-init": (
            "cmpxchg(&curr_node->locked, KD_MUTEX_QUEUE_INIT, KD_MUTEX_WAIT)",
            "cmpxchg(&curr_node->locked, KD_MUTEX_QUEUE_INIT, KD_MUTEX_QUEUE_INIT)"),
        "count-exit-missing": (
            "\tkd_mutex_count_exit(lock, node);", "\t(void)lock; (void)node;"),
        "count-generation-reset": (
            "\tkd_mutex_count_exit(lock, node);",
            "\tkd_mutex_count_exit(lock, node); WRITE_ONCE(node->count_seq, 0);"),
        "later-link-overwritten": (
            "\t\tsmp_store_release(&prev_node->next, curr_node);",
            "\t\tWRITE_ONCE(curr_node->next, NULL);\n"
            "\t\tsmp_store_release(&prev_node->next, curr_node);"),
    }
    with tempfile.TemporaryDirectory(prefix="kd-mutex-publication-") as directory:
        path = Path(directory)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) == 1, (name, candidate.count(before))
                candidate = candidate.replace(before, after, 1)
            (path / "publication_production.h").write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + directory,
                str(ROOT / "tests/unit/mutex/mutex_publication_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if mutation:
                assert result.returncode == 1 and "FAIL publication" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print("publication mutation detected:", name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end="")


if __name__ == "__main__":
    main()

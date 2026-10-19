"""Guest-only production mutex tail, node, embedded-object and entry routing tests.

Keep the real capacities, guest kd_regs and decisions. Kernel scheduling,
physical mutexes, task records, the assembly slowpath and resume trampolines
are deterministic substitutes, not proof of live concurrency or owner ACKs.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

from source_text import ROOT, without_includes
from test_spin_shadow import definition


def production():
    mutex = read_source((ROOT / "kernel_module/kd_mutex.c"))
    hook = read_source((ROOT / "kernel_module/kd_lock.c"))
    # This boundary is substituted, so pin its normal owner result to the
    # actual producer. A consumer accepting other values is not equivalence.
    slowpath = definition(
        mutex, "__kd_mutex_lock_slowpath(struct kd_mutex *lock, int tail,"
    )
    assert "release:\n\tkd_mutex_waiter_exit(aux);\n\treturn 2;" in slowpath
    # These statics belong to separate production translation units. Rename
    # only the per-CPU symbol so both unchanged paths can share one fixture.
    code = without_includes(read_source(ROOT / "include/kd_comm.h")).replace("kd_comm_matches(", "kd_comm_matches_real(")
    code += '\nstatic bool kd_comm_matches(const struct kd_comm_key *key, const char comm[TASK_COMM_LEN])\n{\n    comm_queries++;\n    if (trace_admission) CHECK(sampled_first);\n    return kd_comm_matches_real(key, comm);\n}\nstruct kd_comm_key kd_spin_target;\n'
    code += "#define kd_mutex_shadows cpu_shadows\n"
    code += mutex[
        mutex.index("struct kd_mutex_cpu_state {") : mutex.index(
            "static inline struct kd_mutex_node *kd_mutex_decode_tail"
        )
    ]
    # Include the actual decoder, not a second copy of its field arithmetic.
    # The fixture substitutes only per_cpu_ptr and verifies its node identity.
    code += definition(mutex, "static inline struct kd_mutex_node *kd_mutex_decode_tail(u32 tail)")
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
        "static void kd_mutex_wait_for_result(struct kd_mutex_node *node)",
        "static void kd_mutex_claim_origin_take_ref(struct kd_mutex *lock,",
        "static void kd_mutex_claim_origin(struct kd_mutex *lock, struct kd_mutex_aux *aux)",
        "static void kd_mutex_wait_and_lock(struct kd_mutex *lock, struct kd_mutex_aux *aux)",
        "static bool kd_mutex_has_local_predecessor(struct kd_mutex *lock)",
        "static struct kd_mutex_node *kd_mutex_reserve_node(void)",
        "static void kd_mutex_release_node(struct kd_mutex_node *node)",
    ):
        code += definition(mutex, marker)
    for marker, result in (
        ("_kd_mutex_lock_abi(struct kd_mutex *lock, unsigned long rsp_value,", "void"),
        ("_kd_mutex_unlock_checked(struct kd_mutex *lock)", "int"),
        ("_kd_mutex_unlock(struct kd_mutex *lock)", "void"),
    ):
        code += f"__attribute__((noipa)) {result}\n" + definition(mutex, marker)
    code += "#undef kd_mutex_shadows\n"
    for marker in (
        "static unsigned long kd_mutex_contended_acquire(struct kd_mutex *lock, unsigned long ret_rsp,",
        "static void kd_mutex_contended_entry(struct kd_mutex *lock, unsigned long ret_rsp,",
        "static void kd_mutex_lock_entry(struct kd_mutex *lock, unsigned long ret_rsp,",
        "void __kd_mutex_lock(struct kd_mutex *lock, unsigned long ret_rsp,",
        "void __kd_mutex_lock_clobber_v1(struct kd_mutex *lock, unsigned long sp,",
        "void __kd_mutex_unlock(struct kd_mutex *lock, unsigned long ret_rsp,",
    ):
        code += definition(hook, marker)
    code += "void " + definition(hook, "kd_mutex_direct_contended_clobber_v1(struct kd_mutex *lock, unsigned long sp,")
    code += "unsigned long " + definition(hook, "kd_mutex_outer_contended_clobber_v1(struct kd_mutex *lock, unsigned long sp,")
    return code


def main():
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (ROOT / "include/kd_regs.h").read_text()
    types = definition(ptrace, "struct kd_regs {").rstrip() + ";\n"
    types += without_includes(read_source((ROOT / "include/kd_mutex.h")))
    types += without_includes(read_source(ROOT / "include/kd_mutex_aux.h"))
    # The queue fixture substitutes registry arithmetic separately from the
    # pointer-shaped physical owner. Actual atomics run in test_mutex_aux.py.
    assert types.count('atomic_long_t refs;') == 1
    types = types.replace('atomic_long_t refs;', 'fixture_aux_atomic_long_t refs;')
    code = production()
    # Compile each broken decision first, then require an explicit assertion
    # failure. A crash, compiler error, BUG-only exit or timeout is not a pass.
    mutations = {
        "outer-entry-retries-native-cas": (
            "kd_mutex_contended_entry(lock, sp, ip, bp, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);",
            "kd_mutex_lock_entry(lock, sp, ip, bp, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);",
        ),
        "outer-native-result-routed": (
            "return (unsigned long)current;",
            "return 0;",
        ),
        "outer-queued-result-native": (
            "_kd_mutex_lock_abi(kd_mtx, ret_rsp, ret_addr, bp, abi);\n\treturn 0;",
            "_kd_mutex_lock_abi(kd_mtx, ret_rsp, ret_addr, bp, abi);\n\treturn (unsigned long)current;",
        ),
        "native-success-still-samples": (
            "if (kd_mutex_trylock_fast(lock)) {",
            "if (false && kd_mutex_trylock_fast(lock)) {",
        ),
        "local-predecessor-still-publishes": (
            "if (unlikely(kd_mutex_has_local_predecessor(lock)))",
            "if (unlikely(false && kd_mutex_has_local_predecessor(lock)))",
        ),
        "tail-loses-empty-sentinel": (
            "return (cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET |",
            "return cpu << KD_MUTEX_TAIL_CPU_OFFSET |",
        ),
        "tail-loses-slot": (
            "idx << KD_MUTEX_TAIL_IDX_OFFSET;",
            "(idx & 0) << KD_MUTEX_TAIL_IDX_OFFSET;",
        ),
        "tail-decodes-next-cpu": (
            "int cpu = (tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;",
            "int cpu = (tail >> KD_MUTEX_TAIL_CPU_OFFSET);",
        ),
        "tail-truncates-slot": (
            "& KD_MUTEX_TAIL_IDX_MASK;",
            "& 1;",
        ),
        "tail-ignores-remote-cpu": (
            "return per_cpu_ptr(&kd_mutex_nodes[idx], cpu);",
            (
                "return per_cpu_ptr(&kd_mutex_nodes[idx], "
                "(cpu & 0) + smp_processor_id());"
            ),
        ),
        "missing-stack-accepted": (
            "if (!node->shadow_stack_base)",
            "if (0 && !node->shadow_stack_base)",
        ),
        "reservation-not-published": (
            "WRITE_ONCE(shadow->node_slots, slots | BIT(idx));",
            "WRITE_ONCE(shadow->node_slots, slots);",
        ),
        "poll-enables-preemption": (
            "while (smp_load_acquire(&node->locked))\n\t\tcpu_relax();",
            "while (smp_load_acquire(&node->locked)) { "
            "preempt_enable(); cpu_relax(); preempt_disable(); }",
        ),
        "poll-returns-before-publication": (
            "while (smp_load_acquire(&node->locked))",
            "if (smp_load_acquire(&node->locked))",
        ),
        "release-keeps-gs": ("node->gsbase = 0;", "node->gsbase = 1;"),
        "gate-without-native-lock": (
            "\t\tkd_mutex_claim_origin_take_ref(lock, aux);\n\t\treturn;",
            "\t\treturn;",
        ),
        "fast-owner-restores-reference-pair": (
            "\t\tkd_mutex_claim_origin_take_ref(lock, aux);\n\t\treturn;",
            "\t\tkd_mutex_claim_origin(lock, aux);\n\t\tkd_mutex_aux_put(aux);\n\t\treturn;",
        ),
        "fast-owner-drops-transferred-reference": (
            "\t\tkd_mutex_claim_origin_take_ref(lock, aux);\n\t\treturn;",
            "\t\tkd_mutex_claim_origin_take_ref(lock, aux);\n\t\tkd_mutex_aux_put(aux);\n\t\treturn;",
        ),
        "unlock-restores-temporary-reference": (
            "struct kd_mutex_aux *aux = kd_mutex_aux_borrow_owned(lock);",
            "struct kd_mutex_aux *aux = kd_mutex_aux_borrow_owned(lock);\n\t"
            "if (aux) aux = kd_mutex_aux_lookup(lock);",
        ),
        "unlock-error-drops-owner-reference": (
            'KD_PR_ERR("kd_mutex_unlock: unexpected locked state %d\\n", locked);',
            'KD_PR_ERR("kd_mutex_unlock: unexpected locked state %d\\n", locked);\n\tkd_mutex_aux_put(aux);',
        ),
        "unlock-drops-owner-before-gate": (
            "\t\tsmp_store_release(&aux->locked, 0);",
            "\t\tkd_mutex_aux_put(aux);\n\t\tsmp_store_release(&aux->locked, 0);",
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
        "hook-ignores-task-failure": (
            "if (!kd_mutex_task_get(current)) {",
            "if (kd_mutex_task_get(current) && false) {",
        ),
        "unlock-drops-retained-task": (
            "kd_mutex_task_reroute(current)",
            "(false && kd_mutex_task_reroute(current))",
        ),
        "hook-admits-closed-source": (
            "!kd_source_is_open() ||",
            "(false && !kd_source_is_open()) ||",
        ),
        "borrowed-unlock-bypasses-notification": (
            "if (kd_exec_native_unlock((unsigned long)lock, true))",
            "if (false && kd_exec_native_unlock((unsigned long)lock, true))",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-mutex-resources-") as tmp:
        directory = Path(tmp)
        (directory / "mutex_resource_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == (3 if name == "outer-native-result-routed" else 1), (name, code.count(before))
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
                    str(ROOT / "tests/unit/mutex/mutex_resources_fixture.c"),
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

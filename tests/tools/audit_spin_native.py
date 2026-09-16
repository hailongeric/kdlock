"""Historical guest-only audit of the former shared-word spin protocols.

The current L/S implementation intentionally fails the shared-word contract
check (exit 1). Use test_spin_routing.py and test_17_spin_native_protocol.sh for
current routing/exclusion validation; do not remove the contract to force PASS.

Exit 2 means a compatibility defect was reproduced, NOT a passing integration
test. Exit 1 means the audit could not run; exit 0 only covers these witnesses.
No module is loaded and no live kernel queue is exercised.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unit import configure_paths

configure_paths()
from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def region(source, start, end):
    require(source.count(start) == 1, f"ambiguous/missing start: {start!r}")
    tail = source.split(start, 1)[1]
    require(tail.count(end) == 1, f"ambiguous/missing end: {end!r}")
    return start + tail.split(end, 1)[0]


def uncomment(source):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)


def renamed_functions(source, prefix, encode, decode):
    return (
        f"#define encode_tail {prefix}_encode_tail\n"
        f"#define decode_tail {prefix}_decode_tail\n"
        + definition(source, encode)
        + definition(source, decode)
        + "#undef encode_tail\n#undef decode_tail\n"
    )


def build_headers(read):
    kd = read(ROOT / "kernel_module/kd_spinlock.c")
    hooks = read(ROOT / "kernel_module/kd_lock.c")
    nodes = read(ROOT / "include/kd_spinlock.h")
    bits = read(ROOT / "include/qspinlock_i.h")
    native = read("kernel/locking/qspinlock.c")
    mcs = read("kernel/locking/mcs_spinlock.h")
    ptrace = read("arch/x86/include/asm/ptrace.h")
    native_bits = read("include/asm-generic/qspinlock_types.h")
    api = read("include/linux/spinlock_api_smp.h")
    dispatch = uncomment(read("kernel/locking/spinlock.c"))
    generated = read("arch/x86/include/generated/asm/mcs_spinlock.h")
    generic = read("include/asm-generic/mcs_spinlock.h")
    require(
        uncomment(generated).strip() == "#include <asm-generic/mcs_spinlock.h>"
        and "arch_mcs_spin_unlock_contended" not in uncomment(generic),
        "audit requires the x86 generic MCS wake implementation",
    )
    for source in (nodes, native):
        require(
            re.search(r"(?m)^#define MAX_NODES\s+4$", source),
            "audit requires four per-CPU node slots",
        )
    # A future private-gate implementation must update this witness contract;
    # different node layouts alone do not prove that its queues ever mix.
    for source, snippet in (
        (
            kd,
            "static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_spin_node, kd_spin_nodes[MAX_NODES]);",
        ),
        (native, "static DEFINE_PER_CPU_ALIGNED(struct qnode, qnodes[MAX_NODES]);"),
        (hooks, "kd_spin_lock((struct qspinlock *)lock, ret_rsp);"),
        (kd, "old_tail = xchg_tail(lock, tail);"),
        (kd, "xchg(&lock->tail, tail >> _Q_TAIL_OFFSET_HL)"),
        (native, "old = xchg_tail(lock, tail);"),
    ):
        require(
            re.sub(r"\s+", "", snippet) in re.sub(r"\s+", "", uncomment(source)),
            "shared-lock queue assumption changed; review the audit fixture",
        )
    # The append/wait models below are scoped to these production statements.
    for source, snippet in (
        (kd, "prev_node = decode_tail(old_tail);"),
        (kd, "prev_node->next = curr_node;"),
        (kd, "curr_node->locked = true;"),
        (kd, "smp_cond_load_relaxed_sched(&curr_node->locked, !(VAL));"),
        (native, "prev = decode_tail(old);"),
        (native, "WRITE_ONCE(prev->next, node);"),
        (native, "node->locked = 0;"),
        (native, "arch_mcs_spin_unlock_contended(&next->locked);"),
    ):
        require(snippet in source, f"production queue statement changed: {snippet}")
    for operation in ("lock", "unlock"):
        match = re.search(
            rf"(?m)^.* void __lockfunc _raw_spin_{operation}"
            r"\(raw_spinlock_t \*lock\)$",
            dispatch,
        )
        require(match is not None, f"missing native {operation} dispatch")
        body = uncomment(definition(dispatch, match.group()))
        compact = re.sub(r"\s+", "", body)
        require(
            f"kd_raw_spin_{operation}(lock,rsp,_RET_IP_);return;}}"
            f"__raw_spin_{operation}(lock);"
            in compact
            and "preempt_" not in body,
            f"native {operation} dispatch no longer bypasses the inline API",
        )

    types = region(bits, "#define _Q_SET_MASK_HL(type)", "#ifndef _Q_PENDING_LOOPS_HL")
    types += region(
        native_bits,
        "#define\t_Q_SET_MASK(type)",
        "#endif /* __ASM_GENERIC_QSPINLOCK_TYPES_H */",
    )
    for source, first in (
        (bits, "struct orig_qspinlock {"),
        (ptrace.split("#else /* __i386__ */", 1)[1], "struct pt_regs {"),
        (nodes, "struct kd_spin_node {"),
        (mcs, "struct mcs_spinlock {"),
        (native, "struct qnode {"),
    ):
        types += definition(source, first).rstrip() + ";\n"
    queue = renamed_functions(
        kd,
        "kd",
        "static inline u32 encode_tail(int cpu, int idx)",
        "static inline struct kd_spin_node *decode_tail(u32 tail)",
    )
    queue += renamed_functions(
        native,
        "native",
        "static inline __pure u32 encode_tail(int cpu, int idx)",
        "static inline __pure struct mcs_spinlock *decode_tail(u32 tail)",
    )
    queue += "static inline void\n" + definition(
        kd, "clear_locked_set_completed(struct kd_spin_node *lock)"
    )
    wake = re.search(r"(?m)^#define arch_mcs_spin_unlock_contended\(l\).*", mcs)
    require(wake is not None, "missing native wake macro")
    queue += mcs[wake.start() : mcs.index("\n#endif", wake.start())] + "\n"

    # Compile only uncontended prefixes. Abort on every other path rather than
    # inventing queue, combiner, continuation or per-CPU scheduler behavior.
    fast_lock = definition(
        kd, "kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value)"
    ).split("\n\t/*\n\t * Mid-path", 1)
    fast_unlock = definition(kd, "kd_spin_unlock(struct qspinlock *lock)").split(
        "\n\tfor (j = 0; j < 8; j++)", 1
    )
    require(len(fast_lock) == len(fast_unlock) == 2, "fastpath boundary changed")
    functions = (
        "static void\n"
        + fast_lock[0]
        + ("\n(void)sizeof(cnt); (void)curr_node; (void)rsp_value; abort();\n}\n")
    )
    functions += (
        "static void\n"
        + fast_unlock[0]
        + (
            "\n(void)from_cpuid; (void)j; (void)max_idx; (void)my_idx;\n"
            "(void)sizeof(temp_lock_addr); abort();\n}\n"
        )
    )
    irq_value = re.search(r"(?m)^#define _Q_LOCKED_IRQ_VAL .*$", kd)
    require(irq_value is not None, "missing IRQ lock value")
    functions = irq_value.group() + "\n" + functions
    for operation in ("lock", "unlock"):
        functions += definition(
            api, f"static inline void __raw_spin_{operation}(raw_spinlock_t *lock)"
        )
        functions += definition(
            hooks, f"static void origin_raw_spin_{operation}(raw_spinlock_t *lock)"
        )
        functions += definition(
            hooks,
            f"void __kd_raw_spin_{operation}(raw_spinlock_t *lock, unsigned long ret_rsp,",
        )
    return {
        "audit_types.h": types,
        "audit_queue.h": queue,
        "audit_fastpath.h": functions,
    }


def audit(args):
    started = datetime.now(timezone.utc).isoformat()
    kernel = args.kernel_tree.resolve()
    release = platform.release()
    require(platform.machine() == "x86_64", "only x86-64 is audited")
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {}

    def read(path):
        path = Path(path)
        if not path.is_absolute():
            path = kernel / path
        data = path.read_bytes()
        sources[str(path)] = hashlib.sha256(data).hexdigest()
        return data.decode()

    config = dict(re.findall(r"(?m)^(CONFIG_\w+)=(.*)$", read(".config")))
    require(read("include/config/kernel.release").strip() == release, "KDIR mismatch")
    for name in ("X86_64", "PREEMPT_COUNT"):
        require(config.get(f"CONFIG_{name}") == "y", f"CONFIG_{name}=y required")
    for name in (
        "GENERIC_LOCKBREAK",
        "DEBUG_LOCK_ALLOC",
        "INLINE_SPIN_LOCK",
        "INLINE_SPIN_UNLOCK",
    ):
        require(config.get(f"CONFIG_{name}") != "y", f"CONFIG_{name} unsupported")
    for name, content in build_headers(read).items():
        (args.output / name).write_text(content)
    for path in (Path(__file__), ROOT / "tests/unit/spin/test_spin_shadow.py"):
        read(path)
    fixture = ROOT / "tests/unit/spin/spin_native_fixture.c"
    read(fixture)
    compiler = shlex.split(os.environ.get("CC", "cc"))
    require(compiler, "CC is empty")
    results = []
    for pv in (0, 1):
        binary = args.output / f"spin-native-pv{pv}"
        command = compiler + [
            "-std=gnu11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-DCONFIG_NR_CPUS={int(config['CONFIG_NR_CPUS'])}",
            "-I",
            str(args.output),
            str(fixture),
            "-o",
            str(binary),
        ]
        if pv:
            command.append("-DCONFIG_PARAVIRT_SPINLOCKS=1")
        compiled = subprocess.run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
        (args.output / f"compile-pv{pv}.log").write_text(
            compiled.stdout + compiled.stderr
        )
        compiled.check_returncode()
        ran = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=10, check=False
        )
        (args.output / f"run-pv{pv}.log").write_text(ran.stdout + ran.stderr)
        ran.check_returncode()
        results.append(
            {
                "pv": pv,
                "matches_guest_config": pv
                == int(config.get("CONFIG_PARAVIRT_SPINLOCKS") == "y"),
                "compile_command": command,
                "witnesses": json.loads(ran.stdout),
            }
        )
    incompatible = any(result["witnesses"]["incompatible"] for result in results)
    for name, digest in sources.items():
        require(
            hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest,
            f"source changed during audit: {name}",
        )
    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "kernel_release": release,
        "kernel_tree": str(kernel),
        "scope": "isolated decoders, wake layout, hook and uncontended preemption prefixes; no live kernel queue",
        "sources_sha256": sources,
        "config": {
            key: value
            for key, value in config.items()
            if key.startswith(("CONFIG_PREEMPT", "CONFIG_DEBUG_LOCK"))
            or key in {"CONFIG_X86_64", "CONFIG_NR_CPUS", "CONFIG_PARAVIRT_SPINLOCKS"}
        },
        "results": results,
        "incompatible": incompatible,
        "exit_code": 2 if incompatible else 0,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"{'INCOMPATIBLE' if incompatible else 'NO_WITNESS'}: {args.output / 'report.json'}"
    )
    return report["exit_code"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernel-tree",
        type=Path,
        default=Path(
            os.environ.get("KDIR", f"/lib/modules/{platform.release()}/build")
        ),
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new evidence directory"
    )
    args = parser.parse_args()
    try:
        return audit(args)
    except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        print(f"AUDIT_ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

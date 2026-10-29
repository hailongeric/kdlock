"""Run production rwlock algorithms against C atomics and concurrent callers.

Only kernel primitives and the native contended spin engine are substituted here.
The live workload separately verifies the real queue and returned JIT bodies.
"""
from pathlib import Path
import re
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    header = (ROOT / "include/kd_rwlock.h").read_text()
    header = re.sub(r"^#include .*$", "", header, flags=re.M)
    spin_type = (ROOT / "include/kd_spin_type.h").read_text()
    spin_type = re.sub(r"^#include .*$", "", spin_type, flags=re.M)
    direct = (ROOT / "include/kd_spin_direct.h").read_text()
    native = direct[
        direct.index("static __always_inline u32 kd_spin_direct_native_reserve_inline("):
        direct.index("void kd_spin_direct_native_unlock(")
    ]
    # Keep accounting in the actual production definitions. The C fixture
    # substitutes only primitives and the pending/MCS engine on a failed CAS.
    for helper in ("reserve", "cancel", "finish", "lock", "release"):
        assert f"kd_spin_direct_native_{helper}_inline" in native
    with tempfile.TemporaryDirectory(prefix="kd-rwlock-") as directory:
        path = Path(directory)
        (path / "rwlock_production.h").write_text(header)
        (path / "rwlock_spin_type.h").write_text(spin_type)
        (path / "rwlock_native_gate.h").write_text(native)
        release = (ROOT / "kernel_module/spin/direct.inc").read_text()
        release = release[release.index('void\nkd_rwlock_fast_write_unlock('):
                          release.index('EXPORT_SYMBOL_GPL(kd_rwlock_fast_write_unlock)')]
        (path / "rwlock_native_release.h").write_text(release)
        prelude = (ROOT / "kernel_module/spin/combiner.inc").read_text()
        prelude = prelude[prelude.index('static void kd_spin_rw_begin('):
                          prelude.index('#include "execute.inc"')]
        (path / "rwlock_prelude.h").write_text(prelude)
        def build(name):
            binary = path / name
            subprocess.run([
                "cc", "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-pthread", "-I", str(path),
                str(ROOT / "tests/unit/rwlock/rwlock_fixture.c"), "-o", str(binary),
            ], check=True, timeout=30)
            return binary

        subprocess.run([str(build("rwlock"))], check=True, timeout=40)
        mutations = (
            ("missing-cancel", "rwlock_production.h", header,
             "\t\tkd_spin_direct_native_cancel_inline();", "\t\t/* lost reference */"),
            ("irq-samples-heat", "rwlock_production.h", header,
             "\t\tkd_spin_direct_native_cancel_inline();",
             "\t\tkd_hotlock_spin_entry_pinned();\n\t\tkd_spin_direct_native_cancel_inline();"),
            ("context-before-success-check", "rwlock_production.h", header,
             "failed && in_interrupt()", "in_interrupt() && failed"),
            ("release-overwrites-tail", "rwlock_native_gate.h", native,
             "smp_store_release(&lock->locked, 0);",
             "smp_store_release(&lock->val.counter, 0);"),
            ("cancel-drops-outer-reference", "rwlock_native_gate.h", native,
             "static __always_inline void kd_spin_direct_native_cancel_inline(void)\n"
             "{\n\tthis_cpu_dec(kd_spin_fast_cpu.nondelegated);\n}",
             "static __always_inline void kd_spin_direct_native_cancel_inline(void)\n"
             "{\n\tkd_spin_fast_cpu.nondelegated = 0;\n}"),
        )
        for name, filename, original, old, new in mutations:
            assert original.count(old) == 1, (name, "mutation target changed")
            target = path / filename
            target.write_text(original.replace(old, new))
            # A compile error or timeout is a failed check, never evidence that
            # the fixture detected a protocol error. Each mutant must reach an
            # assertion in the bounded route cases, without running stress.
            binary = build(name)
            result = subprocess.run([str(binary), "--routes-only"], timeout=15,
                                    capture_output=True, text=True)
            assert result.returncode == -signal.SIGABRT, (
                name, result.returncode, result.stdout, result.stderr)
            target.write_text(original)
            print(f"PASS rwlock mutation: {name}")



if __name__ == "__main__":
    main()

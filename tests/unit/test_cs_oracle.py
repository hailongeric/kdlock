"""Exercise the test module's actual CS update and integrity checker in the guest."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PREAMBLE = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define READ_ONCE(value) (value)
#define pr_err(...) fprintf(stderr, __VA_ARGS__)
"""

CHECKS = r"""
static void check(unsigned int failures, unsigned long operations,
                  unsigned long completed, unsigned int active)
{
    unsigned long actual_ops, actual_done;
    unsigned int actual_active;

    assert(kd_cs_validate(&actual_ops, &actual_done, &actual_active) == failures);
    assert(actual_ops == operations);
    assert(actual_done == completed);
    assert(actual_active == active);
}

int main(void)
{
    unsigned int i;

    check(0, 0, 0, 0);
    for (i = 0; i < 100; i++) {
        kd_cs_step(KD_CS_SPIN_A);
        kd_cs_step(KD_CS_SPIN_B);
        kd_cs_step(KD_CS_SPIN_B);
    }
    check(0, 300, 300, 2);
    kd_cs_completed[KD_CS_SPIN_A]--;
    check(1, 300, 299, 2);
    /* Equal aggregate totals must not hide opposite per-lock errors. */
    kd_cs_completed[KD_CS_SPIN_B]++;
    check(2, 300, 300, 2);
    kd_cs_completed[KD_CS_SPIN_A]++;
    kd_cs_completed[KD_CS_SPIN_B]--;
    kd_cs_completed[KD_CS_MUTEX_A]++;
    check(1, 300, 301, 2);
    kd_cs_completed[KD_CS_MUTEX_A]--;
    kd_cs_states[KD_CS_SPIN_B].commit ^= 1;
    check(1, 300, 300, 2);
    kd_cs_states[KD_CS_SPIN_B].commit ^= 1;
    kd_cs_step(KD_CS_MUTEX_A);
    check(0, 301, 301, 3);
    puts("[PASS] test_cs_oracle (7 production update/validation cases)");
    return 0;
}
"""


def main():
    source = (ROOT / "klock_module/klock_module.c").read_text()
    start = source.index("#define KD_CS_LANES ")
    step = source.index("static __always_inline void kd_cs_step(", start)
    end = source.index("\n}", step) + 2
    validate = source.index("static unsigned int kd_cs_validate(")
    validate_end = source.index("\n}", validate) + 2
    body = source[start:end] + "\n" + source[validate:validate_end]
    with tempfile.TemporaryDirectory(prefix="kdlock-cs-oracle-") as directory:
        path = Path(directory)
        c_file = path / "cs_oracle.c"
        binary = path / "cs_oracle"
        c_file.write_text(PREAMBLE + body + CHECKS)
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(c_file),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()

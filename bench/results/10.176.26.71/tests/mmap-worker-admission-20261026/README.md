# Versioned QEMU worker admission: focused checks

The `qemu-workers-v1` admission policy keeps the original 64 vCPU and three
service tasks exact while permitting verified QEMU auxiliary worker lifetimes
and activity. It is separate from the unchanged `mmap-window-v2` control
protocol and preserves default `fixed-aux-v1` behavior. The explicit role and
measurement boundary are documented in [QEMU_WORKERS.md](../../../../mmap_lock/QEMU_WORKERS.md).
No kernel, native MM body, lock implementation, payload or timed client changed.

The first frozen VM check passed **94 Python tests in 0.843 seconds** and
**both basic programs**. Nine additional fixtures cover active worker birth,
retirement and TID reuse; observed counter coverage; foreign/missing TGID;
unknown roles and affinity; core identity and incomplete scans; counter
regression and reappearing lifetimes; preserved legacy rejection; explicit
role binding; consistent initial host admission; and the recorded single
90-second post-setup interval. Existing control-barrier, report-integrity,
21-count matrix, plain-mode and capture fixtures also passed. No skip or
compile failure was counted as a pass.

Independent review then requested two targeted changes: execute the real
`qualify_window` path in a fixture, and preserve `admission_policy` in the
full-campaign summary. The final snapshot passed **55 affected tests in
0.932 seconds** (`test_mmap_window` and `test_mmap_scaling` only), reusing the
unchanged passing basic/capture/plain/paired checks. The new replay fixture
accepts valid dynamic-worker evidence and rejects mismatched policy/manifest,
missing retained evidence, missing/short settling, settling after client launch
and altered worker accounting. External environment checks are stubbed; window
qualification, control replay, bindings and lifetime accounting execute directly.
The full-summary fixture retains the exact 126-case matrix and admission version.

Commands executed in a new frozen recovery VM source directory:

```sh
make -C tests/unit run PY_TESTS=
LC_ALL=C PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/unit/bench \
  /root/kdlock-translation-venv-20261019/bin/python3 -m unittest -v \
  test_mmap_window test_mmap_scaling test_mmap_paired \
  test_mmap_throughput test_mmap_capture
```

The 392-file snapshot contains 3,380,917 source bytes; archive SHA-256:
`60a394b01d75b197490ea7ce435733e3fdd8c94708713724362ff025730fb53a`.
The final source-2 archive SHA-256 is
`9ffeb9784ae5af9e44f024084df8bd73d645ebae66748c687986c307e3aaadc0`.
Source bytes remained unchanged during the checks. The basic programs' negative
translator/error-path output is expected fixture behavior, not a dependency skip.

Raw source archive, manifest, invocation, logs and before/after health are at
`bench/results/10.176.26.71/raw/tests/mmap-worker-admission-20261026/` on 380G10,
and `/root/kdlock-evidence/10.176.26.71/tests/mmap-worker-admission-20261026/`
in the guest. Both commands and SSH exited 0. Before/after recovery identity,
policy and dmesg matched: `6.1.159-kdclobber2`, boot
`b632d1e3-8c42-4f58-a7f5-053d063959fa`, original 73 modules, taint zero,
voluntary preemption, CPUs 0–63 and empty `next_entry`. No competing project
process/open file was detected.

Independent review closed against source-2 with both targeted findings resolved
and no remaining blocker in that bounded review. The reviewer verified the
archive, implementation/fixture hashes and saved 55-test result; it executed no
tests or live helpers. These are offline fixtures, not actual mmap validation
or accepted throughput. The earlier stopped screen and missing settling remain
preserved. The separately authorized two-arm validation is still pending at
this checkpoint; no new performance conclusion follows from these tests.

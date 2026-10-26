# Five remaining KD aggregate controls

The October 26, 2026 (Asia/Shanghai) request completed exactly one KD run at
44, 48, 52, 56 and 60 workers. Every row passed aggregate correctness and drain
checks, with `peak_status=unavailable` and `paired_campaign_accepted=false`.
These are `single_aggregate_control` results: no fresh Native pair, repetition,
variability estimate, latency result or optimization claim. The earlier
[failed sweep](../mmap-functional-scaling-20261026/README.md) retains its verdict;
its 126-session matrix was not resumed.

| Threads | Completed mmap/munmap pairs | Actual wall_ns | Pairs/s |
| ---: | ---: | ---: | ---: |
| 44 | 19,808 | 2,039,563,568 | 9,711.882 |
| 48 | 17,664 | 2,060,406,118 | 8,573.067 |
| 52 | 15,840 | 2,053,125,374 | 7,715.067 |
| 56 | 14,816 | 2,068,768,524 | 7,161.749 |
| 60 | 14,048 | 2,093,299,012 | 6,710.938 |

Rates are `completed_pairs * 1e9 / wall_ns`. The same installed
`6.1.159-kdmm31` kernel/configuration, `kd_mmap=on`, existing payload and unchanged
timed syscall client were reused. Workers used CPUs 0..N−1 and collector 63;
each case retained the 90-second setup interval and plain, untouched 4 KiB
shared-mm mmap/munmap workload. No kernel build/install or MM-body change ran.
[Preflight](../../raw/bench/mmap-aggregate-tail-20261026/preflight.stdout) and
[artifact identities](../../raw/bench/mmap-aggregate-tail-20261026/expected-artifacts.json)
bind the kernel image SHA-256
`17f1fa00971f0084bf1b130c7a09f88cb9aae0544adcded61bcfce20484c7040`
and timed-client SHA-256
`5962210671ac238ae4df8dcca442b3cb7407efb2b5b2edb42ae637ac4902083f`.

Execution/helper commit: `dd08945d2d71f794d9b26228d63d70b657c6ce58`.
The [aggregate helper](../../../../mmap_lock/aggregate.py) permits only the exact
missing-positive-peak outcome; existing functional, identity, affinity,
accounting, timing and progress validation still applies. Historical validators
remain unchanged. Its already completed VM checks passed **two basic programs
and four focused tests**. Their logs are `offline-check-0.log` and
`offline-check-1.log` in the archive below; no tests were rerun for this closure.

## Scope and recovery

Actual consumption was **five timed payload cases, two boots (KD and recovery)
and three full host captures**. The controller completed 44–56 workers, then
reached its conservative recovery-reserve cutoff. Only the source controller
was paused; the separately recorded 60-worker case ran once on the same KD boot,
drained and was archived before that controller resumed recovery. No guest
process was signaled. The original four-case `plan.json` remains unchanged;
[scope-final.json](../../raw/bench/mmap-aggregate-tail-20261026/scope-final.json)
reconciles the separate `manual-n60.stdout` receipt into the five-case total.

[Recovery](../../raw/bench/mmap-aggregate-tail-20261026/recovery-final.stdout)
passed at **2026-10-26 11:33:52 Asia/Shanghai (03:33:52 UTC)**, before the
11:37:08 deadline: `6.1.159-kdclobber2`, original **73 modules**, **taint 0**,
idle and no pending boot (`next_entry` empty). Boot ID:
`8caa1264-4d93-4448-a6d8-6d8393d364ee`. The
[final host capture](../../raw/bench/mmap-aggregate-tail-20261026/final-recovery/host-endpoint.json)
passed placement and recovery-snapshot checks. Its receipt and the recovery
receipt are retained separately from the pre-recovery guest archive.

## Exact evidence

[All five receipts](../../raw/bench/mmap-aggregate-tail-20261026/all-five-results.json)
retain full precision, status, raw paths and hashes; SHA-256:
`517789e7edffcbd30d93041f4af113183606bf01de12e25904064997ff51230c`.
Each raw source is
`/root/kdlock-evidence/10.176.26.71/bench/mmap-aggregate-tail-20261026/N-plain/client.jsonl`;
its archive member is `mmap-aggregate-tail-20261026/N-plain/client.jsonl`, with
`N` given below. The corresponding `result.json` is in the same directory.

| N | Raw client SHA-256 |
| ---: | --- |
| 44 | `8e5ada78931c374735becc1ba2253b60b817d96d76912eb088e75fa471761e7f` |
| 48 | `7fa0e4c95bf6e9ca5e2ac474bec7dc468c0c82d7aa9305ef6a83ae6977cb2c3e` |
| 52 | `4343e40decae2cd444179e3f14c9cb252857b2accc0bee15b27a71ee8987016a` |
| 56 | `db08f528eff74ee7641c68beac22fbd06b0c3129546d2709c3b0e790661ecdc2` |
| 60 | `f9180329f01ac6a9a25979ae2ea5b679b8fe80b43b9159a3478b808d4114b2fc` |

The [guest archive](../../raw/bench/mmap-aggregate-tail-20261026/all-five-guest-evidence.tar.gz)
contains 81 regular files, 1,992,161 uncompressed bytes and 426,468 compressed
bytes; SHA-256:
`0e59358afc4e6e06cc0421a3ed47d02de1ab3eea2a6c551a66b32ed24fa4211a`.
The same raw directory retains exact commands, source/orchestration manifests,
controller pause/resume records and original receipts. Closure used only saved
evidence arithmetic, hash and documentation checks; no further live action ran.

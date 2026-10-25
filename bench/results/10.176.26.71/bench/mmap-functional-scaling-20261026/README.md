# Throughput continuation stopped at the 40-worker KD control

The separately authorized October 26, 2026 (Asia/Shanghai) continuation stopped
at `21:44:45 UTC` on October 25 before any measured case. KD completed its
80,000-cycle functional check and **15 unscored controls through 36 workers**.
The **40-worker control failed** with `no positive full-cohort peak window`.
Controls at 44/48/52/56/60 workers and **all 126 measurements remain unrun**.
There was no retry, optimization, new latency collection or acceptance change.
Recovery was verified with the original 73 modules and zero taint.

Execution commit: `30af034025d6d30b66b507b1c03847e6c765bb4a`; tooling change:
`9b6bb11fcc2e988dff69c579383b3176cba7193e`. Lock and mmap integration remain the
audited `e6fc371` bytes. All 352 frozen source files and 12 orchestration inputs
still matched after the stop. The unchanged `6.1.159-kdmm31` image/configuration,
payload and timed client were reused. Only the fixed userspace client had been
rebuilt during the preceding [offline preparation](../../tests/mmap-functional-eligibility-20261026/README.md).

The explicit policies were `mmap-functional-v1`, `mmap-window-v2` and
`qemu-workers-v1`, with the same 90-second setup interval and worker grid.
Fresh KD admission/readiness and compatibility verification passed. The prior
Native fixed proof and 21 controls were reused through their hash-bound
compatibility receipt; no Native workload ran in this continuation. Those
controls and the [earlier small pair](../mmap-worker-screen-20261026/README.md)
remain separate evidence, with no pooling of rates or new variability claim.

## Failure and what the retained samples establish

The new fixed check returned normal functional completion with
`writer_observation=inconclusive`: 16 joined workers, 80,000 completed cycles,
zero worker/context/fault errors and exact callback/lifetime accounting.
It recorded 79,707 contended mmap callbacks and check counter 372,640. This is
an eligible functional result under the explicit policy, not a positive
sleeping-writer proof. The [older strict-policy failure](../mmap-worker-scaling-20261026/README.md)
retains its failed verdict.

`paired.py::validate` then completed and unloaded the controls at
`1,2,3,4,5,6,7,8,12,16,20,24,28,32,36` workers. At 40 workers,
`business_finish` reached `mmap_writer/timing.py::validate`, which rejected the
result at `spin_cacheline/peak.py::analyze_peak`. The controller and SSH child
exited normally with failure; neither timed out.

| Retained 40-worker observation | Result |
| --- | ---: |
| Joined workers / worker errors | 40 / 0 |
| Completed mmap/munmap cycles | 22,784 |
| Whole-run elapsed time | 2,035,264,522 ns |
| Maps / closes / remaining VMAs | 22,784 / 22,784 / 0 |
| Fault callbacks / context errors / foreign rejects | 0 / 0 / 0 |
| Final cycles per worker | 448–960 |
| Progress samples / eligible samples | 201 / 169 |
| Candidate windows / accepted windows | 139 / 0 |
| Largest number of workers with positive published progress in one candidate | 39 of 40 |

The unchanged rule selects each start's earliest observed endpoint reaching
300 ms after a 300 ms settling interval, and requires positive published
progress for every worker. Progress is published in batches of 256 completed
cycles. Read-only arithmetic over the saved samples reproduces the rejection.
Zero checkpoint delta does not establish zero operations within that interval;
the samples cannot distinguish sub-batch progress from a temporary stall.
The data therefore demonstrate a **measurement qualification failure**, not a
lock ownership defect, proven starvation or an accepted performance loss.

This is a blocking measurement finding in `peak.py::analyze_peak`, reached
through `timing.py::validate`; no implementation fix is claimed. The next
performance step is a bounded review of this saved checkpoint/peak-window
interaction and its throughput contract before proposing another paired run.
Keep the failed verdict and current criteria; do not silently drop the peak
requirement, change batching/duration or skip failed worker counts. A lock
optimization still needs a qualified repeated baseline and causal evidence.

## Consumed scope and recovery

| Operation | Actual | Authorized maximum |
| --- | ---: | ---: |
| Boots, including recovery | 2 | 5 |
| Full host captures | 3 | 384 |
| Payload cycles | 17, including the failed control | 148 |
| Fixed functional checks | 1 | 1 |
| New unscored timed controls | 16: 15 passed, 1 failed | 21 |
| Measured sessions | 0 | 126 |
| Window observers / scans | 0 / 0 | 126 / 12,222 |

Read-only inspection found client PID 2203 gone, all workers joined, no project
process or open project file, and no kernel fault match. Payload health was
`files=0 mm_refs=0 destroyed=1 release_errors=0`, with module reference count
zero. A second check reproduced the same measurement rejection and verified
drain before normally unloading only `kd_mmap_writer_native`. Cleanup passed
separately; the original validation receipt remains `passed=false` and
`drained=false`. No process was signaled or unrelated module unloaded.

The complete guest evidence was archived before the approved recovery boot.
Recovery passed at `2026-10-25T21:50:50.369581+00:00`:
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`257ab0ae-642c-439b-a725-028c0f9b01e8`, original **73 modules**, **taint 0**,
idle and empty `next_entry`. Only missing original `nfnetlink` and `tls` were
restored by normal `modprobe`. Root free space was 4,295,184,384 bytes.
The final host capture at `21:51:21.966272 UTC` passed placement checks and
confirmed snapshot `before-mutex-kdonly-20261017T140354Z` remained listed.
The recovery default and kernel artifacts were preserved.

## Retained evidence and reproduction

Source raw directory:
`bench/results/10.176.26.71/raw/bench/mmap-functional-scaling-20261026/`.
Guest directory:
`/root/kdlock-evidence/10.176.26.71/bench/mmap-functional-scaling-20261026/`.
Exact commands, bounds, process identities and exits are in `campaign.py`,
`events.jsonl`, and command/request/transport JSON. The controller SHA-256 is
`f37653e624a959387de57dd28cfee08fa1b6deb8d6879cb299f5bfde5b2408df`.
Do not relaunch it or reuse its output paths. The unchanged original `plan.json`
records only whole-phase counters; `scope-final.json` reconciles all 17 payload
cycles and manual recovery without changing the failure.

`guest-evidence.tar.gz` retains 211 regular files, 3,813,329 uncompressed bytes
and 979,206 compressed bytes; SHA-256:
`eedcb8daa07c97292ad9d244546c57f025347cef55f6926508d550788c62864a`.
Archive checks verified paths/member types and six inspected evidence files.
The failed raw client SHA-256 is
`ddf52c3e72b7dbefaf64b5112af79d94bf92988a308eeb8e1886b2995dcf2957`.
The 120-file source inventory SHA-256 is
`13669d69f64107b8379535981e79107ee00dc11dc6b8cac22bda9f4473117a6a`.
Final recovery, scope and command records were also copied with verified hashes
to the guest's `source-handoff/`, separately from the pre-recovery archive.

Reproduce the saved sample arithmetic read-only on 380G10, from the repository:

```sh
python3 bench/results/10.176.26.71/raw/bench/mmap-functional-scaling-20261026/analyze-failed-window.py
```

This reads retained evidence; it executes no workload or unit test. Previous
99-test/two-basic-program tooling evidence and 137-Native/161-KD API evidence
retain their original scope. No provider diagnostic or IRQ-release change ran.
The one-jiffy release tradeoff, unexplained historical provider allocation
failure, reader/latency coverage and full Native equivalence remain open.

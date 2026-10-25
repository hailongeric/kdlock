# Throughput sweep stopped at KD fixed-writer proof

The authorized October 26, 2026 (Asia/Shanghai) `plain-scaling-v1` sweep stopped
before any measured case. **Native passed and drained its fixed proof and all
21 unscored timed controls. KD passed boot/readiness, then failed its fixed
writer-observation proof.** No KD timed control or window observer started.
All **126 measured cases remain unrun**. There was no retry or optimization.
The earlier [qualified small pair](../mmap-worker-screen-20261026/README.md)
remains separate evidence; the Native controls here are not qualified rates.

Execution HEAD: `4b76cadb6b83de122ae7e1a7be5cb94c74729b23`. Lock and mmap
integration remain the audited `e6fc371` bytes. The same installed
`6.1.159-kdmm31` image, configuration, build-3 payload/fixed client and
client-build-2 timed client were reused. No kernel, implementation, workload,
policy or instrumentation changed during execution. Admission was
`qemu-workers-v1`; measurement policy was `mmap-window-v2`. Both candidate
admissions and readiness passed; this stop was not a QEMU-worker rejection.

## Demonstrated failure and its limits

The KD fixed client exited 1 with `FAIL line 281: contention_ok errno=0`.
[`client.c::writer_contention`](../../../../mmap_writer/client.c) requires the
exact ELF-bound writer/adapter/MM call chain, task state `D` before and after,
the expected wait channel in both reads, and unchanged nonempty scheduler
counters. It returned without an accepted `writer_stack` row before all
workers finished. `main` retained joins and teardown evidence before reporting
the missing proof. `paired.py::fixed` therefore rejected the command and the
serial controller stopped; it did not start another workload or reboot.

| Saved KD fixed-client observation | Result |
| --- | ---: |
| Joined workers / completed mmap-unmap cycles | 16 / 80,000 |
| Worker errors | 0 |
| Maps / closes / remaining VMAs | 80,000 / 80,000 / 0 |
| Fault callbacks / context errors / foreign rejects | 0 / 0 / 0 |
| Contended mmap callbacks | 79,420 |
| Raw stack rows / matching call-chain prefixes | 64 / 58 |
| Accepted `writer_stack` rows | 0 |
| Reported check counter | 391,097; the overall test failed |

Raw stack rows omit the task-state, wait-channel and scheduler-counter brackets.
Matching prefixes do not establish a valid proof or identify the rejecting
condition. Short or changing waits are a hypothesis, not a demonstrated cause.
This is a demonstrated **validation failure**, not evidence of a lock
correctness defect, Native equivalence or a performance regression. Do not
weaken the predicates, remove the proof or rescue this attempt with a later run.
The narrow next step is a read-only eligibility review: determine whether this
sleeping-writer observation is necessary for the syscall-throughput claim or
is a separate integration proof. Preserve equivalent backend, functional,
ownership and teardown requirements for Native/KD. Any prospective policy
change needs explicit limits and review; this failed observation remains failed.

Native's preceding fixed proof passed 80,000 cycles (reported check counter
350). Its 21 controls covered exactly 1–8 workers and 12–60 by four, each with
`files=0 mm_refs=0 destroyed=1 release_errors=0`. The complete validation
command returned 0 after about 32 min 22 s. These controls lack qualified host
measurement windows and supply no accepted paired throughput or variability.

## Consumed scope and recovery

| Operation | Actual | Authorized maximum |
| --- | ---: | ---: |
| Boots, including recovery | 3 | 6 |
| Full host captures | 4 | 385 |
| Payload load/run/unload cycles | 23 | 170 |
| Fixed-proof attempts | 2: one pass, one failure | 2 |
| Unscored timed controls | 21 Native, zero KD | 42 |
| Measured sessions | 0 | 126 |
| Window observers / scans | 0 / 0 | 126 / 12,222 |

The source controller and SSH command exited normally with failure. Read-only
inspection confirmed fixed PID 1834 was gone, all 16 workers had joined, no
project process or open project file remained, and the kernel fault scan was
clear. Payload health was `files=0 mm_refs=0 destroyed=1 release_errors=0`
with module reference count zero. Only then was the payload normally unloaded;
the separate cleanup receipt passed without changing the failed test verdict.
No unrelated module was unloaded and no process was signaled.

Recovery passed at `2026-10-25T20:16:57.067015+00:00`:
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`d0d9b420-d956-4bb6-8405-eea7b427baca`, original **73 modules**, **taint 0**,
idle and empty `next_entry`. Only missing original `nfnetlink` and `tls` were
restored by normal `modprobe`. The recovery default was unchanged. The final
host capture at `20:17:27.206539 UTC` passed placement checks and confirmed
snapshot `before-mutex-kdonly-20261017T140354Z` remained listed. Root free space
was 4,328,427,520 bytes. No workload or uncertain command remained.

## Retained evidence

Source-host raw records are at
`bench/results/10.176.26.71/raw/bench/mmap-worker-scaling-20261026/`; guest
receipts are at `/root/kdlock-evidence/10.176.26.71/bench/mmap-worker-scaling-20261026/`.
The exact serial commands and bounds are retained in `campaign.py`, command
JSON and `events.jsonl`. Its reviewed SHA-256 is
`aeeb6b2b94969e52665f202b6375ba6ff8f5e818b4645e852256996604705d4c`.
Do not relaunch that script or reuse its output directories. The maintained
[runner guide](../../../../mmap_lock/README.md#plain-throughput-plan) describes
fresh execution after separate approval; this failed sweep has no full report.

The original failed controller counters remain in `plan.json`.
`scope-final.json` reconciles the failed KD payload cycle and subsequent manual
recovery, which the stopped driver could not count. `failure-inspect.stdout`
preserves the failed fixed output and read-only drain inspection;
`failed-proof-cleanup.stdout` records normal cleanup separately.

The guest archive is **1,492,396 bytes**, containing 300 regular files and
6,132,853 uncompressed bytes. SHA-256:
`089fea072db26e8bd04ea1aac9eb5e3080d2a19a2a4f3cf4c8c7a0876e21508a`.
Read-only archive checks verified member types, the Native validation receipt
and the failed KD fixed output against retained source-side copies. The latter
SHA-256 is `e346fc40145fd4b69bfb58c38d83a8778d4a6dc7eae4344cc5d9000341094e39`.
The 143-file source inventory is bound by `evidence-manifest.json`, SHA-256
`55cbf9a35f091b0ef163317931e3390d25378acf245ebc9545c103835e63e431`.

The existing IRQ/atomic reader-release tradeoff and unexplained historical
provider allocation failure remain unchanged. Neither was exercised as a new
diagnostic or used to explain this missing writer observation. Optimization
remains deferred until a qualified repeated baseline is available.

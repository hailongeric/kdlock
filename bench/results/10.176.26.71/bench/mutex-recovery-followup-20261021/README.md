# Recovery-kernel regression follow-up, 2026-10-21

Status: preparation; no measurements yet. Overall performance acceptance remains
open, and all seven original causes remain unresolved.

The actual mmap-lock [focused correctness stage](../../tests/mmap-kd-kernel-20261021/README.md)
completed in both experimental modes and was committed as `b8b31a7`. This
follow-up returns the same VM to its preserved recovery kernel under the user's
existing kernel/reboot approval. It keeps QEMU PID 257489, the original CPU/NUMA
placement, host frequency policy and recovery snapshot. A fresh boot is recorded
explicitly; it must not be represented as the original `b65f0205` boot.

The fixed plan contains 84 serial sessions: c08 at 3/4/5 workers, pipebytes at
3/5, pipecap at 5 and RCUHT at 2; three repetitions and the original four arms
(OUTER, public DIRECT, Native, TCLock). The original provider, workload, client,
daemon, translator and collector bytes from `mutex-public-20261020-r2` remain
frozen. The selection preserves original arm rotation, warmups, two-second
measurements, 300 ms peak/settling windows, 10 ms samples, n16, post64 and all
provider settings. No timing instrumentation or candidate optimization is added.
Unsupported TCLock MM bodies are outside this plan.

Before timing, require the exact original recovery kernel/source/config/ELF,
the original runtime-module set, voluntary preemption, original dependencies,
the real snapshot and exact original 67 host threads with their identities and
affinities. An explicit transition receipt binds the new boot; every other
environment check remains exact. Basic and affected tests run first in the VM.
Do not change the old runner's default boot guard or rewrite old receipts.

Retain immediate endpoint checks, all failures, each repetition and execution
class, range/CV, worker/business results, exact source retirement, final idle and
archives. No favorable-class replacement repetitions or parallel tests are
allowed. A strict endpoint mismatch prevents acceptance even if every session
drains. This run alone cannot isolate causes, acquisition latency or background
host interference; these remain explicit limits.

The first read-only host-preflight request timed out in automatic approval
review before execution. Its permitted retry succeeded without host changes.

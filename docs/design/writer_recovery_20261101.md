# Writer promotion exception and reader recovery

This is the dated promotion/ablation decision record. Its numerical exceptions
apply only to the named results. Current limits are in [open work](../TODO.md);
the ordered work below is historical rather than a new execution request.


## Decision and numerical limits

On November 1 the user requested promotion of candidate
`1b6f256b13e8743aa1fd7bdc958cc82ae7726463`, accepting minor Nano losses and the
known 60-process mmap1 loss in exchange for the measured shared-mm gains.
The historical report at `710cfba70c8c0bab4b20784d6fa3c1e4d508c442` retains
its original failed gates; a policy decision never changes those measurements.

For subsequent candidates, define a minor Nano regression as both:

- Each lock/workload geometric mean ratio is at least 0.98 over the entire
  fixed worker grid, separately for whole-window and qualified peak throughput.
- Every matched point has ratio at least 0.90 on each required metric.

All points must complete and qualify, with identical comparison conditions.
Do not omit NO_JIT cases, replace missing values, pool workloads or trade an
individual large loss against a geometric mean. One round gives no variance
estimate. Functional correctness remains mandatory regardless of performance.

The October 31 candidate meets the 2% per-profile mean bound, but its worst
Nano point is -20.496300%, which fails the 10% point bound. It is not a minor
loss. The user explicitly confirmed that the one-time promotion includes this
specific -20.50% point on November 1. It remains outside the minor-loss
definition and is accepted only for this promotion.
The separate known mmap1_processes loss is -22.385920% at 60 workers; it remains
unresolved even if promotion is authorized. The exception is specific to these
recorded results and is not an open-ended relaxation for new large losses.

## Ordered implementation

1. Commit this decision record before changing production code. Prepare an
   explicit merge of the exact candidate, preserving the original report and
   unrelated master work. Record accepted minor Nano regressions, the separate
   large-point exception if authorized, and the known 60-process loss in the
   merge message. Keep the normal kernel default unchanged.
2. Create a new isolated branch from the resulting master. Restore only the
   f7a84065 reader-entry implementation: the ordered returning reader increment
   and the original eight-probe ordinary read function. Remove the outlined
   read suffix. Retain gate-first local writers, prepared phase-first writers,
   exact OSQ retirement, success-before-signal ordering and bounded phase/drain
   polling. This is an ablation, not a proven performance remedy.
3. Investigate the 60-process loss independently. Both arms were about 98.4%
   CPU-occupied over their full process lifetimes. Baseline per-sample min/max
   counts were about 16.7k/291k, whereas the candidate was about 20k/21k. The
   original logs lack individual worker vectors and event attribution. Do not
   infer parking, a specific CPU, or a particular source instruction as cause.
   Inspect placement, binary/configuration identities and counter aggregation;
   use separately labelled diagnostics if additional attribution is necessary.
   Preserve unchanged upstream applications and native MM bodies.
4. Run basic and affected reader/writer, cancellation/rollback, downgrade and
   actual-MM fixtures on the VM. Adapt assertions to the restored reader code
   without weakening concurrency or ordering assertions. No source-host tests.
5. Run one round per point of all ten Nano profiles and mmap1 threads/processes,
   workers 1..8 and 12..60 by four. Use fresh paired inputs and report both the
   promoted candidate and f7a84065 reference explicitly; do not merge historical
   scores with a new boot/topology cohort. Record exact sources, binaries,
   kernel, host/guest placement, policy, completion and drain.
6. Evaluate minor-Nano bounds separately from MM results. The objective includes
   retaining shared-mm gains and recovering the 60-process loss. Do not label
   that issue fixed without measurement. Retain unsuccessful iterations and
   state their limits; no further large-loss exception is implied.

## Operational boundaries

Source/Git/offline analysis run on 380G10. Builds, fixtures and timing run only
on VM 10.176.26.71, after idle, capacity and recovery-snapshot verification.
Use frozen inputs and new output directories. Never force unload or overwrite
prior receipts. Preserve the main checkout's unrelated changes.

## Completed iteration and remaining limits

The exact promotion is merge `e0f9696cf7ba6268bbbfa5131a9ee881f6553809`.
The isolated reader restoration is `66c68c17457c0ae60d09ff1f3d89b5fff16a500c`;
its corrected scope4 kernel/measurement recipe is
`9f9fb90e9de861fddeb498e068c0c31122919337`. The 96-to-160 GiB second-disk
expansion preserved earlier builds and enabled the full scoped-kernel build.

[The completed report](../../bench/results/10.176.26.71/bench/reader-recovery-20261101/README.md)
retains three fresh Nano arms (210 points each) and the promoted/recovery MM
pair (42 points each), one round per point. Basic/affected checks and 218
actual-MM API assertions per kernel passed. Two preparation failures and an
offline import failure are retained separately from the successful continuation.

Reader restoration remains unaccepted. Nano workload means meet the 2% bound,
but point losses exceed 10%. MM geometric means are -0.780% for threads and
-1.192% for processes against the fresh promoted arm; 60 processes loses
11.261%. There is no fresh f7a84065 MM arm: its phase-queue protocol needs an
explicit source-bound correctness fixture before a common comparison. Do not
combine historical MM ratios with this new pair or claim the process gap fixed.

The 60-process observation again separates a skewed worker distribution from
a nearly uniform one, with about 98.5%/98.4% lifetime CPU occupancy. The new
skewed arm is promoted 1b6f256b itself. CPU/call-site and per-worker attribution
is the next step; extra parking or a particular global lock is not established.
Keep any such diagnostics separate from scored execution and preserve unchanged
application binaries and native MM bodies.

Keep the candidate at `codex/archive-reader-recovery-20261101` and the MM recipe
at `codex/archive-reader-scope4-20261101`. Neither is merged into master. The
normal development kernel is restored; QEMU pool settings are restored to
min=0/max=64/aio-max-batch=0, without claiming the old task map was restored.

## Subsequent explicit promotion and fresh master campaign

On November 1, after reviewing the completed losses above, the user explicitly
requested merging `66c68c17457c0ae60d09ff1f3d89b5fff16a500c` into master.
This supersedes the earlier decision to leave that candidate isolated. It does
not change the recorded failed performance gates or establish a performance fix.
The promotion includes the observed Nano point losses and fresh 60-process
MM loss of 11.260800% against the prior promoted provider.

After the merge, freeze the resulting master source and run a new campaign:
all ten Nano workloads; mmap1 threads and processes separately; and the
maintained real-world syscall workloads. Every arm uses exactly one measurement
round at workers 1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60.
Retain every positive/negative result, failed prerequisite and unrun point.
Select fresh comparison arms explicitly; historical scores are context only.
Run basic and directly affected checks before timing, verify idle state and
recovery before synchronization/live work, and preserve exact source, kernel,
configuration and topology identities. Execute real APIs through syscalls with
native bodies unchanged. Restore the normal VM kernel and temporary runtime
settings after archiving. Source/Git/static work stays on 380G10; all builds,
functional checks and timing stay in the designated VM.

### Fresh master comparison baseline

The user selected fresh Linux Native versus merged master KD for every suite.
The measured provider target is `1f10e050b204eb3ee747b5682211343213e3fb16`;
its production lock sources match `66c68c17457c0ae60d09ff1f3d89b5fff16a500c`.
Run exactly one measurement at each of 1, 2, 3, 4, 5, 6, 7, 8, 12, 16,
20, 24, 28, 32, 36, 40, 44, 48, 52, 56 and 60 workers. Retain every
result, including failures and losses, without replacement measurements.

The campaign covers ten Nano workloads (mutex c01/c16 w100, rwsem and
rwlock c01/c16 w1/w20), unchanged mmap1 threads and processes, and the
original-body syscall suite: setfd, pipe FIONREAD and F_GETPIPE_SZ.
These syscall cases use `bench/kernel_api/run.py` and whole-object binding.
Previous copied-body adapter measurements are separate mechanism evidence.

Freeze the provider source, verify the recovery snapshot and fresh host controls,
then run basic and affected functional checks before timing. Record the actual
kernel recipe separately from the measured provider commit; reuse of an existing
compiled kernel requires verified matching generated lock sources and does not
change its original recipe identity. No old score supplies a fresh baseline.
Restore temporary host settings and the ordinary development kernel afterward.

The MM/syscall harness needs the already validated `kdscope4-native` and
`kdscope4-kd` profiles, including exact three-site writer scheduling observations
and shared MM return-site derivation. Carry forward those reviewed harness and
fixture changes from `9f9fb90e9de861fddeb498e068c0c31122919337`. Extend the
original-body syscall controller to the explicit scope4 Native-MM profile,
keeping both syscall backends on one image and all existing identity checks.
These are measurement support changes; production lock sources remain identical
to the merged candidate. The frozen Nano input is not edited during its run.

The fresh Native comparison is complete: 420 Nano, 84 mmap1 and 126 original-body
syscall points, exactly one round each. See the
[complete campaign report](../../bench/results/10.176.26.71/bench/master-native-20261101/README.md).
Mmap1 geometric-mean changes are +3.35% for threads and -0.28% for processes;
at sixty workers they are +9.88% and +0.15%. The report retains the negative
rwlock c16-w1 and FIONREAD means and every individual loss. This Native baseline
does not remeasure the earlier master-relative losses or close that policy gate.
The ordinary kernel and temporary host settings were restored.

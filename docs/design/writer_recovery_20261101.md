# Writer promotion exception and reader recovery

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

## Scope4 receipt-routing correction

The first scope4 preparation from `aeec505307fc01354bc3e660b7a64d0b279b7111`
passed the two writer-observation units and the identity/profile units, then
failed `bench/mmap_writer/test_linux70.py`. Its existing all-profile assertion
found that `sites.checked_receipt` routed the new scope4 variants through the
ordinary-kernel derivation instead of the shared-MM derivation. No kernel
composition, compilation, installation or MM timing had started. The failed
preparation records no remaining child process and remains failed.

Add only `kdscope4-native` and `kdscope4-kd` to that dispatcher's explicit
shared-MM variant set. Preserve exact disassembly/receipt comparison and the
existing all-profile assertion. The lock provider remains byte-identical to
`66c68c17457c0ae60d09ff1f3d89b5fff16a500c`; the completed Nano measurements
retain that identity and are not repeated for this harness correction.

Freeze the corrected recipe in a new directory and use new preparation/build
receipts. Check the affected shared-MM fixture in the VM, then proceed through
kernel preparation, build and the fresh promoted/recovery MM pair. Keep the
original recipe, failed controller records and the stopped queued stages intact.

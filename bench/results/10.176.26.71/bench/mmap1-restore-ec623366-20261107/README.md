# Focused mmap1 checks after the builtin register-restore correction

The isolated candidate remains **unaccepted**. The corrected kernel, provider,
daemon and identity fixture built successfully. All eight applications returned
and drained, but both eight-worker KD points failed their post-application
image-settlement check. Exact retirement subsequently passed for both KD
sessions. No nano run, promotion or full delegated-body acceptance is claimed.

## Exact inputs and scope

| Input | Identity |
| --- | --- |
| Runtime and runner | `ec623366622d1784f7e819b4e9031ba0482bee9b` |
| Runtime branch | `codex/mmap-reached-jit` |
| Kernel component | `9a5d606aee0249d0e566a1c9667375eb038bc9cd` |
| Kernel branch | `codex/scope5-generated-text` |
| Release | `7.0.0-38-kdscope5` |
| Build ID | `357a7115d21941960b90262ac1165bf70d1b398e` |
| Configuration SHA256 | `7dffb540209d34287f7ece75a6b3635b87dd751179fb7953f92aa2eff9b714aa` |
| Native boot | `46cb854b-3ccb-4c13-bfe3-9fbeeefb80a1` |
| KD boot | `ee67813e-e226-4b9e-a5a2-bf65e488c167` |
| will-it-scale | `75f66e45697e6f5f49c33dd950c4e6b289198f8f` |
| Writer entries | mmap `0xffffffff817b6f68`; munmap `0xffffffff8181c73b` |

Both modes used the same kernel and original userspace applications, with
`kd_mmap=off` for Native and `kd_mmap=on` for KD. Each model ran exactly one
application at one worker, then one at eight workers. Each application retained
the upstream six warmup samples and two measured samples (`-s 2`). There was no
long warmup or repeated point. Workers used CPUs `0..N-1`; the collector used
CPU 63. The VM retained 64 vCPUs across two NUMA nodes, one-to-one host pinning,
fixed 2.0 GHz policy and `full (lazy)` preemption. Application workers use node 0;
KD service executors use `service_cpus=0-61`, spanning both nodes, and the
collector is on node 1. This is not an execution-wide same-NUMA comparison.

KD used existing selected-service counters with translation active. Its
eight-worker point inherited images learned at one worker. These are learning
observations, not quiet performance scores. Native and KD instrumentation
differ, and one round supplies no repeat variance. The counts below cover the
whole application including warmup and learning boundaries; rates cover the
final two samples. Do not combine this run with earlier identities or topologies.

## Build and restore evidence

The kernel correction changes only the two register-restore function bodies in
`kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/provider.c`, plus
its design note. Both finish packet reads before changing the stack; the
instruction continuation also restores arithmetic flags before that transition.
The full prior generation was preserved before reusing the source/build tree.

Normal Kbuild dependencies completed, including 6,901 module links and their
BTF generation. The changed provider object and compiled restore sequences were
inspected. The new initrd audit checked 1,188 included modules. The provider,
daemon and identity fixture built against the corrected kernel, and both
directly affected `Sites` tests passed on the VM. Compiler-name and assembly
warnings remain in the records. The earlier 390 restore fixture cases and six
expected negative controls belong to their earlier receipt, not this new run.

This build establishes the intended restore instruction ordering. It does not
establish that the correction caused or eliminated the earlier MM failure.

## Observed rates

Rates are mmap/munmap pairs per nominal second. Percentage differences below
describe printed samples only; the failed points are retained, not accepted.

| Model | Workers | Native | KD printed | Difference | KD point outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| threads | 1 | 293,308 | 190,140.5 | -35.17% | Completed; local-only cold path |
| threads | 8 | 235,855 | 6,353 | -97.31% | Application drained; settlement failed |
| processes | 1 | 373,437 | 220,459 | -40.96% | Completed; local-only cold path |
| processes | 8 | 1,548,596 | 35,514 | -97.71% | Application drained; settlement failed |

All four Native points passed. Both KD controllers exited 1 with
`AssertionError('demand learning did not reach a quiescent boundary')`.
Neither failed KD point is a valid accepted performance score.

## What the delegation counters establish

At one worker, all selected acquisitions ran locally without an image:
1,522,187 calls per entry for threads and 1,764,158 per entry for processes.
There were no submissions at these points.

At eight workers, the following counts were equal for each row:
`selected`, `submitted`, `bound`, `jit_entered`, `handback`, and
`handback_finished`. Both `local` and `returned` were zero.

| Model | Entry | Requests entering dispatch and completing handback |
| --- | --- | ---: |
| threads | mmap | 50,851 |
| threads | munmap | 50,848 |
| processes | mmap | 283,839 |
| processes | munmap | 283,833 |

The counter contract matters: `exe.c` sets `frame.executed` immediately before
calling the generated wrapper, and `kd_service.c` uses it for `jit_entered`.
It does not count source instructions or prove a returned generated body.
`returned` requires the retained run-to-unlock route, released scope ownership
and continuation return. `handback_finished` requires completed validated
original-task handback; that can include read ownership transferred to native
custody. Therefore these counts prove dispatch and completed handback, not a
delegated downgrade/read-tail return, later executor writer acquisition, or
multi-request physical batching. See `kernel_module/exe.c:392`,
`kernel_module/exe.c:470`, `kernel_module/exe.c:559`,
`kernel_module/kd_service.c:734`, `kernel_module/kd_service.c:1167`, and
`kernel_module/kd_service.c:1184` at the runtime commit above.

Per-request service tracing was disabled. Existing generated images and learned
target tables enumerate possible handback sites, but they do not identify the
actual site for every invocation. No precise runtime share or unique handback
cause is inferred from aggregate counters. Separate child images for selected
KD acquisitions remain unimplemented; allocator and other Native locks retain
their existing instruction-service handling.

## Settlement failure and later retirement

The shared 300-second learning deadline begins before preparation in
`bench/mmap1/campaign.py:148`. After each application returns,
`bench/mmap1/run.py:450` requests another execution-session check.
`bench/mmap1/delegated_point.py:74` then requires no translation children, zero
source state/frames, exactly one source writer, settled registry statuses and
one further stable second. The eight-worker applications returned zero and
their workers were gone before this postrun check failed.

Each model produced six successful, serial translations, three per entry:

| Model | Translation durations, seconds | Total child wall time |
| --- | --- | ---: |
| threads | 50.834, 46.221, 50.696, 49.064, 50.717, 49.327 | 296.858 s |
| processes | 50.694, 46.336, 50.850, 46.270, 51.058, 46.238 | 291.446 s |

For threads, the daemon already existed at approximately 63.02 seconds after
boot. The final translation ran from monotonic 329.730 to 379.057 seconds,
crossing the campaign deadline. Preparation, application time and settling are
additional to the child totals. These records support outstanding compilation
as the reason for failing the settled-receipt deadline. The exact deadline and
every polling observation were not saved, so individual intermediate registry
and child states cannot all be reconstructed.

This does not demonstrate a faulty ownership or pending-image contract.
`bench/mmap1/execution_session.py:90` already permits paired published
code/generation during pending demand transitions; ordinary verification treats
a live translator child as `LEARNING_ADVANCED` at line 278. The learning adapter
deliberately waits for a new settled receipt. Its predicate and deadline were
left intact. A longer budget alone would not establish returned delegated
execution or recover the measured throughput loss.

Both sessions subsequently recorded generation-3 NORMAL images for both
entries, zero frames, zero source writers and `service_progress` equal to
`total=0 shown=0`. Fresh finalizers completed exact source retirement with
`{state:2, modules:0, frames:0, writers:0}`, unloaded normally and verified idle.
Their `retirement_passed` and `drained` fields are true; overall `passed` remains
false. Later retirement does not retroactively pass the failed measurement.

The first thread launch stopped during host admission because the QEMU task
set changed across the capture. No guest workload ran in that attempt. Its
records are retained separately. The subsequent before/after host captures
verified recovery snapshot, placement and frequency policy.

## Recovery and retained records

The normal `7.0.0-38-kdlock1` kernel was restored through its unchanged default.
The running schema-2 check passed with Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`56d8ff57-9ef6-49a3-88fd-5e7e9bcb180e`, and final idle state. No further workload
was run after the two bounded KD sessions.

[summary.json](summary.json) retains rates, counters, translation timelines and
hash references. Raw receipts and generated-image records are retained in both
the main 380G10 checkout and this worktree at
`bench/results/10.176.26.71/raw/bench/mmap1-restore-ec623366-20261107/`.
The guest receipt index contains 352 files, 163,846,972 bytes, SHA256
`812ad2e8dfe7f6392854162e8b5c2ec7a8396f0f0fa7af59a125be5b1ccc8070`.
Source-host launchers, admission failures, host captures and recovery receipts
are retained beside it. Complete generated workspaces remain on the VM.

The next implementation decision requires the exact reached site responsible
for handback and a way to avoid repeated whole-root translation while retaining
the image/source lifetime contract. These observations justify that investigation;
they do not justify weakening settlement, extending budgets blindly, or claiming
that mmap1 delegation or performance acceptance is complete.

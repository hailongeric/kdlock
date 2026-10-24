> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Validated whole-VMA munmap body

The narrow functional milestone passed: **15 real VMA removals completed on a
different task**, with exact mm/request/origin/executor/range receipts and
verified mapping removal. All **16 required serial correctness sessions** passed
across the Native control and KD continuation. One earlier live probe failed and
was retained separately, as were three module-build attempts. No admission check
was removed or weakened. Recovery is restored and idle.

This removes one complete, isolated anonymous VMA (virtual memory area) of at
most 16 pages, with absent top-level page-directory entries. The tests use
three-page ranges. Populated/partial operations return to the waiter and make
later calls local. The [implementation guide](../../../../../kernel_integration/mmap_lock/UNMAP.md)
explains caller-side allocation, ownership and supported scope. General mmap,
munmap and page-fault support, performance, p95 and the seven mutex regressions
remain unvalidated or deferred.

## Frozen identities and runs

Kernel source is `670796f4a27a373b09ab73288673e8efdc156fe4`; the passing probe is
`b787a90` (the failed first probe is `50412ff`). The kernel is
`6.1.159-kdmm4`, Build ID `a4f371bb5bca303f6b6d9354bfbf156275479dcb`, captured by
manifest SHA-256 `ccb394c86a5fb79139d6db97900820b90194bd2de555f97a92c24ca6ba9bf410`.
The original 64-vCPU, 24-GiB, two-node MM VM and host CPU placement were retained.

| Run | Boot ID | Result |
| --- | --- | --- |
| `native-1` | `3b41a9e4-df17-4bee-bfb4-bec6b42d7e87` | Four controls passed and drained |
| `kd-1` | `f8af79bc-47b7-4ae0-99c3-e8ad02e718ff` | Six preservation sessions passed; first munmap probe failed |
| `kd-2` | same KD boot | Six remaining sessions passed and drained |
| `recovery-1` | `880aa11b-ab56-4129-b700-06b037473530` | Exact recovery identity, 73 modules and idle state verified |

## Functional evidence

| Check | Result |
| --- | --- |
| Real whole-range munmap | 16 complete VMAs removed, including 15 remote bodies and 15 matching mapping receipts |
| Concurrent readers and late fault | Two local readers coexist; writer drains them; later hardware fault waits and then gets `SEGV_MAPERR` |
| Partial populated unmap | 16 local continuations, 15 exact handback/acknowledgement (ACK) pairs, 262,144 preserved-content byte checks |
| Sticky refusal | 16 later eligible whole-range calls stay local |
| Cancellation | One queued fatal cancellation returns `-EINTR`, retains its mapping and retires normally |
| Read-first refusal | Real zero-page translation forces local unmap, one exact ACK pair; re-read on original CPU faults; one later call stays local |
| Cleanup | 159 explicit local cleanup calls across three cases; all mappings, workers, references and queue slots retire; normal unload |
| Advice preservation | 1,725 remote bodies, 15 ACK pairs, 512 later local calls and cancellation pass |
| Fault-body preservation | 164 remote page installations, 16 physical-page-bound receipts, 15 ACK pairs and 128 later local calls; cancellation and real userfaultfd retry pass |
| Native/KD base checks | Both basic programs; 121/139 API assertions; 81,000 untouched mmap cycles each; 18 fault cases each; 64 completed file faults each |

The main munmap client performed 263,560 assertions. The cancellation and
read-first clients performed 58 and 123 respectively. The remote body is the
original shared in-tree removal path, not a synthetic callback or local
fallback. No JIT execution is claimed. Mmap and fault workloads remain separate.

The original advice and fault bodies are byte-identical, and all 90 installed
files of each earlier `kdmm2` and `kdmm3` image verified unchanged. Earlier
[advice results](../mm-body-20261022/correctness-result.json) and
[fault results](../mm-fault-body-20261022/correctness-result.json) remain distinct.
Remote completion counts here are single functional observations, not timings
or rerun-variance measurements.

## Commands and artifacts

Use the [three guest probe commands](../../../../../tests/kernel/mmap_lock/unmap_body/README.md)
only on an already approved KD boot with the exact source/baseline and verified
recovery snapshot. The source-side coordinators used `stage-tests.py --attempt 1`
for compile/install, `validate.py --mode native --run native-1`, then
`validate.py --mode kd --run kd-1`. After independent failed-probe drain and the
observer correction, `stage-tests.py --attempt 2 --compile-only` and
`continue-tests.py --mode kd --run kd-2` resumed the same boot. Finally,
`validate.py --mode recovery --run recovery-1` and `seal.py` restored and captured
recovery. These retained run names are occupied evidence, not reusable outputs.

Source-host read-only verification:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-unmap-body-20261022/audit.py
```

The [machine-readable result](correctness-result.json) records every run receipt,
source revision, archive hash, retained failure and remaining gap. Raw evidence
is under [the stage directory](../../raw/tests/mm-unmap-body-20261022/); guest
evidence is `/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022`.

The five [archives and inventory](../../raw/tests/mm-unmap-body-20261022/seal-1/guest-archives-1/archives.json)
contain 258,666,237 compressed bytes, 1,791 regular files and 652 source bindings.
Their [read-only audit](../../raw/tests/mm-unmap-body-20261022/audit-1.json) passed
**12,615 checks with zero mismatches**. Archive manifest SHA-256:
`6a4c9d9d16675c8cddb183a7e77528143e916e83c10066dcedef20b5813b3e62`.
The [final health record](../../raw/tests/mm-unmap-body-20261022/seal-1/final-health.json)
binds recovery, prior-image preservation and all passing sessions.

## Remaining gaps

Forced allocation shortage, tree-height growth during preparation, slot
exhaustion, the 256-request boundary, cancellation after admission, advice/unmap
queue interleaving, broad reader/fault races, swap pressure and oversubscribed
progress remain untested. Other unsupported branches are guarded and source
reviewed but were not individually forced. Only the 73 required runtime modules
were validated; all configured modules, RT, lockdep and whole-kernel replacement
remain outside this milestone. No timing or p95 was collected, no variance was
measured and no performance acceptance is declared. The seven mutex regressions
remain unresolved.

The main agent remained the sole MM code writer. Shared-checkout checks found
unrelated cleanup and nano changes, including new nano output files during this
stage; none was edited, staged or interrupted. No helper edited files or ran
concurrent tests.

## Preparation and failure history

Initial checks found the original MM guest idle on recovery boot
`11968a2a-23e4-4474-95b8-a636a9858fbd`, release `6.1.159-kdclobber2`, with the
expected 73 modules, no MM probe workers, approximately 15.3 GiB free on root,
the original host placement and the real
`before-mutex-kdonly-20261017T140354Z` snapshot. The only pre-existing checkout
changes were the unrelated disk-cleanup report and nano campaign files; they
remain untouched. No other run was interrupted or messaged.

Read-only review copied the actual `kdmm3` kernel sources to the source host.
The first collection returned status 2 because this kernel has no
`arch/x86/include/asm/mman.h`; its 20 other source files were retained and
inventoried. The actual x86 `arch_unmap()` definition was found in
`asm/mmu_context.h`, and notifier registration was checked in
`mm/mmu_notifier.c`. This collection issue is not a test failure or a pass.

The separate candidate was `6.1.159-kdmm4`, built separately at
`/root/kdlock-kernel-work/mm-unmap-body-20261022/candidate-1/linux` with a new
captured baseline. Recovery and `kdmm1/2/3` installations remain protected.
The stage uses `bench/results/10.176.26.71/raw/tests/mm-unmap-body-20261022/`
on the source host and `/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022/`
in the guest. No general mmap/munmap or populated-page teardown delegation is
claimed.

Build source `670796f` passed the two basic programs, five advice and five fault
receipt checks, and completed the kernel image. The final single-module target
failed with two competing `serio_raw.o` compilations: modpost found missing
`MODULE_LICENSE()` and an unresolved builtin reschedule symbol. Nothing was
installed or booted. The first build log and object/command files were retained;
the first retry used the module directory with one job, preserving the image
and checking the same 73-module closure. Admission and runtime checks are unchanged.

The directory retry stopped before compilation because the first competing
compilations had also corrupted `.serio_raw.o.cmd` (missing separator). Both
attempts are retained. The third attempt archived and verified that exact generated
output set before regenerating it; sources, image, configuration and the
73-module requirement remained unchanged.

Regenerating the corrupt outputs compiled `serio_raw.o` correctly. The broad
directory target then failed on unrelated Hyper-V module dependencies. That
third attempt remains a failure. The fourth attempt used the exact external
directory `serio_raw.ko` target with one job; no modpost warnings are suppressed
and the required module set is unchanged.

The exact fourth target passed. All 73 required modules and the baseline
manifest (`ccb394c86a5fb79139d6db97900820b90194bd2de555f97a92c24ca6ba9bf410`)
verified. The kernel image remained
`96bb2fb60a1f5b60b971295c5a811bf30f2f346b72bacfc5b199817f2b67a5d3`;
recovery and prior installed boot artifacts were unchanged. At that point, installation and
live checks had not started. Earlier failures are retained as failures.

Probe revision `50412ff` compiled with warnings treated as errors and passed
five receipt checks in `test-preparation-1`. Installation retained the recovery
default and prior kernels. Native run `native-1` completed all four sessions
and returned idle on boot `3b41a9e4-df17-4bee-bfb4-bec6b42d7e87`. The KD run
then began without claiming a munmap functional pass.

`kd-1` passed API, advice/body cancellation and all three fault-body cases before
its first munmap probe failed: the client could no longer open the late-fault
thread's proc stack file. The kernel emitted 15 remote removal records, but the
client did not finish mapping/content/cleanup assertions; this is not a pass.
No later test started. All client and probe workers exited; no device handle
remained, the probe had zero references, ordinary unload succeeded and the
expected 73-module idle state was verified in `failed-live-drain-1` on the same
KD boot `f8af79bc-47b7-4ae0-99c3-e8ad02e718ff`.

The observer previously opened procfs and first touched its output pages after
writer admission closed. Such first-use faults can block the observer itself
behind that writer until the reader controller's deadline releases readers.
The follow-up prepares and exercises the observer, including its output pages,
and warms the late thread's read/signal-jump path before retaining readers.
The real late target access and both exact stack predicates remain mandatory;
no kernel source or admission check changed. The failed frozen probe was kept
separately. `test-preparation-2` compiled the follow-up and passed the same five
receipt checks; `kd-2` resumed only the six unfinished cases on the same boot.
Native controls and the six completed KD cases were not repeated. The exact
initial observer fault PC was not captured; the first-use explanation remains
an inference supported by the setup and successful prepared-observer follow-up.

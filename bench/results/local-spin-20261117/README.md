# Local spin investigation on 380G10

The baseline and candidate each completed a same-boot Native/KD/TCLock campaign:
465 checked points and 65 API checks per campaign, no failed counts or new
kernel warnings, normal daemon exit and normal module unload. Candidate
200c4eff passed correctness checks but is **rejected** as a performance change.
Its 32-worker short-section result regressed, and it did not remove the
five-worker deficit. Main restored the exact baseline core in a5b3c9d8; the
candidate remains reachable at archive/spin-cas-observation-20261117.
The six-entry contention regression fixture remains in main (6cf72d09).

## Migration soft lockup

The migration warning is consistent with prolonged virtual UART hardirq
processing, not an observed KD lock deadlock. The original warning occurred
on CPU 7, the sole effective CPU for IRQ 4 (`ttyS0`), during the failed bulk
serial transfer. No KD module was loaded: `kd_nano` appears only as the last
unloaded module. The interrupted task was `swapper/7` in native idle.

Exact kernel16 disassembly places `handle_softirqs+0x77` immediately after
interrupt enable, before dispatching a softirq callback. The pending mask
`0x282` contains TIMER, SCHED and RCU. This instruction pointer does not identify
a stuck KD acquisition or even a particular running softirq callback.

A bounded follow-up used three paced 16 KiB serial transfers and an isolated
ftrace instance, filtering IRQ 4 on CPU 7. All 24 entry/exit pairs matched,
with no trace loss. Three handlers lasted 1.499233, 1.498256 and 1.495390 seconds;
the trace flags show hardirq context with interrupts disabled. No new soft
lockup occurred. The instance was removed afterward. This directly demonstrates
long UART IRQ occupancy with the migration transport. It does not time every
component of the historical 26-second watchdog gap; host scheduling may also
have contributed.

The old QEMU configuration placed 40 vCPU threads and the emulator on eight
host CPUs. A later 98-second idle observation showed no long scheduling delay,
but cannot rule out delays during the earlier migration. Kernel16 does not
have IRQ_TIME_ACCOUNTING, so `/proc/stat` IRQ ticks were not used as a duration
measurement. The serial controller had been paused during the original bulk
transfer; QEMU and its vCPUs had not been paused.

## Scope and identities

All VM access was through verified local QEMU UNIX sockets on 380G10.
No access to 10.176.26.71 was made. Master and unrelated files were not edited.
The root disk remains `kdlock-kernel16-fresh-20261114/root.qcow2`; the second
remains `kdlock-kernel16-materials-20261115/builds-current.qcow2`, both below
`/home/eric/vm/qemu-disks/`. The existing two-disk recovery snapshot
`kdlock-kernel16-two-disk-smoke-20261116-01` was checked before live work.
Original kernel16 source, image and recovery data remain intact.

| Identity | Baseline | Candidate |
|---|---|---|
| Frozen main source | 4669a0855c625a791731224c8fd13b87711a2a8c | 200c4effb5dce0c0baa7283cb061da1ea8defc50 |
| Kernel release | 7.0.0-38-kdlocalspin1 #2 | 7.0.0-38-kdlocalspin2 #3 |
| Measurement boot UUID | 802af0c8-f336-4ddb-a1d3-3a1ba605b6db | a7859ec4-59ee-479a-a3a2-7f20060a153f |
| bzImage SHA256 | 27fbfc179ada91f4d02b7324bddf2e0bec24de7a8654226471d3707da07083cb | 26b7b2f5d1f74c9648a6403072f653820debd7a1d7e11fb4f73683e38806366a |

Both use GCC 12.3/binutils 2.38, copied existing tools executed only inside
the local guest task chroot. Guest system compiler tools were not replaced.
The exact config SHA256 is
`056d1931df7a760e0bdb62a087f59868f632748c04ad7f087c11ca314aaceca0`.
KD is built in; old REBUILD, KASAN and XEN_PV are disabled. MM/API replacement
is runtime off. Task stacks are 16 KiB; preemption is full (lazy). Spin batch
limit is 4096 in this clean rewrite, with adaptive entry/exit depth 5/2.
This is a separately built clean-rewrite kernel, not an assertion that the
old kernel16 binary implements the same code.

The VM has 40 vCPUs, two nodes of 20 CPUs/32 GiB, each vCPU pinned to the
corresponding host CPU. Emulator and test controller use CPUs 38–39.
Workers up to 16 use CPUs starting at zero; 32 workers use balanced CPUs
4–35. The packed 0–31 control is separate. CPU frequency observations are
in host-test-preflight.json; no frequency settings were changed.

## Measurement

Each standard cell has three backend-order rotations, a 250 ms warmup and
1,000 ms measurement per backend. Values below are median million operations
per second. Outside work is 64, writes are 100%, and lines are 1 or 16.
Every worker must progress; operation/write sums and shared-data deltas must
match exactly. Native/KD/TCLock share one boot **within each table**; the two
tables use different boots and cannot establish a controlled single-boot
before/after effect. All ranges, daemon-off, post=0 and packed-NUMA controls
remain in the summary CSV files and raw points. No profile was collected.

### Retained baseline

| Lines | Workers | Native | KD | TCLock | KD / Native |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 9.449 | 9.451 | 9.450 | +0.02% |
| 1 | 2 | 6.387 | 6.566 | 6.139 | +2.80% |
| 1 | 3 | 4.315 | 4.224 | 2.532 | -2.10% |
| 1 | 5 | 4.435 | 4.337 | 3.166 | -2.20% |
| 1 | 8 | 4.456 | 4.402 | 5.103 | -1.23% |
| 1 | 16 | 4.519 | 4.448 | 5.559 | -1.56% |
| 1 | 32 | 3.564 | 3.406 | 5.479 | -4.44% |
| 16 | 1 | 8.958 | 9.077 | 8.896 | +1.33% |
| 16 | 2 | 2.555 | 2.436 | 2.459 | -4.66% |
| 16 | 3 | 2.230 | 2.149 | 2.013 | -3.65% |
| 16 | 5 | 2.344 | 2.335 | 2.380 | -0.39% |
| 16 | 8 | 2.365 | 2.376 | 3.053 | +0.43% |
| 16 | 16 | 2.319 | 2.331 | 3.090 | +0.50% |
| 16 | 32 | 1.871 | 1.816 | 3.090 | -2.90% |

### Rejected candidate

| Lines | Workers | Native | KD | TCLock | KD / Native |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 9.449 | 9.450 | 9.450 | +0.02% |
| 1 | 2 | 6.439 | 6.502 | 6.111 | +0.97% |
| 1 | 3 | 4.162 | 4.274 | 2.508 | +2.70% |
| 1 | 5 | 4.512 | 4.387 | 3.179 | -2.78% |
| 1 | 8 | 4.531 | 4.510 | 5.153 | -0.46% |
| 1 | 16 | 4.529 | 4.542 | 5.601 | +0.27% |
| 1 | 32 | 3.729 | 3.284 | 5.469 | -11.93% |
| 16 | 1 | 8.958 | 9.074 | 8.899 | +1.29% |
| 16 | 2 | 2.505 | 2.622 | 2.577 | +4.69% |
| 16 | 3 | 2.258 | 2.217 | 2.025 | -1.79% |
| 16 | 5 | 2.387 | 2.375 | 2.396 | -0.51% |
| 16 | 8 | 2.404 | 2.425 | 3.175 | +0.89% |
| 16 | 16 | 2.382 | 2.399 | 3.225 | +0.72% |
| 16 | 32 | 1.853 | 1.918 | 3.201 | +3.52% |

The candidate's 32-worker short KD median is 3.284 versus baseline 3.406
(-3.57% across boots); within its own boot KD is 11.93% below Native.
The packed control also remains weaker than Native. Improvements in some
long-section and 8/16-worker cells do not justify retaining this mixed result.
Three repetitions are not a universal performance guarantee. The main report
keeps both versions rather than pooling them or selecting only favorable cells.

See [protocol analysis and flowchart](protocol-analysis.md) for the source
reasoning, failed-CAS candidate, ordinary-waiter batch stops, and limits of
causal attribution. Removing lifetime probes or forcing delegation was not used
as a performance fix.

## Validation and preserved failures

Both campaigns passed 465 points, including 27 local checks, nested/raw/handback
fixtures, daemon-off controls, phase changes and forced-mode checks. The API
check reported 65 checks and zero failures. Normal cleanup restored Y/5/2,
stopped the daemon with rc=0 and unloaded all five comparison modules.
Only the existing NLS module remained. No new BUG, WARNING, Oops or soft lockup
appeared. Nested foreign execution was not demonstrated; its zero count is
not presented as coverage. Handback has separate mechanism evidence.

The additional signed contention module checked plain, IRQ, IRQ-save,
IRQ-save with IRQ already disabled, BH and clobber entries. Each had two
workers completing 30,000 operations, shared count 60,000, observed contention,
zero overlap/state errors, and normal unload. This fixture ran on the candidate
boot; it does not establish performance or arbitrary nested delegation.

The first candidate start wrapper failed to parse a newline escape before
running any workload. Its error receipt and original/corrected wrappers are
retained. The retry completed all points. Early build failures from missing
copied basic tools and the old guarded REBUILD field are not counted as passes.
Only the isolated source copy was adjusted for the clean-rewrite patch anchor.
The broad module target was normally stopped and confirmed drained; focused
image and required-module builds succeeded after fixing the task tool set.
The final image was relinked after size helpers became available.

Existing TCLock objtool naked-return/BP warnings remain a limitation, not
clean mitigation coverage. Its spin entry/context switch was inspected.
Bench and TCLock spin `.text` sections are identical across builds (see
matching-bench-text.json). Modules were signed with each build's certificate;
unsigned and signed hashes are preserved. No signing keys are in this report.

The task reused its output/source directories for the candidate. Accordingly,
only the task-created baseline build/source links were renamed with an
`-at-install` suffix and annotated; they no longer masquerade as current
baseline build inputs. Frozen baseline artifacts remain in baseline-artifacts
inside the guest. Rebuilding baseline external modules requires reconstructing
the exact build environment. Original kernel16 links were untouched.

## Evidence and final state

Baseline and candidate raw campaigns are in `baseline/` and `candidate/`.
The host working directory is `/tmp/kdlock-local-spin-20261117`; guest task
files are `/mnt/kdlock-builds2/main-spin-local-4669a085-20261117`.
The candidate archive SHA256 is
`b35fd7cbab608ce5bfb5b3791e56ba1f2e66f172c984bc930b8b37e2836a4465`;
baseline archive SHA256 is
`dee1103785b488415d9598dce10abc306c03a34b95727403cf90a21cd6f5ed4e`.
Both were read from stopped local disks with read-only guestfish and ro,noload.
The retained baseline image is restored and running locally;
final-state.json records the final verified boot and idle/module state.

Final receipt: baseline boot `d96d61a3-3650-4800-9516-e17103acc28e`,
no active jobs or task processes, only NLS loaded, no kernel warnings, Y/5/2
restored. The first receipt save found the build disk not mounted after boot;
its UUID was verified, the existing mountpoint was mounted, and verification
was repeated successfully. No fstab or other configuration was changed.

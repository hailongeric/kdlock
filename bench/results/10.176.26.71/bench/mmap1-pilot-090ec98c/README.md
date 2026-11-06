# Short mmap1 pilot: preliminary image-learning rates

All six applications passed and drained. All six rates are below the preserved
matched Native controls. These are **unscored learning observations**, with
changing images and unmeasured JIT/native execution shares. No worker-attributed
delegation proof, fully delegated read-tail proof or steady JIT score was
collected. The candidate remains unaccepted; no performance gain is claimed.

The pilot's own monotonic timestamps show no overlap between its 12 compiler
jobs (96.082256438 seconds in total) and six application lifetimes
(48.348225668 seconds). This independently checks the actual pilot, rather
than borrowing the earlier campaign's separation result. The application
intervals include warmup. The raw intervals and source hashes are retained in
`path-evidence.json`.

## Results

Units are mmap/munmap pairs per nominal second. Each point ran exactly once,
using the standard six warmup samples and two nominal measured seconds.
Tracing and the identity probe were off; ordinary warmup placement checks
remained active. All rows have `passed=true`, `drained=true`, `scored=false`.
Generations are mmap/munmap.

| Model | Workers | Native | Pilot | Change | Images before → after |
| --- | ---: | ---: | ---: | ---: | --- |
| threads | 1 | 281886.5 | 201283.0 | -28.59% | unavailable → 1/1 |
| threads | 8 | 225144.5 | 49296.5 | -78.10% | 1/1 → 2/2 |
| threads | 32 | 199676.5 | 18189.5 | -90.89% | 2/2 → 3/3 |
| processes | 1 | 354007.5 | 234467.5 | -33.77% | 3/3 → 4/4 |
| processes | 8 | 1692926.0 | 381426.0 | -77.47% | 4/4 → 5/5 |
| processes | 32 | 1793531.0 | 400205.5 | -77.69% | 5/5 → 6/6 |

The first application began with no published image, while translation was
paused throughout its lifetime. Generation 1 was published only after that
application drained. That point is not returned-JIT performance. Later points
had published prefixes but changed histories; generation changes do not count
worker JIT completions or quantify Native continuation. Source/core checks
preserve the existing current-state handback, while its actual worker coverage
is unmeasured here. Do not treat these rates as mature JIT scaling or pool them
across generations into a steady-state aggregate.

The pilot exposes a large loss, especially for shared-MM threads. It does not
isolate the cost among admission, handback, spinning, scheduling or the compiled
body. No runtime-share profile was collected, so causal performance attribution
remains open. All requester counts are within CPUs 0–31; this is not a controlled
cross-NUMA comparison. No Nano/TCLock comparison was run in this phase.

## Source, policy and controls

- Runtime source: `f2d9caf3fca0cd69b38b8b2ea5d18422cbf16e22`.
- Diagnostic runner: `090ec98c9abc1963690ebfef75f1861876038795`, branch
  `codex/mmap-reached-jit`; no merge.
- Active aggregate source-cache budget: 1,048,576 bytes, raised from 262,144.
  The already existing 1 MiB retained/compact constant was not selected by the
  original JIT. The active policy remains 8 KiB lookahead, 4 KiB alignment,
  `direct_call_closure = False`, 32 combined transitions and 33 decode passes.
- Per source lease/read: at most 262,144 bytes, with complete consecutive
  pieces. Image slots remain 4 MiB; the selected pool remains 128 images.
- No new image-retention command or learning-latch protocol was implemented.
- The 36 focused cases passed: 11 selected text/read cases, five generated
  frontier cases, 11 demand/limit cases and nine controller cases. Provider,
  daemon and observer builds passed. The pilot reused matching artifacts and
  unchanged runtime checks by hashes, without another unit suite or build.
  The planner fixture matches the reported byte arithmetic; it is not a live
  reproduction of the earlier generation-49 compilation.
- Two earlier preflight setup failures are retained: an overbroad source-reuse
  guard, then a direct fixture invocation without the maintained import-path
  setup. Neither executed test cases or loaded a module. The corrected third
  preflight passed. Previously reproduced full text-driver failures remain
  historical evidence; the full driver was not rerun for this pilot.

The kernel was `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, boot
`a1259240-a9f9-4b95-95d4-7e636ca42270`. Fresh histories were used, with the
existing explicitly enabled syscall tuple selector and two selected MM roots.
Application bodies and the in-kernel lock API implementation were unchanged by
this candidate.
The unchanged will-it-scale revision was
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`; arguments were
`mmap1_threads` / `mmap1_processes -t N -s 2 -m`.

The preserved [Native controls](../mmap1-scaling-f9fdaa2a/README.md#native-results)
use the same kernel Build ID with `kd_mmap=off`, workload, grid points, sample
definition and placement. The VM has 64 vCPUs, two 32-CPU NUMA nodes and 24 GiB;
requesters use CPUs `0..N-1`, collector 63 and KD executors `0-61`. Host pins and
the configured 2 GHz/performance/turbo-off policy were reverified. Timing is
exploratory, and one observation provides no repeat variance. The Native control
is the Native mode of this matched experimental kernel, not a new stock-kernel
measurement.

Provider SHA-256:
`4c1e891e93818e63a1f580915afe33cd2b97ce8c31edf64e8e11a225bfd867d7`;
daemon SHA-256:
`253243ff1d49cd5422db63d67f37666e22d1247c39b12d5c9e29bf004a375eb9`.
The frozen runner manifest SHA-256 is
`3970ac6b6d618f3897528fce1536164343c35ab6e67a6ab32414ad5fda8578db`;
source-state SHA-256 is
`e42be603c7fe31a0e0cff1cfc04e51ab65238b4c7d9ce7356e881e5e17aa8da6`.

## Prior learning observations and recovery

Before the short pilot, the user ended the long 1 MiB campaign early. It had
33 completed one-worker thread learning applications, all passed and drained,
with rates from 194718.0 to 213922.5. The last was 195366.0 at generations
32/25 before and 33/25 after. Every rate is retained separately in
`prior-learning-f2d9caf3.csv`; none is a quiet score or worker proof. The final
stop-affected application remains a separate failed receipt with `drained=true`
and is excluded from the comparison.

The owned daemon received the ordinary termination/continuation sequence only
after zero frames and no compiler child were observed. No workload received a
signal. The controller and exact finalizer drained and retired that session.
The stop is user-directed, not a new compiler or lock failure; the long run did
not reach the former generation-49 cache boundary.

The short pilot then completed all six diagnostic points and exact retirement:
20 residual bindings reduced to zero through bounded ordinary CPU activity;
retirement returned `state=2, modules=0, frames=0, writers=0`, followed by
ordinary unload and idle. `pilot_data_passed=true`; the strict campaign's
`passed=false` / `campaign_complete=false` remain intentional because no strict
proof/scoring sequence ran. `retirement_passed=true` and `final_idle=true`.

Normal kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored on boot
`c10f42bb-bf47-429b-a46e-0befac4ae769`. Idle and the empty one-shot boot entry
were verified. The VM records remain under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/frontier-090ec98c/kd/`.
`points.csv`, `analysis.json` and `retained-files.json` bind the compact results
and necessary raw receipts. Historical rejected outcomes remain separate.

## Actual paths and critical-section size

The selected lock is `mm->mmap_lock` in both cases. Matched source/ELF establishes
these semantic intervals; the pilot did not trace each worker's release site.

| Selected entry | Protected interval and normal endpoint |
| --- | --- |
| `0xffffffff817b6f68`, `vm_mmap_pgoff+0x118` | After successful killable writer acquisition, `do_mmap()` and its VMA work, through `mmap_write_unlock()` at `mm/util.c:583`. The matched CALL is `0xffffffff817b6ff4` to `kd_mmap_write_unlock_clobber_v1` at `0xffffffff814f4f70`. Userfault completion and population follow release. |
| `0xffffffff8181c73b`, `__vm_munmap+0xbb` | Killable writer admission at `mm/vma.c:3266`, then `do_vmi_munmap()`. The successful userspace syscall passes `unlock=true` at `mm/mmap.c:1078`: `vms_complete_munmap_vmas()` downgrades at `mm/vma.c:1321`, performs the read-protected teardown, then `mmap_read_unlock()` at line 1347. `__mt_destroy()` and userfault completion follow release. Error/other acquisition cases have the outer write release at line 3271. |

The matched downgrade CALL is `0xffffffff81818dd4` to
`kd_mmap_write_downgrade` at `0xffffffff814f4fa0`. Read release routes through
`kd_mmap_read_unlock` at `0xffffffff814f5280`; the ELF contains CALL sites
`0xffffffff81818daa` and `0xffffffff81818e01`. These are static sites, not a
claim that both execute for one request. The outer munmap write-release CALL
is `0xffffffff8181c869`. Holding the downgraded read share remains part of the
protected interval; it is not a fresh unprotected write phase.

Saved runtime frontier tables in the short pilot contain:

- mmap CALL targets: `0xffffffff817f7c10` (`do_mmap`),
  `0xffffffff814f49a0` (`kd_mmap_assert_held_write`),
  `0xffffffff8155b7f0` (`__module_get`).
- mmap IJ history: `0xffffffff814f4a38` → `0xffffffffc0e322f0` and
  `0xffffffffc0e3232c` → `0xffffffff814f4a38`. The module-instance addresses
  are retained exactly; they are not reused as another session's history.
- munmap CALL targets: `0xffffffff8181a5e0` (`do_vmi_munmap`),
  `0xffffffff826bb820` (`mas_find`), `0xffffffff826b5840` (`mas_walk`),
  `0xffffffff8181a3c0` (`do_vmi_align_munmap`),
  `0xffffffff81817f90` (`vms_gather_munmap_vmas`); no IJ addition.

These values came from reached miss reports, rather than a list of every
statically decoded branch. They include provider bookkeeping as well as MM
work. They are not visit counts, complete instruction traces, or proof that a
particular worker produced each edge. Within a reached callee the decoder still
follows alternative basic blocks. Decoding an alternative does not show that
it executed; current records do not establish branch-only construction.

| Separate coverage snapshot | mmap decoded source bytes / instructions | munmap decoded source bytes / instructions | Fetched caches, mmap / munmap |
| --- | ---: | ---: | ---: |
| Cold generation 1 | 152 / 43 | 165 / 39 | 16384 / 8192 |
| Short pilot, generation 6 each | 1100 / 295 | 2676 / 687 | 57344 / 49152 |
| Earlier long run, generations 34 / 25 | 21637 / 5398 | 16971 / 4342 | 212992 / 163840 |

These are unique original-source instruction bytes selected by decoding,
including alternatives; they exclude generated wrapper/control expansion.
They are neither the dynamic executed path nor the complete Native critical
section, which can continue beyond the translated prefix. The last long-run
generation was publication evidence, not a returned-body proof for the last
completed application. None of these figures is a dynamic upper/lower bound
when loops and untranslated callees are present.

The active 1 MiB limit is per-translation cache headroom, not measured code
executed per lock hold. Fetched windows include lookahead. The separate
128-by-4-MiB image pool is slot capacity; the pilot used 12 slots with 116 free.
No dynamic instruction counter, lock-acquire-to-release timing, or
critical-section runtime ratio was measured: `jit_timing=0`, `service_trace=N`
and the identity probe was off. Whole mmap/munmap throughput and application
wall time cannot supply those metrics.

### Selection scope and remaining gap

`kd_provider_capture()` selects the two configured entries and the native-64
syscall tuple. mmap requires anonymous private 128 MiB, read/write protection,
zero requested address/offset and fd -1. munmap requires aligned nonzero address
and length 128 MiB; its mapping type/pair cannot be inferred from those
arguments. Another task issuing the same tuple at the same entry is eligible.
There is no mmap1 task/PID allowlist in this provider capture path.

Factory activation controls new object bindings. Existing bound objects retain
their provider when registration is deactivated. The ordinary task-name matcher
in `kd_service_capture_internal()` is conditional on `!bound`, so MM bound
capture bypasses it. Registry `pid=0` is a shared image key, and `tgid` records
the initial registrar, not a per-request worker predicate. The pilot's initial
registrar TGID 4195 matches its first application; its sampled worker is TID
4196. This does not attribute later miss reports to sampled workers.

The existing exclusion mechanism is correct for one object protocol: an
unselected entry/tuple calls ordinary local KD writer admission before capture,
including the same killable/interruptible variant. It does not switch a bound
KD object to an independent Native lock. A future general requester selector
could reuse the existing task matcher before capture while retaining that
local-KD branch; it would narrow task scope, not prove branch coverage. No such
scope change or new execution backend was introduced for this analysis, and no
additional VM test was run.

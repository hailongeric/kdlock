# Kernel9 cacheline1/post256 comparison, 2026-11-12

All six functional lanes passed and all 54 timed sessions completed with exact
body/mix checks and ordinary retirement/unload. In this instrumented,
exploratory configuration KD trails Native and TCLock. The six one-worker KD
sessions are retained as **NO_JIT**; the twelve contended KD sessions record
completed protected generated bodies. These results establish neither strict
timing qualification nor a new mmap/system-call result.

## Workload fidelity

The measured body is **cacheline1/post256**, selected by the earlier named
`mutex-throughput` and `rwsem-throughput-mixed` profiles. The old
`bench/nano/best_case.py` chooses `--workloads cacheline --cachelines 1` for
those profiles. The copied `body.h` and `post_work.h` match their old bytes.
The new Makefile defines `RB_LINES=1` and `RB_POST_WORK_ROUNDS=256`, without
`RB_NANO`. A writer increments one u64 in a 64-byte-padded slot; a reader loads
that same counter twice and checks stability. The other fifteen snapshot slots
remain zero. Every operation then runs 256 dependent integer multiply/add
rounds outside the lock.

This is different from the separate `RB_NANO` body, which requires
`RB_LINES=2`, updates both sequence and copy in one 64-byte record, and reads
both fields for equality. Earlier session wording saying simply "the original
nano body" was too broad. No equivalence to that pair or an original upstream
benchmark is claimed. [workload-fidelity.json](workload-fidelity.json) binds the
exact reference files; their bytes are in `review/workload-reference/` inside
the archive. All three backends in this comparison use the same selected
generic body; lock shells and instrumentation differ.

Mutex is 100% writes. Rwsem is 20% writes and 80% reads, using deterministic
worker phase `(worker * 17) % 100` and the same evenly spaced selection loop.
Readers execute locally with real concurrent read credits; only writers can
delegate. Each pinned userspace worker invokes one bulk ioctl containing the
loop. This is mechanism/performance evidence for a synthetic body, not a
real-world API substitute.

## Results and denominators

Median of three repeats, million completed operations/second. Each backend cell
shows **whole run / warmed peak**. KD completion share divides exact completed
protected JIT episodes by completed writer operations, then takes the median
of the three per-session shares. It is not physical batch length.

| Family | Workers | Native | KD | TCLock | KD completed writer share |
| --- | ---: | ---: | ---: | ---: | ---: |
| mutex | 1 | 1.916848 / 1.928514 | 0.167590 / 0.169265 | 1.919012 / 1.930237 | NO_JIT |
| mutex | 8 | 2.971355 / 3.002939 | 0.177904 / 0.181759 | 2.612884 / 2.631643 | 94.09% |
| mutex | 36 | 2.475463 / 2.529268 | 0.122551 / 0.145341 | 2.578336 / 2.601356 | 94.10% |
| rwsem | 1 | 1.913919 / 1.925115 | 0.187967 / 0.189440 | 1.916743 / 1.928516 | NO_JIT |
| rwsem | 8 | 1.972910 / 1.989951 | 0.299234 / 0.304728 | 4.584421 / 4.613959 | 57.09% |
| rwsem | 36 | 1.377945 / 1.419295 | 0.127077 / 0.136235 | 4.703954 / 4.739305 | 85.13% |

[sessions.csv](sessions.csv) preserves all 54 rows; [summary.json](summary.json)
also retains group ranges. The aggregate is 193,164,288 completed operations:
110,701,753 writes and 82,462,535 reads. KD records 2,050,200 completed protected
JIT episodes. The enclosing unprotected C-function epilogues remain native.
The runner's `NATIVE` generated-engine label for TCLock does not mean TCLock
performed no delegation: it uses its native borrowed-stack engine. Its mutex
cumulative counters are retained; rwsem delegation counts and physical batch
length distributions were not measured.

Workers use guest CPUs `0..N-1` for N=1,8,36; the collector uses CPU 63.
Each timed interval requests 2,000 ms. Progress publishes every 256 operations
and is sampled every 10 ms. Whole throughput divides completed operations by
actual monotonic elapsed time from before configuration/start through all
worker joins, including task setup, tail work and collection. It does not
divide by a nominal two seconds. The warmed peak uses the highest eligible
full-cohort observed window of at least 300 ms after a 300 ms settle measured
from the last active worker start. Each worker must progress. The denominator
spans actual sample brackets; no interpolated counts are introduced.

Every load first runs 32 local operations. KD then publishes an image and
trains with eight workers, up to four 256-operation waves per worker; the
recorded loads needed the first wave. Before timing, all six backend/family
functional lanes passed at 1,8,36 workers with 256 operations per worker.
Each timing load repeats its warm/functional stages before three repeats of
1,8,36 workers. This differs from the old runner's 48,000-operation warmup.
Compilation/publication is outside the timed phases. Claim-only checks after
each phase found no new facts and made no image change. Family order was mutex
then rwsem; backend order Native, KD, TCLock. Order was not randomized.

## Implementation and overhead evidence

The architectural rebuild predates this run. A task has one canonical S_W and
register backing. Its preallocated request/frame records separately retain
source grants, physical owner duties, pending returns, images and final users.
An active MCS request points directly to S_W; the measurement map is only a
diagnostic association. Entry captures the exact source continuation and moves
wait/control execution to that task's auxiliary stack before publishing source
access. A local selection resumes native source. A proxy uses the existing
UB-derived JIT/GS lowering, stopping before each typed source lock/unlock.
Nested operations reuse the recursive request driver; misses hand back the
current state without replay. Logical unlock, physical release and final
retirement remain distinct. Image publication uses quiesced RCU replacement
with exact active source/execution/exit users and the immutable-text contract.

Kernel9's `6e486ece` change is much smaller: after enqueue has published the
exact possible writer-cohort batch, await permits a predecessor to have
initialized it already. The pointer/identity checks remain; prepublication
acquire still rejects a preinitialized batch. The affected general rwsem
regression passed, but did not force the earlier queue interleaving.

The one-worker mutex KD median is 0.167590 Mops/s versus Native 1.916848;
rwsem is 0.187967 versus 1.913919. Their warmed peaks are similarly low and all
six KD runs are NO_JIT. Thus generated body execution and cold setup cannot
alone explain the gap. Source inspection identifies these costs:

- `kernel/episode.c:258` scans all configured frame slots on collection. This
  adapter configures 256. Native progress calls it on lock and unlock, the
  episode loop calls it again, and native unlock collects again after pumping.
- `kernel/mutex_api.c:141` validates the exact task/binding and progresses owner
  duties. `kernel/episode.c:470` reserves a persistent slot and establishes
  separate exact users, even when the body ultimately runs locally. Entry
  switches to the auxiliary stack; the local driver forwards to native source.
- `kernel/image.c:69` uses RCU plus a shared image-slot spinlock to link each
  exact image use. Extend/drop operations also take that guard. Request-pool
  and release-owner guards serialize their respective bookkeeping. JIT entry
  scans entry-site metadata; typed exits validate source sites and current
  ownership. Source/version byte validation belongs to image construction,
  outside the timed loop.
- `workload_modules/nano/evidence.inc:43` receives core observations, looks up
  the original worker, and takes its per-origin `raw_spin_lock_irqsave` guard.
  It matches acquisition/image/unlock/completion/retirement records. Until the
  first completion witness it copies the 160-byte FRAME_PREPARE event; in a
  one-worker NO_JIT run that condition remains true for every preparation.
  Native and TCLock do not pay this KD recorder cost.
- Task storage, source admission and compiled-image construction allocate
  outside the ordinary lock/unlock loop. No allocator call was found on that
  measured ordinary loop. The whole-run denominator still includes task setup.

These are concrete source costs, not an attribution of measured time. No
controlled ablation was run, and neither tracing nor environmental noise is
established as the cause of the entire gap. A small one-worker comparison of
recording modes, keeping actual ownership/lifetime duties intact and requiring
ordinary drain, would distinguish recording cost before any broader rerun.
Frame-capacity sensitivity would be a separate change with separate evidence.

The adapter configures KD `proxy_limit=16`. For ordinary mutex batches it caps
successful proxy grants across combine calls and excludes the head's own local
grant (`kernel/mutex.c:888`); it does not count completed generated bodies. The
rwsem writer-cohort path also stops after that many selected proxy requests,
or earlier on closure/cancellation/queue conditions (`kernel/mutex.c:785`).
TCLock `komb_batch_size=1024` instead tests a continuation counter in writer
unlock. It starts at zero on the first borrowed body and increments on a jump
to the next waiter; missing successor/lookahead also ends the chain. The
mutex counter records `counter_val + 1` on return. Both controls bound
combining, but their counts are not equivalent 16-body versus 1024-body limits.
Configured limits establish no observed physical batch length or causal share
of the throughput difference. TCLock NUMA selection is enabled.

## Identity and limits

Kernel `7.0.0-38-kdrebuild9`, Build ID
`8198ffae09db584dce9b71d92b5743a4146ba80a`, boot
`ff9d44b5-bcfc-4ec0-ad0c-2e8798bc8f0c`; core `6e486ece`, checkout HEAD
`f87e706e` plus the frozen adapter files. The 215-file source manifest and
2,160,225 source bytes are authoritative, rather than HEAD alone. The source
tar SHA256 is `0e01fc454b82acff11272a67dce786248d2dc98db95da1fa73a12f217171f5d6`.
The 72 new files adapt the binding/runner and retain the earlier TCLock port;
no kernel core source changed for nano. Current compiled source matches the
frozen build input. Later README/report changes are documentation only.

The host has 64 pinned vCPUs, two NUMA groups (0..31 and 32..63), two bound
12-GB RAM regions, fixed 2-GHz min/max policy, performance governor and turbo
disabled. These are configuration checks, not exact effective-frequency proof.
Host/QEMU identity, all 64 vCPU task identities/pins, NUMA and frequency policy
matched before/after. QEMU auxiliary tasks on CPU 63 increased from three to
four under the recorded exploratory policy. [host-comparison.json](host-comparison.json)
therefore explicitly retains `strict_timing_qualified=false`. No old kernel,
topology, source or instrumentation measurements are pooled with these runs.

Eight modules built and were signed: two TCLock providers and six workload
variants. All six workload builds had no compiler warnings; the retained
TCLock warnings remain in the build logs. Both emitted mutex/rwsem context
audits passed. Recovery snapshots, headroom and idle checks preceded live work.
The final supervisor recorded normal drain/unload, no new kernel faults,
no workload/source devices and only the NLS module remaining; taint stayed
4096. The normal kernel remains the persistent boot default. This evidence
does not broaden the admitted API/context/stack/capacity assumptions.

## Retained archive

[receipts.tar.gz](receipts.tar.gz) contains 2092 files with 53027505
uncompressed bytes; SHA256 `7904119b4fb5ef8a940062994cf7d34d495eba614cb237be3eec91d9e0fe8058`. [files.json](files.json) records every
member's length/digest and [archive-check.json](archive-check.json) records the
read-only member verification, including nested source/runtime/module archives.
It includes helper source/arguments, host/recovery receipts, frozen inputs,
build logs, signed and unsigned module objects, all functional/timing rows and
progress samples, exact KD completion witnesses, generated artifacts and
shutdown archival/settlement records.

The original local preparation attempt is retained under
`earlier-local-preparation/`: it stopped on a documentation-hash assertion
before VM staging, build or module work. Its partial source tar is not a build
input. Later source review is under `review/`, separate from runtime evidence.
Functional and timing nested archive SHA256 values are respectively
`df256d9d0dac80e5e7161c65020c3d36b6c7b897f3f515673951d0506274d3f8` and
`0f8c8c56df216e0a8c8dd85a2c997c75583288c2742fe6102ad37a9af36e6aa6`.
The 77-file module archive SHA256 is
`ccc8cc048c87cd7ae0802ccccd925bd4692bbb87fc0238fbaeb6da229bc89a3e`.

The [earlier kernel9 rwsem regression](../../../../../tests/evidence/kernel9-cohort-validation-20261112/README.md)
and the historical kernel8 failure retain separate receipts and verdicts.

[Source review](source-review.json) matches all 54 summary rows to the raw
receipts and confirms unchanged compiled inputs. The full Git whitespace check
reports retained formatting in exact TCLock inputs/review patches and a trailing
blank line in the frozen compiler adapter; it is not recorded as a clean check.

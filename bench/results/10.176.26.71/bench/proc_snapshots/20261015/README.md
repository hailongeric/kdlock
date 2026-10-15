# Proc snapshot comparison, 2026-10-15

KD **completely delegated the argument-boundary snapshot**, returning
93,229,983 complete bodies in the timed comparison. With the tested spin ABI1,
the exact task-name helper was **refused**: `strscpy_pad()` saves uncaptured R13.
Its timing comparison therefore uses an explicit KD native control. All 90
timed samples passed data, worker-progress and final-drain checks.

These are extracted critical sections under one module-owned exclusive spinlock,
matching the ordinary locking semantics of `mm->arg_lock` and
`task->alloc_lock`. They do not include task/MM lookup, procfs enumeration,
remote page access, mmap locking or userspace `ps`. One shared record deliberately
concentrates contention; independent processes and task structures need not share
that lock. The [source investigation](../../../../../../docs/BENCHMARK_WORKLOADS.md#process-inspection-and-mmap-candidates)
explains the real kernel paths and their separate locks.

## Argument-boundary snapshot

The protected body loads four 64-bit words. Every caller validates its returned
tuple after unlocking. Performance uses read-only snapshots and the unchanged
KD adaptive policy: ratio limit 2, NUMA enabled, prefetch mode 2, batch cap 1,024.

Each rate cell below is **median whole-run / highest warmed peak**, in Mops/s,
from three valid rounds of one execution-status group.

| Workers | Native | TCLock | KD | Complete KD delegation |
| ---: | ---: | ---: | ---: | --- |
| 1 | 102.990 / 103.792 | 75.520 / 76.268 | 72.615 / 75.564 | None |
| 8 | 6.697 / 7.709 | 5.609 / 5.712 | 7.319 / 7.724 | 94.30–97.56% |
| 16 | 7.643 / 7.886 | 6.350 / 6.588 | 9.010 / 10.578 | 83.31–96.38% |
| 32 | 6.418 / 6.736 | 6.041 / 6.195 | 4.983 / 5.045 | None |
| 60 | 4.102 / 4.729 | 5.157 / 5.331 | Separate rounds below | Mixed status |

At eight workers, KD's median is 1.093× Native and 1.305× TCLock; at 16 it is
1.179× Native and 1.419× TCLock. KD meets both the median and best-peak criteria
at those two counts. It misses both comparators at one and 32 workers. Increasing
the worker count does not guarantee that the adaptive policy delegates: all
three 32-worker rounds stayed native.

The 60-worker KD samples are intentionally **not pooled** into a three-round
JIT or native result. The runner marks that comparison point incomplete by its
execution-status grouping rule, while retaining all valid measurements.

| KD round at 60 workers | Whole-run Mops/s | Best peak Mops/s | Complete delegated bodies / reads |
| --- | ---: | ---: | --- |
| 0, JIT observed | 3.029 | 3.278 | 33,886 / 6,089,728 (0.5564%) |
| 1, NO_JIT | 3.229 | 3.553 | 0 / 6,492,416 |
| 2, NO_JIT | 3.244 | 3.425 | 0 / 6,523,392 |

The mixed 20%-mutation functional cases at eight, 32 and 60 workers had correct
tuples and exact mutation counts on all three backends; their KD samples stayed
native. Those fixed-count checks alone did not establish delegation. The timed
read-only runs above supply that evidence.

## Exact task-name helper

The body calls the guest's `strscpy_pad()` on a 16-byte name and a 64-byte local
destination. Validation checks every byte, including padding. Mutation checks
alternate three- and 15-character names. No substitute copy loop is used.

The initial image published as NORMAL but contained an unlearned helper call.
At 16 workers, a fully drained learning wave recorded **one entry witness and
zero complete bodies**. After learning the helper, the translator reported:

```text
CONTEXT_NATIVE_ONLY
minimal entry unavailable at 0xffffffff816e3d18:
memory store depends on an uncaptured GPR
```

The [captured disassembly](strscpy-pad-disassembly.txt) resolves that address to
`strscpy_pad+0x8`, `push %r13`, at `lib/string_helpers.c:832`. Spin ABI1 captures
IP/SP/BP and relies on compiler spills for live values; this helper prologue
still saves an incoming register not available to its minimal-entry analysis.
The check rejects the image. This is a concrete ABI/helper-support limitation,
not evidence that copying a task name is inherently impossible to delegate.
An audited register/stack contract or a separately specified copy implementation
would be further work. No capture or admission check was bypassed here.

For a reviewable performance comparison, the following KD column uses
`--delegate off`. It is **KD native execution**, not a delegated task-name score
or a measurement of every possible native-only fallback path. Native and TCLock
execute the same exact copy payload with their ordinary spin APIs.

| Workers | Native whole / peak | TCLock whole / peak | KD native-control whole / peak |
| ---: | ---: | ---: | ---: |
| 1 | 27.041 / 27.503 | 25.548 / 26.162 | 26.538 / 26.752 |
| 8 | 6.562 / 7.592 | 5.778 / 5.833 | 5.777 / 5.863 |
| 16 | 7.313 / 7.807 | 5.540 / 5.910 | 5.341 / 5.549 |
| 32 | 6.501 / 7.196 | 5.134 / 5.355 | 4.978 / 5.047 |
| 60 | 3.963 / 4.628 | 4.919 / 5.046 | 3.182 / 3.532 |

The 20%-mutation controls also passed on all three backends at 32 and 60 workers.
The refused default-KD learning wave validated its returned data and drained;
that correctness result does not turn its partial witness into complete JIT.
TCLock's delegation share is unmeasured in both comparisons.

## Measurement, variation and evidence

Runs used physical host `10.176.26.71` and its regular 64-vCPU recovery VM,
with two 32-core NUMA nodes. Workers use CPU prefixes; collector CPU 63 is
separate. All 64 host CPU pins were checked. The kernel Build ID is
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with `nokaslr`, `nopvspin`, native
qspinlock dispatch and voluntary preemption. Snapshot
`rwsem-snapshots-current-20261015` was saved and verified after the existing
owned-origin series finished. No kernel change was made.

Each timed case has three two-second rounds, reversing backend order in the
middle round, and a matched 48,000-operation-per-worker warmup. Peak uses the
highest valid 300 ms window after 300 ms settling, with progress from every
worker. All backends perform four rounds of register-only post-work. KD's private
entry and completion counters add KD-only overhead; no throughput correction is
applied. Complete counts require a pristine wrapper reaching its matching outer
unlock, rather than merely executing the entry marker.

All valid variation is retained. One-worker Native whole-run spread is 81.77%
for argument boundaries and 80.16% for names; the first rounds were much slower.
At eight workers, argument-boundary Native spread is 24.54%, so its narrow best-
peak difference from KD is not evidence of a robust peak advantage. At 16,
KD argument-boundary whole-run spread is 14.17%. Three rounds describe this
captured run; they do not establish universal gains or acquisition latency.

- [Results and provenance](results.json): source/ELF verification, environments,
  host pins, grouped summaries, refusal and final idle state.
- [All timed samples](samples.csv): throughput and actual complete-body counts.
- [Grouped statistics](groups.csv): whole-run and peak min/median/max/spread,
  best valid warmed peak, and valid-round counts. Mixed-status groups stay separate.
- [Rwsem validation](../../../tests/rwsem-snapshots-20261015/README.md): sleeping
  API and 21 Native/KD functional sessions, including actual ABI2/ABI4 writers.

Guest raw roots are `/root/kdlock-evidence/10.176.26.71/bench/proc-argbounds-20261015`,
`.../bench/proc-taskname-native-20261015`, and
`.../tests/rwsem-snapshots-20261015`. The corresponding host archives are under
`bench/results/10.176.26.71/raw/{bench,tests}/`. `results.json` records archive
hashes. Both timing blocks' frozen sources and all ELF hashes were verified
after download, along with every saved admitted image. Their only source
differences are the helper-readiness fix and its test; the payload/provider
sources match. [Final idle receipt](final-idle.json) confirms no project modules.

All failed candidates remain archived: the initial Native-hook import rejection,
an incorrect pinned-entry import expectation, the strict mixed-case NO_JIT
failure, and the early task-name learning attempt that stopped before any helper
executed. Learning now requires a complete body and saves each admitted image
before replacement. Its regression is among the **16 passing focused harness
tests**. The two basic C checks and the three-backend existing rwlock functional
regression also passed. W=1 builds passed; their logs retain locale fallbacks and
objtool warnings in existing stack-switch/restore assembly. No full suite or
end-to-end container/`ps` benchmark ran.

Reproduction commands and profile definitions are in the
[runner guide](../../../../../rwlock_compare/README.md). Use separate output
directories for default-KD acceptance probes and delegation-disabled controls.
The ordinary sleeping rwsem is implemented separately; killable mmap integration
and arbitrary task/MM execution-context support remain outside this change.

# KD rwsem c01, 20% writes: reader-admission scaling

KD ordinary readers now make at most eight short acquisition attempts, then
queue longer optimistic admission through an abortable OSQ. Only its head polls
the shared reader count and phase; queued callers poll their own preallocated
nodes. Every reader still acquires and executes on its own task. Only writers
are eligible for delegation.

## Diagnosis and change

The baseline is `5c2903ad`, including the newly selected KD 1024/1024 mutex
policy. It reproduces the within-node decline: KD c01/20%-write/post256 falls
from 4.225 Mops/s at sixteen workers to 3.174 at thirty-two. All six of those
observations have zero writer JIT execution, so writer delegation length does
not explain that decline.

The old read slowpath lets every waiting reader repeatedly attempt admission:
read the phase, increment the exact reader count, recheck the phase, and roll
back if a writer raced admission. This distributes shared-count RMW traffic
across contending CPUs. TCLock queues contended readers through its AQS gate.
The earlier [diagnostic profile](../rwsem-optimization-20261018/diagnosis.md)
also exposed reader rollback traffic, but belongs to a different kernel/source.
No new rollback counter profile was collected here. The current controlled
change and timing support admission contention as a bottleneck; they do not
assign exclusive CPU costs to individual instructions.

The selected change retains exact reader and writer counts. OSQ uses the
existing preallocated mutex CPU/slot pool with independent links and explicit
retirement. Its slot is released before enabling preemption, running a read
body or entering the original sleeping fallback. No reader work is executed by
another task. Trylocks, interruptible/killable calls, downgrade, writer
reservations and unlock ACKs keep their existing paths. The emitted object
remains 320 bytes, with the new queue at offset 280; see [layout.txt](layout.txt).

## Matched performance evidence

All three sources ran on `7.0.0-38-kdlock1`, boot
`15dc5977-59d3-4471-a196-d71f03f450ed`, with fixed 2.0 GHz host policy,
workers on CPU prefixes 0..N-1 and collector CPU63. Each source has three
two-second repetitions at 8/16/32/60 workers for both KD and fresh TCLock:
72 timed sessions total. The payload is one padded counter, 20% writes, 80%
local reads, and 256 dependent arithmetic rounds outside the lock. All sessions
passed exact data/progress and drain checks. This is exploratory timing;
strict host timing qualification is not established and no significance claim
is made. Sources and JIT execution classes are not pooled.

| Workers | Baseline KD Mops/s | Selected KD Mops/s | Baseline TCLock | Selected TCLock |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 4.225 | 5.028 | 5.390 | 5.523 |
| 32 | 3.174 | 5.062 | 5.955 | 5.982 |
| 60 | 1.875 | 3.139 | 4.658 | 4.596 |

Each entry above is a median of three rounds. At 16 and 32, both KD sources
are local `NO_JIT`; improvements are approximately 19.0% and 59.5%. At 60,
baseline KD has returned writer JIT while selected KD has none. The 67.4%
whole-implementation difference therefore is not a matched-JIT-class or isolated
delegation comparison. The selected 16–32 rates are nearly flat, but crossing
NUMA nodes still reduces throughput and KD still trails TCLock.

Eight workers retain a regression and mixed execution classes:

| Source | KD class | Rounds | Class median Mops/s |
| --- | --- | ---: | ---: |
| Baseline | NO_JIT | 2 | 5.531 |
| Baseline | Returned writer JIT | 1 | 5.695 |
| Selected | NO_JIT | 1 | 4.934 |
| Selected | Returned writer JIT | 2 | 5.274 |

The initial queued-only candidate measured KD 4.385/4.529/4.472/3.085 Mops/s at
8/16/32/60, all local. It improved the larger points but lost too much at eight.
The eight-attempt fast stage improved those measured candidate rates. The
queued-only production code remains at Git branch
`archive/rwsem-queued-readers-20261028` (`02ab926f`), and its full frozen run is
retained alongside baseline and selected runs. [summary.csv](summary.csv)
retains every class median, range and sample count. No universal rwsem gain,
TCLock parity or actual-MM improvement is claimed.

## Correctness and preserved failure

- Basic C checks and the production read-admission/OSQ unit fixtures passed.
  They cover early retry and head-poll bounds, rescheduling, slot exhaustion,
  queue cancellation, exact retirement before return/sleep, and negative mutations.
- The final live rwsem probe passed eight API, ten cancellation, one downgrade
  and three publication checks, sleeping concurrent readers/writers on CPU0,
  exact counts and final idle. It executes local outer returns, not JIT.
- Read-only and ordinary-local writer controls passed at 1/8/32/60 workers,
  with 100,000 operations per worker, exact data and zero JIT entries.
- All four live basic families completed 1,600,000 operations each, with matching
  returned JIT counts: spin 1,597,669; mutex 1,588,637; rwlock 23,415;
  rwsem writers 1,576,950. All drained normally.

The first semantic-probe attempt failed before running the probe: provider
loading could not allocate 7,592 bytes of per-CPU data. Its load failure and
kernel warning are preserved. Subsequent probes passed after normal load/unload
of the existing `tc_allocator_guard` from the baseline's frozen build, the same
preparation used before benchmark sessions. No allocator metadata or admission
guard was patched, no module was forced out, and no kernel was rebuilt/rebooted.
The actual recovery snapshot `linux70-kdlock1-clean-20261027` was verified.

Final validation uses the selected implementation with a polling comment
clarified and the updated unit fixture; timed source identities remain frozen.
[evidence.json](evidence.json) binds separate source hashes, archive manifests,
host captures and final basic receipts. Complete archives are retained under
[raw/bench](../../raw/bench/rwsem-c01-w20-20261028/) and
[raw/tests](../../raw/tests/rwsem-read-admission-20261028/). The source-host offline
check verified every archive's size/SHA256 and all four final basic receipt hashes.

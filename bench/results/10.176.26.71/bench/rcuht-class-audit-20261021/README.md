# Two-worker RCUHT retained-evidence audit, 2026-10-21

Status: read-only source/ELF/evidence review completed; cause unresolved.
No new test, build, remote action or timing ran. New p95 measurements are
deferred and missing p95 does not block throughput investigation or acceptance.
Existing latency evidence and all failed environment endpoints remain fixed.

## Execution classes remain separate

Numbers below are measured entry witnesses, not measured returned-body counts.

| Separate cohort | OUTER r0 / r1 / r2 | DIRECT r0 / r1 / r2 |
| --- | ---: | ---: |
| Original `mutex-public-20261020-r2` | 3 / 2 / 2 | 2 / 1 / 3 |
| Latency `inputs-4`, `run-2`, plain | 3 / **0** / 5 | 5 / **0** / 3 |
| Same latency run, instrumented disabled | 2 / 1 / 2 | 14 / 13 / 3 |
| Same latency run, instrumented sampled | 6 / 2 / 2 | 5 / 19 / 1 |
| Recovery follow-up `run-1` | 2 / 4 / 1 | 5 / 1 / 2 |

Only the latency plain cohorts have `WITNESSED_JIT / NO_JIT / WITNESSED_JIT`.
Instrumented modes and separate collections cannot replace their missing
same-class repetition. Sampling disabled still uses a different caller binary
from plain; the instrumented execution-mix change does not establish a fix.

| Plain NO_JIT repetition 1 | OUTER | DIRECT |
| --- | ---: | ---: |
| Measured operations | 11,094,272 | 10,406,912 |
| Measured entry delta | 0 | 0 |
| Lifetime slowpath count | 20,078 | 9,867 |
| Lifetime combiner / handoff / JIT-success / resume | all zero | all zero |
| Lifetime origin acquisitions = releases | 750,233 | 532,557 |

Both retain unchanged NORMAL ABI2 publication across measurement, final hot
locks on both worker CPUs and exact successful retirement. Frozen
`mutex/waiter.inc` increments slowpath on delegation-queue entry, but invokes
the combiner only when the queue head finds a successor after physical
acquisition. These sessions show queue activity without a combiner invocation,
not a reproduced instruction-admission refusal. The counters include preparation
and warmup, so they cannot establish measured queue shares or explain why a
successor was absent. Final heat does not reconstruct runtime heat.

The provider's optional completion probe defaults to false and the retained
synthetic load command omits `bench_complete_probe`. Lifetime JIT-success/resume
agreement corroborates execution but cannot substitute for a measured
returned-body delta. NORMAL publication alone remains insufficient.

## Source and emitted paths

The payload protects preallocated hash nodes with one global mutex. Its body
performs source/destination lookup, miss/existing-destination branches, and
value update or unlink/relink. Key generation and post-work are outside the
body; allocation and RCU synchronization are absent from this critical section.

Independent inert ELF parsing compared normalized body bytes and canonical
relocation targets. Original and instrumented bodies match within each arm:

| Arm | `mc_body_0` size | Normalized SHA-256 |
| --- | ---: | --- |
| OUTER | 506 | `e84ed8eeb02282aa4d3ddba9da5eaff39ba6f912289998d90b3cc237933b14b3` |
| DIRECT | 387 | `06c5aa799a54273bd12598f7ae923700f341ecbeb8fafe7a9f7359b82211c009` |

Both retain saved callee registers and argument spill offsets: statistics at
`-0x40`, keys at `-0x38/-0x30`, buckets at `-0x34/-0x2c`. OUTER has bounded
inline owner probes and cookie-dependent local/provider unlock; DIRECT calls
the provider for every acquisition and release. Register allocation and branch
layout also differ, so this does not isolate acquisition overhead. Unchanged
body bytes do not make the surrounding instrumented runner equivalent to plain.

## Artifact identities

Original ELF members are
`mutex-public-20261020-r2/{baseline,current}/rcuht/variants/kdlock/mutex_cacheline.ko`
in the retained [baseline](../../raw/bench/mutex-public-20261020-r2/baseline.tar.gz)
and [current](../../raw/bench/mutex-public-20261020-r2/current.tar.gz) archives.
Original workload hashes are OUTER
`4207705f4791481e5201d5fbec8578cd91a8b9d38be8a81b4c5f49051ef2ee85`, DIRECT
`3c13e2d3d594c0b8fd4f4f6066a4466e408311663f61f69cb573518b2eee8bfb`.

The [instrumented input archive](../../raw/bench/mutex-latency-20261021/inputs.tar.gz)
hash is `3f2cd75766a0cfc926e4113ec8b78675c61f4fb239b329f145ab954c9ca997b4`.
Under `mutex-latency-20261021/inputs-4/`, members are
`bundles/{baseline,current}/rcuht/variants/kdlock/mutex_cacheline.ko`; disassembly
is retained as `assembly-{baseline,current}-rcuht-kdlock.txt`.
Instrumented workload hashes are OUTER
`338a4e5569558c058fd0266ca06de04fbb454b4fd3bec06f1e285fc76195ecbb`, DIRECT
`bd81e6c005e0971ee5df282586648645803ce3bc7e4b85c180f64de2d77f88e8`.

The [measurement archive](../../raw/bench/mutex-latency-20261021/measured.tar.gz)
hash is `c99b2d8bf67c11bc2a297073fe33cc8bd645db4820bc214d78c4c15f9bbfd08f`.
Session prefix:
`mutex-latency-20261021/run-2/measurements/<mode>/<baseline|current>/rcuht/rcuht-t02-r<repeat>-<baseline-kd|public-kd>-<mode>/`.

| Plain r1 file | OUTER SHA-256 | DIRECT SHA-256 |
| --- | --- | --- |
| `session.json` | `4e8a45a4c2b42f88113573917020e0c56decd50d106731fda17d43ab75680a0b` | `d0bdfefa648d762276e374d82dbd872e3db540ea139109369d523759b18d76d9` |
| `kernel.log` | `c64b8e7f47b6667a74fcf00cc8dfa55c11cffb69cc74a130272386e27ec356db` | `cae012b4e2a3084676ca44f714df98366bf21789c3ffbbdfe4061764138ff1f8` |

The independent reviewer touched no files and executed no archived code.
Existing sampled operation-p95 medians, 1.268 us OUTER / 1.361 us DIRECT, retain
their instrumented scope and failed host endpoint; they are not new acceptance
criteria or interchangeable with acquisition latency.

## Smallest next discriminator

A separately identified bounded two-worker control can read the existing frozen
provider counters at joined boundaries before/after the original warmup and
measurement, using [route_snapshot.py](../../../../mutex_api_compare/route_snapshot.py).
Keep publication, heat, physical ownership and exact retirement evidence. This
separates measured queue entries from combiner opportunities without changing
the provider, admission or payload. Added boundary reads are diagnostic overhead
and cannot by themselves establish the throughput cause. Do not launch a broad
matrix or replace an execution class because this audit found a path difference.

All seven causes remain open: c08/3, c08/4, c08/5, pipebytes/3, pipebytes/5,
pipecap/5 and RCUHT/2. Throughput claims still require correct matched work,
compatible execution classes, unchanged environment gates and reported variance.

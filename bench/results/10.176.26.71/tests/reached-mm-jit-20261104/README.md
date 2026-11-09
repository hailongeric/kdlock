# Reached JIT: focused VM evidence, November4 2026

The selected delegated path now compiles reached instructions to x86-64 and
executes generated code on E. The reference interpreter is not selected by the
MM dispatcher. This is the first JIT candidate for this execution-driven path;
previous interpreter results are historical intermediate evidence.

- Branch: `codex/mmap-reached-jit`; baseline
  `1ece229c36d44336acba7b32054b1bbd4e1275e8`.
- Tested provider: `383e830f4c7ac01f8edf9cec05d6c5b91aee8d8f`.
- Kernel component: `1ab7124abb6140752c1f0bb6e862144d426a3875`;
  BuildID `5f2fce72a33480f6e79a79b374b21a0db377ecd1`;
  `7.0.0-38-kdscope5`, `preempt=lazy`, `kd_mmap=on`.
-64vCPUs,24GiB, two NUMA nodes; workers0/1, collector63,
  executor pool0–61. Physical CPU pins,2GHz frequency and actual recovery
  snapshot were verified before live checks.
- Public lock API and Native MM bodies are unchanged. The general runtime
  selects JIT in reached mode; ordinary image mode is separate.

## What executes

The initial compiler unit is **one reached source instruction**, with a cache
of generated functions. Arithmetic, address calculations, conditionals, source
stack/register updates, PAUSE and fences execute as generated Native
instructions. Qualified memory/atomic helpers preserve the existing access
width and RMW operation; declared task-context services retain the existing
bounded O-service/E-resume protocol. This is not a full-register Native basic
block compiler yet. Source SP/BP and source GPRs stay in the canonical packet.

The VM has zero optional near-text blocks. The candidate uses an existing
ordinary preallocated code block and supports near/far helper and return
transfers. No body interpreter or whole-body origin path substitutes for a
missing code allocation or lowering. Encountered unsupported work remains an
explicit failed candidate point.

## Focused results

52756 checks of85 instruction forms, Native effects, read/write failures and
near/far code placement passed. Eight proof-parser checks passed. The W=1
provider/fixture build and all11 live kernel phases passed, with normal drain
and unload. They cover successful killable acquisition, three queued
cancellation positions, selected reader-drain cancellation, nested origin
cancellation preserving the parent, delegated downgrade/read tail and fresh
writer drainage, depth9 nesting, early outer completion,128 child reuses and
nested true controls.

Fourteen successful roots contain generated entry/retirement witnesses,
matching origin/request/generation and a different executor task;448132
instructions retired across those roots and zero interpreted steps were
observed. Selected reader-drain cancellation runs no body. The long spin
fixture changes that instruction total with timing; it is not a throughput or
delegation-length score. See [summary](focused-summary.json) and
[complete focused reply](focused-reply.json).

## Retained intermediate failures

| Source | Observation | Status |
| --- | --- | --- |
| `e4980225` | Standalone fixture omitted kernel `-fno-strict-aliasing`; warning stopped build | No execution/build pass |
| `de58ea6c` |26378 generated checks passed; synthetic multi-root record lacked a required JIT witness | Proof-parser failure retained |
| `2deb9012` |26378 generated checks and eight parser checks passed; W=1 build passed; zero near blocks caused initialization refusal | No live phase passed |
| `383e830f` | Near/far fixture, parser and all11 live phases passed | Focused correctness only |

The corresponding JSON replies remain alongside this record. No failed attempt
is assigned a performance score.

## Application validation and performance

Unchanged will-it-scale `mmap1_threads` and `mmap1_processes` run through their
ordinary syscalls. The selected workload maps/unmaps128MiB without touching
its data; this is not a demand-page-fault throughput claim. Each model uses
two workers and one round. Full-trace checks and untraced timing are separate
experiments; positive and negative results remain separate by source, boot,
topology and instrumentation setting.

Both models passed their full-trace application checks, normal source/frame/
provider retirement and unload, with no lost kernel records or execution fault.
The [application summary](mmap1-proof-summary.json) binds the original complete
proof files by path/hash; those159MB of JSON remain on the VM and in the local
collection rather than being duplicated here. The resident kernel trace is
359189981bytes, retained on the VM.

| Model | Audited returned JIT roots | Delegated read tails | Later same-E writer records | Interpreted steps |
| --- | ---: | ---: | ---: | ---: |
| threads |1076 |538 |531 |0 |
| processes |2128 |1064 |1001 |0 |

All audited roots have matching generated entry/retirement witnesses. JIT
retired5399764 and11475700 instructions respectively across those audited
roots. Sixteen sampled mmap/munmap syscall pairs per model passed the existing
joined checks. These traces do **not** account for all application invocations,
measure physical delegation batch length, prove every final userspace return,
or independently force a fresh reader-drain race. The dedicated live fixture
provides the fresh-reader-drain race evidence separately. These limitations are
retained in the proof rather than inferred away.

The following [untraced timings](timing-summary.json) use plain-kernel boot
`ab2bb986-b894-480b-8a5d-a88b9ca97368`, the same component/BuildID and topology,
two workers and exactly one round per point. Each value is the sum of the two
post-warmup upstream samples divided by the nominal2seconds; actual interval
duration is not independently measured. Every point observes positive JIT
entry/retirement deltas, zero interpreted steps and normal final retirement.
Runner `74a93c37` records these observations separately from provider source.

| Model | Earlier interpreter `0997fd7d` pairs/s | JIT `383e830f` pairs/s | Change |
| --- | ---: | ---: | ---: |
| threads |161.5 |82.0 |−49.23% |
| processes |274.5 |173.5 |−36.79% |

The interpreter values are historical single-round results on the same plain
kernel image/topology, boot `0be9cfa1-bb77-486b-8888-835a2ad6471d`. They are
not a simultaneous run or a statistical estimate. Both JIT regressions remain
recorded. **Performance acceptance fails.** The candidate stays isolated; JIT
execution remains selected rather than switching back to interpretation.
A separate unscored profile is used to locate the regression before choosing
the next compiler/cache optimization.

 No mmap1 gain,
Nano result, general lock replacement approval or master promotion follows
from the focused fixtures alone. The untraced point runner additionally records
positive generated entry/retirement deltas and zero interpreted steps.

The separate unscored profile completed its guest checks and normal retirement.
Its original post-run physical capture failed because the QEMU task set changed
during that capture. The failed receipt is retained; a fresh read-only capture
subsequently verified pins/frequency/snapshot. The original launch is not
relabeled as a full host-admission pass, and its80.5pairs/s is not scored.
[Resolved sampled addresses](profile/resolved-profile.json) bind the exact
measured provider SHA256
`609bb7e8c12add5fd530c2cbbc0e09c2445a93cf71c5a1a784c269f2f802c9dc`.
The profile locates generated-code publication synchronization and repeated
emitter work, alongside origin polling. The next isolated cache optimization
is described in the maintained reached-path design; no gain is inferred yet.

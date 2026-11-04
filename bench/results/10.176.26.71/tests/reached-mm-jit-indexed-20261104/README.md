# Indexed reached JIT, November4 2026

Branch `codex/mmap-reached-jit`; tested provider
`626bd9fb78d1b2876534dce77df8aa213cfabbb9`. The prior JIT provider
`383e830f4c7ac01f8edf9cec05d6c5b91aee8d8f` and historical interpreter
`0997fd7d550aafde9446d419b3b77e5fd90321cf` remain separate evidence.
[Previous JIT record](../reached-mm-jit-20261104/README.md).

## Change and method

The general reached JIT now retains up to512 generated instruction functions
per CPU in an eight-way indexed cache; lookup examines at most eight entries.
The2048-byte lowering unit is unchanged. Up to16 ordinary code blocks are
reserved at module initialization from the existing pool; on this VM that is
64MiB of already preallocated code storage, leaving48 ordinary blocks while
reached mode is selected. No code allocation occurs during an instruction.
Ordinary image mode keeps its existing pool behavior.

Fresh source bytes must match before reuse. Rewriting only replaces inactive
functions, after their previous generated invocation returned. The public lock
API, ownership/cancellation/nesting protocol, source/frame lifetimes and
Native MM bodies are unchanged. The dispatcher selects generated execution,
with zero interpreted steps required. The first compiler unit remains one
source instruction; this is not a full-register Native basic-block compiler.

Kernel component `1ab7124abb6140752c1f0bb6e862144d426a3875`, BuildID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, release
`7.0.0-38-kdscope5`, `preempt=lazy`, `kd_mmap=on`.
64vCPUs/24GiB; two NUMA nodes; workers0/1, collector63, service pool0–61;
verified physical pins,2GHz and actual recovery snapshot. Builds, tests and
timing run only in the VM.

## Focused results

52756 generated-code differential checks of85 instruction forms and near/far
placement, eight proof-parser checks, W=1 provider/fixture build and all11
killable/nesting/downgrade live phases pass. Exact root/owner/source/frame
retirement and normal unload pass. The existing tests remain enabled.
[Complete reply](focused-reply.json).

## Untraced performance

Exactly one two-worker round per model, boot
`ab2bb986-b894-480b-8a5d-a88b9ca97368`, tracing/profiling off. Reported throughput
is map/unmap pairs divided by the nominal2-second post-warmup interval; actual
interval length is not independently measured. Positive generated-code entry/
retirement deltas, zero interpreted steps, final idle state and normal
retirement pass at both points. Cache counts cover the observed application
lifetime including warmup and possible background activity; they are not exact
request-ownership records or timed-interval-only counts.

| Model | First JIT `383e830f` pairs/s | Indexed JIT `626bd9fb` pairs/s | Observed change | Cache hit rate |
| --- | ---: | ---: | ---: | ---: |
| threads |82.0 |88.0 |+7.32% |34.41% |
| processes |173.5 |187.0 |+7.78% |36.54% |

The two JIT candidates use the same boot/image/topology and instrumentation;
they are separate one-round points, not pooled or statistically qualified.
Compared with the historical interpreter on the same plain image/topology but
boot `0be9cfa1-bb77-486b-8888-835a2ad6471d`, the losses remain45.51% and31.88%
(161.5/274.5pairs/s reference). Full [timing summary](timing-summary.json) and
positive/negative receipts are retained. **Performance acceptance fails.**
No promotion to master and no Nano no-regression claim follow from these runs.
Nano was not run in this focused MM phase.

The larger cache removes some repeated compilation but still misses on about
two-thirds of lookups. The first JIT profile also shows origin polling and
source/context service costs. The next compiler direction is reached
straight-line blocks and less repeated canonical-packet traffic, preserving
explicit service boundaries and fresh source/owner checks. This is a proposed
next iteration, not implemented or measured here; returning to interpretation
is not the selected execution mode.

## Actual mmap1 proof

The final full-trace application checks run unchanged mmap1 threads/processes
through ordinary syscalls, one round per model, separately from the scores.
Both models passed and retired normally on diagnostic boot
`7bc570a9-f357-4dce-a165-49e6a7ffa7b5`. No kernel execution fault or lost
resident records was observed. The [proof summary](mmap1-proof-summary.json)
binds each full proof by exact path/hash; raw proofs and traces remain on the
VM and in `/tmp/kdlock-mm-indexed-jit-proof-artifacts` on the source host.

| Model | Audited returned JIT roots | Delegated read tails | Later same-E writers | Retired JIT instructions | Interpreted steps |
| --- | ---: | ---: | ---: | ---: | ---: |
| threads | 989 | 495 | 480 | 6233315 |0 |
| processes | 2213 | 1106 | 1049 | 11932419 |0 |

Every audited root has a matching generated-code witness on a different task.
Sixteen sampled mmap/munmap pairs per model pass the joined syscall checks.
All source, owner, frame, provider bindings and modules retire through their
normal paths. Reads acquired ordinarily still run locally; the deliberate
general exception is a delegated writer's downgraded read tail on E.

The diagnostic does not account for every application invocation, independently
force a fresh reader-drain race, measure physical delegation batch length,
inspect all VMA contents or prove every final userspace return. The dedicated
kernel fixture supplies fresh-reader-drain evidence separately. No broader
API-equivalence or whole-kernel replacement claim is inferred from these
focused paths. Final performance acceptance remains open because the measured
losses against the earlier interpreter persist, and Nano was not run.


## Final state

The VM is idle on its ordinary `7.0.0-38-kdlock1` kernel, BuildID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`0a2b2a34-caf7-4c63-9b38-d4f29a5a2d7d`. Root/build2 free space is
3889049600/9383280640bytes. Only the two previously authorized current standard
logs were cleared after complete experiment records were retained; no benchmark
or historical record was removed. Source/static checks pass; master remains
`20fde062729703208ac54445f51fc0f21f24e0e8`, with unrelated work preserved.

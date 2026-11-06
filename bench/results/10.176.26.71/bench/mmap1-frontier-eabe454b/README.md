# Reached CLI/STI continuation and short mmap1 observations

Provider commit `eabe454b4ee51ea6962a73525372b4b09679c737` adds only the
capability-20 CLI/STI forms to the existing terminal source frontier. Actual
JIT control flow must reach the instruction before permanent waiter handback;
the instruction itself remains first-unexecuted. Alternative branches keep
executing in JIT. The compatibility guard, original backend, GS handling,
source limits and immutable image lifetimes remain in place.

The focused VM generated-state/alternative-branch, one-byte source extent,
capability negotiation/reset, and write/read/downgrade continuation checks
passed. The matching provider build passed. These checks do not establish
general flags, SIMD or IRQ-context equivalence; existing limits remain.
No full suite or Nano campaign was run.

Both models use unchanged will-it-scale
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`, `-t N -s 2 -m`, six warmup
samples and two measured samples, with one application per listed point.
The VM ran `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, lazy preemption,
64 vCPUs, 24 GiB, workers on CPUs `0..N-1`, collector 63, and fixed host
2 GHz policy. Requester CPUs remain on node 0; the existing executor pool
is CPUs 0–61 and spans both NUMA nodes.

Threads use the provider commit's runner at `[1,8]`. Processes use runner
`f0bf9f505442ba97067055a88a1d8c34fe2782f3`, with only the count check widened
to `[1,2,8]`. All provider/translator bytes are identical to the tested
candidate. The two-process point is a bounded extra learning application.
Compilation and counters are active, so every rate is an unscored learning
observation. Counter totals cover warmup and measurement; rates use the final
two nominal seconds. Different learning histories are not pooled.

The Native rates are preserved controls from runner
`14cc632d8e84010448ee84a6411f8bf8f5220a01`, the same kernel build with
`kd_mmap=off`, boot `fac26aa8-65ee-41c5-b1d9-8aa2be6ac155`; they were not
rerun. Prior candidate is `bee6e2b22c6b08ea7e55cc281ca197aa1c7ee3be`.
Differences below are descriptive single-observation comparisons, not
controlled gains or repeat variance. The processes learning schedule differs.

| Model | Workers | Pairs/s | vs prior candidate | vs preserved Native |
| --- | ---: | ---: | ---: | ---: |
| threads | 1 | 188263.0 | +0.64% | -33.21% |
| threads | 8 | 46445.5 | -7.93% | -79.37% |
| processes | 1 | 220110.5 | -0.45% | -37.82% |
| processes | 2 | 329826.0 | — | — |
| processes | 8 | 389100.0 | -2.14% | -77.02% |

Threads now publish both MM images, whereas prior mmap was NativeOnly.
At eight threads each root submits/enters JIT eight times and hands back eight
times, with zero ordinary delegated returns. Mmap has 371604 local acquisitions;
munmap has 371598. Both roots learn the edge
`0xffffffff814f4a38` → `0xffffffffc0e32bb0`. Unique history edges do not
attribute every handback. Generation 2 is published after the eight-thread
application; that point does not exercise its learned callback dispatch.
The 7.93% thread loss against the prior candidate is retained.

Processes used generation 2 at eight workers after the two-worker learning
point. Each root again submitted/entered JIT eight times, handed back eight
times and returned zero fully delegated requests. Local acquisitions were
3111911 for mmap and 3111908 for munmap. Both roots added the edge
`0xffffffffc0e32bec` → `0xffffffff814f4a38`; their retained generation-2
sources show exit 15 at this return dispatch. This is evidence of progress
past the previously learned callback CALL to its return boundary, not of a
complete MM body. Generation 3 was published afterward and was not run.
No new callback mechanism was added. The 2.14% rate decrease from the prior
process candidate is retained, with the different learning schedule explicit.

All five applications passed and drained. Both finalizers reported
`state=2, modules=0, frames=0, writers=0`, with retirement and final idle
confirmed. Normal `7.0.0-38-kdlock1` was restored and verified at boot
`3b392cf0-2e5b-46b0-86e6-a6695deebcf9`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, with an empty one-shot boot entry.

Process results, exact per-root counts and generations are retained in
`analysis.json`. Actual CLI/STI hits and physical delegation chain lengths
are not measured. A published image or JIT-entry count does not prove a
completed MM body or read tail. Performance acceptance remains open.

Each original campaign result is preserved alongside its separate finalization
record. Exact retirement and normal-kernel restoration are recorded separately;
do not reinterpret a false overall performance verdict as a retirement failure.
Raw files are under `../../raw/bench/mmap1-frontier-eabe454b/`; the tracked
manifest binds their size and SHA256. All original VM run directories remain.

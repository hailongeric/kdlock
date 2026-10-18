# Legacy mutex compatibility backport

This page records the accepted `555b8b7` baseline. The subsequent
[KD-only object change](../design/kd_only_mutex.md) retains its delegation protocol and
replaces Linux physical exclusion. Historical comparisons below keep their scope.

This experiment compares the recovered mutex in `74676c3` with the later
owned/adaptive implementation archived at `a49a87c`, then carries independent
execution and admission changes onto the recovered mutex. The implementation is
on `task/legacy-mutex-compat` in `/tmp/kdlock-mutex-legacy-compat`. The original
recovery and post64 benchmark branches remain available as separate baselines.

The primary worktree's 35 pre-existing edits were preserved. A comparison of
non-comment lexical tokens found the same token sequence as its committed code
in all 35 files; the evidence records their exact hashes. The backport uses
reviewed historical commits, rather than copying that worktree wholesale.

## What differs between the implementations

| Area | Recovered legacy | Later owned implementation | This backport |
| --- | --- | --- | --- |
| Physical lock and native compatibility | Original Linux `struct mutex`; the physical owner takes and releases that mutex; a shadow queue schedules delegation | Private `struct kd_mutex`, owner bits, OSQ and wait list; Linux mutex operations cannot be mixed on the object | Retains the original Linux mutex and shadow queue |
| Waiting and combining | Published producers disable preemption and poll; live successors can join a running batch; existing NUMA cohorts and prefetch | Bounded polling/parking, private grants, origin readiness and owned selection; the rejected adaptive version changes admission too | Retains legacy waiting, queue handoff, NUMA selection, batching and admission |
| Caller interface | ABI0 bridge and ABI2 explicit clobber/outer-cookie interfaces | ABI2 plus ordinary-C ABI4, preserved register inputs and a distinct outer cookie/unlock convention | Retains ABI0/2. ABI4 is possible in principle, but requires a separate legacy caller/continuation implementation and separately matched measurements |
| Processor-state admission | Known context checks, but some unsupported instructions could be copied, omitted, or lowered as NOP | Explicit scalar policy, register and raw-encoding checks, out-of-line context-helper refusal | Backported from `98118e9`; unsafe/unknown processor-state instructions are refused before emission |
| Image upload and lifetime | One mutable code block per registered root | Whole-image staging, versioned upload identity, immutable generations, frame binding and stale-miss rejection | Adapted from `95bca27` to legacy mutex frames and ABI0/2 |
| Origin-CPU GS data | Existing pinned-producer GS rewrite and logical-current handling | Sleeping producers need an explicit audited body and exclusive origin claim | Keeps the legacy pinned policy. Owned readiness/claim machinery is not inserted into the legacy queue |
| Workload coverage | Existing cacheline sizes, RCUHT, and Linux-mutex pipe/file adapters | Later coverage changes adapt these workloads to private owned objects | Retains the legacy workload implementations; the c01 and pipebytes business operations are unchanged |

ABI4, owned-origin claims and private-object workload adapters cannot be copied
as isolated source files: their lock type, packet input contract or producer
lifetime differs. This experiment ports instruction admission and immutable
publication. It does not claim feature parity with every owned-mutex interface.

## Adaptation details

Mutex registration publishes the root identity and source pin before allocating
an executable block. `kd_mutex_prepare()` therefore accepts an UNINIT registered
root with no code block; this remains non-executable until a complete image is
published. Failed registration, invalid ABI, terminal native-only policy and
closed source admission still fail. The first live attempt exposed the old
code-block requirement; it drained cleanly, and its evidence is retained apart
from the corrected measurements. A production registry/preparation test covers
this transition and the refusal cases.

The upload header uses protocol 2 and carries entry ABI, image length, upload ID
and base generation. Every chunk belongs to the same upload and extends contiguous
coverage; only the complete, validated image becomes NORMAL. Partial or failed
uploads return their private blocks. Published descriptors and code blocks remain
allocated until terminal session drain and provider teardown. The existing pool
still has 64 blocks of 640 KiB, shared with spin images. There is no in-session
reclamation of published generations; exhaustion refuses publication.

A mutex frame binds one image descriptor, including across FULL continuations.
Replacement publishes a new descriptor without overwriting older code. A miss
from an old generation cannot replace the current generation's status/target.
The existing publication gate now saves/restores IRQ state, including when used
by process-side upload/status paths. Backend/scope validation precedes binding.
Neither the frame's ownership ledger nor its source lease is replaced by the
image pointer.

Capability version 4 advertises `KD_JIT_CAP_MUTEX_IMAGES` (bit 3). This is distinct
from the owned backend's version-3 bit-2 capability; the legacy provider does not
claim owned-origin readiness semantics. The matching translator requires the
legacy capability before reading text. Provider, daemon and translator must be
updated together. ABI0/2 and the two-word wrapper input remain unchanged. No
origin requirement bits are accepted by this legacy image protocol.

The instruction policy screens decoded instructions, sensitive raw encodings at
selected undecodable instruction boundaries, and context helper symbols. Unknown
mnemonics and unvirtualized hardware state are refused. Direct lowering also
fails closed. It removes INT-to-NOP and warning-only special-instruction omission;
it does not implement general flags repair, SIMD/FPU virtualization, access-time
pointer checks or arbitrary native continuation.

Spin/rwlock generated-code storage retains its existing in-place lifetime.
Those backends use the updated upload transport but do not gain immutable frames
from this mutex-specific backport.

## Validation and measurement scope

Validation runs only in the recorded 64-vCPU guest on `10.176.26.71`. It includes
the provider and strict daemon builds, both basic C programs, instruction/context
and codegen checks, image upload/replacement/exhaustion, registry and source
lifetimes, generic dispatch, frame capacity, wrapper inputs and the legacy
clobber/outer interface. Fixtures are distinct from actual kernel JIT execution.

The performance comparison uses c01 with 64 post-unlock rounds and
`api-pipebytes-query-n16`, workers 1–8 by one and 12–60 by four, three repetitions,
2-second timed phases, 48,000 warmup operations per worker, and the API's additional
1-second warmup. The peak uses the documented warmed 300 ms window. Workers use
the prefix of CPUs 0–59; collector CPU 63 is outside every cohort. The second NUMA
node begins at CPU 32. Host frequency policy remains `ondemand`.

The original captured legacy binaries are measured again. Candidate binaries are
built from the separately frozen backport. Baseline/candidate KD samples are
adjacent, with alternating order; Linux Native and TCLock are measured controls.
The first failed setup is excluded from the corrected matrix. Every accepted
sample must pass business-result, worker-progress, affinity and exact drain checks;
contended synthetic KD samples additionally require returned JIT bodies. The
candidate's live ABI, capability and image generation are checked around timing.

## Measured result

The [504-session report](../../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md) records all 21 worker
counts and three repetitions. At 60 workers, legacy/backport median throughput
is 4.820/4.914 Mops/s for c01/post64 and 5.370/5.375 Mops/s for pipebytes n16.
The original high-count pipebytes throughput is retained with these two feature
groups. This is not uniform parity: pipebytes at 44 workers is 9.47% slower,
and low-count cases show large changes and variation. Source hashes prove 65
protocol/caller/workload/control files unchanged; only the preparation helper
changed in the legacy mutex call adapter. The report retains the exact scope,
all samples, failures, frozen source, validation and replay receipts.

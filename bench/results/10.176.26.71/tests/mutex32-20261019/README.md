# Native-sized KD mutex validation

The compact KD mutex passes the basic and directly affected checks in the recovery
VM on `10.176.26.71`. `struct kd_mutex` is 32 bytes, naturally aligned to 8 bytes,
with the same physical member offsets and containing-structure geometry as the
captured Linux mutex configuration. This preserves KD physical exclusion, the
legacy queue/batching protocol, ABI2, pinned published waiters and immutable
images. It does not authorize mixing Linux and KD callers on one object.

Ordinary calls allocate no auxiliary record. Admitted delegation uses a linked
record indexed by lock address; bucket locks protect lookup and exact reference
acquisition. Separate invocation and owner references cover delayed publication,
early outer release, native ACKs and frame retirement. Final release unlinks and
frees the record without a caller destroy step. Allocation refusal falls back to
local KD physical locking before publication. Active delegation still allocates
256 bytes outside the 32-byte object; no total-memory or performance gain is
claimed.

## Checks

| Check | Result |
| --- | --- |
| Provider `W=1 UBSAN_SANITIZE=n`, daemon `-Wall -Wextra -Werror`, isolated `pip check` | Passed; provider retains assembly/objtool and locale warnings |
| Two basic C programs and 12 selected Python drivers | All passed after the fixture corrections below; full suite not selected |
| Production auxiliary registry fixture | Allocation refusal, exact references, 1,000 same-address reuse cycles, 2,048 live objects, duplicate publication and 8 × 4,000 concurrent get/lookup/put operations passed |
| [Ordinary API](local/result.json) | 160,000 operations, eight workers, 2,048 objects reused twice; native geometry, no auxiliary records, no destroy, sleeping/nested ownership, cancellation and drain passed |
| [Rwsem local probe](rwsem/result.json) | API, cancellation, reader/writer sleep, downgrade and unpublished-waiter checks passed; full drain |
| [c08 functional delegation](jit-c08/functional.json) | 8,000,000 completed operations, 5,312,488 returned JIT bodies, PASS and full drain |
| [Instruction exit](instruction-exit/result.json) | Four phases of 3,200,000 operations; cold JIT execution, one original-task escape with effects/flags preserved, permanent NATIVE_ONLY state, no later JIT entry, full drain |

The selected drivers cover auxiliary state, queue resources and balances,
terminal retirement, outer progress, compiled/JIT outer API, real clobber stack
resume, task cache, frame capacity, provider lifecycle, immutable images and
remote outer execution. Exact selections and final outcomes are in
[validation.json](validation.json); original output is in
[unit-first.log](unit-first.log) and [unit-retry1.log](unit-retry1.log).

The c08 run uses CPUs 0–7 and 32–39, collector 63, 500,000 operations per worker,
48,000 warmup operations, post64, NUMA enabled and mutex batch 1024. Instruction
exit uses the same 16 worker CPUs and 200,000 operations per worker per phase.
These are functional runs, not performance comparisons. Historical throughput
for the 256-byte object remains separate.

## Preserved failures and limits

The first unit batch recorded 11 passes and three failures: a stale resource
extraction assertion, a WARN mock rejected by `-Werror`, and a remote-outer mock
using the old `struct mutex` pointer type. The three corrected fixtures passed
on rerun. No production admission or lifetime checks were relaxed.

The first JIT preparation failed at the workload's obsolete 256-byte assertion,
before loading a workload. The workload now asserts native type geometry and
explicitly retains cacheline alignment for its separate benchmark lock. The
[failure receipt](jit/failure.json) and original build log remain archived.
The subsequent [c01 run](jit-retry/functional.json) completed 800,000 operations
and drained, but recorded **NO_JIT**: a NORMAL image was published without an
admitted delegated body. It is not counted as a JIT pass. Admission settings were
unchanged for the successful c08 run.

All builds and execution ran in the VM; source edits, Git and archive inspection
ran on `380G10`. The captured kernel Build ID is
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, release `6.1.159-kdclobber2`, with
64 vCPUs across two NUMA nodes. The actual recovery snapshot was rechecked in
[snapshot-recheck.json](snapshot-recheck.json). No kernel was changed or rebooted.
The retained ring buffer no longer contained the early PV-spinlock boot line;
this is not new timing-policy evidence. RT, ww_mutex, lockdep and whole-kernel
replacement remain unvalidated.

## Preservation

[Layout DWARF](layout-dwarf.json) corroborates the compiled native/KD member
offsets; the live probe enforces natural alignment with compile-time assertions.
Per-session source and ELF manifests retain distinct frozen build identities.
[Tested-source comparison](tested-source-match.json) records their relation to
the committed production inputs: all 90 production files, including 39 private
`.inc` files, match in all four successful live runs. The benchmark providers'
observation patches are reconstructed and checked separately; there are no
unexplained source differences.

The idle-only archiver preserved all attempts in seven groups, with
`completed: true` and `guest_idle: true` in [archives.json](archives.json).
[The independent archive review](archive-review.json) checks preservation against
the hash-bound inventory retained with the raw archives. Raw archives are under
`bench/results/10.176.26.71/raw/tests/mutex32-20261019/` and in the guest sibling
`/root/kdlock-evidence/10.176.26.71/tests/mutex32-20261019-archives/`.
The final [health receipt](health.json) confirms an idle guest after normal
retirement and unload. Archive preservation is separate from test acceptance.

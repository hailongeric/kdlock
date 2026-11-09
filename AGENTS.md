# Development rules

## Scope and authority

The maintained branch is `main`. Rebuild kdlock incrementally for Linux kernel
7.0 on x86_64 without PREEMPT_RT. Pin the exact source revision, configuration
and supported API/context lanes before implementation validation. No other
kernel target or deployment-specific environment is part of this baseline.

Read the five documents in `docs/design/kdlock_redesign/` in order. Fixed user
directions and native semantics are authoritative. Proposed mechanisms,
historical evidence and open choices are distinct. This branch starts without
implementation or performance claims. Do not silently select the C01-C12
mechanisms or report their acceptance specifications as executed.

Preserve the original UB-derived JIT and GS lowering, one canonical S_W and
single regs backing per original thread, optional unique execution selection,
every source lock/unlock as a pre-operation fragment boundary, serial recursive
delegation, exact no-replay handback and cumulative source-versioned learning.
The AS01 general flags/SIMD assumption and local PUSHFQ/POPFQ exception have the
scope specified by the design; neither is a general equivalence result.

## Working method

1. Read relevant source, instructions and Git status before editing. Preserve
   unrelated changes and review staged paths before each coherent local commit.
   Do not rewrite preserved history or publish changes without authorization.
2. Use English for maintained prose, comments and session messages. Prefer
   neutral, precise names about execution, ownership, concurrency and
   performance. Preserve established technical identifiers and their meaning.
3. Implement one reviewed work package or supported lane at a time. Ask for
   required mechanism decisions before they affect code. Start with simple,
   local ownership and structured lifetime proofs; add machinery only when its
   concrete correctness or progress requirement is established.
4. Preserve exact grant/release authority, native API/context semantics, source
   and code lifetimes, final-access-before-reuse ordering and no-replay source
   effects. Keep one canonical source packet rather than packet-sized copies.
5. Run basic and directly affected checks. Full suites require an explicit
   request. Missing dependencies, skips, compile failures and unrun stages are
   not passes. Keep source/build/configuration and instrumentation identities
   separate; never claim a performance gain without measurements.
6. Real-world API validation must invoke the actual userspace system-call path.
   Kernel experiments may change relevant lock API calls and minimal binding,
   routing or lifetime glue, while preserving native bodies, surrounding
   semantics and data structures. Extracted bodies and test ioctls are only
   mechanism evidence.
7. Keep running inputs immutable, require a verified recovery point before live
   kernel/module/JIT experiments, and use bounded commands. A timeout does not
   prove drain; never force unload or discard retained evidence.

## Historical recovery

The repository README identifies the preserved pre-rebuild snapshot. Its code,
results and operational instructions are historical inputs, not current support
or a mandate to restore the old architecture. Do not touch other worktrees or
untracked evidence while rebuilding this branch.

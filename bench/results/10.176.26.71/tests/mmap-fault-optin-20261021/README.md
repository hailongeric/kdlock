# Opt-in mmap/fault implementation stage

Status: implementation prepared; VM validation pending. No correctness or
performance pass is claimed yet.

This follows the retained 46-file mmap/fault review and `d7f7358`, on source
host `380G10` with the same recovery VM. The main agent remains the only writer
and serial test executor. No guest kernel changes or access-setting changes
are planned. The owner-interval diagnostic stays inconclusive; its unvalidated
estimator will not be extended to five workers. All seven mutex regressions and
performance acceptance remain open.

The implementation is a module-owned mapping with a private backing-state lock,
not substitution of selected native mmap-lock calls. Its supported cases,
pre-publication Native fallback, exact originating-task scope and retained
full-mm blockers are defined in the [design](../../../../../docs/design/mmap_fault.md).
Actual CPU faults use ordinary callbacks; controlled ioctls exercise RETRY,
NOWAIT and COMPLETED without attributing those branches to a hardware-fault run.

The fixed correctness order is Native and KD first, then a separate TCLock
validation if both pass. Each invocation runs basic plus directly affected
checks, preserves frozen inputs and retains every failed attempt. No parallel
test or comparison runs are authorized by this plan.

## Retained attempts

`live-1`, source `581ff9c`, stopped in the basic build because the snapshot
omitted `daemon/`, required by `basic/test_daemon_policy`. The control-call
program compiled, but neither basic suite completion nor module correctness is
claimed. No project module was loaded. The failure, source snapshot and logs
remain untouched; actual VM idle was checked before correcting the runner's
snapshot dependency list.

`live-2`, source `7077fcf`, passed both basic programs and built the provider,
TCLock rwlock, payload and client. TCLock module loading failed with
`Cannot allocate memory`; the kernel recorded a 520-byte, 64-byte-aligned
reserved-per-CPU allocation failure. No mmap client ran. This is retained as a
failed attempt, not a correctness pass. The unused KD provider reported zero
modules, writers and frames, retired to state 2 and unloaded normally; actual
idle was then confirmed in `live-2/cleanup.json`.

The same log exposed ignored observation parameters: this runner had compiled
the production provider without the required benchmark overlay. The follow-up
uses the existing private observation preparation, retains its prepared hashes,
and verifies actual parameter values. It also uses the existing allocator hint
refresh module before provider loads, unloaded before any client runs. No
allocator metadata, kernel code or lock admission is changed.

Static review separately found that the controlled fault-in path rechecked
shared/write/execute mode but omitted current read permission. The follow-up
requires `VM_READ` and adds a negative `PROT_NONE` case with zero callback
attempts and exactly one native mmap acquisition/release. No unsafe probe was
run against the earlier implementation. Native/KD validation must pass on the
new revision before the separate TCLock case is eligible.

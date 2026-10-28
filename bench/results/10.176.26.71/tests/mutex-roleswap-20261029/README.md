# Queued role exchange: validation and retained failure

The candidate is isolated in `work/api-roleswap-validation-20261029`; it has not
been promoted to `master`. The production implementation starts at
`cec7db5f` (the integration of `b000b3a95079f7c861eeb0355ccbe021be56330b`).
The VM used Linux `7.0.0-38-kdlock1`, boot
`15dc5977-59d3-4471-a196-d71f03f450ed`, 64 CPUs on two NUMA nodes.
These are correctness mechanism probes, not real-world API measurements.
No role-exchange performance round ran.

## Completed checks

At isolated `47bec219`, two basic unit programs and 22 directly affected drivers
passed. Four additional frame-layout/completion drivers also passed. The
four-family live basic check completed 1,600,000 operations per family and final
idle; returned JIT bodies were spin 1,597,482, mutex 1,588,432, rwlock 32,633 and
rwsem 1,590,187. Later fixture/probe-only changes passed custody-idle checks,
11 then 12 probe assertions, and two emitted-entry audit regressions.

| Role-swap case | Observed outcome |
| --- | --- |
| C completes on W | Passed at `15d1fadb`; two JIT entries, one returned body, no native relay, exact retirement |
| C escapes natively | Passed at `2d4ee3df`; requires original C task/flags, retained W owner, exact native ACK and expected terminal image transition |
| C releases A with proxy spin B held | Controller reported passed at `2d4ee3df` |
| W releases A with native spin B held | Controller reported passed at `2d4ee3df` |
| W releases A with native mutex M held | Kernel assertion at `2d4ee3df`; undrained and not accepted |

The [simple-case proof](simple-proof.json) is copied to this host. Other complete
guest receipts remain on the current disk and in the failure snapshot; their
offline archives have not yet been made. Do not treat this table as whole-kernel,
arbitrary nesting, long-chain, source-close race or performance qualification.

Two preceding probe failures remain failed. The first stopped before module
load because its emitted-entry audit assumed one public mutex CALL per function;
the payload now also acquires M. The corrected audit binds the unique relocation
to the exact named continuation and retains its wrapper-byte checks. The second
completed the native-exit body and drained, but incorrectly required the image
to remain NORMAL. Normal cleanup verified all callers absent, zero lock/frame
state, stopped the exact daemon, retired the source and unloaded normally.
The corrected native case requires exactly one matching escape event, status
`-3`, unchanged code/generation/image files and unchanged drained source state.
Other cases still require NORMAL. These were probe changes, not runtime fixes.

Guest roots are `/root/kdlock-evidence/10.176.26.71/tests/` followed by
`roleswap-basic-20261029`, `roleswap-cases-20261029`,
`roleswap-cases-20261029-r2`, and `roleswap-cases-20261029-r3`.

## Native mutex failure and correction

The `w-early-mutex` run at
`2d4ee3df6c0f31dc442c514a649c1934c3482f3e` stopped at
`kernel_module/mutex/custody.inc:71`, in
`kd_mutex_custody_native_acquire+0x6e/0xb0`. W, PID 532712 on CPU 3,
hit the exact duplicate-entry BUG after acquiring M. C, PID 532711 on CPU 2,
remained in `__kd_mutex_lock_slowpath`; serial evidence records soft lockup and
RCU stall. Guest reads timed out. No force unload, reset, reboot or source sync
was attempted after this failure.

Source inspection identifies double accounting of one physical acquisition:
`kd_mutex_lock_entry` calls `kd_mutex_trylock_fast`, which calls
`kd_mutex_outer_trylock`. The inline successful CAS already invokes
`kd_mutex_note_native_acquire`; the public entry invoked it again. The correction
removes only that second invocation and preserves the duplicate-entry BUG.

The fix and composed regression fixture are committed at
`1c86d6d1a15d96d75c09504f1041772247707804`, integrating
`5b9fce4c41a636ac3aea4cea2a7b821e1de51040`. The fixture composes the actual
entry aliases, fast helper, inline CAS, note and custody ledger, with a mutation
that reinstates the observed error. Static review, Python parsing and whitespace
checks passed. This correction has not been built or executed; the VM must be
recovered before its basic, affected and live retest can run.

## Preserved state and proposed recovery

The [host evidence manifest](preserved-host-evidence.json) records hashes of the
full serial capture, simple-case proof, host identity and monitor receipt.
Copies are under `bench/results/10.176.26.71/raw/tests/mutex-roleswap-20261029/`.
QEMU PID 257489 successfully created the new snapshot
`kdlock-roleswap-failure-20261029`. The monitor verified it alongside
`linux70-kdlock1-clean-20261027`, and reported the VM running afterwards.
The failure checkpoint preserves the nondrained state and current disks; it is
not a successful recovery or drain assertion.

The proposed next action is one QEMU monitor `system_reset`, booting the same
installed kernel from the current disks. This preserves the on-disk evidence
instead of reverting to an older disk snapshot. No kernel change or installation
is proposed. After boot, verify identity, pins/frequency, snapshots and idle;
copy and archive the retained evidence; then synchronize the isolated correction
and rerun basic, directly affected and live cases before timing. This reset has
not been executed. [AGENTS.md rule 7](../../../../../AGENTS.md) excludes guest
kernel reboot by default, so explicit approval is required.

Strict pin overlap `f9f2118823aab58f03d7f6033ce6b2833cd799a6` and rwlock
rollback-first `233f3f50d8abd9c5ffba390400024ca52922d6cb` remain separate,
unexecuted candidates. Earlier strict-pin and rwlock performance losses remain
unresolved. No correctness pass or source correction closes the no-regression
gate.

# Opt-in mmap/fault correctness

These checks validate private backing state and callbacks, as a supporting
experiment for [stage 2](../../../docs/ROADMAP.md#stage-2-prove-scoped-mm-improvement-or-parity).
They leave the actual kernel mmap lock Native. The actual mmap adapter and
generic fault-throughput target have separate correctness/performance scopes.

This serial VM runner validates the supported
[mapping and fault transaction contract](../../../docs/design/mmap_fault.md).
Payload code lives in `workload_modules/mmap_fault`; its userspace client lives
in `bench/mmap_fault`. No guest kernel modification, hook or JIT admission change
is involved.

Run only in the existing confirmed recovery VM, after an actual snapshot and
idle check, using the pinned Python environment. Supply the source-host manifest
of the committed inputs and a fresh external output directory:

```sh
python3 tests/kernel/mmap_fault/run.py --source-manifest /tmp/mmap-source.json \
  --host-state /tmp/mmap-host-before.json \
  --output /root/kdlock-evidence/10.176.26.71/tests/mmap-fault-optin-20261021/live-1 \
  --backends 0,1 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

First validate Native (`0`) and KD (`1`). Only after those pass, use `--backends 2`
and `--native-kd-result <first-run>/result.json` in another new directory for
TCLock's supported short backing-state operations. The prerequisite must use the
same committed inputs. Each payload links one provider; Native is available in
both builds, and unsupported compiled-out backends are refused before creation.
All providers and the payload are frozen and built in the VM. The two basic C
programs run first. The new client requires real CPU faults, all four controlled
outcomes, rejection after read permission is removed, VMA replacement during
retry, shared readers against a metadata writer,
ordinary downgrade where supported, explicit pre-publication Native fallback,
private COW/fork behavior and last-descriptor-close lifetime.

Every selected case must complete with exact mmap acquisition/release counts,
all scopes retired, zero context/data errors and all VMA/file references drained.
No timeout kills a blocked caller or permits unload. Failures retain modules and
logs for inspection. Normal source retirement and unload occur only after all
client and object checks pass. Native fallback is recorded separately from the
requested backend and is not scored as KD or TCLock execution.

The host receipt must confirm current pins and the actual recovery snapshot.
The provider uses the maintained private observation overlay, with source hashes
retained before and after execution. The existing reserved-per-CPU allocator
preparation module is loaded and normally unloaded before each provider load;
it is absent during client execution. The payload's recorded build mode and ELF
imports must match its single provider. This avoids simultaneous provider
reservation pressure without changing the lock implementations or kernel.

No timing comparison is performed by this runner. Observed KD JIT counts must
remain zero; these are ordinary local KD operations. A TCLock-only run has no KD
provider and records its JIT counters as unavailable, with TCLock quiescence
checked instead. Signal cancellation, arbitrary remote
faults and full-kernel mmap-lock replacement are outside this validation.

Add `--split` to both sequential provider runs to check the two independent
workload tasks. `bench/mmap_fault/split_client.c` checks mmap-only at 1/16 workers
with exactly zero callbacks, CPU faults at 1/16 workers with one local reader
pair per completed fault cycle, fifteen fault readers plus one metadata writer,
and sixteen VMA-only lifetimes after every descriptor closes. The existing
retry, revalidation, NOWAIT, COMPLETED, permissions, fallback and downgrade
checks still run. Each worker has its own native mm and an exact PID/CPU/join
receipt. Source and provider execution classes remain in each result; these
functional runs do not report timing or reader delegation.

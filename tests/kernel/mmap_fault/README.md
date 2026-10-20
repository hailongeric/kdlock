# Opt-in mmap/fault correctness

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
  --output /root/kdlock-evidence/10.176.26.71/tests/mmap-fault-optin-20261021/live-1 \
  --backends 0,1 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

First validate Native (`0`) and KD (`1`). Only after those pass, use `--backends 2`
in another new directory for TCLock's supported short backing-state operations.
All providers and the payload are frozen and built in the VM. The two basic C
programs run first. The new client requires real CPU faults, all four controlled
outcomes, VMA replacement during retry, shared readers against a metadata writer,
ordinary downgrade where supported, explicit pre-publication Native fallback,
private COW/fork behavior and last-descriptor-close lifetime.

Every selected case must complete with exact mmap acquisition/release counts,
all scopes retired, zero context/data errors and all VMA/file references drained.
No timeout kills a blocked caller or permits unload. Failures retain modules and
logs for inspection. Normal source retirement and unload occur only after all
client and object checks pass. Native fallback is recorded separately from the
requested backend and is not scored as KD or TCLock execution.

No timing comparison is performed by this runner. JIT counts must remain zero;
these are ordinary local KD operations. Signal cancellation, arbitrary remote
faults and full-kernel mmap-lock replacement are outside this validation.

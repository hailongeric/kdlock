# Ordinary spin root-context live probe

This is a focused correctness probe for the ordinary `kd_spin_lock` /
`kd_spin_unlock` source macros and the root-context discriminator. It uses the
normal provider with the existing private benchmark observation overlay. It
adds no production hot-path hook, changes no heat/queue policy, and does not
claim throughput evidence. Build and run only in the verified recovery VM.

The body has one ordinary lock pair, bounded PAUSEs, an exclusion counter,
exact prefix/suffix effects and a logical task-identity record. It contains no
physical flags-reading or context-changing instruction that would turn the
positive body into a native escape. Context snapshots before entering and after
leaving each ordinary pair verify exact origin IRQ/preempt/BH/RCU/migration
restoration. Reading a translated GS-relative value is not presented as an
independent measurement of the executor's physical context.

The original ordinary macro's anonymous return address is resolved from the
single actual clobber-lock CALL relocation in the built payload, checked against
the loaded module's own function bounds and direct CALL bytes, and registered
outside execution. The payload is not rewritten to use the named DIRECT shell.
One unchanged published image is checked through every phase. Ordinary spin
images with requirements zero use registry generation zero; this probe does
not claim the immutable marker-image generation contract. Warmup runs with
IRQs enabled and must establish actual returned delegation; publication alone
is insufficient.

The homogeneous matrix is:

| Phase | Context around each ordinary pair | Required observed result |
| --- | --- | --- |
| IF-on | Ordinary task, no preexisting pin | Positive matching body-entry and completion witnesses |
| IF-off | Local IRQ save immediately before pair; restore immediately after | Positive matching body-entry and completion witnesses |
| BH | Preexisting `local_bh_disable` | Zero body-entry/completion witnesses; exact local effects |
| RCU | Preexisting `rcu_read_lock` on PREEMPT_RCU | Zero body-entry/completion witnesses; exact local effects |
| Preempt | One extra preemption-disable level | Zero body-entry/completion witnesses; exact local effects |
| Migration | Preexisting `migrate_disable` | Zero body-entry/completion witnesses; exact local effects |
| Mixed IF | Workers alternate saved IF-on/off | Stress-only: exact effects/restoration; no mismatch-refusal claim |
| IF-on final | Ordinary task again | Positive completed delegation from the same image |

Each IRQ-off, BH, RCU, preempt-disabled or migration-disabled region encloses
one bounded operation. No phase-long disabled loop or in-lock rendezvous is
used. Worker coordination occurs while ordinary scheduling is available.
There is no forced unload after a timeout, and the final receipt requires all
worker processes joined, no active execution frames, source retirement and
ordinary unload.

A mixed-IF queue can contain compatible subcohorts. A caller's pre-entry ready
notification does not prove private queue order, and the external payload has
no exported exact queue observer. Therefore mixed stress is **not** evidence of
a particular incompatible candidate reaching the refusal arm. The actual
production-batch unit fixture supplies the deterministic 18-combination
mismatch/handoff oracle. The live probe does not weaken that distinction or add
an approximate counter as authority.

Implementation and actual-ELF inspection precede VM execution. Positive phases
that do not return delegated bodies are inconclusive/failing coverage, never a
pass inferred from a NORMAL image or from ordinary critical-section totals.

The runner reuses the existing address-guard session's source freeze, Linux 7
schema-2 identity, allocator preflight, private provider build, daemon/image
capture, independent entry/completion counters and exact retire/unload checks.
Its compiled-ELF check also requires the only CALL after ordinary acquisition
and before the source end marker to be the paired ordinary unlock. Flags/state
capture helpers remain outside the translated interval.

```sh
python3 tests/kernel/spin/proxy_context/run.py --cpus 0-15 \
  --iterations 2048 --warmup-iterations 32768 --phase-timeout 60 \
  --output /root/kdlock-evidence/10.176.26.71/tests/spin-proxy-context-NEW
```

Use the confirmed recovery environment and exact kernel identity arguments
from [VM operations](../../../../docs/operations/VM.md). There are eight context
phases after one ordinary warmup. Context phases permit at most 4096 operations
per worker, with the eight-PAUSE body and context restoration between every
operation. That is a work bound, not a claim of a hardware IRQ-latency deadline;
no in-lock rendezvous extends an IRQ-off region for observation. The source
heat policy and 1024-body provider cap stay unchanged. A too-cold phase fails
positive coverage instead of bypassing heat admission.

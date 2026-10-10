# IRQ/BH spin API consumer

This uses the normal provider and explicit [IRQ/BH interfaces](../../../../include/README.md#explicit-irqbh-spin-interfaces).
It needs no SELFTEST, daemon, translation registration or kernel change. Build/run
only in an idle verified recovery guest with an actual confirmed snapshot; follow
[operations](../../../../docs/AGENTS.md).

## Coverage and commands

Single-thread checks cover irqsave entered with IRQs on/off, independent nested
flags, irq pairing, existing/nested BH disable depth and plain-native acquisition
inside irqsave. Checks compare IRQ/BH/preempt, per-CPU native counts and fast owner
before and after acquisition/release.

Four pinned workers each execute 10,000 operations; the consumer prefers CPUs
0/1/20/21 when available (at least three online CPUs required). That selection
spanned both nodes in the original 40-vCPU guest and is within node 0 on the
current 64-vCPU destination. They rotate irqsave/irq/BH/plain-native on one KD lock
and join before init returns. Plain-native uses byte 5 without adaptive registration.

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 UBSAN_SANITIZE=n
make -C tests/kernel/spin/irq_api KDIR=/root/linux-6.1.159-kdclobber2
timeout 60s insmod kernel_module/kdlock_km.ko
timeout 60s insmod tests/kernel/spin/irq_api/kd_spin_irq_api_test.ko
# Verify this run's PASS, exact count, context restoration and absence of errors.
timeout 30s rmmod kd_spin_irq_api_test
timeout 30s rmmod kdlock_km
```

Capture exact pre/post dmesg boundaries. Ring-buffer truncation can remove an old
prefix; do not classify new records by coarse uptime or the whole former prefix.
A load timeout does not prove worker drain and must not trigger forced unload.

PASS is explicitly `MCS=unobserved JIT=0`. Contention PAUSEs are not MCS evidence.
This checks local variants sharing the native protocol, not active-combiner handoff,
IRQ/softirq injection or PREEMPT_RT. Pending/MCS fixtures are separate checks.

## Historical validation

The 2026-09-27 check passed 40,000 operations on CPUs 0/1/20/21 with normal unload and
zero final native/frame invariants. Initial fixture/collector failures and reruns
remain in the fixed [full record](https://github.com/hailongeric/kdlock/blob/e533214/tests/kernel/spin/irq_api/README.md).
Raw local `bench/results/380G10/raw/legacy/irq-api-20260927/` and guest evidence archives remain intact.
This is historical local-native evidence, not fresh JIT or a later full-matrix pass.

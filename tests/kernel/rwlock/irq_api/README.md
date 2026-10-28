# Local rwlock IRQ/BH API probe

This correctness-only consumer uses the public [KD rwlock header](../../../../include/kd_rwlock.h)
and the ordinary provider. It needs no daemon, source registration, generated
image or kernel modification. All compilation and execution occur in the verified
recovery VM under [VM operations](../../../../docs/operations/VM.md).

The probe checks local read/write irqsave pairs with IRQs initially on and off,
independent nested flags, IRQ pairs, nested BH depth, trylock success/failure,
preemption restoration, exact native drain references and empty final lock state.

The live ordering case uses three online CPUs. A task on the first CPU holds a
read lock with IRQs enabled. An irqsave writer on the second CPU acquires the gate
and publishes WAITING. An IPI then invokes a reader on the first CPU, interrupting
the original reader. That reader must retain its count and bypass WAITING, while
still excluding an active writer. It must not queue behind the writer waiting for
the interrupted task. The controller releases the original read only after the
IPI reader returns; the writer then acquires, releases, and joins normally.

```sh
timeout 600s python3 tests/kernel/rwlock/irq_api/run.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwlock-irq-<new-run>
```

The runner requires an idle guest and the confirmed snapshot environment. It
freezes source including private `.inc` files, captures kernel identity, builds
provider/probe, records command PIDs and exact kernel log boundaries, and requires:

```text
kd_rwlock_irq_api_test PASS irq_readers=1 writers=1 errors=0 idle=1 JIT=0
```

No result here proves returned JIT execution, NMI support, arbitrary recursive
reads, upgrades, fairness or throughput. Existing mixed-reader/writer JIT checks
remain separate.

Coordination polling has deadlines and module load is bounded to 30 seconds by
the runner. A regression that queues the interrupt reader can deadlock inside the
lock API itself; that is precisely the bug this test detects. The kernel cannot
safely cancel that acquisition. Init therefore retains module text until all
participants have joined, even after a coordination deadline. A load timeout
retains modules/processes for diagnosis and snapshot recovery; it does not prove
drain or authorize unload. The runner never force-unloads or reboots the guest.

# Sleeping rwsem checks

Run only in the verified recovery guest, following
[VM operations](../../../docs/operations/VM.md). This probe exercises the
[current local sleeping KD rwsem](../../../docs/design/rwsem_implementation.md).
It does not start a translator or publish delegated requests.

```sh
timeout 600s python3 tests/kernel/rwsem/run.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwsem-local-<new-run>
```

Set the verified snapshot environment and pinned Python environment first. The
runner freezes source (including `.inc` files), verifies kernel identity, builds
provider/probe, saves commands and kernel logs, checks results, then retires the
source session and unloads normally. A timeout or kernel fault retains modules
for diagnosis; it does not prove worker or source drain.

The probe checks:

- Static initialization, read/write trylocks, writer-to-reader downgrade and
  quiescent inspection.
- Two readers that sleep concurrently while retaining their read counts; a
  writer that sleeps waiting for both; a late reader blocked behind that writer;
  and a writer that sleeps inside its body. All four workers share CPU 0, so
  correctness depends on blocked participants allowing their holders to resume.
- Six cancellation cases: interruptible and killable read acquisition waiting
  on the physical gate; write acquisition waiting on the gate; and write
  acquisition waiting for admitted readers after acquiring the gate. Killable
  waits first receive a nonfatal signal and must remain blocked, then cancel on
  `SIGKILL`. A cancelled drain waiter must reopen reader admission immediately.
- Exact zero error result, expected sleeping transitions, all worker joins, zero
  readers, no drain waiters and an idle physical gate.

Expected result: `api_checks=8`, `cancellation_checks=6`, `readers_slept=2`,
`writer_slept=1`, `late_reader_slept=1`, `colocated=1`, `errors=0`, `idle=1`.
Returned JIT bodies are explicitly zero. The [current receipt](../../../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
records the final probe pass and separate workload checks. The historical
[2026-10-15 receipt](../../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md)
belongs to the archived owned-mutex implementation and is not current evidence.

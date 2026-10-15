# Sleeping rwsem checks

Run only in the verified recovery guest, after following
[operations](../../../docs/AGENTS.md). The ordinary API probe creates two
concurrent sleeping readers, queues a writer that sleeps waiting for them,
queues a later reader behind that writer, and verifies exclusion through each
release. It also checks trylocks, downgrade and final drain. Ordinary SELF
admission uses the owned mutex's Linux-style owner spinning/sleeping path; the
delegation result-poll budget does not control that path. These are real
scheduler checks, **not JIT execution evidence**.

```sh
timeout 600s python3 tests/kernel/rwsem/run.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwsem-api

timeout 1800s python3 bench/rwlock_compare/run.py \
  --lock-kind rwsem --backends native kdlock --workloads cacheline --cachelines 8 \
  --functional --repeats 1 --write-percent 0 20 100 --threads 1 8 32 \
  --collector-cpu 63 --require-jit \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwsem-jit
```

Set the verified snapshot environment and pinned Python environment as described
in the [runner guide](../../../bench/rwlock_compare/README.md). The mixed test
checks every snapshot for a consistent version, every worker's deterministic
operation mix and progress, exact final writer increments, unchanged publication,
returned delegated bodies and source/frame/queue drain. A read-only rwsem run is
a native-reader control. The checked-in TCLock backend has no sleeping rwsem API;
the runner rejects that combination instead of comparing a spinlock as a rwsem.

The [2026-10-15 receipt](../../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md)
records the ordinary API probe and complete delegated writer checks through
60 workers, including a separate ABI2 run with result polling disabled.

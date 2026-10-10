# Migration validation, 2026-10-10

Measured in the migrated VM on `10.176.26.71` with **60 pinned vCPUs**, two
30-core guest NUMA nodes, 24 GiB RAM, collector CPU 58 and kernel
`6.1.159-kdclobber2`. This receipt precedes the change to 64 vCPUs and does not
validate that revised topology.

The bounded run contained one KD spin functional session and 72 RCUHT rwlock
comparison sessions: Native/TCLock/KD, 1%/20% writes, 1/16/32/56 workers,
three rounds and 2,000 ms per timed session. All **73 sessions** completed with
correct results, worker progress and final drain. The spin session returned
455,538 JIT bodies. Of 24 KD rwlock sessions, 15 returned writer JIT bodies and
nine completed as NO_JIT; those groups remain separate.

Seven of eight rwlock configurations met both throughput metrics against both
comparators. At 1% writes with 56 workers, KD was below TCLock by 1.66% in best
warmed peak and 4.52% in median whole-run throughput. Correctness success does
not imply performance parity. The destination's `ondemand` governor also differs
from historical fixed-frequency runs on `380G10`.

The full [raw archive](../../raw/bench/migration-20261010T070707Z/evidence.tar.gz)
is retained outside Git. SHA256:

```text
bcf6dc00c9d298d8c90780f28b4e2a8d3f191af7ffeede3c731751cde2193801
```

The archive preserves every session, environment, frozen input and drain record.
An independent offline audit checked all sessions, 565 captured source hashes,
12 binary hashes and 14 kernel-bundle hashes; no new benchmark was executed by
this directory reorganization.

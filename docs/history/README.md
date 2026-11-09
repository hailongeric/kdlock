# Historical designs and evidence

Current instructions are in the [documentation index](../README.md). Historical
records preserve their original source, topology, numbers and failures. A past
pass does not describe current `master` unless the result binds those inputs.

## November 9 documentation archive

The [tracked archive](documentation-20261109/README.md) retains the superseded
reached-backend guide, expired interpreter performance plan, and full earlier
design/TODO status pages. Its index names current replacements and records
original Git blobs and content hashes. The benchmark-linked reached-stage
anchor remains at its old path. Current implementation and later redesign
proposals retain separate authority and evidence status.

## Pre-cleanup documentation checkpoint

The documentation cleanup on October 28, 2026 removes duplicate guides, expired
campaign recipes, copied old-kernel bodies and long chronological status text
from maintained pages. Their full contents remain at Git checkpoint `cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773`
and explicit archive ref `refs/archive/documentation-before-cleanup-20261028`.
No benchmark result, captured hash, failure receipt or kernel identity is deleted
by this prose cleanup.

| Former content | Fixed version |
| --- | --- |
| Duplicate project/setup guide | [PROJECT_GUIDE.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/PROJECT_GUIDE.md) |
| Superseded throughput execution plans | [THROUGHPUT_PLAN.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/THROUGHPUT_PLAN.md) |
| Complete performance chronology and earlier mutex/rwsem tables | [PERFORMANCE.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/PERFORMANCE.md) |
| Complete validation chronology | [VALIDATION.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/VALIDATION.md) |
| Historical kernel-body excerpts, workload definitions and proc/MM proposals | [BENCHMARK_WORKLOADS.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/BENCHMARK_WORKLOADS.md) |
| Checked semantic analysis and string-service/direct-call contracts | [admission.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md) |
| Historical private ABI/relocation details | [JIT_REGISTER_ABI.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/JIT_REGISTER_ABI.md) |
| Old open-work chronology and diagnostic stops | [TODO.md](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/TODO.md) |

Use these versions to interpret old results, not to configure new Linux 7 work.
The old three-repeat plans remain unrun where recorded; completed single-round
coverage does not fill their repetition slots. Redacted archives retain their
explicit incomplete/replay limits.

## Decisions and result records

| Record | Historical scope |
| --- | --- |
| [Ubuntu/storage migration](vm-ubuntu2604-migration-20261027.md) | Completed approved 43-snapshot purge, 132 GiB expansion and Ubuntu 26.04.1 / stock Linux 7 boot; later KD validation is in the separate port receipt |
| [Linux 6.1 retirement](kernel-retirement-20261027.md) | Single legacy recovery version, preserved results and exact retirement receipts |
| [Linux 7 port](../../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md) | Exact new source/build/boot and focused validation |
| [Main consolidation](main-consolidation-20261018.md) | Accepted baseline and exact branch dispositions |
| [Feature reintegration](feature-reintegration-20261018.md) | Independent features and ordinary rwsem integration |
| [Legacy mutex compatibility](legacy_mutex_compatibility.md) | Historical instruction/image backport; production admission policy changed later |
| [Protocol simplification](protocol_simplification.md) | Closed study; rejected protocols are not an active plan |
| [KD-only acceptance](../../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md) | Selected physical/delegation foundation on the former 256-byte mutex, not a current-layout timing result |
| [Historical workload comparison](../../bench/results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md) | Earlier spin/rwlock/API and superseded owned-mutex evidence |
| [Expanded owned mutex](../../bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md) | Unselected compatibility/performance experiment |
| [Old rwsem validation](../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md) | Historical owned gate/delegated writers, distinct from current phase admission |

The [result index](../../bench/results/README.md) owns archived report locations.
Current Linux 7 coverage, failures and limitations are summarized in
[performance](../PERFORMANCE.md) and [validation](../VALIDATION.md).

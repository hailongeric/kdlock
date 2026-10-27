# Linux 7 normal-boot four-family functional checkpoint

The unchanged four-family basic runner passed after returning from the shared-MM
campaign to `7.0.0-38-kdlock1`, boot
`15dc5977-59d3-4471-a196-d71f03f450ed`. Each family completed 1,600,000 operations
with sixteen workers, correct data, positive returned-JIT execution and normal
drain. This is fixed-iteration functional validation, **not a scored benchmark**.

| Family | Preset | Completed operations | JIT entries = completions |
| --- | --- | ---: | ---: |
| Spin | One cacheline | 1,600,000 | 1,597,271 |
| Mutex | Public API, one cacheline | 1,600,000 | 1,587,779 |
| Rwlock | One cacheline, 20% writes, post-work 4 | 1,600,000 | 26,269 |
| Rwsem | Sixteen cachelines, 100% writes, post-work 4 | 1,600,000 | 1,573,729 |

Dependency, basic and runner checks also exited successfully. Source leases
retired with zero frames, modules and writers; final state was retired. Published
image bytes remained bound to the retained publication records. The exact boot,
kernel identity and module inventory were unchanged, with the expected taint
transition from 0 before project loads to 12288 afterward and no recorded kernel
faults. Host policies remained fixed at 2GHz; three additional auxiliary QEMU
workers were confined to CPU63. The global `/root` writable-file guard was
unchanged and passed before and after the run.

The [offline audit](../../raw/tests/linux70-kdmm1-20261027/normal-basic/15dc5977-59d3-4471-a196-d71f03f450ed/offline-audit.json)
verified the complete archive inventory: 2,112 regular files, 1,286 source
manifest entries, eighteen binary entries, 22 control files and twelve published
image hashes. [evidence.json](evidence.json) binds the exact control, four session,
source/publication and endpoint receipts. Final phase SHA256:
`09133d4475c5badc260305bc37df4f67913e8c6bdafde4cad25573691b831231`.

The production translator uses the user-selected trusted-source policy for
kernel and module code. This smoke test establishes returned execution for the
four selected workloads; it does not prove arbitrary-source semantic safety,
whole-kernel support, a performance gain or equivalence between read/write mixes.
The [MM checkpoint](../linux70-kdmm1-20261027/README.md) separately records the
126 exploratory MM timing points and the return to this normal kernel.

The later [completed catalog index](../../bench/catalog-linux70-complete-20261028/README.md)
selects 52 complete lock/API configurations across three frozen generations.
Their final endpoint remains on this normal boot. Those timings and the separate
MM results retain their own source, preparation and kernel identities; they do
not turn this fixed-iteration basic check into a performance result.

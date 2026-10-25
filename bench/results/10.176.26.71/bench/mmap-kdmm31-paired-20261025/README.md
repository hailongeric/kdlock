# kdmm31 paired campaign: admission stop, October 25

The authorized campaign stopped at its first host admission check, before any
candidate boot or payload load. The capture contained **73 QEMU tasks versus
the required 67**. The unchanged `paired.host_check(fresh=True)` rejected the
saved capture with `Failure('strict original QEMU thread set differs')`.
No current throughput, latency distribution or optimization gain was measured.

Inputs were local master `b7c170d59dcbf63daffc8d578d7f35877ca40c29`, audited lock
implementation `e6fc371b032cc0444dba34ee9025e7d939811125`, and tooling
`82c20b4`/`e15a5aa`. The [prepared workload and bounds](../../../../mmap_lock/README.md)
were unchanged. The user authorized the bounded cycle and root host capture on
October 25 at 19:15 (Asia/Shanghai). The inventory-complete/I/O-stopped handoff
arrived before host admission. No deletion was authorized or performed as part
of this benchmark attempt.

## Activity and stop

| Activity | Authorized maximum | Consumed |
|---|---:|---:|
| Boots, including recovery | 6 | 0 |
| Payload load/run/unload checks | 34 | 0 |
| Full host captures | 55 | 1 |
| Measured sessions | 24 | 0 |

One admission was attempted and rejected. Measured sessions: attempted 0,
completed 0, accepted 0, rejected 0, **unrun 24**. All ten unscored validation
checks remain unrun. The [ledger](../../raw/bench/mmap-kdmm31-paired-20261025/ledger.json)
distinguishes admission failure from a rejected measurement. No later quiet
capture, candidate boot, process kill, VM restart or gate change followed.

At **19:26:23 (Asia/Shanghai)** the reviewed root helper completed successfully:
it read NUMA metadata, verified pins and listed the actual recovery snapshot
`before-mutex-kdonly-20261017T140354Z`. Capture transport success is distinct from
admission. The six extra threads were `worker` TIDs 552145, 552149, 552150,
552157, 552159 and 552163, all observed on affinity `[63]`; no original TID was
missing. These tasks were observed before the helper queried snapshots, so the
snapshot query cannot explain their presence in that initial observation.
Their creation cause is not established by this capture.

Fresh process discovery matched QEMU PID 257489, start ticks 42969155, command
SHA-256 `08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917` and host
boot `2b39cf56-2146-4c87-9fa5-28c66dcee12c`. Frequency policy, host NUMA settings,
memory-binding configuration and pins matched the retained environment.
The strict original task-set requirement still failed. See the
[capture](../../raw/bench/mmap-kdmm31-paired-20261025/capture-00-precycle/host-endpoint.json),
[maintained gate result](../../raw/bench/mmap-kdmm31-paired-20261025/admission-check.json)
and [saved-evidence comparison](../../raw/bench/mmap-kdmm31-paired-20261025/admission-review.json).

## Readiness and recovery evidence

Fresh read-only checks matched all 13 prepared source/binary bindings, 22 runner
hashes, four installed candidate boot files and all 73 installed candidate
modules. The loaded recovery module hashes matched their retained records.
Candidate and recovery source/configuration/build identities passed; candidate
ELF, Module.symvers and embedded BTF, and the live recovery BTF, matched.
This reused build-3 and prior correctness evidence; it ran no new basic,
standalone or actual mmap correctness test and did not repeat a provider load.
The [artifact preflight](../../raw/bench/mmap-kdmm31-paired-20261025/artifact-preflight.json)
records the exact identities and scope.

The actual QEMU system and data images are
`/home/eric/vm/qemu-disks/ubuntu22.04.img` and
`/home/eric/vm/qemu-disks/sda.qcow2`. Their backing filesystem had
143,152,549,888 bytes available. Guest root had 2,996,514,816 bytes available,
the data disk 10,031,104 bytes and `/dev/shm` 5,740,777,472 bytes. Current capacity
supported the earlier 512 MiB campaign evidence allowance; disk space did not
cause the admission stop. The [host discovery](../../raw/bench/mmap-kdmm31-paired-20261025/host-discovery.json)
and [guest preflight](../../raw/bench/mmap-kdmm31-paired-20261025/guest-before.json)
retain the observations. Cleanup proposals remain separate and untouched.

Final health at **19:29:56 (Asia/Shanghai)** confirmed the same recovery boot
`d32e2e18-c340-4a98-8105-335bccec0b5d` on `6.1.159-kdclobber2`, the exact original
73 modules, taint **12288**, 64 CPUs, voluntary preemption, no matching kernel
faults or project processes/open files, and empty `next_entry`. No return boot
was needed because recovery never stopped running. See
[final health](../../raw/bench/mmap-kdmm31-paired-20261025/final-health.json).

## Retention and next step

The source-side [raw manifest](../../raw/bench/mmap-kdmm31-paired-20261025/manifest.json)
binds 14 files totaling 836,953 bytes, including controller partial-capable
receipts, the saved capture, original comparison inputs, source bindings,
preflight/gate/final-health results and the final ledger. The
[executed command record](../../raw/bench/mmap-kdmm31-paired-20261025/commands.txt)
identifies the maintained controller and predicate. Existing output paths must
not be reused. Historical invalid measurements remain rejected.

The next step is a bounded analysis of the extra QEMU workers and a controlled
diagnostic proposal. This attempt does not authorize quiet retries or a weaker
task-set gate. No lock bottleneck or optimization is selected from this failed
admission. Qualified current performance cases remain **zero**.

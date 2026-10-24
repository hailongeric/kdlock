> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Resident-range munmap milestone

Passed: one incremental build, two basic programs, six receipt controls and all
11 serial VM cases. Recovery is restored, all test modules unloaded normally,
and the expected 73 runtime modules remain. This extends whole isolated anonymous
VMA (virtual memory area) removal from one to four resident pages. Source/probe
commit: `6a54dbc6b7bdb4654abfc7b4c40d424043e6aaf4`. No live or build failure
occurred. One read-only final-health lookup used `verify/` instead of
`transition/`; its failure log is retained and the corrected lookup passed,
without a rebuild or repeated live test.

The [nano report](../../bench/nano-20261022/README.md) was finished before this
work: 7,054 completed repetitions, one failed, one withheld/missing and 882
unsupported slots. Its Native spin progress mismatch remains unresolved and
was not reclassified or rerun here. Nano files and the unrelated cleanup-report
edit were untouched. There was one writer, no helper agent, no parallel VM run
and no interrupted in-flight run.

## Scope and implementation

Only `mm/kd_mmap_unmap.inc` differs from the captured `kdmm5` sources; the other
53 files are unchanged. The supported target is one complete isolated writable
private anonymous VMA, one through four resident 4-KiB pages, entirely within
one PMD (the page-middle-directory entry covering 2 MiB). Neighboring VMAs must
retain its leaf page table. Existing exclusions and the populated opt-in remain.
See the [maintained scope guide](../../../../../kernel_integration/mmap_lock/UNMAP.md)
for the full boundary and protocol.

The executor references and trylocks every page before effects. A later refusal
releases all earlier references/locks before exact waiter handback and ACK
(acknowledgement); subsequent calls on that entry stay local. The native
`do_mas_align_munmap_prepared` body still removes mappings, updates accounting
and flushes the TLB (cached address translations). Completion requires every PTE
(page-table entry) empty, mapcount zero, unchanged table bytes and released
temporary locks/references. Owner, queue, cancellation and ACK routing are
unchanged. Reader acquisitions and hardware read faults remain local.

Four pages stay strictly below the eight-page native local gather buffer.
Filling that buffer immediately attempts another allocation in the executing
task's context. General table freeing can also allocate a deferred-free batch.
The capacity limit and retained-table bounds avoid these concrete caller-context
conflicts. Larger ranges, table destruction and mapping creation remain outside
this implementation; a five-page range hands back rather than relaxing admission.

## Recorded run

All case paths below are under guest stage
`/root/kdlock-evidence/10.176.26.71/tests/mm-range-unmap-20261023/`.
Each `focused-1/<case>/` retains one `client.json` and `kernel.log`; the single
`focused-1/result.json` binds their hashes and exact validator results.

| Case in `focused-1` | Observed result |
| --- | --- |
| `four-pages` | 15 remote whole-VMA bodies, 60 original-PFN (physical page number) receipts; 144 originating-CPU translation invalidations; 15 exact partial-unmap handback/ACK pairs; 16 sticky-local calls; two concurrent local readers; real neighbor fault blocked then resolved with zero-filled data; retained contents/charges/references correct. |
| `busy-last` | Locked fourth page refused after acquiring the first three; receipt records `held=3 released=3 effects=0`, with the identical mm/request/origin/executor/range as its handback and ACK. Independent page lock/reference checks passed; one later call stayed local. |
| `over-limit` | Five-page VMA returned to its waiter with one exact ACK, cached translation invalidated, and one later sticky-local call. |
| `cancellation` | Queued fatal cancellation returned `-EINTR` before removal; all four victim pages remained mapped; healthy head completed and queue retired. |
| `free-two`, `free-three`, `free-four` | One remote real removal each, with 2/3/4 original-page receipts. All test references released before the body; final release exercised without dereferencing freed pages. |
| `single-page-smoke` | One remote one-page removal after test references were released; original single-page receipt and cached-translation checks passed. |
| `advice-smoke` | 1,740 returned built-in advice bodies on other tasks; 15 handbacks, 512 later local calls and 16 identity receipts. |
| `fault-smoke` | 148 real remote anonymous first-write page installations; 16 PTE-bound receipts, 15 matched handbacks and 128 later local calls. Separate fault workload. |
| `unpopulated-smoke` | 15 remote unpopulated VMA removals, 15 exact ACKs, 16 sticky-local calls; concurrent local readers and a blocked real fault returning `SEGV_MAPERR` after removal. |

The eight populated cases released all 197 test page references and made 192
explicit local cleanup calls. Multi-page completions total 18 operations and
69 original-page receipts; the single-page smoke adds one operation/page.
Fallback and cleanup are never counted as delegated bodies. These are actual
built-in kernel bodies; no generated JIT (just-in-time compiled) body is claimed.
All four probe modules unloaded normally. Retained logs contain no kernel fault
matches; boot logs retain the six `fd0` floppy I/O messages on each boot, including
recovery. They are not MM-test failures and were not hidden.

## Build, environment and artifacts

The original VM still has 64 vCPUs, 24 GiB RAM and two NUMA memory/CPU nodes,
with the same host pins, boot policy and snapshot
`before-mutex-kdonly-20261017T140354Z`. Candidate boot:
`9d383d0a-0049-4c96-b2f6-af1340a74806`, release `6.1.159-kdmm6`, Build ID
`d192a1d7912339707e8afe9d182904f09834a8c1`. Restored recovery boot:
`8e37a896-fc2a-4965-b8d2-7abacee7d8f0`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Recovery remained the default;
5,686 recorded recovery-module files and captured boot files were preserved.

`build-1` reused the immutable `kdmm5` build outputs through a private OverlayFS
view (a temporary writable layer over unchanged files) backed by RAM. Kbuild
compiled only dependency-selected targets: 45 image compilation steps, 117 for
the required runtime-module targets and eight for the four probes, including
module metadata. The new release and BTF (kernel type metadata) dependencies
required the runtime-module targets; reusing old signed modules was not valid.
No full source rebuild or full configured-module build ran. Each probe/client
was built once and reused. Both basic programs and all six receipt controls
passed; expected error-injection messages remain in the basic-program log.
The RAM workspace was removed and the original build verified unchanged.

The new baseline is `/root/kdlock-kernel-baselines/mmap-kdmm6-20261023`, manifest
SHA-256 `18f552fca114799bf5d968ce3d790ffd4acfca11da627fccfa1c0127d8f55ca7`.
The installed-files manifest SHA-256 is
`89343171b3697497f8b5cb75ef35611328a6a6f1d769ea89845c697af7a4ae40`.
The identity snapshot at `/mnt/kdlock-builds/mm-range-unmap-20261023/linux`
contains 54 sources, 11 build-identity files and configuration; it is not a full
module build directory. Guest `probes-1/` retains the exact binaries, with hashes
in `build-1/result.json`. No old artifact was deleted or recopied into a new
kernel archive. The parent manifest remains
`8f9bd2899aa5c69bb2eb113b4d914d780dd5daa17f20b31ada3bced1a0f71cb1`.

One small archive contains the new logs, receipts and probe/control sources:
`bench/results/10.176.26.71/raw/tests/mm-range-unmap-20261023/collect-1/essential.tar.gz`,
579,105 bytes, SHA-256
`7c8f7a7f87053f7f3f2c39af9d3fd4ae83698610cde3b0a1a58ead359d3ccd5c`.
It excludes kernel/module binaries retained in the VM. The same local raw stage
keeps source-host commands, transitions, `final-health.json.stderr` (the failed
lookup), and `final-health-2.json` (passed). Guest `final-health.json` confirms
idle recovery, all 29 frozen source inputs unchanged, 53 inherited kernel
sources unchanged, no temporary mount and no retained test module. Final free
space was 1,001,959,424 bytes on root and 215,252,992 on the data filesystem.
No historical archive was rescanned.

## Commands and limits

The recorded source-host sequence was `workflow.py prepare`, `build`, `kd`,
`recovery`, then `collect`, each once with attempt 1. Build and live execution
ran only in the VM. These paths are frozen and are not reusable output paths.
For a later authorized rerun, use the [prebuilt commands](../../../../../tests/kernel/mmap_lock/populated_unmap/README.md#reuse-the-installed-candidate-and-built-probes)
with a fresh attempt number; do not rerun preparation/build to repeat unchanged
tests. No new run is needed for these documentation changes.

The [single-page baseline](../mm-populated-unmap-20261022/README.md),
[unpopulated baseline](../mm-unmap-body-20261022/README.md),
[fault baseline](../mm-fault-body-20261022/README.md) and
[advice baseline](../mm-body-20261022/README.md) remain separate references.
This stage did not repeat Native controls, the full historical API/fault-retry
suite or the unchanged missing-neighbor case. The narrow smoke set preserves
their source paths without claiming those omitted tests passed again.
Cross-PMD targets, partially absent PTE ranges, forced allocation failure,
post-admission cancellation, slot exhaustion, the locality handoff boundary,
queue interleaving, broad races, fast page pinning, memory pressure, non-root
memory cgroups and oversubscription remain untested. Only the 73 runtime modules
were built, not every configured module. General mmap/munmap, RT, lockdep and
whole-kernel replacement remain unvalidated. No timing, variance estimate,
p95, seven-regression investigation or performance acceptance is claimed.

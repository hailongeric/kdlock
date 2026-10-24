> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Complete mixed-page munmap matrix

Passed: all 27 serial cases, two basic programs and 262 negative receipt controls.
All nine mixed survivor-residency combinations matched native mapping and
resident-memory state; 18 removals actually completed on different tasks.
Recovery is restored and test modules unloaded normally. No build or live case
failed. No performance, p95, mutex-regression or nano work ran.

Kernel implementation remains `52ad1980362efcfcf9c4505b75bd1b34baf2413b` (`kdmm9`).
Observer/matrix revision: `d619dddb7325f2dc2e7fd3903e40bf65708ec8f0`.
Only the strengthened userspace client was compiled. Kernel, modules, five
preservation clients and their validators were reused with recorded hashes.
The [initial mixed result](../mm-mixed-partial-20261023/README.md) and
[resident/split-error baseline](../mm-resident-partial-20261023/README.md) remain
unchanged evidence; their full campaigns were not repeated.

## Mechanism and scope

One resident anonymous page can be removed from an exactly three-page VMA
(virtual memory area), leaving either or both survivors untouched. The kernel
already admitted all these combinations. This follow-up closes the four missing
edge-layout checks and adds native success controls and direct resident accounting.
It does not widen a guard or raise a page limit.

The caller supplies two VMA descriptors, two reverse-map links (connections
between physical pages and mappings), and mapping-index reserves before queue
publication. Under actual mmap write ownership the executor rechecks the current
VMA, reserve capacity, ancestry and PTEs (page-table entries). Only an absent
survivor can be skipped; the target must remain ordinary, writable, exclusive
and resident. Resident references retain their original slot indices. The same
page-table and native teardown restrictions remain. The
[scope guide](../../../../../kernel_integration/mmap_lock/UNMAP.md#resident-partial-removal-and-post-split-errors)
explains the allocation and ownership ordering.

Pre-effect refusal releases the exact held pages before waiter handback and
ACK (acknowledgement), then keeps later calls local. After a split can take
effect, admitted errors return directly and cannot replay munmap locally.
Readers remain concurrent and local. Native split/unmap and TLB (cached address
translation) invalidation execute on the real combiner for supported requests.

## Results: `focused-1`

Guest stage: `/mnt/kdlock-builds/mm-mixed-matrix-20261023`.
Each case retains `client.json`, `kernel.log` and applicable receipt controls;
`focused-1/result.json` records their hashes. R denotes a resident page, U an
absent untouched slot. Each row below is a native/KD pair, with two remote KD
removals; no cases were deduplicated.

| Shape | Initial slots | Removed slot | Result |
| --- | --- | --- | --- |
| prefix | RUU | 0 | Pass |
| prefix-near | RRU | 0 | Pass |
| prefix-far | RUR | 0 | Pass |
| middle | URU | 1 | Pass |
| left | RRU | 1 | Pass |
| right | URR | 1 | Pass |
| suffix | UUR | 2 | Pass |
| suffix-near | URR | 2 | Pass |
| suffix-far | RUR | 2 | Pass |

Native controls use the ordinary body on the same KD backend with delegation
disabled. Every KD origin matches its native control's normalized VMA bounds,
offsets, flags and per-VMA RSS (resident set size)/anonymous resident bytes.
Independent read-only PTE observations precede controller survivor reads.
`smaps` observes before removal, before those reads and after survivor writes,
without faulting untouched addresses. Exact page identities/references and
reverse-map ownership remain separate checks; approximate counters replace none.

Example: `mixed-prefix-near` request 2, mm `ff1100010416f400`, origin 1887,
executor 1886, removed physical-page number `0x359798`, resident mask 3, untouched mask 4,
two references held/released. The original VMA has 8 KiB RSS; its surviving
two-page VMA has 4 KiB after removal and 8 KiB after writing the untouched page.
The removed address faults on its origin CPU. Retained resident bytes match,
untouched pages first read as zero and then accept writes. A deliberate survivor
fault waits behind the writer and resolves locally; two local readers overlap.

Additional cases: native/KD error after split 2 (one real remote error, same
`ENOMEM` and three harmless retained VMAs); busy-page revalidation/refusal
(one exact rollback/handback/ACK, then sticky local); queued fatal cancellation
(mapping retained and prepared objects retired). The 22 matrix/control cases
release 71 test references and complete 132 cleanup calls. The 262 negative
controls reject corrupt copies of actual records; they are not live executions.

Five preservation smokes passed: fully resident partial (2 remote removals),
untouched partial (15), four-page whole removal (15, 60 physical-page receipts,
144 originating-CPU translation checks), advice (1,719 returned remote bodies)
and separate first-write faults (127 real remote page installations).
All modules unloaded without force. Successful local heads, fallback, cleanup
and admitted errors are excluded from the 18 mixed remote-success count.

## Identity, recovery and retained evidence

| Identity | Value |
| --- | --- |
| Candidate | `6.1.159-kdmm9`, Build ID `e33aeaba03177030ec750342593246d18908c776` |
| Candidate boot | `1f4a04a3-d20f-4215-ac90-7f35a7b84986` |
| Candidate manifest | `645b72e4065136f3833be20e530293b46226f7c34d4aaa1b759ace051e45ce2f` |
| New client SHA-256 | `5b6f8af4cbc42f186893e7c8b0a845a63f5a014541eef3a66dfdd11c9d4baa97` |
| Focused result SHA-256 | `65563f991411ab18fe68a9ce52fee03d394befe4c6aaafb76ee0975fa7239372` |
| Restored recovery | `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Recovery boot | `c5b91ee6-3d1a-4563-a14a-6155038f83b4` |

The original 64-vCPU/24-GiB/two-NUMA configuration, pins, QEMU PID 257489 and
snapshot `before-mutex-kdonly-20261017T140354Z` were verified. Recovery remains
the default with its boot artifacts and 5,686 module files unchanged. Final
health confirms idle recovery, the same 73 runtime modules, no test modules,
no temporary kernel identity in RAM and no new kernel faults. Existing `fd0`
floppy I/O messages remain in the boot log. One MM writer, serial tests, no
interrupted run; unrelated TCLock work and the cleanup document were preserved.

One essential archive, 238,407 bytes:
`bench/results/10.176.26.71/raw/tests/mm-mixed-matrix-20261023/collect-1/essential.tar.gz`,
SHA-256 `2901bf8e6ccf291cf5e57dc8d3e2a169af3f8a9c1868fafcd314bb3394fc7268`.
The raw stage also keeps transport/transition receipts and `final-health.json`.
All 27 client/log pairs were checked against the recorded hashes. Prior archives
and unchanged binaries were referenced, not copied or rescanned.

Storage remains tight: 3,530,752 root bytes and 10,035,200 data bytes free at final
health. Two verified identical historical symbol-map copies now share storage
with their corresponding boot copies; all paths and captured bytes remain.
An initial three-pair inventory refused a missing historical path before any
mutation; the two verified pairs completed successfully, reclaiming 10,297,344
bytes. The failed inventory and successful receipt are both retained. Recovery
files were not changed. Arrange headroom before another transition/build.

## Commands and remaining limits

[Runnable commands](../../../../../tests/kernel/mmap_lock/mixed_partial/README.md#reuse-the-image-and-frozen-probes)
reuse the image and frozen probes. This run used `workflow.py prepare`, `kd`,
`recovery`, then one `collect`, each with `--attempt 1`. Preparation compiled one
client and ran the two basic programs in the VM. Source edits/static review ran
on `380G10`; no kernel/module rebuild or broad historical suite was needed.

Zero-page/missing-target refusals, split-point-1 errors and final physical-page
release reuse the unchanged initial mixed evidence. All-resident edge removal
reuses `kdmm8` evidence. Forced mapping/residency changes between preparation and
execution, allocator pressure, fast page-pinning/reclaim races, complex ancestry,
post-admission cancellation, broader retry/API suites and Native-off controls
were not run. Per-VMA RSS was checked; batched global RSS races were not.
Larger mappings, shared/swapped/huge pages and general page-table destruction
remain explicitly unsupported.

The next small candidate is retaining already-read shared-zero-page survivors
around the same ordinary resident target. It needs explicit zero-page identity
and lifetime checks, unchanged-PTE validation through splitting, and local
write-fault coverage. It remains refused today. General mapping support and all
performance work remain deferred.

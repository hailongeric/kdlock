# Untouched partial anonymous munmap milestone

Passed: one incremental build, two basic programs, six receipt-control tests,
and all 10 serial VM cases. Forty-five partial removals completed on different
tasks, including native VMA (virtual memory area) splitting. Recovery is restored,
all test modules unloaded normally, and the expected 73 runtime modules remain.
Source/probe commit: `f4cceacf7706289179f972631736b80a26cd1445`.
There was no build or live-test failure. One code writer performed the work;
there were no helper agents, parallel tests or interrupted runs. Unrelated
checkout changes and nano work were preserved.

## Scope and implementation

The extension removes a prefix, suffix or interior subrange from one untouched,
isolated private anonymous VMA, bounded to 16 pages with absent top-level page
directories. The existing exclusions still apply. The origin prepares two VMA
descriptors and separate maple-tree reserves (storage for the mapping index)
before publication. Native split/adjust helpers consume them under exact mmap
write ownership, then the shared native unmap body removes the target interval.
Each split inserts the higher address VMA so one prepared store suffices; the
captured maple store destroys unused reserve after each store. Reserve capacity
is checked against the current tree before effects.

Resident partial removal remains unsupported: native splitting can allocate
reverse-map links, which connect pages to their mappings, in the executor's
allocation context. This stage does not solve that problem or increase the
resident-page limit. All refusal precedes splitting. An error after splitting
starts returns directly as an admitted error, never as a local replay. Unused
caller allocations are released only after exact queue-node retirement. The
physical-owner, handback/ACK (acknowledgement), cancellation and reader protocol
remain unchanged. See the [maintained scope guide](../../../../../kernel_integration/mmap_lock/UNMAP.md)
for constraints and the no-replay boundary.

## Recorded results

Guest root: `/root/kdlock-evidence/10.176.26.71/tests/mm-partial-unmap-20261023`.
Run `focused-1` has one `client.json` and `kernel.log` per case, with hashes and
validator results in `focused-1/result.json`.

| Case | Result |
| --- | --- |
| `partial-prefix` | 15 remote bodies with one native split each; VMA count 108→108, mapped pages 37,664→37,648; 34 prepared descriptors accounted for. |
| `partial-suffix` | 15 remote bodies with one native split each; VMA count 108→108, mapped pages 37,664→37,648; 34 descriptors accounted for. |
| `partial-middle` | 15 remote bodies with two native splits each; VMA count 108→124, mapped pages 37,664→37,648; 34 descriptors accounted for. |
| `partial-refusal` | Resident request refused before effects, one exact handback/ACK, one subsequent sticky-local request; surviving patterned bytes and originating-CPU translation invalidation passed; four descriptors retired. Zero remote bodies claimed. |
| `partial-cancel` | Queued victim returned `-EINTR` before splitting and kept its original mapping; healthy head completed; six descriptors retired. Zero remote bodies claimed. |
| `unpopulated-smoke` | 15 remote whole-VMA removals, 15 exact ACKs, 16 sticky-local calls; real blocked fault observed the removed mapping. |
| `four-page-smoke` | 15 remote whole-VMA removals with 60 original-PFN (physical page number) receipts; 144 original-CPU translation checks; 15 exact partial-unmap ACKs, 16 sticky-local calls; real neighbor fault waited then resolved. |
| `single-page-smoke` | One remote removal after both test references were released, one original-PFN receipt, two translation checks; no dereference after page freeing. |
| `advice-smoke` | 1,731 returned built-in advice bodies on different tasks; 15 handbacks, 512 sticky-local calls and 16 identity receipts. |
| `fault-smoke` | 159 real remote anonymous first-write page installations; 16 page-table-entry receipts, 15 matched handbacks and 128 sticky-local calls. Separate fault workload. |

Each successful partial shape used 16 three-page VMAs with one page removed.
The three local heads are excluded from the 45 remote bodies and 60 remote
native splits. Removed slices were inaccessible; surviving bounds, flags,
offsets and zero-filled contents matched, then local pattern writes/readback
passed. Exact total/data/stack/exec accounting and page-table bytes matched.
Two local readers remained concurrent. A real hardware fault blocked behind
writer admission, then returned `SEGV_MAPERR` for the removed slice. Across all
five partial cases, 112 prepared descriptors retired and 159 explicit local
cleanup calls completed. Fallback and cleanup never count as delegation.

For example, `partial-middle/kernel.log` binds request 2 to mm
`ff1100010e128740`, origin 1914, executor 1909, original range
`13000000008000–1300000000b000` and removed range
`13000000009000–1300000000a000`, with two splits and unchanged page-table bytes.
The generic completion matches that exact identity. `partial-refusal/kernel.log`
matches both handback and ACK for request 2, mm `ff1100010e1295c0`, origin 1925
and executor 1924, while retirement shows neither descriptor consumed.
These are real built-in bodies; no generated JIT body is claimed.

All four probe modules unloaded normally. Final idle checks passed with no new
kernel fault matches. Both boot logs retain the six existing `fd0` floppy I/O
messages; they were not suppressed or reclassified as successful MM operations.

## Build, identities and artifacts

The VM configuration remains 64 vCPUs, 24 GiB RAM, two NUMA CPU/memory nodes and
the original host pins/QEMU process. Snapshot
`before-mutex-kdonly-20261017T140354Z` remains present. Candidate boot:
`de926836-d4ff-4433-a471-84205828f7b6`, release `6.1.159-kdmm7`, Build ID
`f74874e3f6b98578fa84ca42f18cd1b47e787b7d`. Restored recovery boot:
`8feab21b-7043-42e2-8d0a-b6b30e66cb73`, release `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Recovery remained the default and its
boot files and 5,686 recorded module files were preserved.

Only `mm/mmap.c`, `lib/maple_tree.c` and `mm/kd_mmap_unmap.inc` differ from the
`kdmm6` kernel-source manifest; 51 captured sources remain identical. `build-1`
reused the immutable `kdmm5` complete build through a private RAM-backed
OverlayFS view (a temporary writable layer), applying the captured `kdmm6`
changes plus this delta. Kbuild selected 171 compilation steps across the image,
required runtime-module targets and four probes. The new release and kernel
type-metadata dependencies required those 73 runtime modules; this was not a
full configured-module build. One new client was built; four unchanged clients
were reused. The two basic programs and six receipt controls passed once;
expected basic-program error-injection messages remain in their log.

Baseline: `/root/kdlock-kernel-baselines/mmap-kdmm7-20261023`, manifest SHA-256
`51b9c2966d288fde821ea9dddc8f410825dca761b3a099fa3db4ccf434bfab0f`.
Installed-files manifest SHA-256:
`a09245d5d98e1f2e2f0d87298f40eba89ca8f928c68ab6b08e39fd704e34068c`.
Parent `kdmm6` manifest remains
`18f552fca114799bf5d968ce3d790ffd4acfca11da627fccfa1c0127d8f55ca7`.
Probe binaries and hashes remain in guest `probes-1/` and `build-1/result.json`.

Only the new ELF is compressed in
`/root/kdlock-kernel-work/mm-partial-unmap-20261023/identity/vmlinux.gz`:
275,354,622 bytes, SHA-256
`ebf8d6010599e144d664dec34847f2255f723ff2db2699dd32880217164af420`.
`identity-store.json` also records the uncompressed hash. The same identity
directory retains 54 sources, 11 build-identity files and configuration, with
the ELF compressed instead of duplicated. The transition expands regular files
in RAM for strict identity verification. This snapshot is not a full build tree.

One essential transport archive contains new receipts, logs and probe/control
sources, excluding kernel/module binaries:
`bench/results/10.176.26.71/raw/tests/mm-partial-unmap-20261023/collect-1/essential.tar.gz`,
548,620 bytes, SHA-256
`0c1707ac68cc47dd4466da4454094b274b3528842f981a3455538b77834f44fd`.
The same raw stage retains source-host commands, transitions and `final-health.json`.
Final health confirms all 35 frozen inputs unchanged, no test module or temporary
workspace, and idle recovery. Free space was 480,976,896 bytes on root and
215,252,992 on the data filesystem. Existing evidence was neither deleted nor
recopied into new kernel archives; no old archive was rescanned.

## Reproduction and limits

The recorded sequence was `workflow.py prepare`, `build`, `kd`, `recovery`, then
`collect`, once each with attempt 1. All builds and tests ran in the VM; source
edits and static checks ran on `380G10`. [Prebuilt rerun commands](../../../../../tests/kernel/mmap_lock/partial_unmap/README.md#reuse-the-installed-kernel-and-frozen-probes)
use a fresh attempt number and require no repeated build. Documentation changes
require no new live test.

The [resident-range baseline](../mm-range-unmap-20261023/README.md),
[single-page baseline](../mm-populated-unmap-20261022/README.md),
[unpopulated baseline](../mm-unmap-body-20261022/README.md),
[fault baseline](../mm-fault-body-20261022/README.md) and
[advice baseline](../mm-body-20261022/README.md) remain separate references.

The partial tests cover three-page inputs and one-page slices, not other widths
within the 16-page bound or multi-page slices. Supported untouched inputs have
no warm leaf translation: TLB (cached address translation) invalidation was
exercised on the resident fallback and separate whole-VMA smokes, not claimed
for remote partial removal. Forced allocation or post-split errors, the native
maximum-VMA-count error, tree-height growth during preparation, and retained-page
faults concurrent with splitting were not injected. Broader races, memory
pressure, fast page pinning, non-root memory cgroups and oversubscription remain
unvalidated. This stage did not repeat Native controls, full historical API/fault
retry tests, the busy-fourth-page rollback or the five-page-limit baseline cases.
The no-replay error boundary is source reviewed, not fault-injection proven.
General mapping creation, resident partial removal, RT, lockdep, whole-kernel
replacement and all configured modules remain outside the demonstrated scope.
No timing, p95, seven-regression investigation or nano campaign ran.

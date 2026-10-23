# Resident partial munmap and post-split error milestone

Passed: two basic programs, all 23 serial live cases and 110 negative receipt
controls. Seven resident partial removals completed on different tasks; six
delegated post-split errors matched native returns and surviving layouts.
Recovery is restored, all test modules unloaded normally, and the expected 73
runtime modules remain. No live correctness case failed. The initial boot-image
packaging failure and successful packaging-only retry remain separate evidence.
One writer performed the work; no parallel test, interrupted run, nano rerun or
performance campaign occurred. The unrelated cleanup-document change is intact.

## Implementation and scope

Source/probe commit: `df824d9ba35a0fcbc927e71ad3d0413296f731ca`.
Packaging completion/transition commit:
`0eb229fbd641f751fb2c2f83a31032ae57182ce9`.
The new explicit opt-in removes one page from exactly three ordinary resident
anonymous pages, supporting prefix, suffix and interior removal. A VMA (virtual
memory area) describes the mapping; reverse-map links connect pages back to its
VMAs. The caller prepares two links plus the existing split descriptors/reserves.
Under exact mmap writer ownership, the combiner revalidates the VMA, one-link
ancestry, PTEs (leaf page-table entries) and resources, holds all three pages,
then uses native split/adjust/unmap helpers. Surviving neighbor VMAs retain the
page table. Native reverse-map locking and reference accounting are shared.

All refusal precedes effects and retains exact handback/ACK (acknowledgement)
and sticky-local fallback. After splitting starts, errors return directly with
no destructive local replay. Injection after either successful split leaves
harmless splits and all requested pages intact, matching native semantics.
Readers stay local and concurrent. The [maintained scope guide](../../../../../kernel_integration/mmap_lock/UNMAP.md#resident-partial-removal-and-post-split-errors)
explains ordering, allocation dependencies and teardown restrictions.

## Live results: `focused-1`

Guest evidence root:
`/root/kdlock-evidence/10.176.26.71/tests/mm-resident-partial-20261023`.
Each case retains `client.json`, `kernel.log` and, for new cases,
`receipt-controls.json`. `focused-1/result.json` binds their hashes and results.

| Cases | Evidence |
| --- | --- |
| Eight untouched error cases | Native/KD pairs for prefix, suffix and interior after split 1, plus interior after split 2. Four remote errors; `ENOMEM`, layouts and retained pages matched. |
| Four resident error cases | Native/KD interior pairs after split 1 and 2. Two remote errors; exact reverse-map links/counts, page references and contents retained. |
| `resident-prefix`, `resident-suffix`, `resident-middle` | Two remote removals per shape. Removed page inaccessible on each warmed origin CPU; survivors, flags, offsets, mapping/page counts and page-table bytes correct. |
| `resident-refusal` | Busy third page released two earlier holds before one exact handback/ACK; subsequent call stayed local. No remote removal claimed. |
| `resident-cancel` | Queued victim returned `-EINTR` before effects and retained its mapping; prepared resources retired. |
| `resident-free` | Test references released before two real removals, including one remote body; no freed-page dereference. |
| Untouched partial / unpopulated whole / four-page whole smokes | 15 remote removals each; whole resident smoke matched 60 original physical pages and 144 originating-CPU translation checks. Both whole smokes matched 15 ACKs and 16 sticky-local calls. |
| Advice / first-write fault smokes | 1,703 returned advice bodies and 148 real remote page installations, separately recorded; each matched 15 handbacks. |

Native error controls use the ordinary native body with delegation disabled on
the same KD lock backend, not a Native-off boot. No failed operation became a
local retry. The 18 new cases released all 66 test references and completed 102
explicit cleanup calls. Exact prepared-object transfer, reverse-map intervals,
page identities/hashes/references/charges and ownership retirement passed.
Two local readers overlapped; a real untouched surviving-neighbor fault waited
for writer release, then resolved locally. ACKs and local fallback are excluded
from remote-removal counts. All 110 corruptions of real receipt copies were
rejected; those are validator controls, not additional live bodies.

Example: `resident-middle/kernel.log` records mm `ff11000109d44880`, request 2,
origin 1972, executor 1970, range `8000000409000–800000040a000`, original physical
page `35092c`, three holds/releases, empty removed PTE and zero mapcount. Its
split and generic completion match. `error-resident-kd-middle-1` records origin
1942/executor 1941, one split, three holds/releases and `-12`; no replay follows.
`resident-refusal` binds rollback, handback and ACK to origin 1979/executor 1978,
request 2, with two holds/releases and zero effects.

## Build, recovery and artifacts

One incremental Kbuild invocation sequence reused the immutable `kdmm5` build
through a temporary RAM overlay. Shared MM-header/release dependencies selected
3,161 compilation steps, the 73 required runtime modules and four probes;
this was not an all-configured-modules build. One new client was compiled and
five unchanged clients reused. `test_control_call` and `test_daemon_policy`
passed once; expected basic-test error injections remain in their log.

`build-1` compiled successfully but failed installation: `mkinitramfs` exited 1
and produced a truncated 27,889,664-byte image, without a specific cause in its
log. It was never booted and is retained as `install/failed-initrd.img` with a
hash receipt. `package-2` used a RAM temporary directory and the same installed
modules, produced a verified 43,519,515-byte image, and passed. `install-2` and
`build-2` completed from those outputs without recompiling or replacing failed
records. The working initrd SHA-256 is
`60c57f7990a457601a6142338dfd1bb9b4b307e75ec0fc79d3a4e38ffb6fb8f2`.

| Identity | Value |
| --- | --- |
| Candidate | `6.1.159-kdmm8`, Build ID `a68292a16b3fe9dcc5910fc031e3dec1e02c80c5` |
| Candidate boot | `b02b091c-be10-4e2e-a7bd-06bb668e457e` |
| Candidate manifest | `0df168102bab521a0353df31c1029fb950c46f2ebbff37fc7bc4791b436cce64` |
| Installed-files manifest | `d5d021b1735bef7023fe83ad5b3c7f55a9161af5aa6182640644669a7c55d2ec` |
| Parent kdmm7 manifest | `51b9c2966d288fde821ea9dddc8f410825dca761b3a099fa3db4ccf434bfab0f` |
| Restored recovery | `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Recovery boot | `6b0db27d-f0d6-46be-9616-792131c2a2d5` |

The same VM retains 64 vCPUs, 24 GiB RAM, two NUMA nodes, original host pins/QEMU
PID 257489 and snapshot `before-mutex-kdonly-20261017T140354Z`. Recovery remained
the default; its boot files and 5,686 recorded module files are unchanged.
No new kernel faults occurred. Each boot retains the six existing `fd0` floppy
I/O messages. Final health confirms all 42 frozen inputs unchanged, no test
module or temporary workspace, and idle recovery. Free bytes: root 213,962,752;
data 72,650,752. Space remains tight; no existing evidence was deleted.

One essential transport archive, excluding kernel/module binaries:
`bench/results/10.176.26.71/raw/tests/mm-resident-partial-20261023/collect-1/essential.tar.gz`,
608,054 bytes, SHA-256
`487f6477f2a74e9676643ff3b0cb49a45bef8bbf503101e4eb4fe6c856b41af1`.
The raw stage also retains host transitions, commands and `final-health.json`.
The new kernel ELF is stored once at
`/mnt/kdlock-builds/mm-resident-partial-20261023/vmlinux.xz`, 142,588,160 bytes,
SHA-256 `14914f961bd18cfb637613c4cd45bce356d0676f7872b22c58f8e324d4c9a7b2`.
`identity-store.json` records its uncompressed hash. No old archive was rescanned.

## Reproduce and remaining limits

[Working prebuilt commands](../../../../../tests/kernel/mmap_lock/resident_partial/README.md#reuse-the-installed-image-and-probes)
reuse the installed image and probes with a fresh attempt number. The recorded
sequence was prepare, build (packaging failed), package-2, finish, KD test,
recovery and one collection. Source edits/static checks ran on `380G10`; all
compilation and testing ran in the VM. The [kdmm7 result](../mm-partial-unmap-20261023/README.md)
retains prior untouched, whole-removal, advice and fault baseline references.

Mixed resident/untouched pages, multi-link ancestry, shared/COW (copy-on-write),
swapped/huge pages, general table destruction and file/notifier operations still
hand back. Resident coverage is one page of three, not wider ranges or general
mmap support. Prepublication allocation failure, resident edge-error injection,
maximum-VMA-count/tree-height failures, fork ancestry, fast page-pinning races,
reclaim/non-root memory-cgroup pressure and oversubscription were not tested.
Errors were injected before destructive removal; no post-destruction recoverable
error path was invented. Native-off controls and the full historical API/retry
suite were not repeated. RT/lockdep/whole-kernel replacement remain unvalidated.

Next smallest useful step: admit untouched retained pages around a resident
target within the same three-page VMA, holding only present ordinary pages and
preserving exact per-slot checks and current table/ancestry exclusions. This
removes a population restriction without raising the size limit. Performance,
p95, the seven mutex regressions and nano work remain deferred.

> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Mixed resident/untouched partial munmap milestone

Passed: two basic programs, all 22 serial VM cases and 153 negative receipt
controls. Eleven mixed-page removals completed on different tasks. Recovery is
restored, test modules unloaded normally and the expected 73 runtime modules
remain. No live correctness case failed. A storage-capacity check failed after
successful compilation/installation; completion reused those outputs without
rebuilding. No performance, p95, mutex-regression or nano work ran.

Implementation/probes: `52ad1980362efcfcf9c4505b75bd1b34baf2413b`.
Storage completion: `076392a`.
One writer handled MM files. Unrelated TCLock edits appeared during preparation;
the user explicitly authorized continuing while preserving them. MM tests ran
serially, and no in-flight run was interrupted. The unrelated cleanup document
and other task changes remain untouched by these commits.

## Scope and execution

The existing resident-partial opt-in now permits absent retained PTEs (leaf
page-table entries) around one resident target in an exactly three-page anonymous
VMA (virtual memory area). The walker retains page references at their original
VMA offsets, skips only absent survivor slots, and verifies every resident page
before splitting. A later refusal releases precisely those held slots before
the existing handback/ACK (acknowledgement) and sticky-local fallback. Caller
preparation, reverse-map links, physical ownership and queue retirement are
unchanged. After splitting starts, errors return directly without local replay.

Native split/unmap/TLB (cached translation) teardown runs on the combiner.
Removed pages must be unmapped, resident survivors must retain their original
physical pages, and untouched survivors must remain absent through completion.
Only `mm/kd_mmap_unmap.inc` differs from the `kdmm8` kernel-source manifest.
The [scope guide](../../../../../kernel_integration/mmap_lock/UNMAP.md#resident-partial-removal-and-post-split-errors)
defines the retained allocation, ancestry and page-table restrictions.

## Results: `focused-1`

Guest root: `/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023`.
Each case retains `client.json`, `kernel.log` and applicable receipt controls;
`focused-1/result.json` binds their hashes and outcome. R below denotes an
ordinary resident page; U denotes an absent PTE.

| Cases | Result |
| --- | --- |
| `mixed-prefix`, `mixed-suffix`, `mixed-middle` | RUU/UUR/URU, remove the resident page. Two remote bodies per shape. |
| `mixed-left`, `mixed-right` | RRU/URR, remove the middle page. Two remote bodies each; exact resident-survivor contents and physical identity preserved. |
| Four `mixed-error-*` cases | Native/KD pairs after either interior split. Two remote errors matched native `ENOMEM` and harmless split layouts; no replay or lost surviving mapping. |
| `mixed-refusal`, `mixed-zero`, `mixed-missing` | Busy final page, shared-zero-page survivor, or missing target. Each released one earlier hold, matched one handback/ACK and kept the next request local. No remote removal counted. |
| `mixed-cancel` | Queued fatal cancellation returned `-EINTR`; victim mapping and prepared-resource retirement correct. |
| `mixed-free` | Test references dropped before real removal; one remote final-release body, without dereferencing freed pages. |
| Fully resident success/rollback/error smokes | Two remote removals; one exact rollback/ACK; one admitted post-split error. |
| Untouched partial / unpopulated whole / four-page whole smokes | 15 remote removals each. Whole resident case matched 60 physical pages and 144 origin-CPU translation checks. |
| Advice / first-write fault smokes | 1,771 returned advice bodies and 139 real remote page installations, separately recorded; each matched 15 handbacks. |

The 14 new cases released all 46 test references and performed 102 explicit
cleanup calls. Sparse pins and independent PTE observations proved that setup
did not populate untouched slots. A real fault inside an untouched survivor
waited behind writer admission and resolved locally after release. Retained
resident bytes, zero-filled survivors and subsequent writes all matched.
VMA bounds/flags/offsets, mapping/page counts, page-table bytes, reverse-map
ownership, exact references and TLB checks passed. Readers stayed concurrent
and local. Local heads, fallback, cleanup and injected errors are excluded from
successful remote-removal counts. Native error controls use the ordinary native
body on the same KD backend with delegation disabled, not a Native-off boot.

Example: `mixed-middle/kernel.log` binds request 2 to mm `ff1100010aeb1d00`,
origin 1923, executor 1925, target `8000000009000–800000000a000`, physical page
`349877`, resident mask 2, untouched mask 5 and one held/released reference.
`mixed-zero` binds zero-effect rollback, handback and ACK to request 2,
origin 1955/executor 1954, with one earlier hold released. The 153 corruptions
of real records were rejected, including invented PTEs and incorrect slot masks.

## Build, recovery and evidence

The available complete build is the immutable `kdmm5` tree; its temporary RAM
overlay reconstructed the captured `kdmm8` changes and this one-file delta.
Kbuild selected 3,161 compilation steps because of those shared-header/release
dependencies. Only the 73 runtime-module targets and four probes were built;
six clients were reused and one new client compiled. Both basic programs passed
once. Standard Kbuild debug stripping before module signing reduced new installed
modules to 13,676,778 bytes; kernel configuration and VM policy were unchanged.
Initramfs packaging used RAM temporary storage and passed.

`build-1` stopped at the storage check: its 142,582,604-byte compressed ELF could
not fit on either disk alone. `build-2` completed using the exact existing image
split into 104,857,600- and 37,725,004-byte parts on root/data, verified separately
and as one stream. Reconstruction matched the captured uncompressed ELF before
temporary build cleanup and again on the candidate boot. No prior evidence was
deleted, and the failed record remains separate.

| Identity | Value |
| --- | --- |
| Candidate | `6.1.159-kdmm9`, Build ID `e33aeaba03177030ec750342593246d18908c776` |
| Candidate boot | `8a43a007-19db-47b2-a839-92a72c9645c2` |
| Candidate manifest | `645b72e4065136f3833be20e530293b46226f7c34d4aaa1b759ace051e45ce2f` |
| Installed manifest | `8d19a52f4f623381bbbfa832885d0e8223fe87ddda6d3388bb0ebe69fbfe237f` |
| Parent kdmm8 manifest | `0df168102bab521a0353df31c1029fb950c46f2ebbff37fc7bc4791b436cce64` |
| Restored recovery | `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Recovery boot | `5f8867b5-bc87-4cde-8bb6-b9c1546419bf` |

The original 64-vCPU/24-GiB/two-NUMA configuration, host pins, QEMU PID 257489
and snapshot `before-mutex-kdonly-20261017T140354Z` remain. Recovery stayed the
default, with its boot artifacts and 5,686 module files preserved. Final health
confirmed idle recovery, all 46 frozen MM inputs unchanged, no test module or
temporary workspace, and no new kernel faults. Existing `fd0` floppy I/O messages
remain in the boot logs. Root/data free space was only 10,895,360/13,078,528 bytes;
another candidate installation requires a storage plan first.

One essential archive:
`bench/results/10.176.26.71/raw/tests/mm-mixed-partial-20261023/collect-1/essential.tar.gz`,
603,140 bytes, SHA-256
`58be34e1185184da90739b55a9bae8e7fad181a31422cab4d55d82d6ad475071`.
The same raw stage retains transport/transition receipts and `final-health.json`.
`/root/kdlock-kernel-work/mm-mixed-partial-20261023/identity-store.json` records
the part paths/hashes and reconstructed ELF hash. Combined compressed SHA-256:
`42848e715ca50b963ba08e07830ca9d05cfaaa9c19fc8ad5edd2b64920e24143`.
Old archives were not rescanned or duplicated.

## Commands and limits

[Prebuilt commands](../../../../../tests/kernel/mmap_lock/mixed_partial/README.md#reuse-the-image-and-frozen-probes)
reuse the installed image and probes with a fresh attempt number. This run used
prepare, build, storage completion, KD test, recovery and one collection.
All builds/tests ran in the original VM; source edits/static review ran on
`380G10`. The [kdmm8 result](../mm-resident-partial-20261023/README.md) retains
the fully resident, untouched and earlier MM baseline references.

The target must remain an ordinary resident page. Zero-page survivors,
multi-link ancestry, shared/COW (copy-on-write), swapped/huge pages, missing
table-retaining neighbors, file/notifier operations and general mapping creation
remain unsupported. Mixed edge cases with one resident survivor, wider ranges,
allocation-pressure and broad reader/fault/fast-pinning races were not directly
tested. Native-off controls and historical full API/retry suites were not repeated.
This is a narrow functional extension, not general mmap support or performance
acceptance.

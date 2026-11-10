# Kernel3 observation build — 2026-11-10 UTC

The 30 requested core object targets and the ordinary `bzImage modules` build
both returned **0** for `7.0.0-38-kdrebuild3`. The final receipt phase is
`BUILT_AND_LINKED_IDENTITY_VERIFIED`. Build orchestration through linked identity
collection took 263.549 seconds; both make commands stayed within their shared
900-second budget.
This record establishes compilation and linked metadata, not installation,
boot, fixture execution, protected JIT completion or recursive delegation.

The build used source snapshot `69ba6b030c1eb7e5f1c3f9461b70f5fef6791309`,
with core observation changes at `1b50e37382d2c739b16953027c47d7e2388562f0`.
All 66 package inputs match the committed manifest; the prior 64 inputs are
bound to kernel2 `81feb2d749ebbca468c0ab2eb895dcdd82fe519e`. Five existing C
files and `Kbuild` changed, and `kernel/observation.c` and `.h` were added.
The shared canonical source state and lock decisions were preserved.

The source and output roots remained separate under
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/{source,build}`.
The first make named 27 C and three assembly object targets with `-j8 V=1`;
unchanged targets could remain up to date. The full build used `-j32` and the
normal kernel compiler/assembly/mitigation flags. No full correctness suite ran.
The exact configuration, 30 normal command files and both complete logs are
retained here; large text records use lossless gzip with raw hashes and sizes.

The actual results are [build/result.json](build/result.json) and
[build/final-identity.json](build/final-identity.json). The latter has SHA256
`17bea6450bf0eb3b0b0be682389276e556b9042c85034336e9120ba988d85d6f`.
It records all 14 final output identities, 6,901 modules and actual module
vermagic `7.0.0-38-kdrebuild3 SMP preempt mod_unload modversions`.

| Artifact | SHA256 or identity |
| --- | --- |
| `vmlinux` | `c099d66949ba99bc0ec200ef1570cc2917e7b8a3eb0acdd97811333247d2a43d` |
| GNU BuildID | `264a4ef8e55952e5d9ceccf93f65f25f05a50c1f` |
| `.config` | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| `System.map` | `e7723218a35731108e2a1ae4ea1b33942fe7c1e44cc6671bc9345f08222c4d22` |
| `Module.symvers` | `fea56b69a34cf90d5fb7b3b35b47d94e2bcb8afe23609351134a2f4d10964bad` |
| `bzImage` | `582e7b7b7be00fe9ba6f373ed25ad27864a13949c0bff1d7fa466271d479733e` |

The fresh GS witness is in [build/gs-config.json](build/gs-config.json) and its
actual function disassembly. At `0xffffffff814f8771`, the linked instruction
bytes are `65 48 8b 05 9f 68 f1 02`; adding the signed displacement to its
next IP gives full `current_task == const_current_task == 0xffffffff8440f018`.
The bytes were independently reread through the actual ELF LOAD segment.
`__per_cpu_start` is `0xffffffff843f7000`; it was not subtracted from the GS
input. These are fresh kernel3 link observations even though the symbol values
equal kernel2's. Running-kernel identity and module relocations remain separate.

[diagnostics.json](diagnostics.json) indexes the complete raw log diagnostics.
The targeted core log has zero warning lines. The full log preserves four
handwritten assembly mitigation warnings, the existing `kd_jit_resume_origin`
fallthrough warning and the vendor `ubuntu-host` missing-description warning.
It also preserves 21,192 Perl locale warning lines. Locale overrides were
requested by the outer helper; vendor subcommands reported `LC_ALL` unset.
Warnings were neither removed nor counted as runtime validation.

Before the overlay, the inactive kernel2 witness was independently copied to
`receipts/retained-kdrebuild2-81feb2d7-20261110-UTC-01`. Its actual retention
manifest has SHA256
`ac0a6e0ee74abb3fba101be5532806b3aa5d237a8969273ef031f60a74ac85c9`.
It reports 14 build artifacts, 64 package sources, 10,346 verified generated
archive members and 121 receipts, totaling 574,183,906 retained logical bytes.
The manifest, journal, generated member index, helper/controller and fresh QEMU
snapshot/headroom receipt are retained under `kernel2-retention/`. The retained
ELF, generated archive and other full build outputs stay in the VM.

The final helper check observed the unchanged normal `7.0.0-38-kdlock1` boot
`ca0b717b-c19d-4027-b598-6a1cf58b93d2`, taint 0, no active build/fixture or KD
devices, unchanged installed boot/default hashes, unchanged six vendor/hook
source hashes, unchanged 66 frozen inputs and more than 10 GB available on the
build filesystem. This was the build window's completion check, not a claim
about later module builds or installation operations.

[remote-index.json](remote-index.json) independently hashes all 63 copied VM
files, totaling 11,546,801 raw bytes. [copy-index.json](copy-index.json) maps
each retained raw hash to its exact or losslessly compressed local file and
also indexes the source-host provenance copies. `SHA256SUMS` indexes all local
evidence files except itself. Collection used receipt reads, hashing and
compression only; it did not rerun a build or test. Some normal command/log
bytes contain literal control characters or trailing spaces; compression
preserves them without rewriting the captured output. The staged whitespace
check reports 37 trailing-space lines in the two raw GNU `readelf` note dumps
and the raw `modinfo` vermagic output; those captured bytes remain unchanged.

# Kernel8 saved completion and boundary checker receipts

Two separate source snapshots passed directly affected checks in the VM. These are synthetic saved-record/compiler-boundary tests and Python syntax checks. They establish no live MM/JIT execution, physical-context equivalence or performance result. Compiled modules remain at fixture `140aecc4`; the kernel core remains `0d42063e`.

| Source snapshot | Actual checks | Result SHA256 |
| --- | --- | --- |
| `b2ef338b` with 142 source files | 12 completion checker cases, zero skips, MM runner AST1 | `976c0acca562fe01f396cc6dbec006c6677f2bb3ae3cc0e4b81c100234011e22` |
| `a99186a5` with 143 source files | 9 source-boundary cases, zero skips, managed-killable runner AST1 | `e4f76bb7ba3f50a4fcb8da57c1a3c478cb3c4dae748dd3bb546a48f05a674f6a` |

All four command return codes are 0. The first batch checks synthetic successful mmap/retained-munmap shapes and rejects cross-slot/owner reuse, early handback, mismatched query reentry, premature physical ACK and malformed producer/ELF data. Its ELF files and scalar events are synthetic. The second batch preserves the eight existing boundary cases and adds a SourceFrame → shared CALL scanner → fragment case using actual GNU objdump on finite data bytes. It checks prefixed SPECIAL pre-CALL cuts, registered-entry precedence and an unchanged ordinary callee. No emitted machine code is executed by these tests. AST1 records syntax only. [Offline audit](audit.json)

Both batches record boot `e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0`, release `7.0.0-38-kdrebuild8`, taint 4096, only `nls_iso8859_1` loaded and empty activity before and after. All 16 pinned kernel outputs agree across the two receipts. The kernel8 linked GS checks and native API/syscall results have separate receipts. [Affected build and GS checks](../kernel8-affected-build-20261111/README.md), [native API and real syscall evidence](../kernel8-native-api-mm-20261111/README.md)

The first collection is complete with 155 guest payloads totaling 3426990 bytes. Its before/after identities, original copy index, all 155 raw transport members, source snapshot, controls and logs remain. The second batch retains three explicitly read guest receipt/log files totaling 114805 bytes, their read index and encoded transfer, full 143-file source archive/manifests, and every file from its closed source-host control directory. No second complete guest collection is claimed. The two source archives remain distinct. [Origin index](origin-index.json)

The earlier refused `b2ef338b-01` export is preserved with its original source.tar. Its directory contains only that archive. The accepted export receipt records that its expected changed-path list omitted two reviewed README changes and that refusal preceded state/manifest publication and VM transfer. That archive has the same bytes as the later accepted source.tar. This is an export-preparation refusal, with no test or runtime outcome assigned to it. [Refusal metadata](audit.json)

Large captures use deterministic lossless gzip. The origin index records every original and stored size/hash, source path and identity. `audit.py` uses only the standard library to check decompression, complete first-collection membership, both regular-only source archives and manifests, actual command logs/counts, the second read envelopes, source identities and saved poststate. It executes no controller or project code. The detailed copy counts and storage extents are retained in `audit.json`. [Audit source](audit.py), [checksums](SHA256SUMS)

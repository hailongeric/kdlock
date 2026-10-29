# Kernel critical-section semantic audit — October 30, 2026

**Analysis only.** This record binds the
[maintained per-lock map](../../../../../docs/design/kernel_cs_semantics.md) to
exact inspected KD and Linux inputs. It records no implementation, build, test,
translator execution, new lock profile or performance measurement. Read-only
VM file capture and host static source/ELF inspection were performed; there was
no synchronization, module load, kernel modification or reboot.

## Identities

| Input | Identity |
| --- | --- |
| Maintained KD | `24b7a80591a3c8367398cc7375ae0c5952069bfb` |
| Unpromoted READY-first candidate | `2dbcd7afbf141dd63dcf0086b65fd0da4b32d6f7`, `work/mutex-ready-first-20261029` |
| Native source | Authenticated Ubuntu package `linux=7.0.0-38.38`, upstream 7.0.14 |
| Captured normal kernel | `7.0.0-38-kdlock1`; CONFIG_KDLOCK_MMAP unset |
| Build ID | `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` |
| Boot at both Linux source captures | `677b7afa-5358-4ece-a650-5f4a4adecd55` |
| Schema-2 manifest SHA256 | `1d65f61df1be4ab03e358b456d67165d5c9bdc3edd50cf8f15ad651281feca17` |
| Configuration SHA256 | `91b6b86611ee18b4c3ef093c9d95cbd135a092602b4546abf762efcf3c0a2aed` |
| will-it-scale reference | `75f66e45697e6f5f49c33dd950c4e6b289198f8f`; fetched reference only, not a measured revision |

Candidate waiter/ownership changes have not been promoted and do not add
real-API/MM execution evidence. The installed October 27 local MM adapter,
older real-API catalog generations, maintained provider and candidate provider
must not be pooled. Candidate MM preparation generation also differs from
master even though the reviewed Linux7 patch and rwsem sources are unchanged.

## Inspection records

- [Real APIs](real-api.md): seven workloads, exact native acquisition/body/release,
  all-object participant examples, adapter differences and retained observations.
- [MM](mm.md): mmap/munmap, per-VMA/read fault paths, individual PTL sections,
  folio, anon-vma and mapping rwsems; mandatory versus conditional operations.
- [JIT/context](jit-context.md): actual CALL/instruction exits, marker lifetime,
  Native-inner learning, context fields and the PAUSE alias/emission defect.
- [Evidence manifest](evidence.json): archive and per-file hashes, original
  source/build/dependency locations, reference files and audit-note hashes.
- [API object sites](real-api-objects.json), [MM object index](mm-objects.json)
  and [native PAUSE sites](native-pause-sites.json): existing ELF observations,
  not newly emitted or executed KD images.

The core capture contains 205 files; the supplemental capture contains 27, with
matching hashes for every overlap. Every captured file was checked against its
transfer manifest. Twelve available pristine files also match the maintained
`kernel_integration/linux70/mmap-base-sha256.json`; its five uncaptured paths
remain explicitly listed. The seven recorded native MM bodies match pristine
bytes. This is a bounded subset comparison, not a fresh full-kernel source/build
replay. The prior port archive's redacted/incomplete provenance is not silently
restored by this capture.

The supplemental request for `include/linux/mmu_gather.h` found no such file in
either source tree; both missing paths remain recorded. The relevant captured
interface is `include/asm-generic/tlb.h`. Missing files are not test passes.
Decoder `arch/x86/arch.py` and `core/cpu.py` were read as source bytes only,
without importing or executing the dependency.

Native `.o` offsets precede final linking and runtime alternatives/static-call,
paravirt or ftrace patching. They establish emitted instruction presence and
branch structure, not live branch frequency. The PAUSE defect is established
by the decoder's prefix/alias selection and KD's NOP emitter; no new generated
execution test was performed. It does not attribute a previous nano regression
to PAUSE or to parking.

## Raw retention and path interpretation

Raw archives, upstream reference C files and API disassembly slices are retained
outside Git at:

`bench/results/10.176.26.71/raw/tests/kernel-cs-semantics-20261030/`

The MM object index also names and hashes the complete raw function-excerpt
JSON; its selected instruction lines are a compact index, not the full graph.

The manifest names and hashes each capture archive. Audit-note `/tmp/` paths are
the actual inspection locations, not required installation paths: core source,
pristine, build and identity trees are archive members of
`kdlock-semantic-source-20261030.tar.gz`; supplemental members are in
`kdlock-semantic-extra-20261030.tar.gz`; the two decoder files have their own
archives. R/ repository references and line numbers use the stated source
commit. Notes are fixed source-specific evidence, not additional maintained
instruction guides.

No exact Linux 7 will-it-scale hotspot ranking was observed. The selected API
objects have intentionally constructed contention; older returned-body receipts
remain scoped adapter evidence. MM candidates are identified from code, with
the older shared-device/private-backing measurements explicitly separated.
The next implementation decision must not turn these feasibility inferences
into a claim of general lock replacement, delegated reads or performance parity.

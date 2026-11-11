# Kernel4 atomic spin build — 2026-11-11 UTC

The 30 requested core object targets and the ordinary `bzImage modules` build
both returned **0** for `7.0.0-38-kdrebuild4`. The final receipt phase is
`BUILT_AND_LINKED_IDENTITY_VERIFIED`. Build orchestration through linked
identity collection took 288.190 seconds and ended at 02:05:58.908 UTC.
Runtime behavior, mitigation coverage and T01–T56 acceptance require their
separate receipts.

The source and core commit is `2d0ad60b0bc46929f3070aefa364e710c0a81115`.
All 67 frozen package inputs were checked before and after the build. Of
these, 27 inputs differ from kernel3, including the new
`include/kd_spin_api.h`. The build uses the existing isolated source/output-separated pair
under `/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/{source,build}`.
The normal flags, configuration and `KERNELRELEASE`-specific build commands are
recorded with the exact invocation. The two make commands shared a 900-second
budget and 4 GB build-space floor.
[Controller command](controller/controller-command.json).

The targeted command named 27 C and three concrete assembly objects with
`-j8 V=1`. The full command used `-j32`. The final identity records 6,901
compiled modules and actual vermagic
`7.0.0-38-kdrebuild4 SMP preempt mod_unload modversions`.
Installation and boot have their own
[record](../kernel-install4-20261111/README.md).

| Artifact | SHA256 or identity |
| --- | --- |
| Linked Build ID | `f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053` |
| `vmlinux` | `310df27ab801ecb0cb291d510a77d491030b6c85388a3930df2f54306bc27dd5` |
| `.config` | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| `System.map` | `5832a5f64db2100543972a9f97e1d7b969f746a4bafed04ec04f04c8f5484c78` |
| `Module.symvers` | `e4b9faad85933d5f3ffbcb70313fc6416135df4587fdd63cc363e1d6a620192b` |
| `bzImage` | `d89fead1a6d3a7ad573e530eb29b460754655c67b05c49780a43dc88d653afbf` |

The final result SHA256 is
`e00db7a5961879692c102a00e072c70ffc5fcbe1c5051a4203b256ea44a7cac1`.
The 14-artifact identity SHA256 is
`7c79198ee04da92873339bc5d02bd9cba47ac14598f13bf56baf25ce36c69a5c`.
The fresh GS instruction at `0xffffffff814f9ec1` has bytes
`65 48 8b 05 4f 51 f1 02`. Its linked effective address is full
`current_task == const_current_task == 0xffffffff8440f018`, with
`__per_cpu_start == 0xffffffff843f7000`. The actual ELF LOAD bytes and signed
relative arithmetic are recorded in the linked metadata. [Final identity](build/final-identity.json),
[GS witness](build/gs-config.json).

The complete logs and diagnostic index preserve all warning lines. The core log has zero. The full log has 21,201, comprising 21,192 Perl
locale lines, eight objtool lines and one vendor missing-description warning.
Objtool reports the four mutex/spin entry naked returns, the native-resume
naked return, the mutex entry indirect call, the existing JIT-resume
fallthrough and unsupported stack-pointer realignment in spin-native resume.
The logs retain these diagnostics and normal mitigation flags. The outer controller requested `LC_ALL=C`. Vendor Perl diagnostics report
their actual subcommand locale state. [Diagnostic index](diagnostics.json).

Before output reuse, kernel3 was independently retained at
`BASE/receipts/retained-kdrebuild3-1b50e373-spin-01`. Its
manifest SHA256 is
`a253bc04061422153b89c6496494ac12f45b4b49c5f6cb8689f8a1810ca3ff4b`.
It records 14 build outputs, 66 package sources, 10,346 generated archive
members and 199 receipts, totaling 612,161,618 retained logical payload bytes.
The manifest records independent copy identities and successful reread checks.
The ELF, generated archive and source payload stay at their exact VM paths.
The helper, generated member index, journal and actual recovery/space receipt
are retained here. Its outer SSH return-zero observation is transcript-only.
The saved manifest and journal independently record completion.
[Retained kernel3 manifest](kernel3-retention/manifest.json.gz).

The build's final idle check observed normal `7.0.0-38-kdlock1`, boot
`884c4a65-4f4c-4a6b-89a3-cefd65221615`, taint 0 and empty build/fixture/device
activity. Its installed boot-file comparison matched the pre-build inventory.
These are the build window's observations.

The remote index independently inventories all 89 copied VM files, totaling
12,020,013 raw bytes. The copy index records raw and stored hashes, including
losslessly compressed logs/member indexes and exact source-host provenance. `SHA256SUMS` covers retained local
files. Collection used completed receipt/configuration reads and source-host
compression. The actual invocation and copy-program bytes are retained.
[Remote index](remote-index.json), [copy index](copy-index.json).

The raw ELF-note/vermagic output and normal command records preserve 67
trailing-space lines. Their captured bytes are retained for hash equality.

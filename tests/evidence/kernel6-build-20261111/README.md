# Kernel6 full build and linked-image identity

The isolated Linux7 candidate is `7.0.0-38-kdrebuild6`, core532b68a6 with
installer/source3512f5dd, at
`/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/{source,build}`.
[Focused compilation and baseline checks](../kernel6-focused-20261111/README.md)
precede this stage. The active guest remained normal7.0.0-38-kdlock1,
boot51b49fa4-4d99-457e-a73e-632b690eb95e, taint0; these are offline builds.

The [original build receipt](compile/payload/receipts/result.json) records
ordinary bzImage0 in289.4957s and the single required NLS module0 in3.7637s,
using16 jobs, a fresh output tree and normal flags. Fresh Module.symvers rows
matched vmlinux.symvers, and the explicit one-module order was written. Only
the required NLS module was built; the full configured modules target was not run.

That original receipt remains FAILED_OR_INCOMPLETE because an overly broad log
regex matched a GCC command containing both `vmlinux.export.o` and
`-Wmissing-declarations` at kernel.log22969. Its exact sole match was recipe
text, with SHA f1d77431e68e04f4023f30533065f5acfc98496ee40a5b6243533c9420ce57b8,
rather than an unresolved-symbol diagnostic. The complete raw logs are retained;
no passing build was repeated or original failure overwritten.

The separate [read-only metadata result](linked/payload/metadata/result.json),
SHA `240d1a501251cd65ea29ec81f8d8b67f9cb077f6aac5a0011fca1ed922d358f9`,
returned0 after validating the actual two rc0 commands/logs, exact known recipe,
actual diagnostic lines, fresh exports/order,16 built-output hashes and all
source/protected/current-normal identity predicates. It then read the actual
ELF, symbols, notes, module metadata and GS instruction. It performed no make,
source edits, installation, load or boot.

[The linked identity](linked/payload/metadata/final-identity.json), SHA
`995255c9c14c513a356a70ba4155beac0879d37f3abd07ab7afb1fc328c0353b`, records:

- BuildID `5ed6cd8cffed6960ce901261dfab3bb019a0442d`.
- Configuration SHA `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
- Full-VMA current_task/const_current_task `0xffffffff84416018`, percpu section
  `0xffffffff843fe000`; this differs from kernel5 and is not a relative offset.
- Actual GS:RIP witness at `0xffffffff8150114b`, bytes `65488b05c54ef102`.
- its_return_thunk `0xffffffff82751ee0`, bytes `c3cc`; __x86_return_thunk
  `0xffffffff82751ef0`, bytes `c390909090cc`.

All16 exact file pins are in that identity. Actual C warnings retained by the
metadata reader include maple_tree.c frame1088 bytes exceeding the1024-byte
warning threshold and an unused variable in the unchanged AppArmor source.
These warnings were not removed or turned into evidence of stack/mitigation
coverage. Existing handwritten/generated return and auxiliary-context limits
remain separate.

Earlier preflight refusals remain in source-host run records: full-01 compared
NORMAL's54 ordinary loaded modules to the future candidate's NLS-only closure;
full-02 stopped at an unidentified transient idle observation. The former was
corrected to pin NORMAL's actual54-name set, leaving candidate module closure
unchanged; the latter's later clear sample does not identify its original actor.
Full-03 reached the actual build described above. No normal module was unloaded.

This proves scoped build/link identity only. Native strip/sign staging, actual
installation/boot identity, selected API/MM behavior and generated execution
are separate stages. No performance result or broad API/context support follows.

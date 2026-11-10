# Targeted module3 build, 2026-11-11

The actual external fixture build returned **0**, producing
`kd_runtime_fixture.ko` with **528,944 bytes**, SHA256
`bbd3ba41a3c4d4a68efbf24843b291ede0a38ef9223a24e421fe978a94635048`.
This is compilation and metadata evidence only. The build did not sign, install
or load the module, execute its source, publish a JIT image or run a workload.

The [actual result](vm/build-receipts/result.json) records 2026-11-10
18:28:53.986541–18:28:56.989412 UTC (November 11 local date), elapsed
3.0025931400000445 seconds, status `RETURNED`. The build observer had a 180-second
deadline that would have retained an outstanding child; this run returned
normally. Elapsed build time is not a lock-performance measurement.

## Exact inputs and command

The source is commit `9f3279524b41c37fec5e0f29e1fd40975e2b8421`, archived to the
fresh VM root
`/mnt/kdlock-builds/kdlock-main-work/module3-9f327952-01a1bc4f`.
Its [state](vm/source-state.json) and [manifest](vm/source-manifest.json) retain
106 files, a 1,310,720-byte tar and archive SHA256
`48fa2eec9764c62593872c055b2e059c6419047617a99a0c6339a5c602a7e83c`.
The source-host worktree had unrelated maintained-document edits; that status
is retained honestly. The archive contains committed bytes and excludes those
edits. No claim of an entirely clean source-host worktree is made.

[Preparation](vm/preparation.json) compared the input to the checked
`18c8f2e4` snapshot: 104 common files were unchanged; only
`tests/kernel/payload/runtime_fixture.c` and `tests/kernel/run_runtime_fixture.py`
changed. Exact [fixture](source/tests/kernel/payload/runtime_fixture.c.txt) and
[runner](source/tests/kernel/run_runtime_fixture.py.txt) bytes are copied.
All 106 files were verified before and after the build. The VM parsed the changed
runner with `ast.parse`; this records syntax inspection, not execution of it.
The common compiler's earlier 4/12 and separate 5-test receipts remain
[separate evidence](../multi-entry-pipeline-20261111/README.md); they were not rerun.

The [command](vm/build-receipts/command.json) is normal external-module make:

```text
make -C <kernel-source> O=<kernel-build> M=<input>/tests/kernel/payload \
     MO=<fresh-module-build> -j8 V=1 modules
```

The complete [build log](vm/build-receipts/build.log),
[controller output](vm/build-controller-output.log),
[compiler command/dependencies](vm/module-build/.runtime_fixture.o.cmd),
[link command](vm/module-build/.kd_runtime_fixture.ko.cmd),
[module metadata source](vm/module-build/kd_runtime_fixture.mod.c),
[symbols](vm/build-receipts/symbols.txt) and
[modinfo](vm/build-receipts/modinfo.txt) are unedited. Normal target flags include
`-mindirect-branch=thunk-extern`, `-mfunction-return=thunk-extern`,
`-mindirect-branch-register` and `-mindirect-branch-cs-prefix`. No mitigation flag
override was added to obtain a test path.

## Kernel and output identity

The actual build/boot target remained `7.0.0-38-kdrebuild2`, boot
`fb0601dd-db5c-4396-aaa5-e59b91b16924`, with taint 12288 unchanged before/after.
Kernel core source is the separately built `81feb2d7` correction. The four
kernel build-output pins match before and after:

| Artifact | SHA256 |
| --- | --- |
| vmlinux | `7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809` |
| .config | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| System.map | `47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f` |
| Module.symvers | `2533c2a4becc4f99f8dacc38e9480608c9032e4c0f3d06a9b4a2fe51fda6752b` |

These are build-artifact checks, not a new kernel installation or boot proof.
The module's vermagic is `7.0.0-38-kdrebuild2 SMP preempt mod_unload modversions`;
modinfo reports `retpoline: Y`, and no signer field. The separately captured
[read-only ELF header/notes](diagnostic/module-elf-header-notes.txt) identify
x86_64 ELF64 relocatable output, BuildID
`b7b67473915c5659cbb1f1e8a2261f057d999700`. The binary remains at the original VM
module-build path; it is not duplicated in this record.

One existing fixture diagnostic remains: `control_read` has a 2,160-byte frame,
above the configured 1,024-byte warning threshold (`-Wframe-larger-than`). It is
preserved in the full build log and was not hidden by flags or capacity changes.

## Changed fixture scope and unrun limits

The compiled fixture can append actual module-owned ITS executable pages to the
two body/helper source regions, using the existing immutable-text/module hold.
It requires explicit dependency-page and total-source-byte limits. Additional
ordinary helper CALLs give distinct once-only counter checks under B and after
the out-of-order A unlock. The runner retains bounded raw ioctl replies and
distinguishes ordinary CALL/JMP observation, merge, emission, publication-input
and ACK stages. These are source changes and successful compilation; no claim is
made here about actual loaded ITS bytes, indirect-JMP learning, nested JIT
execution or returned protected-body completion.

The earlier [live3 prefix result](../runtime-jit-prefix-20261111/README.md) used
the old module and reached an external target before inner B. This new module
does not retroactively extend that execution evidence. Any new boot/load/run
requires its own actual receipts.

## Collection integrity

[copied-files.json](copied-files.json) binds raw copies and exact Git source to
their original paths, sizes and SHA256; [vm-copy-index.json](vm-copy-index.json)
is an independent read-only VM checksum inventory. `SHA256SUMS` covers every
retained file except itself. Source-host
[archive preparation](sourcehost/kdlock-main-prepare-module3.py.txt) and
[build controller](sourcehost/kdlock-main-module3-build.py.txt) source are retained;
the latter exactly matches the VM copy.

This collector read saved receipts and module ELF metadata only. It performed no
project import, parser check, build, test, module operation or guest control
mutation. Raw tool output whitespace is preserved; authored prose/metadata are
checked separately from those original bytes.

# Kernel-2 cold-allocation rebuild, local 2026-11-11

The new `7.0.0-38-kdrebuild2` build completed `bzImage modules` with return code
0 in 270.040330487 seconds. It ran 2026-11-10 16:26:34.271012–16:31:04.318654 UTC
(2026-11-11 Asia/Shanghai). This records source/input verification and compilation/
linking with warnings. Kernel-2 installation, boot, successful runtime construction,
worker/source/JIT execution, T01–T56 acceptance and performance remain separate.

## Source change and preserved failure

The kernel input set is committed
`81feb2d749ebbca468c0ab2eb895dcdd82fe519e`, based on
`950ee6fc494af2db129911b57f567ac4c5e5d3b6`. Exactly one of the 64 build inputs
changed: `kernel/runtime.c`. The retained old source is `runtime-before.c`, SHA256
`e9ff1fdd21542e3dd87a9b6fe97bd8b7efb0540382d551c983f10192a67cca1c`;
the exact new file is `kdlock-main-81feb2d7-runtime.c`, SHA256
`04a3a5d8337aa9111e3f29e1cb67994d905b00ad0bded23c431b1a9ced74c321`.

All five caller-capacity runtime arrays now use `kvcalloc`; constructor-failure
and final-destroy paths use the ten matching `kvfree` calls. The small runtime
header/native objects keep their original allocation/free route. Counts, checked
arithmetic, zeroing, cold preallocation, exact source/code/fact/native user gates
and active CALL_DEPTH refusal are unchanged. No per-lock allocation or smaller
fixture capacity was introduced. The existing Linux 7 `slab.h` supplies both APIs.

The [failed kernel-1 initialization](../runtime-initialization-20261111/README.md)
retains its real ENOMEM/order-12 warning, taint 12800, exact 950 kernel/15a module/
9d runner identities and absence observations. Its 9 MiB item payload exceeded
that old allocator's permitted physical order. This rebuild does not turn that
failure into a passed initialization or body result.

The raw `retained-v1-manifest.json` records old-kernel preservation before the
offline output changed: `V1_ARTIFACTS_RETAINED`, old ELF/public metadata and all
64 source-input hashes, module absence and installed boot files unchanged.
The retained ELF is 508,210,904 bytes, SHA256
`466907d2a9e392eaa976035595ca99da8e5a8a25653efead677de82cab006db9`.
Its guest namespace is
`receipts/retained-kdrebuild1-950ee6fc` under the candidate root; no ELF/module
binary is duplicated here. Earlier installed-kernel/module protection and the
failure record keep their own exact scopes.

## Normal return, trim and exact controller

`return-normal-after-init-failure.json` is the raw reboot request/context, not
itself a successful reconnect. The [separate actual reconnect](../runtime-initialization-20261111/return-normal-reconnect.json)
observes normal `7.0.0-38-kdlock1`, boot
`5dde9006-ad3c-44eb-81ed-213cd003f31c` and taint 0. The build controller requires
that clean normal kernel, module absence, completed v1 preservation and idle
build/trim state before replacing the offline source. The normal/legacy kernels,
installed kernel-1 payloads and frozen probe inputs are separate namespaces.

The authorized `rebuild2-trim.json` records actual
`fstrim --verbose /mnt/kdlock-builds2`, recorded at 16:21:55 UTC with return 0
and elapsed time 4.3322 seconds,
reporting 13,303,353,344 logical bytes trimmed. It records no deletion and is not
a measurement of host physical reclaim. The collector did not dispatch that trim.

The raw controller is `controller.py.txt`; it is retained source, not executed
by the collector. It verifies the externally pinned 64-input manifest, exact old/
new runtime bytes and every unchanged input, then replaces only the offline
runtime file. The actual argv is copied in `result.json` and remains a distinct
list in the report, with no reused-mode argv alias correction:

```sh
make -C /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source \
  O=/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build \
  KERNELRELEASE=7.0.0-38-kdrebuild2 -j32 bzImage modules
```

Its explicit stop checks are 900 seconds and 4,000,000,000 guest-free bytes,
polled every five seconds. Actual completion returned 0; the last reported guest
availability was 12,222,976,000 bytes. These operational bounds are not runtime
pool/stack capacity defaults or a progress proof. The controller records locale
overrides `LC_ALL=C`, `LANG=C`, `LANGUAGE=C`; actual Perl diagnostics below still
show an unset child `LC_ALL` and other inherited locale settings. Those raw
observations are preserved without claiming the overrides removed the warnings.

## Artifact and current-input readback

`final-identity.json` is the unedited controller/checks artifact/tool/source
readback. `independent-readback.json` is a later read-only verification at
16:57:52 UTC. All **64** current kernel inputs matched the immutable 81feb2d7
manifest, with no mismatches; the generated release was exactly kdrebuild2 and
the actual output contained **6,901** `.ko` files. An actual
`arch/x86/crypto/aegis128-aesni.ko` returned vermagic
`7.0.0-38-kdrebuild2 SMP preempt mod_unload modversions`.
The 64-file set is the defined kernel/header/Kbuild input set, not a claim that
all noncompiled Python/docs in the preexisting copied package were updated.

| Final artifact | Identity |
| --- | --- |
| GNU Build ID | fd2262c047e130787ef669419111eba6eb9ebb2c |
| vmlinux | 508,210,360 bytes; SHA256 7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809 |
| bzImage | 17,183,232 bytes; SHA256 a5fc091793ac0b4dbe9ccb59a390743967d89aa61192eb29e497ac066f356439 |
| .config | SHA256 31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483 |
| System.map | SHA256 47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f |
| Module.symvers | SHA256 2533c2a4becc4f99f8dacc38e9480608c9032e4c0f3d06a9b4a2fe51fda6752b |

Actual linked `current_task` and `const_current_task` remain
`0xffffffff8440f018`, with `__per_cpu_start` `0xffffffff843f7000`. These are
kernel-2 linked-image observations; its new boot and live GS operand require
fresh proof. At independent readback the VM was still on the normal kernel,
boot 5dde9006, taint 0. No kernel-2 boot is inferred from this record.

## Warnings and exact raw receipts

The complete build log has 21,198 case-insensitive warning lines, classified
once per line: 21,192 Perl locale lines, four handwritten-entry mitigation
warnings, one existing JIT fallthrough warning and one Ubuntu module-description
warning. The four entries name the raw returns in `kd_mutex_lock_entry_asm`,
`kd_mutex_unlock_entry_asm`, `kd_native_resume`, and the indirect call in
`kd_mutex_entry_asm`. The fallthrough is
`kd_jit_resume_origin() ... kd_jit_mutex_grant_call()`. These repeated objtool
limits are not fixed by a cold allocator change. No compiler/make error line
matched the retained diagnostic summary; actual return 0 establishes completion.

`diagnostics.json` retains every non-locale warning with original line numbers,
counts of each repeated Perl message, the first full locale context and final
build lines. The complete original 4,636,976-byte log remains in the VM at
`receipts/overlay-81feb2d7/build.log`, SHA256
`ae7054e608dbb1b36cbdf33232a803eb493968041af7cfd794e77c27e0f19a93`.
`build.log.gz` preserves its exact bytes losslessly; copied/raw/compressed hashes
and origins are in `copied-files.json`. Results, identities, controller source,
old/new runtime source, input manifest, retention and trim/request JSON are
unedited copies; the independent readback and warning summary are labelled
derived records. No private signing-key contents or kernel/module binaries are
exported. No VM build/test/install/boot/trim was dispatched by this collector.

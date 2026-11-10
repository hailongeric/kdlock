# Full kernel and active-feature guard rebuild, 2026-11-10

Both selected VM builds completed `bzImage modules` with return code 0. The first
used frozen kdlock source `c6becf81`; the second changed only `kernel/runtime.c`
to the reviewed active CALL_DEPTH refusal at `950ee6fc`. Both produced the
`7.0.0-38-kdrebuild1` kernel and 6,901 modules. These are compilation/linking
results with retained warnings. They do not establish installation, boot, live
mutex/JIT execution, auxiliary-stack correctness, coverage publication/ACK,
performance or T01–T56 acceptance.

The [core/application receipt](../kernel-core-20261110/README.md) supplies the
exact Ubuntu `linux=7.0.0-38.38` plus protected older kdlock1 source identity,
isolated source/output layout, schema-2 baseline pins, integration application,
normal-input protection, configuration and 29 core-object checks. The separately
reported raw argv alias errors in that preparation/application summary remain
part of that receipt; they are not rewritten here.

## Exact build sequence

The source and output directories are:

```text
/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source
/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build
```

Both builds used:

```sh
make -C /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source \
  O=/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build \
  KERNELRELEASE=7.0.0-38-kdrebuild1 -j32 bzImage modules
```

| Receipt | Source | Actual interval UTC | Return | Elapsed |
| --- | --- | --- | --- | --- |
| `full-build-result.json` | `c6becf81987ae29a97000a641d76a0ff2e300860` | 14:41:46.134958–14:57:06.572587 | 0 | 920.436 s |
| `overlay-950ee6fc/result.json` | `950ee6fc494af2db129911b57f567ac4c5e5d3b6` | 15:03:00.710243–15:06:50.900209 | 0 | 230.182 s |

The first controller recorded a 3,600-second bound and a 4,000,000,000-byte
minimum guest-space check; its final reported guest availability was
13,815,136,256 bytes. The second controller verified all 64 package build inputs
against the retained overlay manifest. Only `kernel/runtime.c` differed from the
first build: SHA256 changed from
`dccbc0e7676f4903b34807969e157ad841fa5d570c5df43113557ea108ea4be3`
to `e9ff1fdd21542e3dd87a9b6fe97bd8b7efb0540382d551c983f10192a67cca1c`.
The guard checks `cpu_feature_enabled(X86_FEATURE_CALL_DEPTH)` before runtime
allocation/admission and returns `-EOPNOTSUPP` when active, because that return
thunk changes native-escape flags. Compiled capability remains enabled; no
mitigation option was disabled to obtain the build. The second build explicitly
set `LC_ALL=C`, `LANG=C` and `LANGUAGE=C`.

Both configurations are SHA256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
The actual configuration and GCC/binutils commands are retained in the core
receipt. The rebuild triggered normal module/BTF work as recorded in its log;
its elapsed time is not mutex/JIT performance evidence.

## Artifact identities

| Artifact | First full build | Final guarded build |
| --- | --- | --- |
| GNU Build ID | `c47a4ca310ddc48498096a4e231df72149c7d44e` | `f34c6d56a0f0545790efd04c566dc390cae8d2ae` |
| `vmlinux` SHA256 | `ee019971f99d6b53974b19e7becd559ee9e146bd60ed17fd7ffb535a28c1a838` | `466907d2a9e392eaa976035595ca99da8e5a8a25653efead677de82cab006db9` |
| `bzImage` SHA256 | `01945023f39400fb7626accc69c3fd94bdb6a1dd94a32c5b7a0987041685ab22` | `b3e3ecb331bd163c7a4b97ca6c82f365b07519488b7e499f90dee875d945ddbd` |
| `System.map` SHA256 | `51acdecdc9d282d014882e07f22cc9e21342d28fbc75533c4ae95dfa1e141056` | `47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f` |

`Module.symvers` remained
`2533c2a4becc4f99f8dacc38e9480608c9032e4c0f3d06a9b4a2fe51fda6752b`.
The final independent readback at 15:10:55 UTC found stable hashes during each
artifact read, all 64 package inputs matching `950ee6fc`, and 6,901 `.ko` files.
An actual built `arch/x86/crypto/aegis128-aesni.ko` supplied the vermagic example
`7.0.0-38-kdrebuild1 SMP preempt mod_unload modversions`. One example does not
replace per-module loading or execution evidence.

The raw first identity receipt records an earlier failed metadata attempt:
its collector assumed `ext4.ko`, but ext4 is built in. That `modinfo` failure
occurred before an identity receipt was written; it was not a kernel build
failure or mutation. The retained successful identity uses a real built module.
This note remains unedited in `full-build-identity.json`.

The final linked current-task symbols are recorded as `0xffffffff8440f018` for
both `current_task` and `const_current_task`; `__per_cpu_start` is
`0xffffffff843f7000`. They are linked-artifact observations, not proof of a
future relocated boot or loaded module's GS operand. At readback the VM was
still running `7.0.0-38-kdlock1`, boot ID
`3d32656f-6162-4a0a-9304-bf383d34298d`, taint 0. Later installation and boot
must retain their own identities and checks.

## Warnings retained without a clean-build claim

The complete logs, exact warning lines and line numbers are retained. Counts
below classify each line containing case-insensitive `warning` once; they are
not counts of distinct defects or completed tests.

| Warning class | First full build | Guard rebuild |
| --- | ---: | ---: |
| Handwritten kdlock entry return/indirect-transfer mitigation warnings | 4 | 4 |
| Existing `kd_jit_resume_origin` fallthrough warning | 1 | 1 |
| Vendor/native frame-size warnings | 9 | 0 |
| Vendor/native unused-variable warning | 1 | 0 |
| Vendor fortify compiler-check warnings | 20 | 0 |
| Existing Ubuntu module-description warning | 1 | 1 |
| Perl locale warning lines | 21,201 | 0 |
| Total warning lines | 21,237 | 6 |

The four handwritten-entry warnings name `kd_mutex_lock_entry_asm`,
`kd_mutex_unlock_entry_asm` and `kd_native_resume` raw returns under
`MITIGATION_RETHUNK`, plus `kd_mutex_entry_asm`'s indirect call under
`MITIGATION_RETPOLINE`. The fifth objtool warning is
`kd_jit_resume_origin() falls through to next function kd_jit_mutex_grant_call()`.
They remain limitations requiring their own analysis/validation; ordinary C
compiler flags and the CALL_DEPTH refusal do not establish complete mitigation
coverage. The absence of recompilation-only vendor warnings in the incremental
log does not mean those source warnings were fixed.

The first log retains its failed locale settings and repeated Perl fallback
messages; the second has explicit C locale overrides. Frame-size, unused-variable,
fortify compiler-check and module-description diagnostics are not suppressed or
reported as passes. `diagnostics.json` provides all non-locale warning lines,
locale text counts and zero matched compiler/make error lines. The actual two
return codes establish build completion; this simple diagnostic classifier is
not an additional kernel validation result.

## Raw logs and receipts

The complete original logs remain at the VM receipt paths in `log-index.json`.
After read-only transfer, local gzip level 9 with mtime 0 stored exactly their
original bytes in `full-build.log.gz` and `overlay-950ee6fc/build.log.gz`:

| Log | Original bytes | Original SHA256 |
| --- | ---: | --- |
| First full build | 6,075,232 | `144c8e07d3e0f72eefec19c57a11c9a6eebfd018d9eb649a25f72ac4926fb532` |
| Guard rebuild | 608,236 | `d7e23afa02b4bcfaeffb2a8446a3e7d0f91f5aec954f77c487cdedee380d79b4` |

The index records compressed sizes/hashes as well. An offline readback decompressed
both payloads and matched every original byte, raw size and hash.
`diagnostics-and-final-lines.txt` is a convenience
excerpt, not a replacement. The actual result/input/first-identity JSON files
are unedited copies. `overlay-950ee6fc/final-identity.json` is the independent
read-only final artifact/ELF/module/input receipt; its repetitive diagnostic
arrays were replaced by a reference to the separate complete logs and summary.
No build, test, install or reboot was invoked by this evidence collector.

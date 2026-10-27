# Ubuntu Linux 7 KD port — October 27, 2026

The user-directed cleanup removed retired benchmark records and parts of mixed
source archives. Archival provenance is **REDACTED / INCOMPLETE**. Original
complete-archive hashes and full-source replay claims below describe the earlier
collection, not the current retained subset; retained measurements are unchanged.

This port targets Ubuntu source **`linux=7.0.0-38.38`**, matching the installed
`7.0.0-38-generic` packages. Its development release is
**`7.0.0-38-kdlock1`**. The source package contains upstream version 7.0.14;
the Ubuntu ABI release and upstream version code are recorded separately.
Linux 6.1 is retained only as historical evidence and recovery material.

## Source and implementation

The source archives were authenticated through Ubuntu's signed InRelease,
Sources-index hash and archive SHA256 chain. The separate DSC uploader key was
unavailable locally; no successful DSC-signature verification is claimed.
[Source identities and kernel patch](../../../../../kernel_integration/linux70/README.md)
record the three archive hashes and acquisition receipt.

The pristine guest source is
`/mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0`.
The development source and build are separate directories under
`/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/`.
The source-host inspection copy is
`bench/results/10.176.26.71/raw/tests/linux70-port-20261027/pristine-source`.
Builds and tests run only in the VM.

The port preserves KD physical exclusion, ABI2, source leases, immutable mutex
images, pinned published waiters, exact unlock routing and fail-closed admission.
The mutex remains 32 bytes with total cap 1024 and NUMA boundary 768.
Compatibility changes cover separate Linux 7 module-memory regions, the moved
unaligned-access header and renamed return/call-depth mitigation options.
Five small kernel exports provide the required interfaces. Ordinary Linux spin
macros and native MM bodies remain unchanged.

The optional near-text direct-helper pool stays unavailable under the selected
call-depth-tracking configuration. Existing dispatcher paths remain distinct
from that optional capability; successful module loading alone cannot establish
direct-helper support.

The separate mmap overlay preserves Linux 7 writer sequence-count and per-VMA
ordering. Its acquired asynchronous read token retains the mm until the matching
release completes. `CONFIG_KDLOCK_MMAP` defaults to disabled and is disabled in
the first development kernel. See [MM scope](../../../../../kernel_integration/linux70/MMAP.md).

## Validation record

| Gate | Result |
| --- | --- |
| Source authentication and exact extraction | Passed |
| Basic C checks and directly affected source-lifetime/assembly checks | Passed |
| Linux 7 identity mutation tests and legacy identity regression checks | Passed, 12 + 8 cases |
| Active catalog/nano command plans and runner checks | Passed; no live workload implied |
| Disabled mmap overlay | Five affected objects compiled; native-body hashes unchanged |
| Enabled mmap overlay in a separate output directory | Ten adapter/wrapper objects and six additional native callers compiled |
| Module and probe compilation | 97 retained configurations compiled after affected retries; TCLock emitted-code qualification is separate |
| Full development kernel | Revision 2 passed: source/configuration unchanged during build; first image retained uninstalled after the BPF review finding |
| Installed custom kernel | Image/config/map match the build; 6,901 module copies and initramfs installed; signing repair verified 6,827 signatures and 74 Ubuntu staging exclusions |
| Booted custom kernel | Second boot passed with the expected Build ID, ITS/lazy policy, taint 0 and no kernel errors/failed services; first unsigned-module boot retained |
| Schema-2 identity | Captured and running verification passed; manifest plus all 23 named bundle files independently copied and hash-verified |
| Original-task instruction continuation | Mutex OUTER and spin passed cold delegation, hot native resume with exact effects/flags, terminal ban and post-ban zero delegation |
| Native/TCLock controls | All eight unscored sessions passed: four families × two backends, 80,000 operations each, correct data and complete drain |
| New performance measurements | Not requested or performed |

The first stock-header provider probe correctly failed because stock Ubuntu
does not provide the required spin-clobber ABI. It is a retained failure, not
a successful KD build. Kernel preparation initially lacked `dwarf.h`; installing
the matching `libdw-dev` dependency allowed preparation to pass without removing
Rust or BTF from the stock configuration.

The first Python 3.14 translator checks exposed Miasm 0.1.5's removed `ast.Str`
dependency: five semantic/code-generation drivers failed. Their logs remain
separate from subsequent compatibility checks. Decoder imports alone were
insufficient to establish semantic-lifter compatibility.

The exact [four-site dependency patch](../../../../../disassem/compat/README.md)
restores `ast.Constant` handling with explicit string-type checks. The five
failed drivers subsequently passed 77 cases; six new semantic/type/hash tests
passed. Two fixture setup errors were corrected and retained separately. The
translator now checks the installed dependency bytes before semantic analysis.

Static review after the first full kernel build found that a nested BPF helper
could select the same per-CPU mmap unlock work before its outer caller queued
completion. The initial token did not reserve that interval. The image was not
installed or booted. The correction reserves ownership before callbacks, cancels
failed acquisitions, and keeps the exact upstream BPF path when the mmap option
is disabled. The reviewed correction and subsequent checks have separate receipts.

The first external-module matrix retained 16 compile failures and 13 blocked
comparators. Affected retries resolved GCC 15 pointer typing, missing newline
separators after Linux 7 assembly annotations, removed `no_llseek` and mmap API
changes. None of those failures was counted as a pass. Old phase-probe instruction
addresses remain historical and are explicitly refused at runtime; object-only
compilation is not qualification of their old byte offsets.

The final module metadata audit found all named return/indirect thunk branches
and direct calls represented by their appropriate tables. `CONFIG_KLP_BUILD=y`
delays objtool processing until the composite module link. Existing handwritten
stack/frame warnings and raw returns remain visible. Complete return-mitigation
coverage for handwritten transfers and flat generated wrappers is unvalidated.
Active call-depth tracking is rejected before provider initialization because
its selected thunk would change restored arithmetic flags.

Linux 7 module executable regions can be smaller than the translator's
speculative text lookahead. The decoder retries only a page-aligned mandatory
prefix for EPERM/ESTALE, preserving every old byte and 15 bytes at each new
target. All bytes still require the same source lease. Forty-five boundary
tests include missing roots, holes, truncated instructions, old-byte retention
and resource refusals; none becomes a partial image.

The three accesses to the private lexical outer routing cookie use ordinary C
to avoid unnecessary volatile stack spills and potential aliases in translated
bodies. The polling origin does not access that frame while a delegated body
owns it; lock atomics, exact routing values and all assembly clobbers remain
unchanged. Retained evidence covers the source and lifetime review plus the
standalone poisoned-cookie generated FULL/COMPLETE fixture. The removed
diagnostic workloads and compiled-body admission experiments provide no
retained validation claim here.

The four TCLock acquisition trampolines retain their six explicit register saves
and use function-scoped frame omission so GCC does not add a second stack frame.
Other functions retain kernel frame policy. The rwlock audit binds the complete
R8 argument/return-value flow and both exact PV IRQ relocations. Context fixtures
and negative audit mutations passed, followed by the eight live Native/TCLock
controls. TCLock mutex recorded 78,641 delegated bodies; the other TCLock
families' delegated counts were not measured. These are correctness checks,
not throughput measurements.

The final image has Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` and
SHA256 `8530a19fcca7b3ef65c39aa35ad2e8a46904ded34d124afb2e4f4285f9631d71`.
Its five required GPL exports and Linux version code `458766` were verified.
Final-vmlinux DWARF places `pv_ops.irq.irq_disable` at offset `0xf0`, giving
the exact `R_X86_64_PC32` addend `0xec` for the TCLock context audit.

The first installation printed `SIGN` and exited successfully, but Ubuntu's
non-executable signing-policy hook failed inside a shell conditional. The
initial checks missed those permission-denied diagnostics, and the first custom
boot loaded unsigned modules before KD. Both logs and the signing-failure
correction are retained. The approved repair changed only that development
hook's mode from 0644 to 0744, repeated installation with debug stripping, and
verified every policy-selected module's signer/key/SHA512 metadata. The built
certificate also verified aesni's PKCS#7 signature independently. Ubuntu's 74
explicit staging exclusions remain unsigned. Source contents, kernel artifacts,
original unstripped modules, recovery boot files and GRUB stayed unchanged.
The corrected installed modules total 668,795,275 bytes; the regenerated initrd
SHA256 is `a13aaa736d57c6d9a52e8acea99ee6de42379882f000cbbff857a05de68e0769`.
The subsequent boot `59172bf2-ccd2-49bd-bc1b-fea1d12056a7` verified taint 0,
the expected Build ID, ITS return thunk, lazy preemption, `nokaslr`/`nopvspin`,
and no recorded kernel errors or failed services. This preserves the first
unsigned-module boot as a failed qualification attempt.

Linux 7 also changes API workload identity. Xattr uses a red-black tree and
shared readers (`xattr-rbtree-read-v1`); its KD readers execute locally with zero
JIT-eligible operations. OFD fields use `file_lock.c`, seek no longer writes the
removed `f_version` cookie, and UTS uses the new namespace reference API. The
[workload catalog](../../../../../docs/BENCHMARK_WORKLOADS.md) preserves the old
list-based xattr results separately. Seventeen real-API planning/execution tests
pass, including rejection of JIT activity or missing reader-drain evidence in
the new local-reader path. No new throughput follows from these mocked checks.

## Retained live results

Eight Native/TCLock controls use c01, eight workers and 80,000 operations per
session; reader/writer families use 20% writes. Each passed data and drain checks.
The maintained KD basic presets now use c01 and require new returned-JIT and
drain receipts; no previous-payload result is transferred to them.

The mutex OUTER and spin instruction-exit checks each completed four phases of
160,000 operations. Cold delegated phases returned 158,037 and 158,711 JIT
bodies respectively. Each hot phase recorded one validated original-task escape,
then the entry stayed `NATIVE_ONLY` with zero later JIT bodies. Exact effects,
arithmetic flags, task/context checks and final drain passed. This validates
architectural continuation on the selected ITS boot; it does not establish
complete mitigation coverage for every generated return.

The final guest remains on `7.0.0-38-kdlock1`, with no project modules, kernel
errors or failed services. Taint 12288 records unsigned out-of-tree modules used
by these checks; the signed pre-live boot was separately verified at taint zero.
The new `linux70-kdlock1-clean-20261027` snapshot is retained alongside the legacy
snapshot. Custom Linux 7 is the normal boot default; stock Linux 7 remains a menu
recovery entry.

Actual-MM/page-fault runtime, legacy phase instrumentation, whole-kernel lock
replacement, RT/lockdep/ww_mutex and new performance comparisons remain outside
this validation. The ordinary development kernel keeps `CONFIG_KDLOCK_MMAP=n`.
The near-text direct-helper pool is unavailable with this configuration, and
active call-depth tracking is refused. No Linux 6.1 performance result is promoted
to this platform.

[Evidence index](evidence.json) binds the retained source/build, failure, correction
and live-result receipts by SHA256. It does not merge their source versions.

Raw source, build and test evidence is under
`bench/results/10.176.26.71/raw/tests/linux70-port-20261027/`.
This is kernel-port evidence, not retained OS-upgrade transcripts.
The earlier [OS migration](../vm-ubuntu2604-migration-20261027/README.md)
has its own platform receipt. No Linux 6.1 result is relabelled as a Linux 7 pass.

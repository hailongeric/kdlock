# Linux 7.0 direct-provider prerequisites

[kernel.patch](kernel.patch) targets the authenticated Ubuntu source package
`linux=7.0.0-38.38`. It supplies the small kernel interface needed by the current
direct KD provider. It is independent of the retired Linux 6.1 patch chain and
does not establish KD compatibility before a new build and live validation.

## Source and build identity

The source was acquired through signed Ubuntu Release metadata, its authenticated
Sources index and the exact source-file SHA256 checksums. The source-package
changelog begins `linux (7.0.0-38.38) resolute; urgency=medium`.

| Source file | SHA256 |
| --- | --- |
| `linux_7.0.0.orig.tar.gz` | `c6343795c8c7e4feff55f5b309365c8e0eaf49cd6abcb412e32315313f149536` |
| `linux_7.0.0-38.38.diff.gz` | `98e913d4a1c1f810e4dcfa573cbcf0f1a3a4427bdcd503722555298a794c52b2` |
| `linux_7.0.0-38.38.dsc` | `016d43577bd8a61629a02e140e3b88072b5ccdd1c90cb1ce2f3c8e5c28756e7e` |

The acquisition receipt SHA256 is
`5c5e8a574cf8affb7aedd66e9f609ca006041c1cde0d3fc4e086a4f9849f545a`.
The source-host inspection subset and its per-file manifest remain under
`bench/results/10.176.26.71/raw/tests/linux70-port-20261027/source-subset/`;
the full pristine guest source is
`/mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0`.
The complete source-host inspection copy is the adjacent `pristine-source/`
directory. Keep these inputs separate from the development build tree.

The package's top-level Makefile contains upstream version **7.0.14**, despite
the Ubuntu package/kernel ABI name `7.0.0-38`. The development release is
`7.0.0-38-kdlock1`. Preserve `SUBLEVEL=14` and the resulting Linux version code;
use the explicit packaging-style `KERNELRELEASE=7.0.0-38-kdlock1` selection in
every full-kernel build/install invocation. Verify generated `utsrelease.h`, `kernel.release`
and UAPI `version.h` separately: the release string must identify the development
kernel while the version code still describes 7.0.14. A plain build otherwise
starts with `7.0.14`. Preserve the source package identity separately from the
resulting release string.

Ordinary external-module wrapper Makefiles use the captured build directory as
KDIR and read its existing `include/config/kernel.release`. Do not globally
export `KERNELRELEASE` into those wrappers: many select their inner Kbuild branch
when it is already set, bypassing the outer build target.

This follows Ubuntu's own `debian/rules.d/0-common-vars.mk` release selection:
its `kmake` passes `KERNELRELEASE=$(abi_release)-<flavour>`. Top-level Kbuild
persists a command-line release to `include/config/kernel.release`, uses it for
`UTS_RELEASE` and module installation, and generates the Linux version code
independently. The expected 7.0.14 `LINUX_VERSION_CODE` is `458766`.

All builds, module checks and live work run in the VM. Apply this patch only to
an independent development tree; keep the installed Ubuntu generic kernel and
the single legacy recovery version. Establish a new-platform recovery snapshot,
source/configuration hashes, build ID and module identities before live KD/JIT
work, following [VM operations](../../docs/operations/VM.md).

## Kernel interface

The patch adds five GPL exports:

| Interface | Current use |
| --- | --- |
| `kallsyms_lookup_name` | Source residency boundaries, scheduler I/O helpers, optional per-CPU arena detection and audited hostcall resolution |
| `set_memory_x` | Executable permission for preallocated JIT blocks, before publication |
| `wake_up_q` | KD's local mutex wake queue, including retained task references |
| `kd_raw_spin_lock_clobber_v1` | Explicit native spin caller-clobber entry |
| `kd_raw_spin_unlock_clobber_v1` | Matching explicit native spin caller-clobber release |

The new `linux/kd_spin_hooks.h` provides a real `KD_SPIN_CLOBBER_V1` capability
and its compiler-facing call macro on x86-64 SMP with frame pointers and without
PREEMPT_RT. The native entry arguments are RDI = Linux raw spinlock,
RSI = pre-CALL RSP, RDX = continuation RIP and RCX = caller RBP. The macro keeps
RSP/RBP and declares every other GPR, flags and memory clobbered, matching the
[spin caller ABI](../../docs/JIT_REGISTER_ABI.md#entry-identities-and-packet-states).

An explicit native caller may use:

```c
__kd_spin_clobber_call_v1(kd_raw_spin_lock_clobber_v1, lock);
/* Original caller's protected body. */
__kd_spin_clobber_call_v1(kd_raw_spin_unlock_clobber_v1, lock);
```

These bridges execute `__raw_spin_lock/unlock` with native paired preemption and
unchanged IRQ state. Ordinary Linux `raw_spin_lock/unlock` macros remain
unchanged. There are no global selectors, hook pointers, static-call installers
or removers. KD spin objects continue through KD's own same-ABI module entries;
they must never be passed to the native bridges. KD mutex continues to use its
own ABI2 entries and physical ownership, without Linux mutex backing.

No futex, INT3, legacy mutex slowpath or global-hook exports are added. The
current module-memory and executable-allocation adaptations belong in the
provider. This patch adds no `execmem` exports and makes no near-JIT allocation
capability claim.

## Configuration and validation boundary

The installed Ubuntu configuration already has `CONFIG_FRAME_POINTER=y` and
`CONFIG_UNWINDER_FRAME_POINTER=y`, with ORC unwinding, PREEMPT_RT,
DEBUG_MUTEXES and DEBUG_LOCK_ALLOC disabled. Preserve these required settings;
the ABI guard is not a replacement for checking the complete built configuration.
SMP, module support, KALLSYMS/KALLSYMS_ALL and the matching module symbol-version
identity also remain required.

Start from the captured stock configuration and record the complete result of
`olddefconfig`. The source includes the configured Canonical trusted/revoked
certificate files; there is no need to erase these paths. Its `certs/Makefile`
can generate the configured local `certs/signing_key.pem`. Use a distinct
`CONFIG_VERSION_SIGNATURE` for the development kernel. Ubuntu's amd64
annotations enable Rust and BTF; verify their build dependencies before
configuration regeneration so missing tools do not silently remove features.

Before freezing build inputs, check that the development copy of
`debian/scripts/sign-module` is executable. The authenticated Debian source
extraction supplied it without execute permission. Ubuntu's `modules_install`
recipe invokes that hook inside a shell conditional; a permission failure can
therefore print a `SIGN` label and still exit successfully without signing.
The first installation reproduced this failure and its first boot had taint
8192 before any KD load. Its logs and failed signing gate remain in the port
record. The reviewed repair changes only that hook's mode with `chmod u+x`,
then repeats full-kernel `modules_install INSTALL_MOD_STRIP=1` under the explicit
custom release and regenerates its initramfs. Record the source mode change
separately from unchanged source-content and kernel-image hashes. Verify actual
installed signer/key IDs against the built certificate, retaining Ubuntu's
explicit staging-driver exclusions; exit status and `SIGN` labels are not
signature evidence. A later clean boot is required to recheck taint.

The new Ubuntu baseline has dynamic lazy preemption and no kernel IBT, unlike
the preserved Linux 6.1 measurement baseline. Retain these differences in every
new result identity. Do not pool old and new measurements or claim equivalent
instrumentation. Build success, symbol exports and a boot are separate gates
from ownership, cancellation, source-retirement, returned-JIT and performance
validation. No such pass is inferred from this patch alone.

Native-escape instruction markers require arithmetic flags to survive the
return from their restore trampoline. The provider rejects the active
`X86_FEATURE_CALL_DEPTH` policy before initializing any service: Linux 7's
call-depth return thunk changes those flags. Enabling
`CONFIG_MITIGATION_CALL_DEPTH_TRACKING` only compiles support and does not prove
that the running CPU selected it. Record the selected thunk after boot; the
ITS, Retbleed and SRSO return sequences in this exact source preserve flags.
Keep the restore probes and return mitigations enabled.

This check establishes an architectural restore requirement. Generated
`include/wrapper.S` exits still use raw `RET`, so complete kernel mitigation
coverage for dynamically generated wrappers is not established. The optional
near-text helper pool remains disabled when call-depth support is configured.
The captured configuration uses `CONFIG_KLP_BUILD=y`, which runs objtool after
linking multi-object modules; inspect return, call and indirect-branch metadata
in the final module, not only its intermediate objects. A successful compile
does not establish either complete mitigation coverage or live correctness.

## Separate mmap adaptation

This patch leaves `mm_struct`, native MM bodies and mmap/page-fault behavior
unchanged. The [legacy mmap preparation](../mmap_lock/README.md) hardcodes Linux
6.1 source hashes and applies the retired ancestor hook chain; it is not a
Linux 7 preparation procedure.

The separate [Linux 7 mmap adapter](MMAP.md) preserves writer sequence-count
begin and `vma_end_write_all` ordering, per-VMA locking and original-task
execution. Its preparation script produces a separate overlay, and
`CONFIG_KDLOCK_MMAP` defaults to disabled. In this source, mmap lock initialization
occurs directly in `kernel/fork.c`; `mmap_lock.h` has additional assertions and
per-VMA uses of the rwsem. The adapter's build, asynchronous read-release lifetime
checks and live validation remain separate gates. Any whole-kernel replacement
remains unvalidated on this platform.

The separate [kdscope1 composition](SCOPE.md) combines this core patch, the local
MM overlay and the scoped file-table/pipe API binding in a new source/output
pair. Its two explicit schema-2 profiles preserve the existing development and
MM profiles. API objects default to Native in both MM boot modes; per-object
selection and actual syscall evidence remain required.

# Captured Guest Kernel

This directory records the existing x86-64 recovery guest prerequisite. It does
not modify the guest, install a kernel, add hooks, or fix hook-reader lifetime.
The captured configuration and patch are evidence, not a recommendation to use
this historical kernel on production machines. Rebuilding/installing the guest
kernel still requires separate approval under `docs/AGENTS.md`.

This is the original `6.1.159` baseline, not the current ordinary-spin ABI.
The current provider requires spin and mutex caller-clobber v1 on
[`kdclobber2`](../kernel_experiments/mutex_clobber/README.md) and does not build on this
original kernel; retain this bundle for verification, recovery and reproducing
its historical source versions.
The separate [spin-static](../kernel_experiments/spin_static/README.md) and
[caller-clobber](../kernel_experiments/spin_clobber/README.md) experiments retain
independent source/build trees and external captured bundles. Select the bundle
matching the running kernel as described in [the manual](../docs/PROJECT_GUIDE.md#kernel-identity);
do not overwrite this original capture or delete it as an obsolete artifact.

## Contents

- `linux-6.1.159-guest.patch`: the 13 existing content differences against
  official Linux 6.1.159, not newly proposed kernel changes. Historical comments,
  disabled debugging code and whitespace are preserved to reproduce file hashes.
  The narrow `.gitattributes` whitespace exception applies only to this artifact.
- `guest.config`: the complete captured `.config`, byte-identical to the installed
  `/boot/config-6.1.159`. It includes no signing key material.
- `manifest.json`: archive checksum, 18 patched/interface source hashes, nine
  build-file hashes, installed image/config identities and running uname/Build ID.
- `verify.py`: standard-library-only, read-only checks. It does not download,
  extract, patch, build, load/unload modules, restart the VM or write kernel files.

The source archive is [official Linux 6.1.159](https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.1.159.tar.xz).
Its SHA256, checked against the
[kernel.org checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc), is:

```text
1f207ebe93980829ecc0a18b694816f22b715e9893767731651969a168342b9e
```

The HTTPS checksum was verified; this collection did not verify the checksum
list's OpenPGP signature. Do not claim independently authenticated release
provenance or a bit-for-bit reproducible binary build from this observation.

## Existing Differences

| Area | Captured behavior |
|---|---|
| `kernel/locking/spinlock.c`, `include/linux/spinlock_api_smp.h` | Plain spin hook pointers, saved-stack/caller-IP arguments and out-of-line unlock selection. |
| `kernel/locking/mutex.c` | Plain mutex hook pointers and exported native slowpaths. No `struct mutex` layout change. |
| `kernel/kallsyms.c`, `arch/x86/mm/pat/set_memory.c` | Existing symbol-lookup and executable-page exports used by kdlock. |
| `arch/x86/kernel/traps.c`, `kernel/futex/{core,waitwake}.c` | Historical INT3/futex hook pointers and futex exports, not registered by current kdlock initialization. |
| `kernel/sched/core.c`, `kernel/signal.c`, `lib/plist.c` | Historical `wake_up_q`, `do_no_restart_syscall`, `plist_add` exports. |
| `drivers/acpi/acpi_ipmi.c`, `lib/maple_tree.c` | Whitespace-only differences retained for exact content reproduction. |

The hooks test raw function pointers and call them without a matching module
reader pin or RCU critical section. Setting those pointers to NULL followed by
`synchronize_rcu()` in kdlock does **not** prove safe hot unload. No removal/drain
protocol, source-module pin or owner handoff is added by this baseline bundle.

The complete comparison inspected 78,681 official file/symlink members, with no
missing members. Besides the 13 content differences, one PowerPC selftest
symlink differs only by a redundant `./`; link comparisons normalize that
equivalent spelling. Archive permission differences are not source-content
differences. The source-candidate inventory outside official members contains
5,840 files, predominantly generated module/config/build sources. Those extra
files, compiler inputs outside the tree, signing keys and arbitrary generated
files are not authenticated by the archive-member scan.

## Read-Only Verification

Run in the recovery guest, from `/root/host_fs/kdlock`:

```bash
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
```

Default checks cover the two shipped artifacts, 18 named source/interface files
and `.config`. `--build` adds the nine captured build files, including `vmlinux`,
`bzImage`, symbol maps and generated configuration headers. `--running` compares
release, version, architecture and the GNU Build ID parsed from live raw ELF
notes in `/sys/kernel/notes`; `uname -r` alone is insufficient. Installed `/boot`
hashes are recorded in the manifest as separate observations, not checked by
these options or treated as proof of which image was booted.

For all official source members, provide the already-downloaded archive:

```bash
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 \
  --archive /tmp/kdlock-baseline-linux-6.1.159.tar.xz --build --running
```

The full scan first verifies the archive checksum. Patched files use the captured
hashes; other official members must match the archive. Missing/changed files,
incorrect links, malformed manifests/notes and identity mismatches exit nonzero
with a JSON diagnostic. A successful scoped check is not a full source check.
Neither result proves semantic compatibility, hook lifetime or absence of
unexpected added/generated build inputs. Results are observations, not an
atomic snapshot against concurrent administrative changes.

The observed running identity is:

```text
release: 6.1.159
version: #28 SMP PREEMPT_DYNAMIC Wed May 27 08:20:42 UTC 2026
machine: x86_64
GNU Build ID: 6f9f2e9fec382e97f620553793aa90b527a30af5
compiler: gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
linker: GNU ld (GNU Binutils for Ubuntu) 2.38
```

Relevant captured configuration includes SMP, voluntary preemption with dynamic
preemption support, PV spinlocks, frame pointers, module versioning, strong stack
protection and out-of-line spin unlock. Debug spinlocks/mutexes and debug lock
allocation are disabled. The guest currently exposes 40 CPUs; `CONFIG_NR_CPUS=8192`
is a compile-time maximum, not its online CPU count. Other configurations are
not validated by matching a few of these options.
The observed boot uses `nokaslr` and the runtime preemption selector reports
`none (voluntary) full`. Neither dynamic preemption nor boot arguments are
checked by `--running`; its Build-ID result establishes identity, not the full
runtime execution-context contract.

## Source Reconstruction

Reconstruct only in a separate temporary tree, never over the active guest
source/build tree. The following are source-data operations, not permission to
build/install a kernel; use absolute paths for `BUNDLE` and `ARCHIVE`:

```bash
BUNDLE=/home/eric/vm/vm-shared/kdlock/kernel_baseline
ARCHIVE=/tmp/kdlock-kernel-baseline.SQbmuD/linux-6.1.159.tar.xz
printf '%s  %s\n' \
  1f207ebe93980829ecc0a18b694816f22b715e9893767731651969a168342b9e \
  "$ARCHIVE" | sha256sum -c -
TREE=$(mktemp -d /tmp/kdlock-kernel-reconstruct.XXXXXX)
tar -xJf "$ARCHIVE" --strip-components=1 --no-same-owner -C "$TREE"
git -C "$TREE" apply --check "$BUNDLE/linux-6.1.159-guest.patch"
git -C "$TREE" apply --whitespace=nowarn "$BUNDLE/linux-6.1.159-guest.patch"
cp "$BUNDLE/guest.config" "$TREE/.config"
```

The increment's reconstruction test extracts the 18 named official source
members into a temporary host tree, applies the patch and compares all 18
resulting file hashes plus `.config`. Full-archive comparison separately runs
against the existing guest source. No clean full-tree kernel build or newly
booted image has been tested. Timestamps, build sequence, toolchain and generated
signing material can change a rebuilt binary's identity. A future kernel change
needs separate review and approval, clean build/boot evidence and renewed
hook/register-layout/JIT validation.

At the historical baseline checkpoint, the checker and unchanged-runtime
regressions pass on 158 frozen inputs:
34 unit programs without skips before/after and 16 fresh integrations
(13 actual-JIT / three native-only). Final audits pass at
2026-09-07 20:48:39 +08; evidence and scope are recorded in
[VALIDATION](../docs/VALIDATION.md#captured-kernel-baseline). These are not the
latest matrix results. General C1/C2/C5,
source/hook lifetime and the explicitly deferred C3/C4 semantic work remain open.

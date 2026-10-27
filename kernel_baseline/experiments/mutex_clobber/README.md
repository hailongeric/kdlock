# Ordinary mutex caller-clobber v1

The retained legacy recovery kernel is `6.1.159-kdclobber2`, derived from the
captured `kdclobber1` spin experiment. Ordinary `mutex_lock/unlock` use ABI identity 2;
ordinary spin retains identity 1 and legacy callers retain 0 in this historical
kernel interface. Current KD mutex uses its own object and clobber entry and
does not require `KD_MUTEX_CLOBBER_V1`; see the [current contract](../../../docs/design/kd_only_mutex.md).
The later rwlock writer identity 3 is a provider/JIT addition on this same kernel,
described in [the rwlock guide](../../../docs/design/rwlock_implementation.md); it
does not change the captured patch or Build ID below.

Linux 6.1 development is retired. Ubuntu 26.04 / Linux 7.0 is the user-selected
future adaptation target and remains unvalidated. The
[retirement record](../../../docs/history/kernel-retirement-20261027.md) defines
the single complete legacy version and its preserved provenance. The build and
boot sequence below is historical reconstruction documentation, not a current
installation workflow.

[guest-kernel.patch](guest-kernel.patch) changes only the mutex caller macros,
a new hook header and versioned bridges in `kernel/locking/mutex.c`. RDI carries
the lock, RSI the pre-CALL RSP, RDX the local continuation label and RCX the
caller RBP. The compiler preserves cross-boundary values through explicit GPR,
`cc` and `memory` clobbers and `ASM_CALL_CONSTRAINT`; RSP/RBP remain intact on a
normal native return. The bridge's native fast/slow paths bypass public macros.

Function-pointer calls, explicit nested APIs, IO, interruptible, killable and
trylock retain the original contract. `KD_MUTEX_LEGACY_CALLER` opts a compilation
unit into ordinary legacy calls for compatibility tests. The legacy function
symbols, two-word wrapper args, real Linux mutex owner and owner ACK remain.
Hook installation/removal uses static calls and a serialized update lock; it
still requires the project's existing no-new-callers/drain boundary and does
not add general safe hot unloading.

The [ABI document](../../../docs/JIT_REGISTER_ABI.md#mutex-clobber-and-outer-cookie)
defines MINIMAL/COMPLETE/FULL, node reuse and restoration. The full packet is
preallocated but ordinary entry/completion never initializes or copies it.
Intermediate exits materialize FULL and detach into frame-owned storage before
C services, because owner ACK can outlive the waiter's node reservation.

The historical build/install sequence ran only in the idle recovery guest and
preserved its then-existing trees and boot entries. The retained independent
build is
`/mnt/kdlock-builds/linux-6.1.159-kdclobber2`, linked from
`/root/linux-6.1.159-kdclobber2`; the auxiliary ext4 disk is mounted by UUID.
This recipe assumes the historical parent tree is available and creates a
separate tree. It does not format disks or overwrite an existing tree.

```sh
cp -a /root/linux-6.1.159-kdclobber1 /mnt/kdlock-builds/linux-6.1.159-kdclobber2
ln -s /mnt/kdlock-builds/linux-6.1.159-kdclobber2 /root/linux-6.1.159-kdclobber2
cd /root/linux-6.1.159-kdclobber2
patch -p1 --fuzz=0 < /root/host_fs/kdlock/kernel_baseline/experiments/mutex_clobber/guest-kernel.patch
scripts/config --set-str LOCALVERSION -kdclobber2
export LC_ALL=C
make olddefconfig
timeout 7200 make -j20 bzImage modules
make INSTALL_MOD_STRIP=1 modules_install
cp -n arch/x86/boot/bzImage /boot/vmlinuz-6.1.159-kdclobber2
cp -n .config /boot/config-6.1.159-kdclobber2
cp -n System.map /boot/System.map-6.1.159-kdclobber2
update-initramfs -c -k 6.1.159-kdclobber2
update-grub
cd /root/host_fs/kdlock
python3 kernel_baseline/experiments/mutex_clobber/capture.py \
  --source /root/linux-6.1.159-kdclobber2 \
  --parent /root/kdlock-kernel-baselines/spin-clobber1-20260918 \
  --output /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

`capture.py` refuses configuration differences beyond LOCALVERSION and verifies
the parent bundle before writing a new one. Parent and ancestor manifests have
separate names. Frame pointers, mitigation options and dynamic preemption config
remain unchanged. The captured Build ID is
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`.

The historical boot procedure was to confirm the monitor's recovery snapshot,
select the exact new GRUB submenu entry with `grub-reboot`, then reboot once,
preserving the existing default and recovery entries. After boot, it ran
`python3 bench/spin_cacheline/kernel_identity.py` and rebuilt target modules.
Actual run evidence and remaining limits belong in
[Historical tests/README.md](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#mutex-clobber), not this build recipe.

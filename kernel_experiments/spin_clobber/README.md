# Ordinary spin caller-clobber v1

This is now kdlock's default ordinary spin lock/unlock boundary. The provider
requires `KD_SPIN_CLOBBER_V1` at build time; it no longer installs hooks on the
older pointer/static-only kernels. Legacy callers on this kernel still work.

The verified kernel remains `kdclobber2`; its captured
[mutex extension](../mutex_clobber/README.md) is historical provenance. The following records how its preserved spin parent was created.
Apply [guest-kernel.patch](guest-kernel.patch) only to an independent copy of the
captured `6.1.159-kdstatic2` source/build. Preserve the parent kernel, configuration,
installed modules and baseline. The release is `6.1.159-kdclobber1`; only
`CONFIG_LOCALVERSION` changes. Frame pointers, retpoline, return thunks and IBT
remain enabled. IRQ/BH/irqsave/trylock, explicit nested APIs and mutex keep their
existing contracts. `KD_SPIN_LEGACY_CALLER` selects the old ordinary caller ABI
when compiling comparison modules against the same new kernel.

The new exported bridges accept `(lock, pre_call_sp, continuation, caller_bp)`
in RDI/RSI/RDX/RCX. Their native helpers call `__raw_spin_*` directly, avoiding
macro recursion. A local asm label defines the continuation. The inline asm
declares all other GPRs, flags and memory clobbered, keeps RSP/RBP intact and uses
`ASM_CALL_CONSTRAINT`; the compiler saves live caller values. This follows the
[GCC 11 extended-asm constraints](https://gcc.gnu.org/onlinedocs/gcc-11.4.0/gcc/Extended-Asm.html#Clobbers-and-Scratch-Registers).
The versioned hook installer retains legacy callbacks alongside new callbacks.

All commands below run in the idle recovery guest. Confirm a recoverable monitor
snapshot before installing/loading experimental code; see the existing
[operating guide](../../docs/PROJECT_GUIDE.md#guest-workflow) for VM and module lifecycle.
Do not apply this patch to the parent tree or overwrite its captured bundle.

```sh
cp -a /root/linux-6.1.159-kdstatic2 /root/linux-6.1.159-kdclobber1
cd /root/linux-6.1.159-kdclobber1
patch -p1 --fuzz=0 < /root/host_fs/kdlock/kernel_experiments/spin_clobber/guest-kernel.patch
scripts/config --set-str LOCALVERSION -kdclobber1
make olddefconfig
LC_ALL=C timeout 7200 make -j20 bzImage modules
LC_ALL=C make INSTALL_MOD_STRIP=1 modules_install
cp -n arch/x86/boot/bzImage /boot/vmlinuz-6.1.159-kdclobber1
cp -n System.map /boot/System.map-6.1.159-kdclobber1
cp -n .config /boot/config-6.1.159-kdclobber1
LC_ALL=C mkinitramfs -o /boot/initrd.img-6.1.159-kdclobber1 6.1.159-kdclobber1
```

Capture the installed build before booting it. The capture refuses configuration
changes beyond LOCALVERSION and writes a new external bundle:

```sh
cd /root/host_fs/kdlock
python3 kernel_experiments/spin_clobber/capture.py \
  --source /root/linux-6.1.159-kdclobber1 \
  --parent /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --output /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

Append a distinct entry to `/boot/grub/custom.cfg`, copying the parent entry's
root UUID and boot arguments and changing only the label/id and release. Do not
run `update-grub` or change the default entry. Use the new id with `grub-reboot`
for a one-shot boot. After boot, verify source/config/build and live
Build ID with `bench/spin_cacheline/kernel_identity.py --kernel-source ...
--kernel-baseline ...`. Rebuild every tested module against the new tree.

The request state machine and fixed wrapper directory are documented once in
[JIT_REGISTER_ABI.md](../../docs/JIT_REGISTER_ABI.md#entry-identities-and-packet-states).
Directed results belong in [tests](../../tests/README.md); same-kernel four-arm
performance results belong in [spin_cacheline](../../bench/spin_cacheline/README.md).

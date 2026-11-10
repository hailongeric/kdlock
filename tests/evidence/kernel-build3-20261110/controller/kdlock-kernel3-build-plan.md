# Kernel3 incremental build plan (not executed)

This helper runs only in the VM. It does not install a kernel, change GRUB,
load a module, execute generated code or reboot. The source host only wrote
and read this helper and the plan; no Python parser or project import ran.

The source input is the exact committed `69ba6b03` snapshot, with core changes
at `1b50e373`. The 66-input build manifest has SHA256
`8779c43983d5ee4c2ae7ce4886b38ba2806f8ca91d1c0dbb97a8cd2f23f777ad`.
Its old 64 hashes match kernel2 commit `81feb2d7`. Exactly six existing core
files change, and `kernel/observation.c` and `.h` are added. The fixture and
host source are not copied into the kernel package by this helper.

Before any candidate source/output change, the helper requires the actual
completed `KERNEL2_WITNESS_RETAINED` receipt and externally supplied hash. It
rereads all 14 retained build files against the still-current build outputs,
checks old final kernel2 pins, all 64 package hashes, all 66 new input hashes,
the unchanged six vendor/integration source files and the explicit normal
boot identity. The retention receipt remains a separate operation and result.

After checking idle state and at least 4,000,000,000 available bytes on the
build filesystem, it creates a fresh receipt directory, saves the six old
changed files and atomically replaces only the eight reviewed paths. Existing
source/output roots remain separated. No old build/receipt directory is removed.

The first make command names the current 27 C and three assembly core targets
with `-j8 V=1`. Existing unchanged objects may be up to date; that is not a
claim that all 30 were freshly compiled. Their actual normal `.cmd` files are
retained. The second command is ordinary `-j32 bzImage modules`. Both use the
new release `7.0.0-38-kdrebuild3`; only locale environment values change.
Mitigation, assembly and kernel compiler flags remain the target's normal flags.

The aggregate make budget is 900 seconds and the minimum available space is
4 GB. A guard violation sends SIGTERM to that build's separate process group,
then SIGKILL only if it has not returned within 15 seconds. It retains logs,
exit status and the partial candidate build. A guard stop never counts as a
successful build, drain or runnable kernel. There is no automatic retry.

A successful command return is followed by input/configuration readback,
unchanged installed boot/default hashes, all final kernel output hashes,
actual BuildID, actual module count/vermagic and a fresh GS witness. The GS
witness requires the new System.map `current_task == const_current_task`
full high address and an actual linked `GS:RIP MOV` whose signed displacement
resolves to it. The raw instruction is independently reread through the ELF
LOAD segment. No per-CPU subtraction or kernel2 witness address is used.
Failure to find a witness is an incomplete identity stage, not a reused proof.

The root must fill the actual retention manifest hash after that operation
returns, then review the exact invocation before dispatch:

```text
python3 /tmp/kdlock-kernel3-build.py \
 --input /mnt/kdlock-builds/kdlock-main-work/module4-69ba6b03-01a1bc4f/input \
 --manifest /mnt/kdlock-builds/kdlock-main-work/module4-69ba6b03-01a1bc4f/kdlock-main-69ba6b03-build-inputs.json \
 --manifest-sha256 8779c43983d5ee4c2ae7ce4886b38ba2806f8ca91d1c0dbb97a8cd2f23f777ad \
 --retention-manifest /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/receipts/retained-kdrebuild2-81feb2d7-20261110-UTC-01/manifest.json \
 --retention-sha256 ac0a6e0ee74abb3fba101be5532806b3aa5d237a8969273ef031f60a74ac85c9 \
 --expected-boot ca0b717b-c19d-4027-b598-6a1cf58b93d2 \
 --receipt-dir /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/receipts/overlay-1b50e373-kdrebuild3-20261111-01
```

Source/archive transfer, VM syntax checking and helper execution require the
root's separate authorization/window; none is implied by this plan.

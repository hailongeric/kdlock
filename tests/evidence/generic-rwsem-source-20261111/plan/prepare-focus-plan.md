# Kernel6 fresh candidate: source construction and focused compile only

Prepared source-host only; no helper execution, network, staging, build or VM mutation occurred. Execution remains held after the parent-reported host preflight permission denial until the separately requested authorization resolves it. Do not retry that host action or use another route.

- Core: `532b68a65bdf96504e2cede6c23a5bc1476d94e9`.
- Frozen source snapshot: `02ffa1ec4f4813e4051ebe109fcd0777ba6304fa`. Kernel code matches core532; the v2 installer adds explicit native query exports. Its SHA is `a64f59682d507e44cecb2afee6fa78e53d2b59592714a9752c0f660f5f52eda6`.
- Package manifest `/tmp/kdlock-kernel6-package-02ffa1ec.json`, SHA `b9c1dc31a6fc361c19faeea504a10bf6ce5e1e71f4c1ba28bf4031921bdb7a98`:76 C/header/assembly/Kconfig/Kbuild inputs plus the exact installer,77 files total. Generated from committed Git objects with no project parsing/imports.
- VM-only controller `/tmp/kdlock-kernel6-prepare-focus.py`, SHA `7f8200b5fa11c3fb2c9416507e68963398532c04e189e8b9803ba7b2a66a33b5`. Root must source-review before dispatch; no automatic retry/resume.

Protected baseline normal source is `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source`, with its separate output `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build`. Retained schema2 normal bundle `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027/manifest.json` SHA `1d65f61df1be4ab03e358b456d67165d5c9bdc3edd50cf8f15ad651281feca17` records authenticated Ubuntu `linux=7.0.0-38.38` plus protected historical KD source changes. This is the same scoped source baseline used by the original main integration; it is not a claim of a freshly authenticated entire tree. The controller externally pins the eight current v2 integration inputs (Makefile plus seven edited files) before copying. Six normal pins come from the retained original integration readback; the two original rwsem inputs match the freshly exported unchanged native files. Any mismatch stops before candidate creation.

Fresh candidate root:

`/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-01`

It contains fresh `source`, fresh `build`, and `receipts/focused-01`. Kernel5 remains at `/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/{source,build,receipts}` and is not modified, copied into the new output, or cleaned. All71 kernel5 package inputs and14 final output hashes are checked before and after. Existing retained kernel3/4 witnesses stay untouched. All boot/module/GRUB namespaces stay untouched.

The normal source is copied with ordinary `cp -a --reflink=auto` into the fresh candidate. This asks for independent reflink storage where available and otherwise creates ordinary independent byte copies; it does not request cross-device hardlinks or write shared source inodes. Source is on data1 and candidate on builds2, so relying on `cp -al` across those mounts would be incorrect. The new O directory starts empty; it is not seeded with kernel5 or normal objects, dependency files or generated headers. Only exact config31d9701e is copied as the reviewed configuration seed. Fresh source+full later O were estimated at about40–45GB; the current measured76,095,098,880B builds2 availability and242,879,787,008B host availability can cover that estimate, but the controller still checks explicit floors.

Before any copy, root provides a newly captured supported read-only HMP proof through the already authorized route: `info status`, `info snapshots`, normal process/drive identity and all-three recovery tag `kdlock-builddisk-clean-20261031`. No qemu-img retry, lock bypass, snapshot operation or new route. The controller pins the exact proof SHA, requires an age at most900s, the all-disks rather than partial-snapshot section, running status and caller-measured host free bytes. Guest gate is normal51b49/kdlock1/taint0, no active build/fixture/module/device/Dthreads, no compiler/flags environment override; root floor1GiB, builds2 and host floors48GiB each. Any access denial or changing input stops for review.

The only project execution in this first stage will happen in the VM:

1. Verify frozen package bytes and protected normal/kernel5 inputs; copy normal source and exact package into the fresh candidate.
2. Run exact installer v2 `inspect`, retain externally checked source/config/package fingerprints, then `plan`, `apply` and `verify`. It must produce a complete seven-file application journal. No patch fuzz, reinstall over partial state or automatic rollback.
3. Run normal `make ... olddefconfig`; require the same configSHA31d9701e. MM body files and mmap wrapper bytes are checked unchanged across integration.
4. Run `make -C <fresh source> O=<fresh build> KERNELRELEASE=7.0.0-38-kdrebuild6 -j8 V=1` for33 KD units (30C+3S) plus `kernel/fork.o`, `kernel/exit.o`, `kernel/locking/rwsem.o`, `mm/mmap.o`, `mm/vma.o`, `mm/mmap_lock.o`, `mm/util.o`, `mm/memory.o`. This is41 directly affected objects; no tests, full suite, full kernel, modules or live workload.
5. Compare protected inputs again and retain actual command lines/logs/rc/config/output release and headroom. A timeout retains the child and partial candidate; no kill/retry/cleanup. Stop at `FOCUSED_COMPILE_COMPLETE` only on actual rc0 and all identity checks.

A later separately reviewed `bzImage modules` dispatch after the focused stage is required before install/boot; necessary kernel build/install/reboot work is already user-authorized. C12 rwsem/task layout changes require rebuilding every loaded module caller for release6; no old module binary is carried over. Kernel6 linked BuildID, ELF/map/image hashes and exact full-VMA GS/current_task proof are unknown until that link. Do not substitute kernel5 GS/ELF evidence. No runtime or mmap/munmap result follows from this source plan or a future successful focused compile.

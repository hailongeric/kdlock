# Verification-only reuse of the completed r2 modules_install output

This is a new verification attempt, not a successful rewrite of the failed r2
stage. The r2 result remains FAILED at SHA
`b55eee6dad571da7d1f5a55a74f04b7ed8c1c34f755aa8e3a8bb60174885046f`.
Its recorded Kbuild modules_install child completed with return code 0 and no
remaining descendants; verification then stopped on the first module. The
existing DATA tree is reused without running make, modules_install, strip,
signing, depmod, loading, installation or boot actions again.

The actual first pair has identical 25 allocated section properties/bytes and
1041 normalized relocations into allocated sections. Its only symbol inventory
difference is 18 removed unnamed local STT_SECTION symbols with info 3, other 0,
value 0, size 0, none referenced by a retained relocation. R3 excludes exactly
that canonical unreferenced class from the standalone symbol inventory. Named,
global, noncanonical and referenced symbols remain compared; every relocation
continues to retain its normalized symbol record. No allocated bytes or
loader relocation is ignored to make this case pass.

Implement a new `/tmp/kdlock-scope-stage-modules-r3-20261030.py` with the same
schema 2 and helper-facing API as r2, so the existing install-r2 controller can
consume the new result and controller hashes without source changes. Keep
STAGE/MODLIB at the existing r2 DATA paths. Use fresh evidence output
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kernel-scope-module-stage-r3-20261030`.
Only that new evidence directory is writable. Require the existing source/build
links; do not recreate or repair anything in the reused stage.

The new attempt binds and copies the failed r2 result, original controller and
helper, exact build/preinstall identities, operations journal, modules-install
log and protected-before inventory into a prior-stage-r2 evidence subdirectory.
It validates the one retained successful modules-install operation, argv, log
hash, return status and drain. It independently checks the same full kernel
source/build/module manifest before and after verification. The 6,901 expected
module paths must match modules.order exactly, with no compressed or extra
modules. All 6,901 build/stage loader identities and vermagic release strings
must pass. Built-in metadata and the existing build/source links remain exact.

The old protected-before file is separately pinned at
`fb8ec836f5b907e364d0e5094704291fdc5753ef8a717a1b10f46a82bf26f11d`
because the failed result did not get far enough to record that field. Require
it to equal a fresh protected inventory; save fresh before/after inventories
and require both to match. Likewise save and compare complete reused-stage
before/after inventories. The earlier attempt did not save its in-memory stage
inventory; do not invent one or claim retrospective byte stability. The new
pass proves the current entire stage corresponds to the retained build and was
unchanged during this verification.

A successful result preserves the install-r2 state and fields:
`DATA_MODULE_STAGE_VERIFIED_NOT_INSTALLED`, passed=true, unchanged kernel/build
and protected paths, all module releases and loadable identities verified,
module_count 6,901 and the complete hashed file set expected by bind_stage().
Additional fields explicitly record prior FAILED evidence, stage reuse,
modules_install_rerun=false and the normalization policy. Historical kernel
commit 8446 remains distinct from the current f7 provider. installed/loaded/
rebooted/performance_accepted remain false.

Failure retains the r2 stage and both attempts' evidence. A running timed-out
child is not killed or assumed drained. No failed receipt is converted to a
pass, no partial module set is accepted and no repair/retry is automatic.
Development now is source/AST inspection only on 380G10; future execution is a
separately controlled VM installation-verification step.

# Small kernel16 KD spin correctness fixture

Source: [payload/kd_spin_simple.c](payload/kd_spin_simple.c)

This isolated candidate directly uses kd_spin_init(), kd_spin_lock() and kd_spin_unlock() from pinned source 7338197a587fd84110fe710be63abafde270c02b. It does not modify the shared checkout or the earlier Nano lane. It installs no hooks, resolves no symbols dynamically, and provides no Native substitute or image publisher.

## Actual API requirement

The pinned include/kd_spin_api.h defines struct kd_spinlock as one struct kd_mutex queue; kernel/mutex.h defines that queue as two pointers (tail and owner). On this x86-64 target the source layout is 16 bytes, with queue at offset zero. There is no policy_epoch. Source-level assertions reject another size/offset, and the offline check compares all 88 packaged KD source files against kernel16's retained build receipt.

kd_spin_init is a function. kd_spin_lock and kd_spin_unlock are compiler clobber macros that call kd_spin_lock_entry_asm and kd_spin_unlock_entry_asm. Those three symbols are GPL exports in kernel/exports.c. They are not callable ordinary spin_lock wrappers. kernel/mutex_api.c prepare_current_with_image rejects an unattached task with BUG_ON. kernel/integration/README.md requires an atomic spin runtime, preallocated task/control storage and task attachment before use.

Consequently this standalone module includes the exported source-provider/runtime setup and per-task enter/leave calls. This is necessary API provisioning, not a new Nano harness. It creates no translated image. The runtime API registers its ordinary control channel internally; no controller should open it or publish images during this fixture. The run assesses the public KD spin acquisition/release path with local source execution, not foreign delegation or physical batch length.

## Test and lifetime design

Two kthreads are bound to distinct explicitly selected online CPUs (defaults 0 and 1). CPU hotplug is held off for this short test. Both finish setup before a common start gate opens. Each performs 64 acquisitions, increments a shared non-atomic total while holding KD, records its own count and releases KD. An independent atomic occupancy diagnostic detects overlapping critical sections; it is not used to guard the total. A passing result requires two completed workers, 64 increments each, total 128, zero remaining occupants, zero overlaps and no setup/join error. This finite test does not prove all interleavings or guarantee observed queue contention.

All allocations occur before lock-loop calls. No allocation, sleeping or scheduling occurs inside the critical section. cond_resched occurs only after unlock. No source owner, request, stack, binding or release-ACK record is fabricated or replaced by the diagnostic counter.

Creation failure opens the start gate with abort set and joins every created worker. A worker with retained setup storage attempts exact current-native detach before reporting done. Finished workers remain alive until kthread_stop joins them. Module init returns only after all workers have joined and runtime/provider teardown has succeeded. Init error is reported only after that cleanup.

Five-second waits are observer deadlines. Expiry reports incomplete progress and continues waiting with state retained. An unexpected detach/destroy error retains the task/module init rather than freeing live state. Neither a timer nor kthread_stop can interrupt a wedged KD spin acquisition. A stalled run may therefore leave insmod pending and require recovery; no force-unload path exists.

## Gates and configuration

The inspected kernel16 config has CONFIG_KDLOCK_REBUILD=y and CONFIG_PREEMPT_COUNT=y, with PREEMPT_RT, DEBUG_SPINLOCK, DEBUG_MUTEXES and DEBUG_LOCK_ALLOC disabled. Runtime setup also refuses unsupported call-depth instrumentation through the existing implementation. Module source refuses the unsupported configurations explicitly.

Module parameters immutable_text, auxiliary_contract and gs_verified default false. They are evidence prerequisites, not proofs created by setting booleans. A reviewed run must establish immutable source dependencies, the auxiliary-stack/control capacity contract and the exact GS offset before setting them. gs_offset must come from the verified target, not an old boot assumption. The fixed storage sizes follow the pinned runtime fixture's existing provisioning values; this source check does not establish their complete stack bound for the new module.

## Build status and precise prerequisite

No .ko was built. The host exposes GCC 11/12; the exact old compiler is GCC 15.2.0-16ubuntu1 with a declared libc6 >= 2.38 dependency, retained inside the stopped source system. Prepared kernel16 inputs also remain on the stopped source build disk. The source lookup verified 126 recorded hashes, including the full ELF and generated ABI inputs. No compatible already-running, authorized build environment containing those inputs is available in this task. A new environment, package installation and booting the source VM were expressly excluded, so compilation stops here.

Target release: 7.0.0-38-kdrebuild16
Target GNU Build ID: 40d0694cb395dfcc98f8275d033b96797d2e5cb2
Target Module.symvers SHA256: de0efc1f0aedfe4b2f48fe2d01a4fa6dfa9082b9af71ed572f8844f5ac8781b8

Once a compatible build environment is separately available, the external-module shape is:

    make -C <exact-kernel16-source> O=<exact-kernel16-output> \
      M=<this-directory>/payload MO=<fresh-module-output> \
      KD_SOURCE_ROOT=<this-repository-root> modules

This is a command template, not an executed build or readiness claim. Verify all actual imported symbols, MODPOST CRCs, emitted clobber routing, vermagic, source/config/compiler identity and module signing/admission requirements before any load. CONFIG_MODULE_SIG_FORCE being unset does not establish admission. No key was accessed and no signed or unsigned artifact exists.

The new guest remains stopped. Its recovery snapshot/profile is preserved. Same-QEMU-process restore was verified earlier; fresh-process restore remains untested. No runtime launch/load was attempted.

## Offline checks actually executed

Run python3 check_offline.py to reproduce:

1. GCC 11 C syntax checking with -Wall -Wextra -Werror and mocked Linux/runtime declarations. No object is emitted. This does not verify kernel declarations, linking or ABI.
2. Preprocess the actual pinned kd_spin_api.h and kd_mutex_api.h; confirm routing to the exact spin assembly entry symbols. Linux dependency declarations and queue types are mocked for this check.
3. Verify all 11 expected KD imported symbol names appear as GPL exports in pinned source. This is source evidence; actual .ko imports/CRCs are unrun.
4. Match all 88 packaged KD source files against the retained kernel16 build receipt, including the private headers and exports.

All four checks passed. No kernel test, module build, live exclusion/progress check, signature check, throughput run or recovery test was performed. checks.json and the two logs retain actual offline results. This candidate still requires a real kernel compile and review of its runtime prerequisites before live use.

## Git preservation

This directory preserves the standalone source candidate on a dedicated branch from 7338197a. The checker now resolves this checkout and its retained expected-kernel receipt through relative paths. Only Python AST/path inspection was repeated during Git finalization; the four recorded offline checks predate that path-only change. Original checker and results are preserved under tests/evidence/spin-preparation-kernel16-20261114/fixture. Export/CRC inspection later confirmed all 11 source-expected KD exports in the exact retained Module.symvers; this is not an emitted-module CRC comparison. No new compile, test execution or live work occurred during finalization.

# Original-task instruction-service validation

The initial candidate is `ace6eaf882c54bc822b8fe4f4eea4d85fc605473`, following
the documentation-first plan `6b4e5d6de928afed868c37d8396f86237526d8cc`.
It adds bounded original-task RDTSC/RDTSCP/CPUID execution and same-image JIT
re-entry for the sole-outer ABI2 mutex case, including a prepared rwsem writer's
mutex gate. Other reached instructions and arbitrary native CALLs retain the
existing waiter suffix; generic branch-only CALL re-entry is not established.

## Initial VM attempt

All work below ran on `10.176.26.71`, kernel `7.0.0-38-kdlock1`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`. The exact clean synchronization contained
5,863 tracked files. Its receipt SHA256 is
`6195b3ffd5f40611aa9ba17719944204f91bf9cebd19aa8f9549ab798597383b`.
The frozen guest output is
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/origin-instruction-unit-ace6-20261030`.

Kernel identity passed. The two basic C checks and twelve directly affected
Python drivers reported **11 passed, 3 failed**; the provider build was not
started. A failed driver is not a pass merely because some assertions within
it succeeded. No live module or performance result belongs to this candidate.

The three failures require the following bounded follow-up before proceeding:

- `test_origin_instruction_codegen.py`: the old-provider native-marker control
  used the checked-source default while expecting production trusted-source
  behavior. Explicitly select the documented source-trust mode in that control;
  do not change admission policy to make a fixture pass.
- `test_jit_escape_runner.py`: `RepeatedMarkerProbe.phase` still has the previous
  three-argument signature. Preserve all ordinary-marker checks while accepting
  the new explicit force-suffix argument, which must be false for this probe.
- `test_jit_entry_scope.py`: the production consumer fixture exited without a
  diagnostic in stderr. Retain its exit status/stdout/stderr and diagnose the
  original failure before deciding whether a fixture or runtime change is
  required. Do not count a crash as successful mutation detection.

The separate production-handshake fixture passed its retained packet/owner/node
and post-ACK next-publication checks, including the four intentional mutations.
The generated wrapper's eight other instruction-service checks passed. These
limited observations do not override the failed unit gate.

The original unit output and each diagnostic attempt remain separate. GDB was
unavailable, so its diagnostic stopped at preflight before building or running
a fixture. A subsequent ASAN diagnostic completed the production consumer's
8,950 checks, then its diagnostic recorder incorrectly tried to overwrite its
first expected mutation-failure receipt and stopped. That diagnostic is not a
complete unit pass and does not resolve the original ordinary-build exit.

## Required next gates

The separate plain optimized diagnostic reproduced SIGSEGV (`returncode=-11`)
with final idle and unchanged source. Its retained binary SHA256 is
`3e239cb78fd51ae771dd7d333d5ac1ca8fc470db022f154cbb218827b38b3363`.
The kernel's fault RIP maps to ELF offset `0x95a5`, the full-register copy in
`kd_exec_frame_save_continuation`. `continuation_sp` aliases `borrowed_regs`;
writing it while borrowing remains active makes the copy target the virtual
stack. The computed 16-byte write crosses exactly the recorded fault page.

Two successful direct-helper loops in `native_escape.inc` and `native_calls.inc`
bypass the production dispatcher's FULL-packet ownership transition. Correct
only those setups with `kd_exec_frame_own_regs`; retain the via-dispatch and
malformed-input cases. Static review of all fifteen production continuation-save
call sites found no corresponding bypass. This is a source finding, not a live
claim for every nesting case. The runtime has not been changed for this fixture
failure; the corrected fixture still needs VM execution.

After source-host review and a separate correction commit, run the basic plus
directly affected tests in the VM, then build and inspect the provider. Only
after those pass may the all-family basic checks, original-task instruction
probe, prepared-rwsem writer probe and mixed mutex-to-spin control run. Preserve
every failure, exact source generation, physical owner, source lease and unlock
ACK. The earlier `8446f4ecb08816380a4c233197a8ce5e4d333aac` nano campaign cannot
validate this newer runtime or establish its no-regression acceptance.

## Renamed-family VM attempt

The clean `f1811d1dba0417854cc47f0d651d3a1ccc31ec91` generation renames the
active functional family to `jit_continuation` without changing production
runtime bytes. Its 5,864-file synchronization receipt has SHA256
`d13e2a0995cdb96bbfcd0819214a4547ffc06831435105d69a7046b6fc7c070f`.
The output is
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/continuation-unit-f181-20261030`
on the same normal-kernel boot recorded above.

Kernel identity passed. The basic and directly affected unit selection reported
**12 passed, 2 failed**. The production consumer completed 8,955 checks with
zero failures; its `indirect-accepts-jump-opcode` mutation then exited with
SIGSEGV instead of the required explicit failed assertion. The repeated-marker
runner fixture omitted the new `origin_service` field and raised `KeyError`.
The provider build and live tests did not start. These are failed test groups,
not completed validation.

Before another VM attempt, give the ordinary-marker fixture its explicit
non-service mode and diagnose the mutation's direct-helper ownership setup.
Preserve the ordinary-marker invariants and require explicit assertion failures
for intentional mutations; a crash must not count as detection. Keep production
changes separate from fixture corrections and retain this failed generation.

Source inspection identifies the same borrowed-packet union issue in the
direct indirect-CALL refusal loop: accepting the intentionally malformed opcode
reaches continuation saving before the fixture has performed the production
dispatcher's ownership transition. Own the FULL packet for those direct-helper
cases; preserve case 15's deliberately foreign borrowed packet. The runtime
dispatcher already performs this transition. Both corrections affect only test
fixtures and require a new VM run; the mutation must still fail an assertion.

## Corrected fixtures and observation preparation

At `28d479d4de96cf038829176124abb29039f7ff19`, the same VM selection completed
**14 passed, 0 failed**, including explicit detection of the intentional
execution mutations. The output is
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/continuation-unit-28d479d4-20261030`;
the clean synchronization SHA256 is
`bf3dda2052dabe5649bfa78b442701315187d8dad33cb20cbc792d9010cca580`.

Private provider preparation then failed before compilation: the first
`kernel_module/exe.c` observation hunk expected adjacent declarations, but the
new `resume_after_origin` declaration separates them. Preserve the failed
private tree. Update only the patch context to include that declaration; keep
all instrumentation additions and production code unchanged. Include the
directly affected completion-accounting unit driver in the next VM selection.
Unit success here does not establish a provider build, live execution or timing.

The first context-only correction, `dc56e2ed6539dbae9780217830b948607f8aac80`,
passed `git apply --check` but the added VM completion-accounting driver still
failed at that hunk. Four leading context lines and three trailing lines make
GNU patch require an end-of-file match. Use ordinary three-line context on both
sides, starting at `resume_after_origin`, without relaxing `--fuzz=0` or changing
any instrumentation. The failed attempt remains in
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/continuation-unit-dc56e2ed-20261030`.

For this formatting-only follow-up, retain the successful fourteen-group
`28d479d4de96cf038829176124abb29039f7ff19` unit evidence rather than repeating
unchanged tests. Bind its actual owner receipt, log and synchronization manifest;
allow only this result document and the observation patch to differ. Run the
basic checks, directly affected completion-accounting driver and provider build
on the new generation. The earlier overall attempt stays failed because provider
preparation failed; only its successful unit block is reusable evidence.

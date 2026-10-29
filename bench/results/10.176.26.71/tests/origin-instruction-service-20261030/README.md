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

After source-host review and a separate correction commit, run the basic plus
directly affected tests in the VM, then build and inspect the provider. Only
after those pass may the all-family basic checks, original-task instruction
probe, prepared-rwsem writer probe and mixed mutex-to-spin control run. Preserve
every failure, exact source generation, physical owner, source lease and unlock
ACK. The earlier `8446f4ecb08816380a4c233197a8ce5e4d333aac` nano campaign cannot
validate this newer runtime or establish its no-regression acceptance.

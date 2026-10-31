# Kernel correctness tests

Use the [project roadmap](../../docs/ROADMAP.md) to identify whether a check
supports a standalone lock, the actual-MM adapter or future broader integration.
Passing a module-object probe does not establish kernel-wide API coverage, and
passing an MM correctness case does not establish mmap1 throughput or parity.

Organize tests by lock family or execution feature. A test directory owns its
runner and guide; a correctness-only loadable module belongs in its `payload/`
subdirectory. Keep the module Makefile, C source and ioctl header together so
source freezing includes the complete build input. Existing provider probes
may keep their small module directly in their test directory.

| Test | Runner | Kernel payload |
| --- | --- | --- |
| Conditional instruction exit (mutex, spin, rwlock, rwsem) | [jit_continuation](jit_continuation/README.md) | [payload](jit_continuation/payload/README.md) |
| Checked spin pointer-load continuation | [spin/address_guard](spin/address_guard/README.md) | [payload](spin/address_guard/payload/module.c) |
| Original kernel strcmp delegation | [spin/string_service](spin/string_service/README.md) | [payload](spin/string_service/payload/module.c) |
| Reader/writer exclusion and delegation | [rwlock](rwlock/README.md) | [payload](rwlock/payload/README.md) |

Other family and provider probes remain in their existing subdirectories; see
the [test index](../README.md) for coverage and affected-check selection.
Benchmark modules and modules shared with timing runners remain under
[workload_modules](../../workload_modules/README.md), including the mmap fault
and writer workloads. Benchmark runners live under `bench/`.

Build and execute only in the verified VM under [VM operations](../../docs/operations/VM.md).
Source snapshots must include nested `payload/` files and private `.inc` files.
Moving a payload does not change its module name, device, ioctl ABI or ownership
and retirement requirements. Historical evidence retains the original paths and
source hashes; use its frozen source when reproducing those records.

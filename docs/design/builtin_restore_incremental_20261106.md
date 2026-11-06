# Scope5 builtin restore correction

This kernel component starts at `1ab7124abb6140752c1f0bb6e862144d426a3875`.
The reviewed workflow is recorded in `compiled_mm_continuations.md` at
`f3b287bb7bdd0e0b09c6839545cb468d11e288df` on the runtime candidate branch.

Apply only the bodies of `kd_rwsem_provider_resume_instruction()` and
`kd_rwsem_provider_resume()` from
`b1884ccbe3227c138d8c427b83328407648b00be`. Both restore all packet registers
before raising the active stack pointer. The instruction continuation retains
its source CALL word and restores arithmetic flags before changing stacks.
The ordinary continuation retains its existing return contract. No public API,
ownership record, module lifetime, packet layout or generated-text producer
changes in this component.

Before changing the VM source/build tree, retain and verify the complete current
v3 generation on 380G10. Reuse the same source/output paths and keep the existing
16 GiB amendment/link guard, normal kernel default and recovery artifacts.
Generate a fresh MM preparation whose sole changed output is
`kernel/locking/kd_mmap/provider.c`; retain the existing API and generated-text
preparations. Bind the new preparation and component identity into composition
and later kernel bundles. Build the affected object, then normal `bzImage modules`
dependencies without changing configuration. All builds and live checks run on
the VM.

The runtime candidate's 390 passing restore fixture cases and six expected
negative controls establish only the local register contract. A matching kernel
build and bounded live mmap1 thread/process checks remain required. The first
failure from the earlier warmup is not attributed to this correction without
matching request/image evidence.

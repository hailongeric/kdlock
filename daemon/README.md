# kdlock daemon

`daemon` is the userspace bridge between `/dev/kd_dev` and the Python
translator in `../disassem/disassem.py`.

See [the execution and test guide](../docs/JIT_EXECUTION.md) for the current
JIT-scope contract. An ordinary direct CALL miss transfers this invocation to
the original waiter permanently; daemon learning/recompilation applies to
future invocations. The translator rechecks the expanded scope when a callee
becomes decoded. Lock-control calls and allowlisted hostcalls can still resume
JIT and therefore retain their continuations in admission and generated code.

Its kernel hooks/exports depend on the captured
[guest baseline](../kernel_baseline/README.md), not merely a `6.1.x` release
string. The read-only source/build/Build-ID check is an operator prerequisite;
it is not a daemon publication/version-isolation change or a hot-unload guarantee.

Build and run only in the recovery guest, from this directory:

```sh
cd daemon
make
./daemon --mode 2
```

Modes:

- `--mode 1`: use one flat workspace per translated entry: `./<RIP>/`.
- `--mode 2`: isolate workspaces by process: `./<RIP>/<tgid>/`. This is the
  default.

These select workspace layout, not benchmark mode or hostcall policy. Kernel
lock entries use `pid=0` as their lookup key, but retain the registering task's
`tgid`. Their mode-2 workspace is still `./<RIP>/<tgid>/`, not `./<RIP>/0/`.

Useful options:

- `--quiet`: suppress normal progress output.
- `--verbose`: print initialization, miss, and compile messages.
- `--poll-us N`: set the polling interval in microseconds. The default is
  `100000`.

For each new entry the daemon creates an isolated `asm/` workspace and empty
`callee_table.txt` and `ij_table.txt` files. It updates those tables when the
kernel reports a missing call or indirect jump, invokes the translator, and
writes the generated `jit.bin` back through `/dev/kd_dev`. No pre-created
workspace template is required.

The daemon rejects empty images and images larger than the shared 640 KiB code
block. It streams the artifact in chunks of at most 4000 bytes, checks every
file and device transfer, and marks the entry `KD_EXE_NORMAL` only on the final
complete chunk. The kernel validates the entry key, destination offset, payload
length, and status before copying each chunk.

This relies on a trusted, single daemon completing the transfer. The kernel
does not track total image length, chunk continuity, image generation, or live
executors. Recompilation overwrites the same executable block; release/acquire
publication does not protect an old execution from those writes. The
`install JIT chunk` diagnostic is emitted after key validation but before payload
copy, so even `status=0` is not a completed-install acknowledgment.

The concurrent-overwrite risk applies when independent lock instances share
one RIP-keyed artifact; a fixed entry serialized throughout execution by one
lock is not that scenario. Early A release does not serialize an entire B suffix
against a following A request; its tests stop the daemon after publication,
not while an old artifact is being replaced. The project treats the risk as low probability
(not a measured rate) and defers immutable versions, complete-image checks,
coherent miss snapshots and old-version reclamation. Lock serialization does
not itself validate missing chunks or stale jobs. These are known limitations,
not current daemon implementation tasks; future work is retained in
[TODO C3](../docs/TODO.md#c3-immutable-jit-publication-and-lifetime).

## JIT Diagnostics

`KD_JIT_BODY_WITNESS=1 ./daemon --mode 2` enables generated-body observation.
It defaults to 0; invalid values are translation errors, not policy refusals.
Common integration-test launches force 1.

Each emitted block/continuation writes one using MOV to the wrapper's reused
second-output slot. The wrapper resets it to zero and returns it in args[1].
The kernel records the first positive return per high-level invocation as
`JIT body witness: entry=... lock=... body=1`. The two input words and wrapper
layout are unchanged. Dispatcher-only exits return zero.

A returned marker is required execution evidence, not every-path/instruction
coverage or a generation identity. Zero does not authorize replay. Observation
adds stores/logging and is not a performance baseline. Environment changes do
not retrofit existing artifacts; drain executors before replacement.

Translator warnings/errors use `[KD_JIT][WARN]` / `[KD_JIT][ERROR]` on stderr,
including with `--quiet`. Read the reason, action, source RIP/instruction and
address/alias provenance before interpreting an aggregate failure.
`CONTEXT_NATIVE_ONLY` reports policy rejection; `CONTEXT_ADDRESS_WIDENED`
reports analysis precision loss, not proof of a real invalid access.
An eligible nested entry may then report `ENTRY_GUARD_WAIT_TEXT` while fetching
cold branches, followed by `ENTRY_GUARDED_ADMISSION` on conditional success.
Its `scoped_calls=true` field identifies the single-entry learned-callee path:
actual CALL/RET effects are checked against generated return targets. A learned
address alone is not permission to inherit entry facts; IJ history, disconnected
targets and inconsistent return edges cannot use this path.
Read the final verdict, not the first unconditional-analysis warning alone.
`CFG_ROOT_EXTEND` seeds a newly reachable block inside an already cached window;
cached bytes alone are not proof that its CFG was decoded and checked.
The generated image checks all collected entry predicates before body; runtime
`ENTRY_GUARD_REFUSED` means that invocation remains unstarted and native, not
that the daemon should disable the entry or replay completed work. No extra
daemon switch is needed. Scope and protocol are documented in
[the usage guide](../docs/JIT_EXECUTION.md#5-入口条件与嵌套续点).
Existing INT/special-instruction and flags diagnostics describe limitations;
they do not repair semantics or establish a general privilege verifier.

For a failure retain the test's `Evidence:` directory, daemon stderr, dmesg,
`asm/jit.S`, `jit.bin`, callee/indirect-target tables and source hashes.
A pre-call IP or `install JIT chunk` log alone is not JIT execution proof.

## Admission And Launch Outcomes

Translation selects the possible JIT episode before checking context and
generating both instructions and entry dispatch. Ordinary direct CALL misses
remove only their native-only return edge. Alternate JIT paths, controls,
hostcalls, decoded callees and indirect calls retain their relevant successors.
Every recompile rechecks learned targets; a previously admitted prefix is not
blanket approval for an expanded callee or suffix.

Retained GS memory, FS operands, recognized context-sensitive calls and backend
mismatches refuse publication. Memory checks include lifted implicit effects,
CALL stack writes and bounded cross-block facts. The analysis does not read
runtime memory or assume private source stacks. Unknown aliases, incomplete
lifting and concurrent mutation remain limits, not a security boundary.

A policy refusal exits the translator with status 2, removes stale generated
assembly/binary artifacts and publishes native-only. Launcher errors, signals,
missing dependencies and unexpected translator exceptions are not policy
verdicts; they remain diagnostic/retry failures. Do not turn arbitrary Python
failures into accepted native fallback.

Actual runtime continuation and test commands are maintained in
[JIT_EXECUTION](../docs/JIT_EXECUTION.md). Current results, including learned
mutex-depth JIT and native continuation, are in
[VALIDATION](../docs/VALIDATION.md#original-waiter-signals), not duplicated here.

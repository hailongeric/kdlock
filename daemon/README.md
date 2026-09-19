# kdlock daemon

`daemon` is the userspace bridge between `/dev/kd_dev` and the Python
translator in `../disassem/disassem.py`.

For a complete host/guest setup, publication check and ordered shutdown, start
with the [manual sequence](../docs/PROJECT_GUIDE.md#3-一步一步运行). Do not source
`tests/common.sh` interactively or start a second daemon alongside a test driver.

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

Install the [pinned Python runtime](../disassem/requirements.txt) with the
[guest-only venv procedure](../docs/PROJECT_GUIDE.md#33-检查依赖与空闲状态) first.
The daemon invokes `python3` with `execlp`, inheriting its launcher's PATH;
put the selected venv's `bin` first before starting it or the test drivers.
`VIRTUAL_ENV` alone does not select Python, and sudo may reset PATH. No daemon
option or global dependency upgrade is needed. Version pins do not freeze the
compiler, installed bytes or executable JIT generation.

Build and run only in the recovery guest, from this directory:

```sh
cd daemon
make
./daemon --mode per-tgid
```

Modes:

- `--mode flat` (or legacy `--mode 1`/`--mode v1`): use one flat workspace per translated
  entry: `./<RIP>/`.
- `--mode per-tgid` (or legacy `--mode 2`/`--mode v2`): isolate workspaces by
  process: `./<RIP>/<tgid>/`. This is the default.

These select workspace layout, not benchmark mode or hostcall policy. Kernel
lock entries use `pid=0` as their lookup key, but retain the registering task's
`tgid`. Their mode-2 workspace is still `./<RIP>/<tgid>/`, not `./<RIP>/0/`.

Useful options:

- `--quiet`: suppress normal progress output.
- `--verbose`: print initialization, miss, and compile messages.
- `--poll-us N`: set the polling interval in microseconds. The default is
  `100000`.
- `--metrics`: additionally record each reaped translator child's wall time,
  CPU time and resource usage on stderr; disabled by default, independent of
  `--quiet` and generated-body observation.

Entry identity comes from the kernel registration: `entry_abi=0` is legacy,
`1` is ordinary spin clobber v1, and `2` is ordinary mutex clobber v1.
The daemon passes it to the translator and validates the emitted directory's
identity and lock kind before upload. A minimal entry requires the versioned
wrapper; a legacy image cannot be reused under a clobber identity. The current
provider requires the [kdclobber2 interface](../kernel_experiments/mutex_clobber/README.md).

For each new entry the daemon creates an isolated `asm/` workspace and empty
`callee_table.txt` and `ij_table.txt` files. It updates those tables when the
kernel reports a missing call or indirect jump, invokes the translator, and
writes the generated `jit.bin` back through `/dev/kd_dev`. No pre-created
workspace template is required.

### Translation Accounting

With `--metrics`, each completed child produces one `KD_TRANSLATION_METRICS`
JSON record containing the entry RIP, pid/tgid, lock kind, child PID, raw wait
status and classified result (`0` success, `2` native-only, `-1` error). Errors
and refusals are retained, not filtered out of the measurements. The opt-in
[paired experiment](../docs/JIT_EXECUTION.md#34-原生锁与-jit-配对实验) enables this
option; normal regression/manual launches retain the default unmeasured path.

`started_ns` / `finished_ns` use `CLOCK_MONOTONIC` immediately before fork and
after wait4 reaps that child. `wall_ns` therefore includes process launch,
Python imports, symbol/text inspection, analysis, code generation, assembler
children and scheduling. It excludes daemon polling, workspace preparation,
image upload and kernel JIT execution. It is not a breakdown of compiler passes.
`user_ns` / `system_ns` come from wait4, including descendants reaped by the
translator; their original CPU resolution is microseconds. `maxrss_kib` is
Linux's largest-process high-water RSS, not summed concurrent process-tree
memory or kernel code-pool consumption. Fault and context-switch counters are
software resource observations, not hardware cache misses or lock queue time.

The default still uses waitpid without these clocks/counters. In measured mode,
clock/resource/output errors remain launch/experiment errors, never policy
native-only results; do not infer a successful run from a partial record set.
A successful translation record does not prove publication or execution. Keep
the NORMAL/image and returned-body checks, and do not add translation duration
to preparation duration: translation can overlap the promotion workload.

For function-level profiling, use the existing translator CLI in a separate
workspace after workers and the daemon have drained, with the provider still
ACTIVE. This adds no daemon option and does not upload the profiled image; see
the [profiling flow](../docs/JIT_EXECUTION.md#35-翻译器剖析).
Context-symbol matching compiles only the fixed glob rules into one anchored
regex union. It does not cache live names/addresses or remove any policy rule.
The [measured increment](../docs/VALIDATION.md#context-symbol-matching) verifies
the real symbol map and byte-identical images before reporting a compiler gain.

## Device Session

Load kdlock before starting the daemon. It opens `/dev/kd_dev` once with
`O_RDWR|O_CLOEXEC`, before cleaning workspaces, and uses that description for
all snapshots, image chunks and native-only publications. I/O failures never
reopen the path into a potentially different provider session.

Only the translating child inherits the descriptor, named by the internal
`KD_DEVICE_FD` environment value; do not set this variable manually. Python
checks character-device identity and read/write access, takes a non-inheritable
duplicate, checks the source-control API, then queries runtime capabilities
once on that same description before any text inspection. The mutex-stack and
module per-CPU range caches are valid only inside the lease and clear on close.
Each real `/proc/kcore` read range is pinned, including cold extensions and
learned callees. Assembler/workspace children do not inherit the descriptor.
Direct translator CLI use acquires its own lease for translation; its generated
files alone do not prove publication into that session. Imported real-text use
must explicitly enter `device_session.session()`; byte fixtures substitute I/O.

An old provider's ENOTTY or an unknown/malformed capability disables both bounds
with a warning; other I/O errors abort inspection. Version 1 can report the old
optional mutex bound but not the module arena. Current translation requires
that module range and reports an infrastructure error before text inspection
when absent; inspection/retirement remain usable. Rebuild/reload the matching
provider, not an environment override or second device. The guarantees are not
a `mutex_jit` switch or executable generation. Guarded stack analysis uses only
its optional mutex bound; module ranges guide static address refusal, not object
liveness or runtime access validation. The protocol and boundaries are in
[the stack-check guide](../docs/JIT_EXECUTION.md#53-mutex-控制-call-的栈检查).

A missing, closed or mismatched inherited descriptor is `TRANSLATION_FAILED`,
not native-only policy. It is never silently replaced. Stop and wait for both
daemon and translators before unloading: a surviving translator retains the
device fops owner, even after its parent exits. Do not force unload on `in use`.
The device reference protects provider use. Separate session-wide source pins
retain at most 64 distinct LIVE modules; registration/ordinary CALL targets
require core text, while read windows may also include resident core rodata.
Init/unknown/GOING text or dependency exhaustion is refused before inspection.
This does not pin arbitrary dynamic lock allocations or protect hook readers.
The learned-depth gate now exercises root/learned text in two modules. A
module's sysfs refcnt includes native importers too, so it is not interchangeable
with the source-control module count; the test observes both separately through
retirement and normal unload. Flow is in the [usage guide](../docs/JIT_EXECUTION.md#5-入口条件与嵌套续点).

The source controls use a separate ioctl ABI, not extra wrapper words or changed
entry packets. From the guest repository root:

```sh
python3 disassem/device_session.py status
python3 disassem/device_session.py capabilities
# Only after stopping new workloads and draining callers and translators:
python3 disassem/device_session.py retire
```

`status` reports numeric state (`OPEN=0`, `DRAINING=1`, `RETIRED=2`), module pins,
frames and writer open descriptions. `capabilities` reports
`{"mutex_stack_bytes": 256, "percpu_module_bytes": 8192}` for this provider,
with unsupported fields zero. It is
a readonly diagnostic, not the translator's validated lease or permission to
start JIT. The readonly control FD is not a writer.
`retire` requires CAP_SYS_MODULE and terminally closes new writer/frame/root
admission. Busy writers, frames or queue/task/origin state return EBUSY and keep
all source pins; closing is not undone. Existing holders can finish inspection
or native/remote continuation, but cannot publish another image. Stop/wait for
them, then retry retirement. Do not restart the daemon into a draining session.
Successful retirement marks all used entries NATIVE_ONLY before dropping source
references. New write opens stay refused. Only then unload source modules and
kdlock under the recovery-only quiescence procedure; rebuild the entire session
to resume JIT. `tests/common.sh` enforces this before normal test cleanup.
No command forcibly cancels callers, unloads modules or reopens the session.
Hook-reader and lock-allocation lifetime remain [TODO C2](../docs/TODO.md#c2-one-protocol-per-physical-lock).

The [parallel lifecycle test](../docs/JIT_EXECUTION.md#66-独立队列的并行-native-frame)
exercises the real compiler fork/exec with a substituted lease-probe script.
After its parent exits, the child reads pinned text in DRAINING, checks both its
cached bound and a new capability query on the same descriptor, and observes
ESHUTDOWN on header-only publication. Its writer blocks retirement even after
all native frames finish; only final description release permits completion.
The probe is not itself a translation or JIT witness. The separate generated
prefixes and native owner ACKs in that complex workload supply execution evidence.

## Publication

The daemon rejects empty images and images larger than the shared 640 KiB code
block. It streams the artifact in chunks of at most 4000 bytes, checks every
file and device transfer, and marks the entry `KD_EXE_NORMAL` only on the final
complete chunk. The kernel validates the entry key, destination offset, payload
length, and status before copying each chunk.

This relies on a trusted, single daemon completing the transfer. The kernel
does not track total image length, chunk continuity, image generation, or live
per-image executors. The session frame counter supports terminal retirement,
not concurrent version replacement. Recompilation overwrites the same executable
block; release/acquire
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

`KD_JIT_BODY_WITNESS=1 ./daemon --mode per-tgid` (or `--mode 2`) enables generated-body observation.
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
`SOURCE_ROOT_REFUSED` skips registration of unpinnable source text;
`SOURCE_TARGET_REFUSED` is a non-continuable exit after JIT progress, not a
request to replay the entry. A rejected read range is native-only policy,
while an unavailable/incompatible source-control device is an infrastructure
failure. Inspect the address and errno; do not retry against a new provider.
`CONTEXT_NATIVE_ONLY` reports policy rejection; `CONTEXT_ADDRESS_WIDENED`
reports analysis precision loss, not proof of a real invalid access.
`STATIC_PERCPU_SCREENING` reports core static and boot-reserved module ranges
added through the same lease (`cpus`, `core_bytes`, `module_bytes` and their
sum `bytes_per_cpu`). Missing module capability or unavailable, invalid or
unstable metadata produces `CONTEXT_SYMBOLS_UNAVAILABLE` and a translation error,
not an empty safe range set or a native-only verdict. Dynamic allocations,
object lifetimes and unknown pointers remain outside this guarantee; the
[static-range contract](../docs/DESIGN.md#722-static-per-cpu-ranges) records the limits.
`CONTEXT_SCREENING_ONLY` is emitted once after successful code generation,
before assembly/build. It identifies the entry and explicitly reports
`runtime_address_guard=false` and `concurrent_memory_validated=false`.
It is a contract warning, not a detected fault, per-access analysis report,
successful build/publication or runtime protection. Unknown pointers are not
automatically rejected; see the
[dynamic-address gap](../docs/DESIGN.md#721-dynamic-address-gap).
During admission an eligible nested entry may report `ENTRY_GUARD_WAIT_TEXT` while fetching
cold branches, followed by `ENTRY_GUARDED_ADMISSION` on conditional success.
Its `scoped_calls=true` field identifies the single-entry learned-callee path:
actual CALL/RET effects are checked against generated return targets. A learned
address alone is not permission to inherit entry facts; IJ history, disconnected
targets and inconsistent return edges cannot use this path.
The scoped analyzer partitions proven RSP facts (at most 64 partitions per block).
It narrows a RET's effect flow only for exact sequential return-slot values;
unknown/partial values still join every emitted target. Partition/work exhaustion
is a native-only refusal, not permission to omit an alternative or assume a
balanced call stack. `mutex_stack_bytes=256` in guarded admission identifies the
negotiated local mutex summary: only facts covered for every RSP survive its
memory clobber. Spin, hostcall, unknown and out-of-window effects do not acquire
that guarantee. A zero bound retains the old conservative behavior.
Return-table construction uses an iterative callee-grouped walk with a 65536
work-unit budget. Missing walked CFG locations/successors or exhausted work
produce `CONTEXT_NATIVE_ONLY`, including at final emission after unconditional
admission. No partial table is committed. This is a translation refusal, not
a runtime JIT timeout or a new hostcall; inspect the diagnostic RIP and detail.
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

Explicit GS memory operands use the pinned origin base; supported `current_task`
loads use the logical waiter. FS operands, hardware segment/base manipulation,
recognized context-sensitive calls and backend mismatches refuse publication. Memory checks include lifted implicit effects,
CALL stack writes and bounded cross-block facts. The analysis does not read
runtime memory or assume private source stacks. Unknown aliases, incomplete
lifting and concurrent mutation remain limits, not a security boundary.

A policy refusal exits the translator with status 2, removes stale generated
assembly/binary artifacts and publishes native-only. Launcher errors, signals,
missing dependencies and unexpected translator exceptions are not policy
verdicts; they remain diagnostic/retry failures. Do not turn arbitrary Python
failures into accepted native fallback.

Actual runtime continuation and test commands are maintained in
[JIT_EXECUTION](../docs/JIT_EXECUTION.md). Latest scoped results are in [tests](../tests/README.md); earlier learned
mutex-depth and native-continuation evidence is indexed by frozen version in
[VALIDATION](../docs/VALIDATION.md).

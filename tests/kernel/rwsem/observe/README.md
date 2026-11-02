# Generic rwsem API observation

This diagnostic records callable rwsem API boundaries. It accepts exact symbol
names and an explicit TID list; there is no application-name or syscall filter.
The source API may be KD, Native, or another compatible implementation with the
same first lock-pointer argument and the declared return convention.

This is API timing only. It cannot establish a logical origin, executor,
publication, proxy-body execution, returned JIT body, or delegated read credit.
Every snapshot explicitly reports `proxy_proof = false`. A return from a lock
function is not proof that a different task executed the caller's body.

Build and run only in the designated VM, after its normal identity, idle,
recovery-snapshot and source-freeze checks. No source-host build/test is allowed.
Keep the observer separate from scored runs. Instrumentation can perturb short
API intervals and scheduler/queue behavior.

The ABI is in [payload/api.h](payload/api.h). The module exposes
`/dev/kd_rwsem_observe`. One ARM starts one observation with 1..64 explicit TIDs
and a 1..1000 ms requested duration. An automatic work item then unregisters
all probes. STOP can close the window earlier. Read is permitted only after
STOP has frozen the snapshot; it never follows a recorded object or task pointer.
Event/window timestamps use `ktime_get_ns()` (CLOCK_MONOTONIC), not a nominal
arm duration. `task_start_boottime_ns` is a task-lifetime identifier in its own
clock domain and is never subtracted from event timestamps.
The capture cutoff closes entry admission. Already selected returns may drain
for `drain_ms` (default 100, maximum 1000 ms), followed by normal probe
unregistration. Cutoff and final stop timestamps are separate and may exceed
the requested duration. A call still in flight makes completeness fail; its
work is never forced to return. No timeout or failed collector establishes application drain.

Storage is allocated before ARM and bounded by `capacity` (default 16384,
maximum 262144 events). Handlers reserve one slot with an atomic index, copy
scalar identifiers and publish its sequence. They do not retain object/task
references, allocate, sleep, or use a global lock for event storage. Each
invocation has a unique pairing ID; its entry and return use the same ID.
Task start time distinguishes TID reuse. Calls spanning entry cutoff may leave incomplete API pairs. A fully observed
API pair can also belong to a body interval crossing cutoff; those body
intervals are censored separately. Any overflow, missed kretprobe instance or underlying kprobe hit, retained
invocation, unpublished slot, malformed event or mismatched pair makes the
analysis incomplete and remains visible in the raw snapshot and JSON report.
Normal module unload unregisters callbacks; forced unload is never used.

The exact `api_symbols` module parameter has these eleven positional slots:

1. write acquire, void return
2. write killable acquire, zero means success
3. write interruptible acquire, zero means success
4. write trylock, nonzero means success
5. read acquire, void return
6. read killable acquire, zero means success
7. read interruptible acquire, zero means success
8. read trylock, nonzero means success
9. downgrade, void return
10. write release, void return
11. read release, void return

Defaults are the corresponding `kd_` callable symbols. Empty slots are disabled.
Native Linux lacks an ordinary interruptible writer, so omit slot 3. Duplicate
nonempty symbols are refused. Exact clone/alias symbols are not inferred.
Kretprobe recursion suppression and unsupported/non-probeable symbols can
limit observations; registration failure is a failure, never a skipped pass.
`maxactive` defaults to 256 per enabled API and may be selected explicitly.

The Python tool only arms/stops/collects/parses this diagnostic. It does not
load/unload a provider or observer and does not launch or alter an application.
An external controller must record the exact module/build/symbol configuration,
TID lifetimes, boot, workload and normal application completion separately.

```sh
make -C tests/kernel/rwsem/observe/payload KDIR=<verified-build> W=1
insmod tests/kernel/rwsem/observe/payload/kd_rwsem_observe.ko capacity=16384
python3 tests/kernel/rwsem/observe/collect.py arm --tids <tid1> <tid2> \
  --duration-ms 10 --output <new-output-directory>
```

The default `arm` command waits for the requested interval, issues STOP, writes
`events.bin` before decoding, and writes `result.json` even for incomplete data.
It exits nonzero for incomplete capture. `--arm-only` records the arm reply and
returns for an external controller; a later `stop` command must use a new output
directory. `decode` reads a retained binary without touching the kernel.
Generic `symbols` prints an exact module parameter string for a selected API
prefix or Native family; it does not resolve symbols or prove availability.

The decoder reports acquisition latency and successful acquisition/release
pairing where fully observed. Its protected-body intervals start at successful
API return and end at release invocation. A downgrade return changes an observed
write share to read; downgrade invocation/return is reported separately. API
boundary timestamps do not claim exact physical-owner transition times. The
collector has no matched per-worker runtime denominator, so it never reports a
critical-section ratio. Direct API observation cannot reconstruct a delegated
ownership ledger or prove non-owner cross-task release semantics; such releases
remain unmatched in the body-pairing view instead of being guessed.

`missed` conservatively sums kretprobe instance misses and underlying kprobe
misses, including recursion suppression. It is a completeness indicator, not a
count attributed to the selected tasks; unrelated traffic can make it fail.

The first Linux 7 observer build at `ba82a657` failed because `no_llseek` is
absent in that kernel. The observer now leaves `.llseek` unset, so seeking is
refused by VFS while ordinary sequential reads retain their file offset. The
failed build is retained separately; no module or workload ran in that attempt.

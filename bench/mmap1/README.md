# Unchanged upstream will-it-scale mmap1

This runner is the final application workload for the staged kernel replacement
plan. It runs the original `mmap1_threads` and `mmap1_processes` executables from
will-it-scale commit `75f66e45697e6f5f49c33dd950c4e6b289198f8f`. No syscall loop,
MM body, upstream harness or executable is rewritten. One iteration is the
upstream 128 MiB anonymous private `mmap`/`munmap` pair; the mapping is untouched.
The process and thread models remain separate results. Threads share their mm;
process workers have separate mms and are a control for shared-lock contention.

## Frozen experiment contract

There is one round per point, with workers 1–8 and 12–60 in steps of four, for
each model and explicitly selected backend. The measured window contains two
upstream one-second samples. The upstream harness also performs its own warmup;
the runner does not repeat points, add a separate timed warmup, select peaks or
silently retry failures. A new source campaign uses a new output directory.

The original **`-s 2`** option produces exactly two post-`measurement`
samples. In the pinned `main.c`, the marker is printed at old counter value5;
the next sample increments the counter from6 to7 without ending the run, and
the second increments it from7 to8 and satisfies the strict `> 2+5` stop
condition. Six samples precede the marker. The runner retains upstream's
integer `average:` and reports the sum of the two post-marker totals divided
by two, preserving fractional rates when the upstream integer average truncates.
These are two nominal one-second intervals (`sleep(1)`), not an externally
guaranteed exact elapsed two seconds. Complete process elapsed time includes
setup and warmup. No source or executable modification is used.

The upstream `-m` option places workers on distinct hwloc processing units. The
harness/runner collector uses CPU 63; worker placement is checked from `/proc`
during the upstream warmup, before the measured intervals. The exact observed
CPU set, task IDs, process start times and topology are retained. A 64-vCPU,
two-node guest and the existing fixed-frequency host/recovery checks apply.
The runner does not infer placement from a `taskset` command alone.

## Preparation and execution design

`run.py prepare` will verify a clean pinned upstream Git checkout and every
tracked file, copy those exact files into a new output tree, and invoke its
unchanged Makefile for only `mmap1_threads` and `mmap1_processes`. Compiler,
linker/library versions, executable hashes and all copied input hashes are
retained. Building occurs only in the development VM. The same prepared
executables are reused across compared modes; no compiler or flag override is
accepted. Preparation does not run a timing point.

`run.py measure` will verify the selected Linux 7 schema-2 kernel identity,
installed/build/source binding, boot UUID, recovery snapshot, fixed-frequency
host capture and frozen preparation before launching any application. The
existing explicitly reviewed kernel variants remain the admission authority;
a new kernel generation must first gain its own reviewed verifier profile.
No arbitrary manifest can silently introduce a new release or backend.

Every launch retains the exact argv, executable digest, task identity and
placement, raw stdout, monotonic process interval and result. Output is parsed
strictly and must include all six warmup and two measurement samples plus the
consistent upstream average. A timeout, surviving worker, missing output or
kernel warning fails the point and stops the campaign. No forced kill/unload or
retry is performed by the runner. Normal upstream thread cancellation and
process SIGTERM/reaping are its original shutdown behavior; an exit code alone
does not prove all workers disappeared. The runner verifies recorded task
lifetimes are gone and preserves failed evidence.

The result initially leaves host endpoint acceptance pending. The immediate
post-run host capture must be checked against the retained pre-run reference
before a comparison is accepted. Instrumented observations and performance
runs remain separate evidence.

## Actual object identity and scope

A verified kernel mode is not proof of which lock a particular application
used. An external unscored observation of the unchanged executable must bind
its actual worker PID/TID lifetimes, `mm` pointer, actual `mmap_lock` pointer and
backend, with the same boot, executable and kernel identity. The existing
current-task mmap probe alone does not establish mmap1 workers' objects. A
runner receipt must state when this evidence is absent; it must not fabricate
pointer identity or report an unobserved replacement as accepted.

Same-boot actual MM API, mapping, fault, completed-fault, cancellation,
downgrade and destruction checks remain kernel-stage prerequisites. Module
mechanism tests, custom device timing and a NORMAL translation image are not
substitutes for this real syscall workload. The local adapter currently keeps
native MM bodies on the originating task; this runner does not enable or prove
delegated MM, change fairness, or add killable polling.

The delegated candidate uses an explicit execution-session contract at the
Python `run_point` boundary. The ordinary Native path keeps its existing idle
checks. An opted-in session verifies one frozen provider module identity, its
selected parameters, the exact daemon PID/start time/executable/workspace,
the complete ready immutable image registry and an open source with no live
frames or publishers before and after each application lifetime. This is an
alternative exact execution environment, not a general idle exemption. The
controller must start itself and the daemon before provider activation, prepare
every recorded writer site, activate only after every image is ready, and then
launch fresh unchanged application processes so their new mms select the
provider. Deactivation precedes exact binding/frame/publisher drain and normal
source retirement. The execution-session verifier does not perform those
lifecycle transitions or turn object selection into delegation proof.

The identity probe's ABI2 appends the immutable provider pointer and a route
value to the original task/mm/lock/backing/CPU fields: Native is 0, builtin KD
is 1, and module provider is 2. Runtime request identity/generation and actual
O/E execution events must be joined to the observed task lifetime and backing
lock before claiming returned delegated MM execution. Diagnostic tracing stays
separate from throughput measurements.

Diagnostic points and explicitly traced delegated sessions drain their own
`/dev/kmsg` descriptor continuously onto the evidence filesystem. An independent
external collector does not advance that descriptor. The diagnostic reader
runs on collector CPU63, keeps only a bounded text tail for fault matching,
and stores complete raw records in `kernel.log`, with every read error in
`kernel-log-errors.jsonl`. The shared storage budget is 256 MiB, with 64 MiB
additional free-space headroom required before launch. A ring overrun,
exhausted budget, I/O error, kernel fault or unjoined reader fails the point;
the retained prefix and error summary never count as a complete capture. Stop
and join are bounded and do not imply drain when their deadline expires.
Ordinary Native timing keeps its existing end-of-run reader and all fault
checks. These continuously collected diagnostic points remain unscored.

The implementation and focused runner fixtures are source-reviewed first.
Builds, unit tests and live measurements run only in the VM under the root
controller. Until those checks complete this directory is an implementation
candidate, not performance evidence.

## Interfaces

The current small throughput pilot selects `execution_mode: "image"` in the
configuration for `delegated_point.py`. It reuses the ordinary daemon,
all-site image preparation and `ExecutionSession`; the older reached-mode
configuration remains historical. No lock implementation or MM body changes.
Each model uses one upstream `-t 2 -s 2 -m` lifetime, workers 0/1 and collector
63. Tracing stays off for timing. Native and KD points retain separate receipts.

The image registry, source/frame ledger, provider, daemon and input identities
must match before and after the application. A learning update or unfinished
compiler fails this pilot rather than weakening those checks. A failed point
retains its raw upstream output but supplies no accepted score. Deactivate
before stopping the daemon, then use a fresh process to verify binding/frame/
publisher drainage, retire the source and unload normally. All gates remain.
Throughput is completed mmap/munmap pairs per nominal second; delegation entry,
fully returned JIT bodies and handed-back prefixes remain separate claims.
The pilot does not establish those claims without a matching diagnostic proof.
Focused runner checks include the diagnostic `kdscope5-log16-kd` variant, which
uses the `kdscope5` kernel/build family with its own explicit runtime profile.

Use the existing pinned Python and a real confirmed recovery snapshot. Both
commands require `--mode native|kd`, `--boot-id`, `--host-state`,
`--host-reference`, `--host-reference-sha256`, `--kernel-variant`,
`--kernel-source` (the separated build directory), and `--kernel-baseline`.
The selected mode must agree with the verifier's explicit kernel variant.
For example, after the controller supplies those verified arguments:

```text
python3 bench/mmap1/run.py prepare --upstream /root/will-it-scale-75f66e \
  --output /root/mmap1-inputs-NEW <verified platform arguments>
python3 tests/kernel/mmap1_identity/run.py --inputs /root/mmap1-inputs-NEW/inputs.json \
  --output /root/mmap1-identity-NEW <verified platform arguments>
python3 bench/mmap1/run.py measure --inputs /root/mmap1-inputs-NEW/inputs.json \
  --identity-result /root/mmap1-identity-NEW/result.json --model both \
  --api-result <same-boot API result> --mapping-result <same-boot mapping result> \
  --faults-result <same-boot faults result> --completed-result <same-boot completed result> \
  --output /root/mmap1-measure-NEW <verified platform arguments>
```

`--model threads` or `--model processes` selects one distinct 21-point tree;
`both` creates 42 separate points. There is no repeat/duration override.
`prepare` and the unscored identity observation support the disabled ordinary
kernel as a Native control. `measure` currently requires an enabled-MM variant
with all four existing exact-mode correctness receipts; adding a new kernel
profile is a separate reviewed integration change.

The identity runner observes two workers for each model, with a bounded kprobe
loaded only for that unscored lifetime. `measure` replays its stopped records
against the retained task/CPU observations and file hashes. It does not reuse
the diagnostic pointer values for timed workers. See
[the identity probe contract](../../tests/kernel/mmap1_identity/README.md).

Successful output retains `result.json`, `plan.json`, copied schema-2 kernel
bundle, frozen runner sources, input/executable/library hashes, host reference,
environment/topology, and each point's command, raw output, task snapshot and
kernel log. Whole-process elapsed and CPU times include warmup and shutdown;
they are not the denominator of the two raw measurement intervals. Both
measurement intervals must show positive minimum worker progress. A zero
warmup minimum is retained; zero measured progress fails the point and remains
visible in its raw log. The immediate post-run host endpoint and paired
performance decision belong to the controller. Archive only after verified
idle; the existing archiver's release admission must explicitly support the
selected kernel variant before it is used.

The directly affected guest checks are the two basic unit programs,
`tests/unit/bench/test_mmap1.py`, and a `W=1` build of the identity payload on
the selected exact kernel. The focused driver checks the upstream counter
boundary, bad/truncated output, source/binary binding, worker placement,
identity/sharing/reference conservation, and failure paths that must not become
drain or forced cleanup. Source parsing alone is not a test pass.

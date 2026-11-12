# Kernel9 cacheline1/post256 runner

This runner binds the rebuilt KD runtime and the retained Native/TCLock
comparators to one padded-counter workload. The current evidence is the
[2026-11-12 report](../results/10.176.26.71/bench/kernel9-nano-20261112/README.md):
six functional lanes and 54 exploratory timed sessions on the exact kernel9
image. KD trails both comparators in that instrumented configuration; all six
one-worker KD NO_JIT sessions remain included.

The [single-worker recorder comparison](RECORDER.md) is a separate, source-only
handoff for the test session. It keeps recording enabled by default and adds
quiescent on/off phases without changing the kernel protocol or payload.

The measured payload is the generic `RB_LINES=1` branch of
[body.h](../../workload_modules/nano/body.h), followed by 256 register-only
multiply/add rounds outside the lock. It matches the earlier named
`mutex-throughput` and `rwsem-throughput-mixed` profiles. It does not select
the separate two-word `RB_NANO` body. The benchmark directory name is not a
claim that every historical nano workload is equivalent.

## Binding and measurement

[direct.h](../../workload_modules/nano/direct.h) selects the actual mutex or
rwsem API. KD readers remain local and concurrent; only writers can delegate.
[runtime.inc](../../workload_modules/nano/runtime.inc) admits immutable module
text and the exact built-in return thunk, creates the runtime once, and gives
each registered worker preallocated storage before its loop. It configures
256 request/frame records, 128 KiB auxiliary stack, 64 KiB required control
space and proxy-grant limit 16. These are bounded workload assumptions.
TCLock retains its original native-stack mechanism, NUMA selection and
continuation-counter limit 1024; those counts are not equivalent batch lengths.

[evidence.inc](../../workload_modules/nano/evidence.inc) observes the exact
request lifetime, image, typed writer unlock and completed protected episode.
Its bounded records and first completion witness do not replace actual core
ownership/retirement checks. Recording stays enabled during KD timing and adds
per-event work, including a per-origin IRQ-saving spinlock. Native and TCLock
have different instrumentation. The recorded result is not isolated protocol
overhead or uninstrumented KD performance.

Each pinned worker issues one bulk ioctl; mutex is 100% writes and rwsem is
20% writes. The deterministic mix, post-work and final counter deltas are
checked independently. Progress publishes every 256 operations and samples
every 10 ms. Whole throughput uses actual start-through-join elapsed time;
the warmed peak uses a measured full-cohort window of at least 300 ms after
300 ms of settling. The report explains both denominators and timing limits.

## VM workflow

Source editing, Git and offline archive review belong on the source host.
All builds, compiler execution and live checks belong in the development VM.
Keep a fresh immutable source snapshot, source/output-separated builds, exact
kernel/source/configuration/GS proof, verified recovery snapshot, sufficient
disk space and an idle guest. Never edit running inputs or infer drain from a
timeout. A bounded command failure preserves its child/module state for review.

[build.py](build.py) accepts `--repo`, `--kernel-source`, `--kernel-output` and
a fresh `--output`. It builds/signs the six family/backend workload modules and
two TCLock providers for `7.0.0-38-kdrebuild9`, records tool/module hashes and
requires emitted TCLock context audits. It does not establish a new kernel's
identity or recovery readiness itself.

[run.py](run.py) requires the frozen repo, build receipt, fresh output, family,
backend, stage (`functional` or `timing`), exact boot UUID, kernel ELF and GS
proof. The captured invocation files in the result archive preserve the exact
arguments used. Timing additionally requires all six current functional result
files through repeated `--prerequisite` arguments, matching the same boot and
build receipt. The runner trains KD before timing, fixes the published image,
checks claims without rebuilding during timed phases, and checks exact normal
shutdown before unload. Clear TCLock's diagnostic target before unloading the
workload, then unload its provider only after complete task/queue drain.

`reused-inputs.json` records the earlier files selected as adaptation inputs.
It is not a claim that every adapted file remains byte-identical. The report's
frozen source manifest, signed binary hashes and archive member hashes bind the
executed version. Spin/rwlock, other workloads, general API/context support,
strict timing qualification and actual syscall validation are outside this run.

# JIT continuation payload

This is a focused correctness workload for KD mutex instruction exits. Use the
[guest runner](../README.md); this directory contains
only the kernel payload and its userspace command layout.

JIT means just-in-time compiled code that lets a lock holder execute a waiting
task's protected operation. A **marker** is generated code that stops delegation
immediately before a reviewed instruction and returns execution to the original
waiting task. The marker must preserve work already done and must not execute
the reviewed instruction itself. The original task continues at that instruction
for a native suffix. Eligible sole-outer ABI2 mutex gates on v13 may instead execute
a bounded instruction service there and return to the same JIT invocation; the
runner distinguishes both. Explicitly prepared rwsem writers use that same gate
without releasing their write admission; shared readers stay local.

`JIT_CONTINUATION_ORIGIN_INSTRUCTIONS=1` adds RDTSCP, CPUID leaf 1/subleaf 0 and another
RDTSCP after the existing RDTSC. Native pre-lock observations are per worker,
outside the translated interval. Each instruction has its own exact effect
counter and CF/PF/ZF/SF/OF/conditional-branch check. Eligible ABI2 writer builds omit
LAHF because it is itself a native marker; AF is covered by the separate
full-flags fixture rather than claimed as live evidence. Both raw TSC_AUX values and all
CPUID outputs must match the original worker. A separate read-only snapshot
command exposes the four counters and source PCs without changing old ioctl
layouts. Only a mutex with no nested spin may build this variant.

The protected operation increments a prefix counter, checks a mutable condition,
and increments a suffix counter before unlocking. The condition starts false:
the unusual instruction is present in the original code, but normal calls never
reach it. `JIT_CONTINUATION_MUTEX_API=outer` selects the existing explicit outer pair;
`public` selects literal `kd_mutex_lock/unlock` calls. Both use ABI2, the existing
machine-level calling agreement for delegated mutex operations. The public
shell's named entry aliases DIRECT's actual captured continuation and must pass
the runner's ELF audit before loading. Atomic active-writer counts
check that no two tasks execute the protected operation simultaneously.

After all workers finish, the runner makes the condition true. It later clears
and sets the condition again through idle-only controls, without preparing or
replacing the image. Both cold phases must complete delegated bodies and both
taken phases must reach validated markers. That branch uses
`RDTSC`, the x86 read-timestamp-counter instruction. It safely reads a processor
counter on the designated guest and leaves arithmetic condition flags unchanged.
The instruction does not change interrupt enable state or write privileged
processor settings. Its named `jit_continuation_marker` label identifies the exact
original instruction address expected in the runtime exit event.

Immediately before that address, `CMP` compares 1 with 2, establishing known
arithmetic flags. An unconditional jump carries them across a generated-code
block boundary. Immediately after `RDTSC`, `SETcc` instructions record whether
each condition is true. The flags tested are carry (CF), parity (PF), zero (ZF),
sign (SF) and signed overflow (OF). Native-suffix family/nesting variants retain
`LAHF`, which copies low status flags into a register and additionally checks
auxiliary carry (AF). Eligible ABI2 writers omit LAHF so that it does not force a
second native boundary after a successful instruction service. The full arithmetic
mask is `0x8d5`, with expected value `0x95` for this comparison. These checks catch
condition-flag corruption during generated-code instruction accounting or exit.

The continuation also reads the current task pointer. After the
function unlocks and returns, the caller compares that pointer with its own task
and checks the recorded flags. That logical task observation alone does not prove
which physical CPU executed a service; the extended RDTSCP/CPUID observations and
the runtime's exact original-task transaction checks supply that evidence.
Every caller must complete every requested
operation without an error. Each phase also requires exact prefix and suffix
increments, the expected number of taken branches, zero active writers, and an
idle KD mutex. An idle workload is followed by the runner's separate source and
execution-record retirement checks.

The command interface refuses phase changes while any caller is active. There
is no runtime switch that skips checks, retries failed effects, or substitutes
an unsafe privileged instruction. This workload supplies correctness evidence;
it is not a performance benchmark or proof that arbitrary instructions can be
delegated safely.

Helper mode also has a distinct two-to-five argument mapping phase and one
53-byte zeroed allocation/free phase. The former records both logical and Native
targets, the compiler-issued source CALL end, five actual Native arguments and
original-task stack/context. Post-CALL CF/PF/ZF/SF/OF are captured with `SETcc`
before a flag-changing instruction; the transaction trace separately compares
the complete done/resume flags. A new version-1 240-byte snapshot leaves the existing
observation ABIs unchanged. Mapped registration occurs through an idle-only
post-load command before publication; normal owner unregistration removes both
identity and mapped descriptors after source retirement. These are mechanism
checks and do not substitute for an actual application workload.

# Conditional instruction exit workload

This is a focused correctness workload for KD mutex instruction exits. Use the
[guest runner](../../tests/kernel/jit_escape/README.md); this directory contains
only the kernel payload and its userspace command layout.

JIT means just-in-time compiled code that lets a lock holder execute a waiting
task's protected operation. A **marker** is generated code that stops delegation
immediately before a reviewed instruction and returns execution to the original
waiting task. The marker must preserve work already done and must not execute
the reviewed instruction itself. The original task continues at that instruction.

The protected operation increments a prefix counter, checks a mutable condition,
and increments a suffix counter before unlocking. The condition starts false:
the unusual instruction is present in the original code, but normal calls never
reach it. The explicit KD outer mutex pair uses ABI2, the existing machine-level
calling agreement for delegated mutex operations. Atomic active-writer counts
check that no two tasks execute the protected operation simultaneously.

After all workers finish, the runner makes the condition true. That branch uses
`RDTSC`, the x86 read-timestamp-counter instruction. It safely reads a processor
counter on the designated guest and leaves arithmetic condition flags unchanged.
The instruction does not change interrupt enable state or write privileged
processor settings. Its named `jit_escape_marker` label identifies the exact
original instruction address expected in the runtime exit event.

Immediately before that address, `CMP` compares 1 with 2, establishing known
arithmetic flags. An unconditional jump carries them across a generated-code
block boundary. Immediately after `RDTSC`, `SETcc` instructions record whether
each condition is true. The flags tested are carry (CF), parity (PF), zero (ZF),
sign (SF) and signed overflow (OF). `LAHF`, which copies low status flags into a
register, additionally checks auxiliary carry (AF). Their combined arithmetic
mask is `0x8d5`, with expected value `0x95` for this comparison. These checks catch
condition-flag corruption during generated-code instruction accounting or exit.

The same native continuation reads the actual current task pointer. After the
function unlocks and returns, the caller compares that pointer with its own task
and checks the recorded flags. Every caller must complete every requested
operation without an error. Each phase also requires exact prefix and suffix
increments, the expected number of taken branches, zero active writers, and an
idle KD mutex. An idle workload is followed by the runner's separate source and
execution-record retirement checks.

The command interface refuses phase changes while any caller is active. There
is no runtime switch that skips checks, retries failed effects, or substitutes
an unsafe privileged instruction. This workload supplies correctness evidence;
it is not a performance benchmark or proof that arbitrary instructions can be
delegated safely.

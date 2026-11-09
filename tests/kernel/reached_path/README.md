This directory now retains a standalone decoder/effect reference. It is not a
production interpreter or an alternative JIT. The provider uses the original
compiled-image backend only. Historical receipts remain bound to their source.

# Reached scalar execution check

This focused check executes the exact `tests/kernel/reached_path/fixture/reference.inc` component in
a separate kthread. Its canonical source RSP points into a retained fixture
array on the waiting module-loading task's stack; the executor keeps its own
kernel C stack. The payload records
distinct executor and module-loading task identities. It creates no application
image, invokes no compiler and explores no successor graph.

The Native differential matrix covers ADD, OR, ADC, SBB, AND, SUB, XOR and CMP
at 8, 16, 32 and 64 bits, including carry input, boundary operands, partial
register updates and 32-bit zero extension. It compares the defined arithmetic
flags; logical AF is undefined and excluded. Other cases cover effective/RIP
addresses, AH versus REX/SPL, MOVZX/MOVSX, conditional moves, source PUSH/POP and
LEAVE, actual Jcc selection with unavailable successor bytes, indirect CALL
whose source operand is overwritten by the return push, inherited RET words,
RET adjustment, tail JMP, PAUSE, fences and ENDBR64.

The check also verifies MINIMAL materialization without consuming unspecified
GPR values, persistent budget across segment returns, the fixed 64-instruction
local cap and cold progress with preemption disabled. Unsupported LOCK/XCHG,
truncated source and failed writes must leave the packet and data unchanged;
these results are unfinished instructions, not successful public API results.
The supplementation case commits an increment and JMP before encountering an
unavailable target, adds only the actual reached target bytes, and continues on
E through MOV and an inherited RET without replaying that increment. A truncated
MOV is completed and retried at the same source IP without resetting the budget.

The payload compiles the provider component directly from the immutable input
tree, rather than exporting additional production symbols. The runner builds
the ordinary provider separately. Fixture callbacks use resident arrays; they
do not qualify arbitrary kernel memory, MMIO, exception/fixup behavior, source
epoch handling or live MM delegation. Existing killable/nesting/downgrade
protocol checks remain separately required. Family/cache/control joins belong
to later stages and are not inferred from this scalar check.

Build and load only on the designated VM, using `run.py` and a new external
output directory. Retain the exact snapshot, boot, recovery, logs and normal
unload result. A successful row starts with
`KD_REACHED_TEST result=PASS cases=... executor_pid=... origin_pid=... source_fetches=...`.

# Conditional JIT instruction exit check

Run only in the verified recovery guest, following
[VM operations](../../../docs/operations/VM.md). The runner freezes the source,
including private `.inc` implementation files, and builds the provider, daemon,
allocator guard and [kernel payload](../../../workload_modules/jit_escape/README.md)
inside a new output directory. Source and binary hashes record the exact inputs.

JIT means just-in-time compiled code used to execute a waiting task's work on
another lock holder. An instruction **marker** exits that code before an
instruction that must run on the original task. This check uses `RDTSC`, the
safe x86 instruction that reads the processor timestamp counter. It does not
exercise instructions that disable interrupts or change privileged settings.

Set the verified snapshot variables and the pinned Python environment described
in the VM guide before running:

```sh
timeout 900s python3 tests/kernel/jit_escape/run.py \
  --cpus 0-15 --iterations 100000 --warmup-iterations 100000 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-escape-NEW
```

The four phases remain in one provider/source session:

1. `cold-warmup`: run with the unusual-instruction branch disabled, leaving it
   present in the code. The image must publish as `NORMAL`, which means ready
   for execution, and no instruction marker may be reached.
2. `cold-delegated`: repeat that workload and require positive, matching entry
   and completed-body counts. A completed body reached its matching unlock;
   publication alone is insufficient.
3. `hot-escape`: after all callers join, enable the branch and run contention.
   Require a validated instruction-exit count, an event naming this exact
   instruction address and one of these worker tasks, and the terminal registry
   state `NATIVE_ONLY`. That state disables future delegation for the entry.
   Prefix/suffix counters, the original-task check and arithmetic condition-flag
   checks must still pass for every operation.
4. `post-ban`: after the prior callers join, run the same taken branch again.
   Neither generated-code entries nor instruction exits may increase, and the
   registry must remain `NATIVE_ONLY`. Operations still execute correctly on
   their original tasks.

The runner accepts capability versions 6, 7, 8, 9 or 10 only when feature bit 5
(native instruction exit) is present. The current provider advertises version 10;
the version alone does not establish support. The private benchmark observation
overlay supplies entry/completion counts, including validated root completions
after helper services; the production `native_escape_count` counts validated
marker events.
That count does not by itself prove that a native continuation completed. The
operation and final-retirement checks supply the additional evidence. The marker
log is rate limited, so the test does not require one printed line per count.

Every phase records worker process identifiers, exact per-worker progress,
counter snapshots, registry state and kernel messages. The payload checks all
six arithmetic condition flags carried from a comparison through an
unconditional branch, the marker exit and `RDTSC`; see its README for the flag
names and expected values. Existing mutex ownership, release acknowledgements
and source-lifetime rules remain in force.

A timeout or kernel fault preserves running callers and loaded modules for
diagnosis. It does not prove that work finished and does not authorize forced
unload. Successful completion requires workers to join, zero active execution
records, successful source retirement, ordinary module unload, and final idle
inspection. This is a focused correctness check; no throughput result is claimed.

This check covers the selected KD mutex ABI2 instruction-marker path. The
[spin address-guard probe](../spin/address_guard/README.md) and
[original strcmp service probe](../spin/string_service/README.md) exercise
separate negotiated boundaries. Their feature bits do not authorize arbitrary
instruction traps, memory faults or replay of a partially executed body.
The string probe now requires valid short and 300-character inputs to complete
delegated comparison calls, without the former helper prechecks. That change
does not alter this instruction marker's continuation or permanent-disable checks.

"""Versioned arithmetic-flags transfer for retained block-budget pauses."""

REQUIREMENT = 1 << 7


def entry_dispatch(output, targets):
    """Run after PUSHFQ; each accepted or refused route consumes that word."""
    output.write("CMP Stack_CLOBBER, 0\nJNE kd_budget_regular_dispatch\n")
    output.write("MOVABS R15, KD_REG_BUDGET_REENTRY_TAG\n")
    output.write("CMP QWORD PTR[REG_BANK + KD_REG_ORIG_AX], R15\n")
    output.write("JNE kd_budget_regular_dispatch\n")
    output.write("MOV QWORD PTR[REG_BANK + KD_REG_ORIG_AX], 0\n")
    for offset in sorted(targets):
        output.write(f"CMP R14, 0x{offset:x}\nJE kd_budget_dispatch_{offset:x}\n")
    output.write("POPFQ\nMOV Stack_IJ, 0x2\nMOV R15, R14\nJMP exit\n")
    output.write("kd_budget_regular_dispatch:\n")


def continuation_dispatch(output, targets):
    for offset in sorted(targets):
        output.write(f"kd_budget_dispatch_{offset:x}:\nPOPFQ\n")
        output.write("PUSHFQ\nPOP R15\n")
        output.write("AND R15, ~KD_REG_ARITHMETIC_FLAGS\n")
        output.write("MOV R14, QWORD PTR[REG_BANK + KD_REG_FLAGS]\n")
        output.write("AND R14, KD_REG_ARITHMETIC_FLAGS\nOR R15, R14\n")
        output.write("PUSH R15\nPOPFQ\n")
        output.write("MOV Stack_JIT_WITNESS, 1\n")
        output.write(f"JMP loc_{offset:x}\n")


def exhausted(output):
    # DEC changed physical flags, but the instrumentation's saved source word
    # still tops the wrapper stack. Export it before any wrapper cleanup.
    output.write("POPFQ\nPUSHFQ\nPOP R15\n")
    output.write("MOV QWORD PTR[REG_BANK + KD_REG_FLAGS], R15\n")
    output.write("MOVABS R15, KD_REG_BUDGET_READY_TAG\n")
    output.write("MOV QWORD PTR[REG_BANK + KD_REG_ORIG_AX], R15\n")

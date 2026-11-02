"""Exact arithmetic-flags reentry after a registered returning primitive CALL."""

REQUIREMENT = 1 << 9


def entry_dispatch(output, targets):
    output.write("CMP Stack_CLOBBER, 0\nJNE kd_service_regular_dispatch\n")
    output.write("MOVABS R15, KD_REG_SERVICE_REENTRY_TAG\n")
    output.write("CMP QWORD PTR[REG_BANK + KD_REG_ORIG_AX], R15\n")
    output.write("JNE kd_service_regular_dispatch\n")
    output.write("MOV QWORD PTR[REG_BANK + KD_REG_ORIG_AX], 0\n")
    for target in sorted(targets):
        output.write(f"CMP R14, 0x{target:x}\nJE kd_service_dispatch_{target:x}\n")
    output.write("POPFQ\nMOV Stack_IJ, 0x2\nMOV R15, R14\nJMP exit\n")
    output.write("kd_service_regular_dispatch:\n")


def continuation_dispatch(output, targets):
    for target in sorted(targets):
        output.write(f"kd_service_dispatch_{target:x}:\nPOPFQ\n")
        output.write("PUSHFQ\nPOP R15\n")
        output.write("AND R15, ~KD_REG_ARITHMETIC_FLAGS\n")
        output.write("MOV R14, QWORD PTR[REG_BANK + KD_REG_FLAGS]\n")
        output.write("AND R14, KD_REG_ARITHMETIC_FLAGS\nOR R15, R14\n")
        output.write("PUSH R15\nPOPFQ\nMOV Stack_JIT_WITNESS, 1\n")
        output.write(f"JMP loc_{target:x}\n")

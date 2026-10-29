# Actual measured ELF inspection

These are source-host static observations, not builds, fixture runs or live
samples. `baseline-provider-provenance.json`, `baseline-workload-provenance.json`
and `candidate-elf-provenance.json` identify exact archived members and hashes.
ELF bytes remain in the raw archives and authenticated temporary data copies;
no executable binary is added to this report.

`measured-text-sections.json` compares every `.text*` section for all ten KD
workloads and providers. All ten workload section maps match byte-for-byte.
`provider-function-maps.json` records `.symtab` offsets, sizes and raw function
hashes from the actual mutex c01 provider pair; it is not a source estimate.
`measured-type-sizes.json` records structure sizes from those modules' DWARF.

`method.json` records the tools and exact command forms. The disassembly files
come from `objdump -d --no-show-raw-insn --disassemble=FUNCTION MEASURED_ELF`.
Normalization removes printed instruction addresses and numeric addresses before
symbolic targets; it retains instructions, operands and symbolic relative
offsets. Empty normalized diffs for the five recorded mutex/rwsem functions
mean equal instruction listings under that rule. They do not prove identical
relocation targets, runtime addresses, caches or timing.

The spin `run_combiner` listing changes, including its stack reservation,
initialization size and context checks. Its source counterpart is
`kernel_module/spin/combiner.inc` at the two explicitly measured commits.
Those observations establish code differences; they do not assign a percentage
of throughput loss to those differences.

The initial optional workload-ELF extraction failure is recorded separately.
All ten copied workload bytes were subsequently checked against their actual
archive members and binary maps without modifying either. Both complete
campaign audits and the full matched comparison passed on their first runs.

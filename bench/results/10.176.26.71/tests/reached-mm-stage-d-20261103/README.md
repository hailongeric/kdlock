# Reached MM activation: Stage (d)

Isolated branch: `codex/reached-path-translation`, continuing from
`1fec704bbeb19b3391066c49a5cb1e303528d2e9`. Native MM bodies, the MM integration
layer and the pinned will-it-scale executables are unchanged. This campaign
activates the general reached-mode rwsem provider; it adds no mmap1-specific
production helper or origin suffix.

## First candidate: `c7e10b24`

Exact source: `c7e10b24d80f6d710f12791a5159c23f1e9573a7`. The new session
contract requires no translator, image or writable device descriptor. General
provider preparation validates and pins the complete writer-site table without
allocating image slots. The old image session remains a separate contract.

| Check | Result |
| --- | --- |
| Affected session/runner unit driver | 21 cases passed |
| Delegated MM proof driver | Six cases passed |
| Syscall-pair driver | Nine cases passed |
| Private frozen-source driver | Nine cases passed |
| Ordinary provider and observation module builds | Passed |
| Actual mmap1 launch | Failed during the fresh child's exec MM setup |
| Returned mmap1 worker body / syscall pair | Not proved |
| Process-model run | Not started |
| Final retirement | Failed/undrained; VM recovery required |

The kernel was `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`17478c05-2012-4095-ada6-977c32222817`, with `kd_mmap=on` and full/lazy
preemption. The exact v3 ELF site audit has SHA256
`bcc3b8b23fc332904e26929e7e43961416d11db705480ed63e301dca07e1a7a1`;
all 55 records were audited. The retained unit and build receipts are separate
from actual application completion.

The first captured root was `create_init_stack_vma`, entry
`ffffffff8181cc7d`, O `18533`, E `18513`, request identity
`ff11000633db8fa8`, generation 1. It stopped at `ffffffff817f66da` in
`find_vma_intersection`, after reaching artifact sequence 82. The instruction
`65 4c 8b 25 26 49 c1 02` is a 64-bit GS load into R12. It reads the kernel's
per-CPU stack guard; the existing decoder recognized it, but the runtime read
policy allowed only preempt-count operands and returned `-EINVAL` internally.
The existing diagnostic path stopped E; O remained pinned and waiting. No
public lock error or completed body is inferred.

The stopped origin occupied the collection CPU during exec, so the ordinary
guest collectors could not record a final state. Before reset, the QEMU host
preserved the full serial file and a paused, consistent copy of the kernel
printk ring, descriptor array, info array and data buffer. The decoded
[failure excerpt](first-kernel-ring.log) is offline diagnostic evidence,
not a continuous complete-run receipt. [Raw capture identities](first-ring-capture.json)
and [retention locations](first-retention.json) preserve the original bytes.
The failed guest's persisted controller/build/session files were copied after
recovery; [the controller state](first-controller-state.json) remains at
`APPLICATION`, without worker return or drain.

One QEMU reset recovered the failed VM to the ordinary kernel; a one-time GRUB
entry then returned to scope5 KD. Default GRUB configuration was unchanged.
Recovery is not successful retirement. New attempts use separate frozen inputs,
output directories and boot identities; no counts are pooled across attempts.

## General instruction-service correction

The design was committed first as `8536bf61`. General resident GS loads/tests
now use the returning O instruction service, retaining exact CPU/GS base, IRQ,
Native owner, source frame and artifact ACK checks. Only actual preempt-count
operands receive count normalization; an ordinary read allocates no preempt
owner. This is an instruction interval, not an MM body moved to O.

The encountered function's normal epilogue contains
`65 48 2b 15 f8 48 c1 02` at `ffffffff817f6708`. General GS-source SUB32/SUB64
to a register is added with its exact input register value, width, destination
and Native arithmetic flags. The input operand is retained through all four
service/ACK stages. There is no named canary or caller-specific execution path.
This bounded inspection of the reached callee's return neighborhood does not
require an upfront CFG closure.

The correction still requires a fresh VM build and actual mmap1 retry. It does
not establish general faulting GS access, all context instructions, returned
mmap1 delegation, throughput or a Nano gate. Remaining unsupported operations
must be supplemented explicitly when reached; no entire suffix is run on O.

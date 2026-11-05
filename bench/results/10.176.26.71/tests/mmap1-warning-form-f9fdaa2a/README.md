# Bounded reproduction of the refused munmap instruction

On a new boot of the matched kernel, the maintained leased instruction reader
captured 15 bytes at `0xffffffff81817f57`. The first instruction is the exact
five-byte `67 48 0f b9 3a` UD1 form. The pinned Miasm decoder returned
`Disasm_Exception: cannot disasm (guess) at 2`, reproducing the earlier
decoder failure pattern. No application or performance comparison ran here.
The `passed` result refers to capture and drain, not successful decoding or
delegation.

The earlier campaign did not retain its live bytes. This new capture supports
the diagnosis on the same Build ID; it does not recover or directly prove the
old boot's instruction bytes.

## Identity and source path

- Reproduction kernel: `7.0.0-38-kdscope5`, Build ID
  `5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`.
- Reproduction boot: `c301906d-c322-47a2-9e9e-a0840f4401d6`.
- Frozen reader source: `f9fdaa2aa6a71ca0b03dd3a859d63bf746c0983a`.
- Provider build source: `130b65939053026339014833774e5fb11b234972`; binary
  SHA256 `e8870c9b469e6489227f5f20f6ef9a24700061afd9480e37dbdaaef5c8fa8274`.
- Full 15-byte sequence: `67480fb93ae99ffeffff41bff4ffff`; SHA256
  `58f4d16ccb215daa05e539d9da5c7e004ef481983c504d21086fb24c5e9c35ba`.

The disk ELF has a CALL to `__SCT__WARN_trap` at this site. The matching Linux
source defines the five-byte replacement in `arch/x86/kernel/static_call.c:32`
and selects it for `__WARN_trap` at lines 77–80. Its interpretation is documented
in `arch/x86/kernel/traps.c:98`. These source files are retained with hashes.

The site belongs to the inlined `file_ref_inc()` in `get_file()` within
`__split_vma()`, rather than the separate initial VMA-boundary checks:

`mm/vma.c:537` → `get_file(new->vm_file)` at line 538 →
`include/linux/fs.h:1311` → `include/linux/file_ref.h:120–121`.

The reference increment happens before `WARN_ONCE(prior < 0, ...)`. The
diagnostic branch is skipped when `new->vm_file` is NULL; otherwise a negative
prior count selects the warning. There is no evidence that this warning branch
executed during the benchmark. The compiler refused it while exploring the
expanded reachable graph.

## Required correction, still a proposal

Recognize only the exact confirmed instruction form and represent its reached
site as an explicit frontier in the original retained JIT backend. Untaken
branches must keep executing in the JIT. If taken, hand back at the original
first-unexecuted UD1 address with the current IP/SP/flags/GPRs and every earlier
effect intact. In particular, do not replay the reference increment, push or
consume a CALL word, or copy UD1 to a helper address.

This needs an explicit retained-frontier outcome and negotiated image contract
alongside the existing owner/source/frame/ACK handoff transport. Adding the
instruction to the legacy marker list alone is insufficient: that image class
does not permit retained-service combinations. Reporting a fictitious indirect
miss would also give incorrect provenance and futile learning. No packet-layout
change, instruction interpreter, separate backend or caller-specific MM code is
proposed. The public lock API, killable arbitration, nested owner records and
downgrade/read-tail protocol remain unchanged. This protocol change has not been
implemented or validated.

## Retirement

The provider factory remained inactive with zero bindings. The text read held
the source writer lease, then closed it. Exact retirement returned
`state=2, modules=0, frames=0, writers=0`; ordinary unload and idle checks passed.
The normal `7.0.0-38-kdlock1` kernel, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored and verified on boot
`3da48c0e-7596-469a-bfea-45122dfd4d81`.

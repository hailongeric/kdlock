# Reached direction-state boundary correction

Exact `STD` and `CLD` can now end a retained JIT path before the instruction,
using the existing permanent original-task continuation. Other branches keep
executing generated code. The focused VM checks and provider compilation passed.
No provider was loaded and no mmap1 application or performance point ran.

| Artifact | Commit |
| --- | --- |
| Starting report | `8e9a78384055c81174f1ea0e5c1d9bc7413ef2b3` |
| Design, committed first | `7a36560d` |
| Implementation | `971eddfbb8b912fb640ec5201e1e990426d26e47` |
| Checked source, with fixture correction | `d726952d8f03bffe62b83028fb51d6726fb1f434` |

The earlier [fixed-point report](../../bench/mmap1-settled-276f2647-20261107/README.md)
identified a new `mas_wr_bnode` target and a replacement translation that
selected `STD` at `0xffffffff826f0777`. Its 195.512-second exit-2 result was
translation evidence; it did not establish that the application executed STD.
That historical failure and its receipts remain unchanged.

Deleting the whole-image refusal would select an incompatible mechanism.
Legacy `NATIVE_ESCAPE` and retained `SERVICE_QUEUE` images use different
consumers and ownership records. The existing retained `SOURCE_FRONTIER` route
already exports the FULL scalar packet and stops before an exact instruction.
This correction adds only unprefixed `fc`/`fd` to that decoder and the kernel's
one-byte validation table. Capability version 21 plus the existing frontier
feature negotiates these forms on the actual device lease; version 20 cannot
enable the new direction-state decoder option. Session close resets the option.

On a reached boundary, generated code spills mapped registers, saves arithmetic
flags and exports the first unexecuted IP without adding or consuming a source
CALL word. `kd_jit_source_frontier()` validates the retained continuation,
executor, source lease, packet, immutable image, stack range and exact source
byte. The existing `KD_EXE_RUN_HANDOFF` route retains ownership and lifetimes
through acceptance, actual releases and final ACK. The origin resumes the
native suffix permanently. There is no JIT successor from that instruction
and no executor reentry through the native copy/clear sequence.

The matching v4 ELF, Build ID `357a7115d21941960b90262ac1165bf70d1b398e`, contains:

```text
0xffffffff826f0777  STD
0xffffffff826f0778  REP MOVSQ
0xffffffff826f077b  CLD
0xffffffff826f077c  MOV [R10],R11
0xffffffff826f077f  JMP 0xffffffff826f0868
0xffffffff826f0868  JMP 0xffffffff82704e30
```

The completed prefix has already loaded R11, retained the destination in R10,
adjusted RSI/RDI and shifted RCX to the qword count. Resume at STD, preserving
those values and virtual SP, rather than repeating the function entry. This
suffix does not consume incoming condition flags before copy/clear/return.
Plain `REP MOVSQ` uses RCX/DF. The origin sets DF with STD and clears it with CLD
without returning the suffix to generated execution.

The existing restore mask remains `0x8d5`, covering arithmetic flags only;
the origin keeps its actual IF/DF/AC. This relies on the existing DF-clear
scalar execution contract before the boundary. No transfer of executor DF=1,
general flags equivalence or SIMD/FPU restoration is added or claimed.
The lock protocol, public API, cancellation/nesting/downgrade ordering,
original JIT/GS behavior, depth-five/lock-region limits and immutable online
publication are unchanged.

VM validation on the unchanged normal boot
`78a62f64-862a-4a19-89d5-7a0e2d5e8951` passed:

- Eleven source-frontier fixtures, including reached/bypassed STD/CLD paths,
  exact pre-STD GPR/SP export, no successor beyond the terminal, retained memory
  services in the same image, and exact byte/capability handling.
- Four selected capability fixtures, including v20 refusal of the new option
  and v21 lease reset.
- Production retained join fixtures for write, downgrade and read, with supplied
  physical/task primitives and the original ownership/ACK checks.
- The existing source-lifetime baseline: 49,916 checks, zero failures. Mutation
  variants were not run.
- Provider compilation with `W=1`, against the existing `7.0.0-38-kdscope5`
  output for kernel component `9a5d606aee0249d0e566a1c9667375eb038bc9cd`.
  The recorded compiler-name and objtool return/stack warnings remain.

The overlap fixture executes the real generated prefix, checks that no copy
occurred and one prior source effect occurred, then runs a small native suffix
double on a separate C stack. It verifies the overlapping result, canaries,
return value, DF clearing and no repeated prefix effect. It does not exercise
kernel original-task restoration or prove live mmap1 execution. The first
fixture run at `971eddfb` passed ten of eleven tests; the coexistence fixture
lacked mock lock symbols. `d726952d` corrects only that fixture setup. Both
attempts remain retained.

Final provider SHA256:
`602c5bd93770e8f4118ae163f66b12382d8b39cd888f297f4efd9be7fed48262`.
The provider stayed unloaded. Frozen input bytes passed verification afterward,
and the normal kernel remained verified and idle. The former whole mmap
translation was not replayed, and no throughput change is claimed.

The separate offline munmap g9 inspection found a remaining return frontier.
The learned pair `0xffffffffc0000f28` -> `0xffffffffc0e32980`
(`kd_provider_assert_held`) is emitted once despite two history rows. Both the
provider callback and `kd_rwsem_assert_held` body are present. The inner RET
edge `0xffffffffc0e31e36` -> `0xffffffffc0e3298e` is present. However the outer
CALL pushes `0xffffffff814f4918`; shared RET dispatch at
`0xffffffff82704e21` omits it from 317 targets. That path therefore retains an
exit-15 miss. A generic entry label for the address does not supply its RET edge.
This correction does not alter return-graph learning.

Whole retained g9 image inventory, excluding assembly comments:

| Static frontier | Count | Qualification |
| --- | ---: | --- |
| Untranslated callee stubs | 118 | Runtime identity selects a service or permanent handback |
| Indirect CALL tables | 14 | Thirteen have no learned target |
| Indirect tail tables | 10 | Nine have no learned target |
| Generic RET/IJ tables | 166 | Root RET has no learned target |
| Permanent source frontiers | 32 | Handback requires the existing runtime checks |
| Origin-memory descriptors | 149 | 101 supported; 48 explicit refusal descriptors |

The 101 supported memory descriptors comprise 22 INC, 17 DEC, 58 loads and four
TEST operations. The other 48 have no JIT successor and return `-EOPNOTSUPP` if
their service path is taken; a guarded read need not take that path. They are
remaining support boundaries, not successful continuations. The 4,100 budget
boundaries are yield/resume machinery, and 83 emitted UD2 instructions belong
to source assertion/error branches. None of these static counts establishes
runtime frequency, cost or complete-body execution.

G9 was published after the preceding application and remains untested. Its
mapping/inner return are verified in saved assembly; complete callback return,
delegated read-tail completion, later writer acquisition and performance remain
unproved. [munmap-g9.json](munmap-g9.json) retains exact addresses, line references,
counts and artifact hashes. Its source inspection identifies `d726952d`; the
retained image belongs to runtime `ec623366622d1784f7e819b4e9031ba0482bee9b`.

[summary.json](summary.json) binds the source, ELF review, focused checks and
build receipt. Nine guest receipt/log files (53,189 bytes), both frozen-source
manifests, source-host records and the original offline review remain in both
checkouts beneath
`bench/results/10.176.26.71/raw/tests/direction-boundary-d726952d-20261106/`.
The guest index SHA256 is
`9fd8f8990c9e0f7451ea981d79837279df6418dad84ee9759ed4ce34728ba0bb`.

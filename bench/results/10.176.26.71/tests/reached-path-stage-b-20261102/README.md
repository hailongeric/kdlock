# Reached-path Stage (b)

This record covers the isolated `codex/reached-path-translation` branch, based
on design commit `9fc7893f0b15086e2c924f8f7a89229d1fb81d45`. Master remains
unchanged. These are focused functional checks, with no application or Nano
timing and no performance claim.

## Source and environment

The initial implementation is
`d25b210352aea98a1d13b2ab79c5e1baf4c20166`. The fixture-only correction is
`55231559c70646c9b6de969b127eecf132054fdd`; it changes documentation and the
existing source-lifetime fixture, leaving the engine unchanged. Results remain
separate by exact source commit.

The verified VM uses `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`22c0a1d3-64b3-4de3-867c-e0521c6ba8c3`, `kd_mmap=on`, `full (lazy)`
preemption, and the pinned Python 3.14 environment. Recovery snapshot
`kdlock-builddisk-clean-20261031`, host CPU pins and the fixed 2 GHz policy were
confirmed before the focused runs. Source edits and static checks ran on
380G10; builds, unit checks and kernel execution ran only on the VM.

Both private VM input trees were transferred only while idle. Exact hashes and
file totals are in [the initial transfer](d25b-source-transfer.json) and
[the corrected transfer](5523-source-transfer.json). The canonical source and
previous immutable inputs were preserved.

## Implementation and limits

`disassem/reached_path.py` uses a sequential instruction decoder. It stops at
the first control/service boundary or a local cap, without traversing either
successor or a callee. `kernel_module/kd_reached.c` is the resident scalar
engine: one canonical packet, actual source RSP/CALL/RET words, no per-step
allocation, a hard 64-instruction local cap and one persistent instruction
budget. PAUSE and fences execute on E. A missing reached instruction can be
supplemented without replaying the committed prefix. Unsupported instructions
produce an explicit unexecuted event, never public success or an origin suffix.

The internal retained-frame adapter validates exact packet custody and absence
of pending transactions. It preserves committed-prefix state even if a later
instruction stops. Its first store contract covers the retained source stack;
arbitrary data stores, atomic operations, GS/context instructions and fault
handling still need their full contracts. The supported scalar subset and
callback requirements are explicit in `include/kd_reached.h` and the design.

Image-free public capture is **not activated**. Family/cache publication,
immutable cold-service artifacts and the Native/control-path joins remain
later stages. The existing complete-image path remains for its separate
protocol fixtures. This record does not prove cold-path killable/nesting or
downgrade integration, actual mmap1 delegation, or arbitrary Native-equivalent
MM instruction coverage.

## Initial implementation: `d25b2103`

| Check | Result |
| --- | --- |
| Reached decoder | 19 cases passed |
| Private-source admission | Nine cases passed |
| Source-lifetime fixture | Compilation failed before execution |
| Separate ordinary provider build | Passed |
| Separate resident cold-engine fixture | 37,700 assertions passed |
| Fixture retirement | Normal unload and final idle passed |
| Existing helper/killable phases | Not run on this commit |
| mmap1 / performance | Not run |

The first unit attempt stopped at a stale assertion expecting capability
version 16, although the baseline already exposes version 17. No provider or
live fixture was launched in that attempt. The fixture correction retains
all earlier probes, checks the existing indirect-tail bit and adds a missing
indirect-tail probe. This failure remains in
[the exact first reply](d25b-unit-attempt.json), SHA256
`b02d448f25137b356874b4e3159434820ba6b842c4c6e1bedd33aef7835a482c`.

A separate component check then built the ordinary provider and the cold
fixture from the same frozen engine source. It did not treat the failed
source-lifetime fixture as passed. Its 37,700 assertions include 12,544 Native
arithmetic tuples across eight operations, four widths, 14 boundary operands
per input and both carry inputs. The other checks cover scalar addressing,
partial registers, actual branch selection, indirect CALL operand-before-push,
inherited RET, positive missing-target supplementation, truncation retry,
unsupported operations without effects, and preemption-disabled bounded
execution. E was task 29867; O was task 29866. O's source-stack storage remained
alive until E joined. The fixture records `cases` and `checks` as the same
assertion count; it does not mean 37,700 distinct instruction encodings.

The exact [component reply](d25b-cold-checks.json) has SHA256
`a5845cbf398e861e569a6200b2bbd3a675c1f410cae4ee5aa1b290f7dad66619`.
Its provider was built but not loaded; the standalone fixture links the exact
engine source. This is component execution evidence, not live frame-adapter
or MM evidence.

## Corrected candidate: `55231559`

| Check | Result |
| --- | --- |
| Reached decoder | 19 cases passed |
| Source lifetime | 49,916 assertions, zero failures; all 35 negative variants detected |
| Private-source admission | Nine cases passed |
| Ordinary provider build | Passed |
| Cold engine | 37,700 assertions passed; E 31420, O 31419 |
| Returning helpers | All 11 phases passed and drained |
| Killable/nesting/downgrade | All 11 phases passed and drained |
| Final state | Idle, no provider/fixtures loaded, all 6,805 frozen files verified |
| mmap1 / performance | Not run |

The killable phases include queued cancellation while the holder remains
locked, selected reader-drain cancellation, origin-signal cancellation of a
nested request, mixed and early-outer depth-nine nesting, 128 repeated child
requests, and `executor-downgrade-and-fresh-writer`. The helper phases include
sleeping helpers, mapped allocation, an indirect tail, Native spin/RCU ownership,
GS preemption service and non-LIFO Native write release. These are the existing
complete-image protocol fixtures, separate from the new cold component.

The [exact focused reply](5523-focused-checks.json) has SHA256
`139fdc5d4977514bf975826224a945545efcb5b85975661ecca769a2017d270d`.
The [host receipt](5523-host.json) has SHA256
`dc98d1576a85c7e8d6192910453fc38640172a98bbe7c4d1670f853903576ab4`.
The [final state and build-log inventory](5523-final-state.json) has SHA256
`91656a15939bc668af93b2b697dde0593ee508e3f85310e88a6642145a30085e`.
Build logs retain the compiler-identity warning and objtool warnings in the
existing restoration/combiner/bridge routines. No warning names the cold
component. Passing these checks does not resolve those existing build limits.

Final static review then identified a separate adapter issue: frame and packet
addresses can be reused, so address equality cannot authorize old execution
state. Add the exact request identity/generation and a focused adapter fixture
before final Stage (b) delivery. Its validation is a new source revision; the
passes above remain attached only to `55231559`.

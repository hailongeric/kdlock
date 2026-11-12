# Mutex fast-path candidate handoff

The bench session owns all builds, unit tests, module work, VM operations and
timing. This source candidate accelerates eligible top-level native mutex pairs
through an empty-tail claim and exact local handoff. It leaves rwsem and other
families on their existing paths. The [protocol and focused checks](../../tests/mutex_fast/README.md)
state the eligibility, source/record lifetimes, nested restrictions and evidence
changes. This source handoff establishes no candidate runtime or performance
result.

Preserve baseline `0d3fc6fb9173cdf96933371db8b05a20d15774b4`, whose core collector
is `629f20ab6d5b9fe17bac420c4eac03fcd50056a5`, and its measured kernel
`7.0.0-38-kdrebuild10`. The completed baseline report is
`/tmp/kdlock-main-collection-57eab6a3-20261112-mu3e4j8x/collection-report/README.md`,
SHA256 `c7b506ceca728129bc4284c2e0410557b0da22964895b1660146f16c383ea49e`.
Keep that report, raw receipts, immutable source, kernel/output, installed boot
files and recovery entries. The prior collector and recorder baselines remain
historical evidence with their original source/build/boot identities.

The private task-root layout changes. Build an isolated complete kernel with a
distinct release from the frozen candidate's `Kbuild`, `include/` and `kernel/`
inputs; rebuild every dependent fixture and nano module. A candidate module on
kernel10 is not validation. Preserve the existing source/output separation,
authenticated Linux/config/compiler baseline, idle/headroom and recovery gates.
The previous build's final disk space does not satisfy a new build's gate.

Record exact source/compiled-input manifests, kernel configuration, compiler,
ELF hash/Build ID, boot ID, module hashes and fresh GS proof. Re-establish that
boot's live and ELF `its_return_thunk` identity and its exact admitted `c3cc`
span. Keep the existing identity checks; no GS probe or translation change is
part of this optimization. Synchronize only idle inputs and never overwrite a
frozen or running tree.

Run the seven production-excerpt checks and the affected recorder/ABI units in
the VM, then build and run the mutex runtime fixture, rwsem reader/mode fixture
and managed killable fixture on the candidate kernel. The mutex runner adds
two small single-task cases with an admitted image and checks normal handoff
from fast holders in the existing recursive scenes. Preserve current checks
for exact source effects, original task, mode/cancellation, physical ACK and
final retirement. No full suite or mmap campaign is requested here. Failures,
skips and missing dependencies remain explicit; a timeout is not drain.

Use the existing `bench/nano/build.py` and `run.py` commands from
[the collector handoff](COLLECTION.md#bounded-validation-and-measurement) with
fresh output paths and the candidate's explicit release/thunk/boot/ELF/GS
arguments. Run both families' `recorder-pair` functional lanes before either
timing lane. Keep one timed worker on CPU0, collector CPU63, one cacheline,
post256, mutex 100% writes, rwsem 20% writes, proxy limit 16, unchanged
eight-worker training, fixed image/empty claim and three two-second pairs per
family ordered on/off, off/on, on/off. This is the same twelve-phase small
comparison. Workload bodies and postwork are unchanged.

Evidence ABI2 reports exact fast pairs independently of pool requests. A
single-worker mutex phase should account for its operations through these pairs;
it must not fabricate pool lifetimes or JIT completions. Training must still
establish real returned JIT episodes through contended requests. The rwsem lane
must report zero fast pairs. Recorder-off counts remain unavailable. Keep every
sample, all normal unload/drain proofs and current placement/qualification
limits. Report candidate-on against kernel10-on and candidate-off against
kernel10-off with distinct boot identities; whole-workload throughput does not
measure pure lock latency or resolve the full Native gap.

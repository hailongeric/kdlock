# Scoped compiler and upload provenance

Implementation `d77637675c87ee4d6ba00292d527484c5e51fbc2` adds optional
compiler-manifest -> accepted upload payload -> existing registry-observation
evidence on `codex/mmap-reached-jit`. No merge or push occurred. This record
contains independent userspace checks in the designated VM, with regular-file
transport doubles. It contains no provider load, campaign, live publication
check, mmap1 learning application or measurement.

## Source and environment

The implementation parent is `ec9436d606fc1178cdd2f523c2f1060bea9648e7`;
the earlier runner implementation remains
`f1b410fefffd48b06aab5b4d91cedc43bc771cca`. A staged source snapshot was
transferred into a new ext4 directory at
`/mnt/kdlock-builds2/kdlock-unit-provenance-lx1y5mf7/source`, preserving the
canonical source tree and all frozen campaign inputs. It contains 1,082 files
and 10,425,740 bytes, excluding historical result archives and captured kernel
experiments. The source manifest SHA256 is
`fb6d38458212874720ff6d5e59f24ab7a48fcd159ecc232dc17f85a1b0875996`.
[source-state.json](source-state.json) retains the parent and staged-patch hash;
[verification.json](verification.json) confirms all 18 implementation/test files
in `d7763767` are byte-identical to their tested inputs. Later guide/report edits
are outside that executable-input claim.

The guest remained on normal `7.0.0-38-kdlock1`, boot
`6148a091-cca7-4258-8d0b-d75227134564`. Checks used the designated pinned
Python environment and guest GCC. Initial disk headroom was 3,756,388,352 bytes
on `/` and 16,463,233,024 bytes on the second build disk. Read-only inspection
found no project module or work process before staging. No guest boot or
configuration change occurred.

## Implemented claim

Capture is disabled by default. Only the settled runner's configured
`required_publication` selects a root and enables it through the maintained
daemon launcher. Ordinary launches clear inherited provenance variables.
There is no kernel/header ABI change.

The compiler records its actual validated descriptor/CAPS observation, service
and control tables, consumed CALL/IJ history, patched assembly and successful
binary identity. Cache entries retain the original compiler attempt/digest.
The daemon mirrors only payload bytes from existing accepted write buffers,
records final-write completion separately from evidence completeness, and
preserves production return values, errno and retry decisions on evidence
failures. Failed finalization cannot publish a usable complete record.

The verifier timestamps the existing fixed-receipt registry read and binds the
captured files to that receipt. It rejects missing/conflicting evidence,
compiler/upload mismatch, changed lifetimes/contracts, pending misses,
overlap and stale/later generations. For the selected immutable ABI2 row,
observed generation must equal successful upload base generation plus one,
following the preserved publication source contract. No device read, learning
acknowledgment, polling or retry is added. Body/frontier/history predicates use
the captured compiler inputs rather than current workspace files.

Evidence is limited to 64 compiler attempts and 64 uploads, 8 MiB per retained
text artifact and 4 MiB per binary payload. Existing input readers retain their
previous read-all behavior; these are retention bounds. Enabled compiler
metrics include capture/hash/finalization overhead and remain separate from
evidence-disabled timings.

## Checks and retained failures

The [first receipt](first-pass.json) remains failed; it preserves both the
text-regions failure and the original registry-controller timeout. The
[follow-up receipt](followup.json) records the baseline comparison and completed
bounded registry rerun. No missing dependency or compile failure was counted
as a pass.

| Check | Observed result |
| --- | --- |
| Daemon compilation | Passed, no compiler warnings |
| Basic C checks, including opt-in provenance transport fixture | 3 programs passed |
| Compiler-manifest mocks | 12 passed |
| Provenance association/integration mocks | 13 passed |
| Existing settled runner | 10 passed |
| Existing campaign boundaries | 10 passed |
| Source frontier | 11 passed |
| Source lifetime | 44,345 checks, zero failures; mutation cases detected |
| Execution registry | 32,707 checks at capacity 64; 63,488 at 128; zero failures; all 16 mutations detected |
| Text regions, candidate | 85 tests; 14 failures and one error |
| Text regions, checkpoint production overlay | Same 85 tests; identical 15 failure/error headings |

New mocks cover producer/consumer linkage, failed builds and evidence
finalization, cache-hit workspace replacement, exact multi-chunk/EINTR writes,
partial/short transport, evidence I/O faults, descriptor/session mismatch,
pending misses, changed/ambiguous generations, temporal overlap and unchanged
registry-read/retry counts. The producer/consumer integration test invokes the
real recorder with supplied input doubles, without invoking a compiler or
opening a provider.

The text-regions comparison used a separate copy with the exact checkpoint
versions of the three modified translator files: `disassem.py`,
`device_session.py` and `memread.py`. Other driver inputs were unchanged;
new unused files were not represented as a pristine checkpoint checkout.
The overlay hash map is retained in the raw archive. Eight failures concern
exact capability dictionaries omitting already-present frontier flags; one
error supplies service rows where the existing paged reader expects state.
Six compact-window/CFG cases also fail on the checkpoint production overlay.
These failures remain unresolved; fixtures and refusal checks were not weakened.

The initial registry driver exceeded its 90-second outer controller bound.
[post-timeout-state.json](post-timeout-state.json) records an actual subsequent
process scan and unchanged source hashes; the timeout itself supplied no drain
proof. The same driver then passed in 99.313 seconds under a 240-second bound.
Final inspection again found no remaining test process or project module and
verified all frozen source hashes. The empty initial registry log and the
timeout receipt remain preserved.

## Retained artifacts and limits

The ignored raw directory is
`bench/results/10.176.26.71/raw/tests/provenance-chain-ec9436d6/`.
It contains `checks.tar.gz` (all logs/receipts/manifests), `inputs.tar.gz`
(tested source), and `baseline-production.tar.gz` (checkpoint overlay).
[verification.json](verification.json) records their exact sizes and SHA256s.
The original guest copies remain at the new unit-check directory; no cleanup
of unrelated files occurred.

This establishes source-derived association under the immutable ABI2 contract.
It does not establish a kernel-reported loaded-memory digest, durable kernel
lease ID, exclusive publisher history, exact acknowledged learning revision,
returned JIT body, live expanded mmap image or throughput. General restoration
and performance limits remain unchanged. Historical 17-fixture/recovery receipts
do not validate this implementation; the new checks above have separate inputs.

The platform error "This content was flagged for possible cybersecurity risk"
remains unresolved. No stopped provider/campaign/publication/learning/measurement
operation or alternative route was attempted. The independently implemented
recorder and offline verifier do not clear that restriction.

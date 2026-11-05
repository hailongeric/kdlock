# Original-JIT retained handback: component results and live preparation

Production implementation: `da55414fa576a6e683f98364523cf9353b598c0e` on
`codex/mmap-reached-jit`. The later fixture commits `615cdb0b` and `2bfbb8dc`
have identical `kernel_module`, `include` and `disassem` Git trees; see
[source identity](source-identity.json). Master is unchanged. No merge,
module load, reboot, mmap1 execution or timing point occurred in these checks.

## Exact attempts, including failures

| Frozen source | Build | Directly affected checks | Result |
| --- | --- | --- | --- |
| `a6fe0bb269642cf2dd6f07c3430b6933f9c0557a` | `W=1` provider build passed against the separate scope5 output | Seven drivers passed; query images failed one assertion; service retirement did not compile under `-Werror` | Overall failed; [receipt](a6fe0bb2-checks.json) |
| `da55414fa576a6e683f98364523cf9353b598c0e` | `W=1` provider build passed | Query images: 6 cases; retirement: 4 positive modes and 9 rejected inconsistent states; Native-service join: 3 modes; segment lowering, final reader access, saved-state restore and CALL boundaries passed. Resource and OSQ drivers stopped during obsolete-helper extraction | Overall failed; [receipt](da55414f-checks.json) |
| `615cdb0ba809255b4f5521d65c042d0c67f6ce3d` | Not repeated; production bytes unchanged | OSQ: 26 scenarios passed and all 14 mutations detected. Resource driver compiled, then failed at its supplied ordinary-peer outcome | Overall failed; [receipt](615cdb0b-checks.json) |
| `2bfbb8dc992ce9cb8ef38521cbc2ca43c35e6f48` | Not repeated; production bytes unchanged | Only repaired resources rerun: 19,164 checks, zero failures, all 27 mutations detected | Focused rerun passed; [receipt](2bfbb8dc-checks.json) |

The first query failure was an incorrect assumption about a legal continuation
label; the later fixture executes the actual inner service target and both
source CALL words. The first retirement compile failure was its supplied CPU
ID's signedness. Production additionally rejects a missing reservation before
retiring source/task references. The old resource/OSQ extraction failures were
caused by fixtures naming helpers removed by the canonical-queue migration.
The first repaired resource run then exposed an ordinary peer not represented
by its assembly substitute. The correction routes that peer through the real
physical-wait helper without assigning it a delegation gate.

Both provider builds retain compiler-name and return/frame diagnostics; a
completed build is not live execution evidence. Every attempt records final
idle state and unchanged frozen inputs. The passing drivers are source-specific
component results carried across byte-identical production revisions, not a
single new combined run or a newly measured performance result.

The exact original reply and freeze bytes are copied here. [Artifacts](artifacts.json)
records their source-host paths and hashes. Full build/unit logs remain under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/` in the corresponding
`handback-queries-a6fe0bb2`, `handback-queries-da55414f`,
`mutex-fixtures-615cdb0b` and `mutex-resources-2bfbb8dc` directories.

## What the component fixtures establish

The Native-service join uses production registration, acceptance, typed owner
matching/release, final O-stack acknowledgment and terminal continuation
retirement. Its physical admission/release, task binding and source references
are supplied. Its nested E-stack anchor is retained through pthread joining;
it does not prove immediate inaccessible-storage behavior after the final ACK.
Read-release fixtures establish the final decrement as the last object access.
Retirement fixtures supply CPU/work APIs, including concurrent offline-slot
release; they do not exercise real CPU hotplug. Query fixtures use synthetic
source bodies and the actual original image backend.

These checks do not establish a real kernel stack switch, live retained MM
ownership, general flags/SIMD or IRQ/NMI coverage, mmap1 completion, delegation
length, or throughput.

## Fresh installed/running identity preparation

The [read-only identity receipt](live-identity-2bfbb8dc.json) freshly verifies
the selected installed `kdscope5-kd` bundle: 59 bundle files, 70 named source
files, 12 build files and 4 installed files, with `kd_mmap=on`.

| Component | Fresh identity |
| --- | --- |
| Installed scope5 kernel Build ID | `5f2fce72a33480f6e79a79b374b21a0db377ecd1` |
| Built `vmlinux` SHA256 | `75f511e8eecdc1cd06e480ea1d4b465def3697d8ab5ad5dd64a55013b45f934d` |
| Kernel `Module.symvers` SHA256 | `1b2b6686a7078c214120fc6d5aa41bd74226d6b461003be1a25357f8fb9cb7af` |
| Unloaded provider SHA256 | `0184c67b4cebcf7a8d0e1a25f12f77e364c593330c4ed66dd35a7542f089de1c` |
| Provider release in vermagic | `7.0.0-38-kdscope5` |
| Actually running kernel | `7.0.0-38-kdlock1` |
| Actually running Build ID | `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` |
| Actually running boot UUID | `0a2b2a34-caf7-4c63-9b38-d4f29a5a2d7d` |

The shared facade header, object layout header and adapter match the installed
source exactly. The differing provider header and builtin restoration source
match the recorded `1ab7124a` kernel recipe blobs and differ from this candidate
only in comments; see [the exact diff](kernel-interface-comparison.diff).
The generator's new builtin-local definition is recorded separately in that
diff. This interface review does not relabel all kernel generation inputs as
the new provider's source revision or prove arbitrary caller compatibility.

The next live step cannot use the current normal-kernel boot. Before any module
load, verify a real recovery snapshot, the selected running scope5 Build ID,
boot UUID, exact command line, MM mode and preemption policy with
`kernel_integration/linux70/verify.py --variant kdscope5-kd --running`.
Bind that result to the provider hash/target symvers and the exact freshly built
daemon plus translator inputs. No running-scope5 pass or loaded-provider pass
is claimed by this preparation.

## Minimum live acceptance preparation

The current killable runner requires returned JIT bodies and an unchanged image
registry; the mmap1 diagnostic accepts returned event sequences. Neither is a
validator for a permanent current-position handback followed by later learning.
Do not run those unchanged validators and call a failure or a returned-only
result proof of the new path.

1. Start with the existing generic continuation fixture. Force a cold direct
   CALL and actual indirect edge after a counted compiled prefix. Check prefix
   effects once, O's first unexecuted source position, exact SP and source return
   words. Require distinct handback acceptance and terminal-retirement events.
2. Retain nested mutex/writer owners across that boundary, including release of
   an older owner first. Exercise downgrade and Native read custody without a
   reader decrement at transfer, ordinary/non-owner read release, and a later
   freshly admitted writer. Check origin signals and cancellation before body
   effects, success priority and retirement before `-EINTR` separately.
3. Keep the first capture image immutable. Observe actual CALL/IJ reports and a
   later image generation with the reached target, then require later compiled
   execution and exactly-once effects. No same-invocation compiler wait or replay.
4. Execute the three actual public query bodies through the installed facade and
   current provider. Permit only the exact inner owner query's declared service;
   synthetic query-body fixtures alone are insufficient for this live claim.
5. Only after those joins pass, run one focused `mmap1_threads` and one
   `mmap1_processes` point through real syscalls on `kd_mmap=on`. Record fully
   returned JIT episodes separately from handed-back prefixes, exact E/O identity,
   read-tail release, and complete drain. Timing and a Native comparison remain
   separate from this functional proof.

No production lock or caller-specific MM code was changed by the fixture repair.

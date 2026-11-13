# Ordinary rwsem evidence regression

`f3b1d75b-native-readers.bin` is the unchanged 6,280-byte observation capture
from the **failed** kernel15 rwsem mechanism attempt on November 13, 2026.
The runner stopped at `ReaderCases.credits()` because ordinary read records
were incorrectly required to have managed request reservations. This artifact
does not turn that attempt into a pass. No corrected oracle or VM check ran in
the source session that added this regression.

- Core revision: `f3b1d75b2fcae57661f85b375192c7dead784518`.
- Release: `7.0.0-38-kdrebuild15`.
- Boot: `2c9f45e6-5d91-4be7-993f-2f075ff234dc`.
- Header: version 1, 20 fields, capacity 65,536, 39 events, zero overflow.
- Capture SHA-256: `b1a797ef0f3fb9088e05022b49072ab2943ecde6d6347903fcced69d7c93efd1`.
- Original source-host directory: `/tmp/kdlock-rwsem-split-f3b1d75b-20261113-01`.
- Original `rwsem-events-retained.json` SHA-256:
  `26f2aae4c45b8a3990166fee5776bc03ea1b20808acd53e2c2c6028ad1639ca5`.
- Original `rwsem-failure-state.json` SHA-256:
  `48142eacbea56c189d02c698c7b168a2e4bd3bf8d7748ee7748cdb89b00d9a91`.

Rows 0–23 contain eight ordinary local writer pairs. The failing scene starts at
24: read acquisitions 24/25, releases 28/30, ordinary completion 29/31, and local
MCS writer acquisition/release 32/33. Its queue departure is 35, physical end 36,
owner retirement 37 and ordinary completion 38. Prefix rows 26/27 are the exact
native enqueue and selection. They have no managed source state or reservation.
The retained post-stop control snapshot reports `locks_clear=1`; that is cleanup
evidence, separate from the failed oracle disposition.

The VM-only `tests/test_rwsem_evidence.py` uses this capture directly and creates
explicit synthetic variants for local and queued true downgrade, repeated and
distinct reads, delayed DONE observations, and invalid identity/retirement/order.
These variants are validator inputs, not additional live observations. Execute
the focused unittest only in the benchmark VM under the normal workspace rules.

The correction leaves generated-entry, exact continuation, side-effect and
managed retirement requirements intact. A separate source-review concern
remains: rwsem `source_scene(7)` requires a foreign nested writer while an
ordinary outer reader is held, whereas `prepare_rwsem_writer()` selects local
MCS when `native_grants` is nonempty. This correction does not reclassify that
scene or claim its generated requirement passed.

At `f3b1d75b`, `kd_rw_local_read_lock()` keeps both fast and contended reads in
ordinary records, and `link_local()` adds the record to `root->native_grants`.
`kernel/mutex_api.c:293` then excludes the nested writer from image preparation.
Independently, `kernel/episode.c:520` marks any native-grant holder local-only,
and `local_service_limit()` at line 689 disables its service loop. Generic
borrowed lock aliases also reject nonempty native grants in
`kernel/linux_rwsem.c:120`. Removing one check would not restore the common path
or establish release authority.

Before this candidate, a contended outer read failed the fast probe and used
the existing managed shared-read slow path. That exact READ grant stayed on
the canonical source state while the nested writer could be selected remotely.
One restoration candidate for that prior supported path is to retain successful
ordinary fast admission, but return an unused ordinary record after a failed
read CAS and use the existing managed read slow path. A failed CAS acquired no
READ count, so this requires neither release/reacquire nor replay, and restores
the existing managed acquisition and release routing without a new authority
mechanism. This candidate is not selected: it restores managed lifecycle work
to contended readers, contrary to reserving preparation for eligible writers.
On-demand promotion at the eligible contended writer boundary could better
preserve both ordinary reader paths, but must retain the already-held read's
exact identity/count, source ownership, release route and storage lifetime.
That requires a reviewed core protocol and new kernel validation; merely
removing `native_grants` checks establishes none of those obligations. Neither
alternative is implemented here. This is an eligibility regression diagnosis,
not evidence of an ordinary lock exclusion failure.

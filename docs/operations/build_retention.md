# Current build retention and space observations

These observations were supplied by the existing benchmark session after direct
owner approval. Times below are November 13, 2026 PST, with exact UTC equivalents.
They are dated observations, not guarantees of present free space. This guide
adds a current record without replacing the pre-cleanup inventory or historical
receipts. All listed deletions completed permanently without backups.

## Completed exact deletions

| Completion observation | Deleted path | Guest bytes reclaimed |
| --- | --- | ---: |
| 21:03:46 PST / November 14 05:03:46 UTC | `/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build` | 33,143,619,584 (30.867 GiB) |
| 21:11:07 PST / November 14 05:11:07 UTC | `/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/build` | 4,965,412,864 (4.624 GiB) |
| 21:17:31 PST / November 14 05:17:31 UTC | `/mnt/kdlock-builds/nano-20261022/rwsem/records.json` | 247,877,632 |
| Same completed old-data batch | `/root/.debug/mnt/kdlock-builds/linux-6.1.159-kdclobber2` | 772,751,360 |

The first deletion changed build1 (`/dev/sdb`) available bytes from
13,941,436,416 to 47,085,056,000. Source, boot files, installed modules and
symlink objects were preserved. The approved old kdmm1 installed build link now
dangles; its source link still resolves. Build2 received no benefit.

The second deletion changed build2 (`/dev/sdc`) used bytes from 134,211,178,496
to 129,245,765,632 and available bytes from 41,699,713,024 to 46,665,125,888
(43.460 GiB). This exceeded the unchanged 40 GiB gate by 3,715,452,928 bytes.
Sibling source, receipts, input, staging and ops directories, installed modules
and links, `/boot`, kernel16 and all other paths were preserved. No build started.

The separate old-data batch is VERIFIED COMPLETE, with direct approval and
command exit 0 in benchmark turn `01a1d87c-9bcb-7371-ba25-38d2eb178bb5`.
Its total was 1,020,628,992 bytes (about 0.95 GiB). Root available bytes changed
from 11,706,519,552 to 12,479,270,912; build1 from 47,085,056,000 to
47,332,933,632. Build2 remained 46,665,125,888. Protected metadata, current
evidence and kernel16 boot identity were unchanged. The deleted raw/debug data
is no longer available; no recoverability is claimed. Retain summary reports,
sources, snapshots and current nano, Native and TCLock data.

These are guest filesystem reclaimed bytes, not measured host QCOW2 shrink.
No snapshot removal or valid recovery copy is established by these observations.

## Current incremental base and future operations

The single suggested current keeper is
`/mnt/kdlock-builds2/kdlock-main-kernel16-7338197a-01`: total 8,291,069,952 bytes,
build 6,367,793,152 and source 1,825,075,200. It matches the observed running
`7.0.0-38-kdrebuild16`, boot `1110d227-f79f-471b-bdd5-73f917862891`.
Its `modules.order` lists only one module against 6,709 configured module
targets. It is the current kernel/core incremental base, not a verified complete
all-module build. Preserve its frozen identity. Other historical trees have not
all been removed.

A bootable historical reference does not require a full editable compiled tree.
Audit module/provenance links before each exact cleanup; the completed approvals
above do not authorize additional deletions. Before future builds, recheck space,
idle state and the applicable recovery/identity gates in the
[build guide](../../kernel/integration/BUILDING.md). This documentation update
performs no VM action, build, test or recovery validation.

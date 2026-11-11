# Reader fixture ordinary recovery receipts

This retains three exact completed cleanup sequences after failed fixture
attempts. Recovery completion preserves the original failures; it is not a
reader correctness, JIT completion or performance pass. No snapshot restore,
forced unload, source replay, new compilation or fabricated coverage ACK is
claimed by these records.

| Recovery | Exact recorded outcome |
| --- | --- |
| [rwsem capacity](guest/rwsem-capacity/result.json) | EXACT_ORDINARY_RECOVERY_COMPLETE / ORDINARY_UNLOAD_VERIFIED; zero claimed/SETTLED facts; END sequence 10; dmesg unchanged |
| [rwsem learning](guest/rwsem-learning/result.json) | EXACT_ORDINARY_RECOVERY_COMPLETE / ORDINARY_UNLOAD_VERIFIED; one claimed fact durably archived and SETTLED; END sequence 53; dmesg unchanged |
| [rwlock native](guest/rwlock-native/result.json) | ORDINARY_NATIVE_ONLY_RECOVERY_COMPLETE; zero compiler cycles, zero wire reservations, source not exported; ordinary rmmod return 0; dmesg unchanged |

The first recovery reconciled the exact failed STAGE_LOAD sequence 4/status -28
cache, then used ABORT 5, END 6, SHUTDOWN 7, ARCHIVE_CLAIM 8, durable raw archive,
SETTLE 9 and END 10 before ordinary destruction/unload. Its zero-fact archive is
4,187,139 raw bytes, SHA256
`2bf0ad97e9055bbbcf1ed7998571f8471d91a14464c32add8beeeaef1237f8c0`.
The prior failed capacity attempt is retained separately in
[runtime-rwsem-capacity-20261111](../runtime-rwsem-capacity-20261111/README.md).

The second recovery used SHUTDOWN 50, ARCHIVE_CLAIM 51, actual durable history
archive, SETTLE 52 and END 53. Its one-fact raw archive is 46,010,268 bytes,
SHA256 `980f532169b1eb5073b2a40a274d7f7385f47f6538e7e5008c500df0e208e9c9`.
Both archives are retained losslessly, including original source/version/history
and producer material, with exact raw wire/cache/claim/settlement receipts. The
helpers require their source-host/guest durable archive write and readback before
settlement; an empty fact set is not an empty history archive.

The native-only rwlock cleanup did not create a claim/publication/archive
workflow merely to tear down a module. Its saved stop/destruction/unload results
and no-source/no-wire fields are the evidence. Retained before/after dmesg bytes
match independently for all three recoveries. Recorded worker/module/control
end states are scoped to those operations, not later tests or current VM state.

The exact source trees were the recovery directories under fixture versions
`e990fde3` (capacity), `68a2e5ed` (learning) and `e5b78520` (native rwlock),
as listed in `guest-index.json` and the actual launch command. Their original
failed runtime/controller output remains separate; this package does not edit
or substitute those results. It preserves cleanup and selected history only.

The completed read-only collection contains 101 guest files / 51,222,876 raw
bytes. Caller limits were 10,240 files, 40,960 paths, 256 MiB total, 48 MiB per
file, 16 MiB metadata, 90 seconds per inventory and 180 seconds for copy. Exact
before/copy/after inventories and hashes matched. The 46,010,268-byte raw archive
fits the per-file bound. No bound was silently enlarged, and no host-image/QEMU
operation, test, module action or reboot was performed by the collector.

`guest-index.json` retains original guest paths/identities/hashes. `copy-index.json`
records source-host origins plus raw/stored sizes and SHA256. Large JSON/logs
are losslessly gzip-compressed; every stored gzip was decoded and compared with
its complete raw source. Original helpers, source-host native-cleanup controller
receipts and the collection launch are retained as context, not reexecuted.
The redundant collector transport tar stays at the source-host collection path;
its SHA256 and command/result are retained along with all validated payload
members. All other original collection metadata is in `collection-control/`.

`SHA256SUMS` covers every stored file except itself. Preserve tabs, terminal
sequences and trailing whitespace in raw logs/JSON/helpers as evidence. Packaging
was source-host-only; it staged/committed nothing and did not touch the separately
owned runtime evidence or maintained guides.

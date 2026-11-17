# Migration to the local 380G10 VM

Completed the user-selected migration of this session's existing local source,
modules, scripts and reports into
`/mnt/kdlock-builds2/main-spin-migration-20261117` inside the existing local VM.
All 416 file/link entries match the prepared package; regular files were
independently reread and SHA-256 checked after reconstruction.

`current-main/` is the main working source and reports at host commit 6264b5a5.
The two frozen source tar files and original benchmark module are also present.
The complete remote kernel build directories and installed test kernels had
already been deleted on the user's explicit cleanup request; no full kernel
build environment or bootable test kernel is claimed migrated. Included modules
belong to kdmainspin1/2 and must not be loaded on the running kernel16.

The local VM remains `7.0.0-38-kdrebuild16`, boot UUID
`84a3b76f-af03-4db6-86b4-7d81e2472f50`. No reboot, build or test-module load occurred.
The module list still contains only nls_iso8859_1. The original two block images
and empty removable drives match final QMP verification. No prohibited remote
access occurred after the completed rollback and final remote verification.
The persistent prohibition is in `/home/eric/.codex/AGENTS.md` and main AGENTS.md.

## Transport observations and limits

Per-byte serial JSON transfer was slow. SATA and PCI hotplug attempts were
refused; both temporary block backends were removed. A bounded bulk-reader
attempt temporarily paused the serial controller and raised its speed, but
host sending timed out; the child then hit its recorded deadline, resumed the
controller in its finally block and restored speed 9600/9600. During that attempt
the guest recorded one soft-lockup warning on CPU 7 (26 seconds, swapper/7).
The warning is retained; migration does not certify kernel stability or erase
that event. Final checks found no additional such warning and the controller
responded normally.

An existing empty CD-ROM accepted read-only media, but the guest lacked the AHCI
modules needed to expose it. No driver was built or loaded. The media was ejected.
The successful transfer reused 36 already verified chunks, plus five delta chunks
(654,866 bytes), reconstructed every original package file, and independently
reread all hashes. All those temporary chunks were removed after verification.
The complete compressed transport archive is retained on 380G10; its extracted
contents, rather than a reconstructed gzip container, are in the guest.

This is a completed file migration, not a performance result or authorization
to run the included historical remote-host scripts.

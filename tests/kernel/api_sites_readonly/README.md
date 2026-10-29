# Read-only page-table proof for the scoped API site table

This diagnostic inspects the running kernel mapping of the exact 48-byte,
three-row `.kd_api_sites` table. It is a correctness-only provider probe, not a
workload or a substitute for actual syscall/JIT execution. It does not change
page permissions, register a KD provider, acquire a tested lock, or write to the
site table. Its own module storage and ordinary load/unload bookkeeping change.

The scope kernel config SHA-256
`7131e48d4bb556e54f9fc287c04e6fab33a3de80eb923a215872a01a07609f4b`
has `CONFIG_PTDUMP_DEBUGFS` disabled. This was established offline by reconstructing
the exact recorded config bytes from the authenticated ordinary Linux 7 config
and the three documented scope configuration changes. The diagnostic avoids a
kernel rebuild solely to enable the page-table debugfs view.

The module must be built only inside VM `10.176.26.71`, against
`/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build`. The fetched actual `Module.symvers` (SHA-256
`e28cfc4bb5d25918157353fa0aeca12b741018c0f988d4f0ada2159f508dac6b`)
exports `lookup_address` (CRC `0x448a179e`) and `kd_api_sites`
(CRC `0x4df9740c`) as GPL symbols from `vmlinux`. The runner rechecks these
exports; declaration in a header alone would not establish availability. A missing
export or failed build is a blocker, not a skip/pass. Keep this probe's source
commit and complete file hashes separate from the frozen provider generation.
Copy its reviewed files to an external DATA directory; never synchronize this
probe into a running or frozen provider checkout.

`expected_address` is the exact linked table address from the authenticated
preinstall `linked-api-audit.json`. The module compares it with `kd_api_sites()`
and requires three entries. For every 4K page covering the complete 48-byte
interval, it calls `lookup_address`, checks a supported leaf level (4K, 2M or
1G), reads the entry with `READ_ONCE`, and requires PRESENT with RW clear. USER
must also be clear. Leaf read-only permissions are sufficient for this mapping;
a parent cannot grant writes that the leaf denies. NX is reported but is not a
condition for this read-only proof. The normal strict kernel write-protection
policy remains required. This does not prove that every physical alias is
read-only or audit unrelated mappings.

The module provides a read-only `report` parameter containing addresses, levels,
raw entries and copied site rows. The runner checks all table bytes against the
linked proof, the live/build GNU Build ID, release, `nokaslr`, no `rodata=off`,
explicit MM mode and the unchanged module/source hashes. It uses ordinary
`rmmod` after collecting and validating the report; no forced unload, retry,
permission weakening, or arbitrary address lookup occurs. A failed or timed-out
live action retains evidence and unknown-drain state for inspection.

Build once with the standalone runner's `build` action, then use its `verify`
action after each relevant boot with the same frozen artifact. All commands,
paths and hashes are explicit; see `run.py` argument definitions. The build
receipt and source manifest must remain unchanged across verification runs.
The existing postboot controller must consume the probe receipt alongside its
kernel identity and linked audit; ELF section flags alone remain insufficient.

An external module honestly retains its out-of-tree metadata. The runner records
before/after taint, allowing only the ordinary out-of-tree/unsigned-module bits
introduced by its load. It never marks the module as in-tree or clears taint.
Boot orchestration must account for that persistent observation explicitly;
unloading the module does not reset taint. A failed page-permission assertion
never becomes a successful proof because the module unloaded.

Status: source, static review and saved actual exported-symbol evidence only.
No build, live load, unload or page-permission validation has run for this probe.

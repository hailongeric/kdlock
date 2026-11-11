# Ordinary return to normal after kernel5 reader validation

This is operational return/identity evidence, separate from the earlier kernel5
JIT and reader results. The actual ordinary `systemctl reboot` returned 0; the
subsequent read-only proof returned 0 with `NORMAL_IDENTITY_VERIFIED`. Packaging
used only completed source-host copies and performed no VM/host access or tests.

| Identity | Before ordinary reboot | Verified normal boot |
| --- | --- | --- |
| Release | `7.0.0-38-kdrebuild5` | `7.0.0-38-kdlock1` |
| Boot ID | `03779fbf-d0ca-48da-b058-b0f9732d2571` | `51b49fa4-4d99-457e-a73e-632b690eb95e` |
| GNU Build ID | `a0314627518435aa4e937dae6741de947c9cf864` | `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` |
| Taint | 12288 | 0 |

[pre-reboot.json](guest/return/pre-reboot.json) records the successful same-boot
rwlock, spin and mutex controller hashes, source
`09834f094acf904c835ee74e6c3960abcf96749d`, core
`1114b41ea0f6ecf92f2c9af2904a4218bb344829`, common module-build/input identities,
actual protected-episode proofs and completed unloads before return. The helper
accepted rwlock's retained intentional fact baseline (`warm_claim_no_new_facts`),
while spin/mutex required their empty warm claims. It checked every recorded wire
response/sequence, each actual final `9,10,11,6` shutdown/archive/settle/end chain,
and exact durable archive bytes. Counts were read from each result rather than
assumed: rwlock 70 wire attempts / 10 acknowledged keys / 3 settled keys; spin
32 / 4 / 1; mutex 32 / 8 / 0.

The helper independently checked the running candidate GNU notes, actual
unloaded/no-device/no-worker/no-test state, the selected built-in source
profile and retained kernel-input identities, unchanged normal GRUB default with no pending one-shot, and eight exact
normal/legacy boot files before invoking the one ordinary reboot. It did not
select a boot entry, reset controls, unload code or force/retry a reboot. It retained a 32 MiB bound for receipt reads; whole-file archive/boot hashes
were streamed separately.

[reboot-result.json](guest/return/reboot-result.json) retains return 0, empty
stdout/stderr and the sole command. The [normal proof](guest/return/post-normal/result.json)
then establishes a fresh normal boot, taint 0, the matching normal Build ID and
actual absence of all four fixture modules/devices/workers. The helper also
requires the normal and legacy module namespaces to exist. The eight protected
boot rows are identical before/after; GRUB configuration SHA256 remains
`4cb0e54c275387c4e725b1dc3d6c69393ec98207a5ea71d1c736c227b5eb93be`,
the normal default is unchanged and `next_entry` is empty. Raw running-kernel
notes are retained for independent Build ID decoding.

The return helper is SHA256
`cf98bf1ff0d3cff9f20b347110b35b96eee95487fca841a824d1ea1dd18c3d85`;
the source-host orchestrator is
`4669e9aa911a953fcb4f9ab0eccf590b903752bf80a12508787cbf4b5a4cb74c`.
Both sources, actual controller commands/stdout/stderr and the guest helper copy
are retained. This normal boot is not new JIT or reader execution evidence.
Those results remain in their separate kernel5 runtime evidence directories;
this helper does not promote unrelated rwsem failures or recoveries into passes.

The completed read-only collection contains five guest files / 145,068 bytes.
Bounds were 1,024 files, 4,096 paths, 32 MiB total, 16 MiB/file and metadata,
30 seconds per inventory and 60 seconds for copy. Before/copy/after identities
and hashes matched. The small complete transport tar is retained here with all
metadata, unlike larger packages that retain its hash plus individual payloads.

`guest-index.json` preserves original guest paths and identities;
`copy-index.json` maps every source-host copy to raw/stored size and SHA256.
All copies are uncompressed and byte-exact. `SHA256SUMS` covers every stored file
except itself. Preserve raw tabs/trailing whitespace in command, helper, JSON and
terminal records as evidence. No files were staged or committed, and closed
kernel5/recovery evidence or maintained guides were not edited.

# Ordinary return after live5 — 2026-11-10 UTC

One ordinary `systemctl reboot` returned 0 after live5 completed, unloaded and
became idle. The separate read-only proof then returned 0 with phase
`NORMAL_IDENTITY_VERIFIED`: release `7.0.0-38-kdlock1`, fresh boot
`884c4a65-4f4c-4a6b-89a3-cefd65221615`, GNU BuildID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, taint 0. Eight normal/recovery boot
files retained their exact size, mode and SHA256, and the normal GRUB default
remained selected with no pending one-shot entry.

This is a return and running-identity record. The protected JIT, recursive
handoff and physical-release observations belong to the separate live5 record;
the normal reboot does not establish those mechanisms.

The frozen [helper](guest/return-normal-live5-controller-9b3d.py), SHA256
`9b3d2ec7087bcf283d0217eee41341403b00c2b001e41ce42308eb5ad9db8f5a`,
has two explicit phases. Its [VM syntax receipt](guest/return-normal-live5-controller-9b3d-syntax.json)
is separate from the actual phase invocations.

Before invoking reboot, the helper required the actual live5 controller return
0 and `protected_jit_recursive_mechanism_pass` result for source `69ba6b03` and
core `1b50e373`. It checked positive protected root/child completion, distinct
current return endpoints, the fixed-image plain case, an empty final warm
claim, zero observation overflow and drained managed native holds. All 32
actual wire attempts had completed with status 0, ending in SHUTDOWN,
ARCHIVE_CLAIM, SETTLE and CLAIM_END (`9,10,11,6`). The durable archive's actual
SHA256 was `4b65ba08199ff76d46a7be866b5c99fb3e1c26b077d38920c88e814f544f638f`.
The helper accepts varying learning/fact counts; the captured run had eight
acknowledged facts and zero settled facts.

[pre-reboot.json](guest/return-normal-after-live5-20261110-UTC-01/pre-reboot.json)
retains the actual kernel3 boot `bceee25d-a189-4f51-89fa-0e31322b70e6`,
taint 12,288 (O/E), module/device absence, idle activity and the exact input
receipt hashes. Dynamic boot/default values came from the new kernel3
postboot proof, whose input records are copied under
`guest/postboot-kdrebuild3-20261110-UTC-01/`.

[reboot-result.json](guest/return-normal-after-live5-20261110-UTC-01/reboot-result.json)
records the sole command `systemctl reboot`, return code 0, empty stdout and
stderr, and phase `REBOOT_COMMAND_RETURNED`. No boot entry was armed or reset,
and no module was forcibly unloaded. The 240-second read-only reconnect
observer reached the fresh normal boot on its first query; this is not a boot
latency measurement.

The [normal proof](guest/return-normal-after-live5-20261110-UTC-01/post-normal/result.json)
and actual [running note bytes](guest/return-normal-after-live5-20261110-UTC-01/post-normal/running-kernel-notes.bin)
bind the normal GNU BuildID to the fresh running kernel. The proof independently
rechecked the eight normal/recovery boot files, module namespace presence,
module/device absence and idle state. GRUB configuration SHA256 remained
`17c2ab033f0f294e903ebf53b4a1c3aac5fe88ed8ee4df19aa3c0661937a6fbd`.
Installed module-file protection remains scoped to the separate installation
receipt; this phase checks namespace presence.

[guest-index.json](guest-index.json) independently indexes all nine copied VM
files, totaling 292,429 bytes. [collection.json](collection.json) records the
copy checks and the two actually observed helper exit codes. Source-host SSH
output and the bounded reconnect receipt are under `source-host/`.
`SHA256SUMS` covers all local files except itself. Collection copied and hashed
completed receipts; it did not repeat reboot, proof, module work or a test.

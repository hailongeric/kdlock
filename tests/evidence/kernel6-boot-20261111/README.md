# Kernel6 isolated installation and boot

The [linked candidate](../kernel6-build-20261111/README.md), core `532b68a6`
with source/installer `3512f5dd`, was installed and booted after the exact
[NLS staging and API-module builds](../kernel6-api-build-20261111/README.md).
All operations ran in the VM. The actual commands, individual return values,
stdout and stderr remain separate in the controller records here.

The isolated stage and separate check both returned 0. The
[measured root budget](stage-check/payload/root-budget.json) recorded
12,622,807,040 bytes free against 1,401,888,768 bytes needed, including a
1 GiB reserve and 256 MiB working allowance. Its exact one-module closure
contains only the rebuilt signed `nls_iso8859-1.ko`. The private initramfs is
30,886,395 bytes, SHA
`5c29a79b24c208a44ebc941d5e1bce144b306db285d7f10d2f3706ad785bfca8`.

Installation and arm each returned 0. Installation created only the candidate
kernel/module namespace. It appended one 1,008-byte entry to the existing
`custom.cfg`, preserving its entire 8,208-byte prefix and file identity/mode.
The combined file has SHA
`10704ea47ac50dfef89b9a0f2a6870f668bbaf7bb4935254d14f4c2dea829255`.
The main `grub.cfg` stayed byte-identical at SHA
`4cb0e54c275387c4e725b1dc3d6c69393ec98207a5ea71d1c736c227b5eb93be`.
No GRUB generation command ran. All old entries and the persistent normal
default were retained; arm changed only the one-shot selection.

The [ordinary reboot command](reboot-controller/result.json) returned 0.
After bounded reconnect, the unchanged postboot helper returned 0 and saved
[POSTBOOT_IDENTITY_VERIFIED](postboot/payload/postboot/result.json), SHA
`dc85e8cb778cecf0feead51c41e12776529fb19dccb223fd3043234b71888b08`.
It establishes:

- Release `7.0.0-38-kdrebuild6`, boot
  `4400eea1-c8fc-40e1-b6b7-f7a99ecc1364`, initial taint 0.
- Running GNU Build ID `5ed6cd8cffed6960ce901261dfab3bb019a0442d`, matching
  the actual ELF/config/image/map and installed signed NLS bytes.
- Exact [GS proof](postboot/payload/postboot/gs-proof.json), SHA
  `db303f2274c1cf19ecb1c6838673df129d776fca2f9b4c9a070846b0e0504733`,
  including full current-task alias `0xffffffff84416018` and `nokaslr`.
- Consumed one-shot selection, unchanged normal default, eight normal/legacy
  boot files and twenty previous candidate boot files preserved.
- Required mounts and SSH available, with no experimental module loaded.

[Tool identities](postboot-controller/tool-identities.json) retain the original
kmod aliases and hashes of their resolved executable bytes. They are subsequent
test inputs, separate from kernel or module identity. This record establishes
installation and boot only. Native API/MM completion and private generated
execution have their own evidence; boot supplies no performance result.

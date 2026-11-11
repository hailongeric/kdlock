# Spin and mutex fixture builds — 2026-11-11 UTC

Both separate fixture module builds returned **0**, and both runner AST parses
passed. The final controller status is `COMPLETE` with return code 0 at
02:23:06.306 UTC. This receipt covers compilation, saved flags and syntax
parsing. Each runtime invocation has its own evidence.

The fixture source is `0a07f67876a81c9b341670107bfef39b66a99f9e`.
The built kernel package/core is `2d0ad60b0bc46929f3070aefa364e710c0a81115`.
The controller checked all 103 frozen source files, the 67 actual package
inputs and six actual kernel-output pins before building and after each build.
The source state retains the actual worktree status at archive construction.
Kernel build and installation have separate receipts.
[Source state](source/source-state.json), [kernel build](../kernel-build4-20261111/README.md),
[kernel boot](../kernel-install4-20261111/README.md).

| Fixture | Module SHA256 | Bytes | Build observer seconds |
| --- | --- | --- | --- |
| Spin | `180d36459307576ff3c54b874186a058da710acf9c8c76ba28e5929efffe8b47` | 612,840 | 2.514796 |
| Mutex | `57a20a4e5d821cd649e73e8baaf1aa66543aa18ce5a6977cf2c4f5b09f3bfd53` | 581,920 | 2.513788 |

The actual final result SHA256 is
`1bfa8f99cbd05c231e39000749f6772944c2bf1586cc9856525533bde3d0c620`.
Each build uses the ordinary kernel make path with `-j8 V=1`, an immutable
`M=<fixture source>` and a distinct `MO=<module output>`. The explicit release
is `7.0.0-38-kdrebuild4`. Normal compiler and mitigation flags are preserved in
the complete build logs and normal command files.
Both module `modinfo` records report the matching release-specific vermagic.
The before/final build identity is normal `7.0.0-38-kdlock1`, boot
`884c4a65-4f4c-4a6b-89a3-cefd65221615`, taint 0. Each child observer
recorded completion within its bound. The successful controller path includes
an idle check after each build. The saved process listing is the pre-build
observation.
[Build result](module-build-receipts/result.json), [normal commands](normal-command-files).

The spin log preserves a 2,288-byte frame warning at the shared
`runtime_fixture.c:624` control-read function. The mutex log preserves its
2,264-byte warning at the same source function, both against the ordinary
1,024-byte warning threshold. Actual source paths and complete diagnostics
remain in the separate logs. The observer uses a 300-second bound per child,
and the result records actual pre-build root/output space availability.
The complete normal compiler commands are retained.

The six kernel pins have SHA256
`503fab29b3b8066ead750fe2223278865b4df6d60d991b532cacf588ec834886`.
They bind the module builds to ELF
`310df27ab801ecb0cb291d510a77d491030b6c85388a3930df2f54306bc27dd5`,
config `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`,
actual `System.map`/`Module.symvers` and release/generated-UTS files.
The independent collection reread each actual module binary and matched its
saved size/hash. The binaries remain at their exact guest paths under
`/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-0a07f678-01a1bc4f/module-build`.
The retained symbol tables and `modinfo` output describe those exact modules.
[Six kernel pins](source/actual-kernel4-six-kernel-pins.json).

The remote index inventories 34 copied VM metadata files, 680,079 raw bytes,
plus the separately hashed module identities. Its scope is read-only completed
receipts and command files. The copy index and `SHA256SUMS` record all local
origin/stored hashes. The collection helper
and command receipts are retained. T01–T56, recursive execution, physical
release/retirement and performance require their separate runtime evidence.
[Remote index](remote-index.json), [copy index](copy-index.json).

The raw modinfo/build output and normal command records preserve 14
trailing-space lines. Their captured bytes are retained for hash equality.

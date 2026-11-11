# db7 spin and mutex fixture compilation

Both fixtures compiled successfully from `db7d7d6e38e1341e24b643553bd83633616d4ea7` against the unchanged kernel4 core `2d0ad60b0bc46929f3070aefa364e710c0a81115`. The actual build controller returned zero with `COMPLETE`, from 2026-11-11 03:25:59.677398 to 03:26:06.592727 UTC. Its result SHA256 is `cb79249bfbb6f883935b93dbeef33045a4714deecdc2da5082163830987399af`. This is compilation evidence. The later live runs are recorded separately. [Actual result](module-build-receipts/result.json)

The frozen source snapshot has 103 files, with 67 kernel package inputs and six exact kernel pins. Source and output remained separate through explicit `M` and `MO` paths. Each build used eight jobs, a 300-second bounded observer and normal compiler flags. Both runners passed their actual VM syntax checks. Snapshot, package and kernel hashes matched before and after compilation. The build ran after the failed-run recovery, on kernel4 boot `84e4ba94-b616-4b65-9efe-820921f36c16`, taint 12288. The source manifest, state, seven fixture files and private observation include are retained here. [Source state](source/state.json), [source manifest](source/manifest.json), [six kernel pins](source/six-kernel-pins.json), [saved normal command files](normal-command-files)

| Module | Bytes | SHA256 | Actual build duration |
| --- | ---: | --- | ---: |
| `kd_spin_runtime_fixture.ko` | 615800 | `79521d2ec8f87b5750c7ac2dc7f4e4fff2959d39928d30db1736985569642e1f` | 3.023514470 s |
| `kd_runtime_fixture.ko` | 584856 | `bdbfb2111e64d13a8b8416c2b43b91851c227346fdbe3c7fc6e06253a9ac0515` | 2.510897083 s |

The fixture status function produced frame warnings of 2288 bytes for spin and 2264 bytes for mutex, each above the configured 1024-byte warning threshold at shared source line 632. Complete logs, normal return/indirect thunk flags, modinfo and symbols are retained. Both modules report vermagic for `7.0.0-38-kdrebuild4`. Binary modules remain at the exact guest paths identified by the result and remote index. [Spin build](module-build-receipts/spin/stdout.log), [mutex build](module-build-receipts/mutex/stdout.log), [independently read module identities](remote-index.json)

Read-only collection retained 41 guest metadata/source files containing 787,686 origin bytes. It independently inventoried each file and both module byte identities, then verified the copied payload against that inventory. Scope is fixture compilation and retained binary identities. Generated execution, recursive correctness, timing and full acceptance-matrix completion require separate evidence. Raw spacing remains unchanged. [Copy index](copy-index.json), [collection commands](collection.json), [SHA256SUMS](SHA256SUMS)

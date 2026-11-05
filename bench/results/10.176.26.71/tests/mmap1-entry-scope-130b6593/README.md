# Focused mmap1 writer-entry scope

Runtime source: `130b65939053026339014833774e5fb11b234972` on `codex/mmap-reached-jit`.
The scope implementation is `c66af150a83f8dd324003ef699dd03fc389846c3`; subsequent commits add the scoped scoring gate and correct two existing fixture expectations. Master remains unchanged.

## Scope and identity

- Selected root entries: `0xffffffff817b6f68` (`vm_mmap_pgoff+0x118`) and `0xffffffff8181c73b` (`__vm_munmap+0xbb`).
- `rwsem_provider_entries` is immutable after load, validated against the builtin site table, read back, and bound into receipts. Empty selection keeps the existing unrestricted default.
- Excluded facade captures acquire through callable local KD APIs on the same bound object. Killable/interruptible results, unlock and downgrade routing are preserved. Nested execution still uses the existing same-image service path.
- Kernel `7.0.0-38-kdscope5`, Build ID `5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, preemption `full (lazy)`.
- Runtime boot: `de5174e2-ed8c-4ca8-80e1-3fdd2bd7b889`. Provider SHA256: `e8870c9b469e6489227f5f20f6ef9a24700061afd9480e37dbdaaef5c8fa8274`.
- 64 vCPUs, two NUMA nodes; workers 0/1 on node 0, collector 63, services 0–61; verified host pins, fixed 2 GHz and recovery snapshot.
- Provider built with `W=1`, NUMA enabled, batch 1024 and 128 image slots. Daemon SHA256: `9a80d79d1c43d7c1be8a27fdc2bd2cfd0c278ba76c855e581a85a0ad962bf413`.

## Correctness and retained failures

All four affected Python groups passed: 8 demand/scope, 22 mmap1, 9 controller, and 4 image-retirement cases. The compiled public rwsem API fixture passed. The production admission fixture passed 15 deterministic cases and detected all four altered-order variants. These component checks do not establish live concurrent cancellation or multi-image execution.

Both unchanged mmap1 models passed a separate unscored local-path check. No daemon or published image was present. Unknown entry selection was rejected; the valid entry parameter was read back with mode 0444; only the two selected UNINIT roots registered. This proves scoped local routing and application progress, not proxy execution.

Retained failures:

- `c66af150`: standalone rwsem API fixture lacked the existing Native release-route declaration and operation enum. The four preceding Python groups passed; module build did not run.
- `19e591aa`: public API runtime assertions passed; the emitted-control expectation omitted the existing flag-save prefix. The corrected fixture requires the full five-instruction sequence.
- The functional controller reached its 15-second binding-drain limit with zero frames/writers and two bindings. After it exited, a fresh finalizer observed zero bindings before ordinary CPU progress, then retired and unloaded normally. The original failed receipt remains unchanged.
- Process benchmark cleanup reached its 10-second binding-drain limit after closing the idle daemon. A fresh finalizer observed one binding before ordinary per-CPU activity and zero afterward, then retired and unloaded normally. The owning MM and precise cause were not attributed.

## Unscored comparison

Unchanged will-it-scale `75f66e45697e6f5f49c33dd950c4e6b289198f8f`: `mmap1_threads -t 2 -s 2 -m` and `mmap1_processes -t 2 -s 2 -m`. Each lifetime includes six warmup samples and two post-marker samples. Rates are completed mmap/munmap pairs divided by two nominal seconds; they are not whole-process rates.

The retained Native controls use the same kernel Build ID, workload binaries, CPU grid, and lazy preemption with `kd_mmap=off`; their source, boot and receipt identities remain separately recorded. No Native rerun occurred.

| Model | Retained Native pairs/s | KD learning range pairs/s | Scored KD points | Verdict |
| --- | ---: | ---: | ---: | --- |
| threads | 250,997.0 | 101,836.0–111,089.5 | 0 | LEARNING_ADVANCED |
| processes | 669,612.0 | 328,337.0–339,131.5 | 0 | LEARNING_ADVANCED |

Every one of the eight application lifetimes in each model completed and drained. Both models stopped at the eight-lifetime limit because registry generations still changed. Neither reached a scored application; the 1800-second deadline was not the stopping reason. Both selected roots were NORMAL at generation 9 after final learning, but readiness at that boundary does not prove stability on another invocation.

| Learning lifetime | Threads pairs/s | Processes pairs/s |
| --- | ---: | ---: |
| 1 | 103,493.5 | 339,131.5 |
| 2 | 103,751.0 | 330,268.5 |
| 3 | 108,424.0 | 330,629.5 |
| 4 | 111,089.5 | 328,337.0 |
| 5 | 101,836.0 | 330,536.5 |
| 6 | 104,743.5 | 331,562.5 |
| 7 | 106,203.0 | 330,297.0 |
| 8 | 104,864.0 | 330,261.0 |

| Model | Successful serial compilation jobs | Compilation seconds | Application-lifetime seconds | Published images |
| --- | ---: | ---: | ---: | ---: |
| threads | 18 | 241.994 | 64.299 | 18 |
| processes | 18 | 242.476 | 64.297 | 18 |

Each session retained 18 published images (two roots × nine generations), leaving 110/128 slots free. No capacity failure occurred. The scope reduced the number of roots being compiled; it did not resolve the stability barrier or establish an application throughput gain. The performance/regression gate remains open.

## Evidence and recovery

`summary.json` retains configurations, all learning rates and completion states, compiler metrics, image tables, Native control identities, original unaccepted results, and retirement receipts. Full guest records remain under:

`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/scope2-130b6593-8x1800/`

Functional and build records remain under `.../tests/scope2-functional-130b6593/` and `.../tests/scope2-preflight-130b6593/`. The two failed preflights retain their separate namespaces and copied diagnostics in `fixture-failures/`.

Exact final retirement reached `state=2 modules=0 frames=0 writers=0` in both models, followed by ordinary unload. Recovery verified `7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot `1461714d-b4f5-4f6a-b544-f96729550101`, idle, with the one-shot boot setting consumed.

Image publication and global learning are the available JIT evidence here. Worker-attributed returned bodies, live nested acquisitions, physical delegation length, and critical-section ratio remain unmeasured. This candidate does not implement separate child images, a new matching-release cutoff, image reuse, or a numeric CFG cap.

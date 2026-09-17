# 2026-09-17：共享 spin request 与批次 lease

保留 JIT，改为 waiter 预备共享 request/frame，combiner 按指针绑定，复杂/native/
remote 路径共用逻辑寄存器包，最终恢复后归还引用；source/provider lease 改为
每批次一次。当前仍逐请求进入 JIT wrapper 和 C dispatcher，未实现 TCLock WWJUMP。

本页测量冻结在随后恢复 shadow 等待栈之前；后续
[shadow 等待栈验证](../../../tests/README.md#spin-shadow-wait-validation)
只包含定向功能检查，不能将本页数值当作最终等待栈版本的测量。
包含 shadow 栈和后续嵌套优化的性能重跑见[当前完整扫描](20260917-current-spin.md)。

**16/16 会话通过，但未测得整体提速。** 对比
[上一版 waiter 包与原子 frame lease](20260917-waiter-packet.md)，20 线程两点
分别下降 **12.0%/4.9%**。本次结果不能作为共享 frame 已提升性能的证据。

| cacheline | 线程 | 原生中位 Mops/s | 上一版 kdlock 最佳 | 本版 kdlock 最佳 | 相对上一版 | 本版 best/median | 最佳会话 JIT 占比 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 2.976 | 0.708 | 0.677 | -4.4% | 0.2273 | 56.18% |
| 1 | 20 | 3.248 | 1.029 | 0.905 | -12.0% | 0.2786 | 99.84% |
| 16 | 4 | 1.960 | 0.622 | 0.627 | +0.9% | 0.3199 | 52.95% |
| 16 | 20 | 1.954 | 0.951 | 0.905 | -4.9% | 0.4630 | 99.84% |

每点两对交替顺序的原生/JIT 会话，每线程 100,000 次，CPU 0–19、NUMA 0，
`bench_quiet=1 jit_timing=0`。共 19,200,000 次操作、8,887,387 次测量期 JIT
正文，最长测量批次 2.244 秒。负载源码与上一版相同，均保留四组锁外乘加。
比较的是各自运行的最佳 kdlock 吞吐；只有两个样本，宿主核独占与频率未控制。
未进行函数级或缓存事件采样，不能把下降直接归因于某个字段或共享缓存行。

本轮源于 `81a82ce` 加共享 request 改造。frame/context/request 为 656/5272/672
字节，每可能 CPU 额外预分配 12 个 request（8064 字节）；普通/bench provider
静态 per-CPU 节为 7424/7488 字节。静态节变小不代表总内存减少。

guest 为既有 `6.1.159-kdstatic2`，nokaslr、voluntary；Build ID
`460d77502af4709a0cca794b322cedc20c2cc478`，恢复快照
`pre_static_boot_20260915`。没有修改或重编译内核。全部数据、实际 JIT、
退休/卸载检查通过；源码/二进制/boot ID 在运行中未变，结束后无内核 fault。
宿主离线复算全部会话计数、CPU 放置、最佳值与比较值，核对 189 项冻结源码和
24 项生成映像哈希。早期观测补丁因日志上下文变化无法应用，修正后再构建；
没有放宽 `--fuzz=0`，生产逻辑未加入 benchmark 观测代码。

```sh
# 确认快照后在 guest 执行；宿主 SSH 另有外层 timeout。
LC_ALL=C KDIR=/root/linux-6.1.159-kdstatic2 KDLOCK_RECOVERY_CONFIRMED=1 \
KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 timeout 840s \
  python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 16 --threads 4 20 --cpus 0-19 \
  --iterations 100000 --repeats 2 \
  --output /root/kdlock-evidence/spin-tclock-shared-20260917
```

- [汇总 CSV](/tmp/kdlock-tclock-jit-20260917/evidence/spin-tclock-shared-20260917/summary.csv)、[逐会话 CSV](/tmp/kdlock-tclock-jit-20260917/evidence/spin-tclock-shared-20260917/raw.csv)。
- [独立复算](/tmp/kdlock-tclock-jit-20260917/audit.json)、[最终身份与排空](/tmp/kdlock-tclock-jit-20260917/evidence/spin-tclock-shared-20260917/postflight.json)。
- [相关功能验证](../../../tests/README.md#tclock-shared-validation)；guest 持久证据为上述 output 目录。
- [完整归档](/tmp/kdlock-tclock-jit-20260917/evidence.tar.gz)，SHA256：
  `c668405de0ea788b12c653dea1a3c735cb7510d4a5ec46db1251bbca9efe1ced`。

本结果页在测量后补写；冻结说明文件以各次运行归档为准。

# 2026-09-20：continuation 交接后的三方性能测试

提交 `644f2317f6cbedb3265df63572eb6e9d8fe080c7`，正式 **150/150 场通过**，
完成 **147000000 次操作**。12 场小规模检查另完成 300000 次操作；两组不混合汇总。
测试前核对全部 Git 跟踪文件与提交一致，测量期间不修改源码或二进制。

20 线程、1 cacheline 下 KD 为 4.979 Mops/s，是 Linux 的 1.212×、TCLock 的
0.999×；16 cacheline 下为 4.763 Mops/s，是 Linux 的 1.909×、TCLock 的 1.433×。
单线程和四线程仍低于两个对照后端。本轮比较当前三个后端，没有同期运行旧版 KD，
不能将历史成绩差异单独归因于 continuation 存储或退休协议。

## 配置与计量

- cacheline 正文，1/16 cacheline × 1/4/8/16/20 线程 × 三后端 × 五次重复。
  每线程 100000 次，各线程绑定 CPU 0 起的前 T 个 guest CPU，均在 NUMA node 0。
- Linux、TCLock、KD 使用各自显式 API，逐轮正反交替；KD 为 observe 固定准入、
  `spin_delegate=on`，保留实际 JIT 完成计数。不是 adaptive 或不代理对照。
- 显式翻译准备和单 CPU 48000 次预热不计时。计时前停止 daemon/翻译者；
  计时包含加解锁、固定 cacheline 更新、锁外四组乘加及循环成本。
  吞吐为完整操作吞吐，摊销 ns/op 不是独立获取锁延迟。
- TCLock 沿用当前移植版：批次上限 1024、关闭 IRQ 检查、没有新增执行计数，
  不含已删除的等待调度检查/调度点；TCLock 后端及三个 workload 均关闭模块 UBSAN。
  本轮未修改 TCLock、内核或任何执行源码。
- recovery/ext4 guest，40 vCPU，内核 `6.1.159-kdclobber2`，nokaslr、voluntary；
  Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。加载前 monitor 确认
  `pre_static_boot_20260915` 快照存在。不假定 guest CPU 独占宿主物理核。

## 五次中位数

吞吐单位为 **Mops/s**，越大越好；KD JIT 占比也取五次中位数。

| cacheline | 线程 | Linux | TCLock | KD | KD/Linux | KD/TCLock | KD JIT 占比 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 16.721 | 14.457 | 5.922 | 0.354× | 0.410× | 0.00% |
| 1 | 4 | 3.693 | 2.975 | 1.831 | 0.496× | 0.615× | 58.39% |
| 1 | 8 | 3.955 | 4.274 | 3.955 | 1.000× | 0.925× | 98.07% |
| 1 | 16 | 3.786 | 4.982 | 4.922 | 1.300× | 0.988× | 99.80% |
| 1 | 20 | 4.107 | 4.985 | 4.979 | 1.212× | 0.999× | 99.80% |
| 16 | 1 | 14.085 | 10.978 | 5.685 | 0.404× | 0.518× | 0.00% |
| 16 | 4 | 2.117 | 2.190 | 1.565 | 0.740× | 0.715× | 59.81% |
| 16 | 8 | 2.315 | 3.163 | 3.979 | 1.719× | 1.258× | 98.84% |
| 16 | 16 | 2.354 | 3.449 | 4.696 | 1.995× | 1.362× | 99.75% |
| 16 | 20 | 2.495 | 3.325 | 4.763 | 1.909× | 1.433× | 99.83% |

全部样本保留。16 cacheline 单线程 TCLock 有一次 32.972 Mops/s，其余为
10.833–11.942 Mops/s，未剔除高值；汇总使用中位数。20 线程 KD 的五次范围为
4.970–5.002 Mops/s（1 cacheline）和 4.755–4.805 Mops/s（16 cacheline）。
其他配置的完整样本及范围见离线审计文件。

## 正确性、边界与证据

基础两个 C 程序及运行器 9 项检查通过。先跑 12 场小规模检查，再跑正式 150 场；
没有失败、未执行场次或中途重试。每场检查正文数据、完成数、CPU 亲和性、
IRQ/preempt 恢复、内核错误日志及排空，正式 KD 的 **40/40 场竞争测量有实际 JIT**。
10 场 KD 单线程为零 JIT，属于无竞争原生执行，不记为 JIT 正例。
TCLock 没有额外执行计数，代理数量为 `UNMEASURED`，不推断其批次长度。

冻结源码/二进制哈希复核通过，最终 worker/daemon 退出、测试模块全部卸载。
构建保留已有换栈 objtool 告警；没有本轮 kernel BUG/Oops/WARNING。
provider 沿用默认 `mutex_jit=1` 参数，但负载只调用 spin，本轮没有验证 mutex JIT。
未运行全量回归、跨 NUMA 负载、nested/early 性能或远端 native 强制时序；
这些协议的已有功能结果与边界见 [continuation 验证记录](../../../tests/README.md#continuation-validation)。

正式命令（使用固定依赖 venv，另有宿主 SSH 外层 timeout）：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --workload cacheline --cachelines 1 16 --backends native tclock kdlock \
  --threads 1 4 8 16 20 --repeats 5 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/continuation-perf-20260920/matrix
```

guest 证据目录 `/root/kdlock-evidence/continuation-perf-20260920/`，包含基础测试、
运行器检查、smoke、matrix、构建日志、源码/ELF、JIT 生成物、内核身份及逐场日志。
`host-commit-sha256.json` 记录提交身份，`audit.json` 记录哈希复核、场数和最终空闲状态。
结果文档在测试结束后更新，未纳入冻结测量输入。

[汇总 CSV](../../.tmp/continuation_perf/summary.csv)、
[逐场记录](../../.tmp/continuation_perf/records.json)、
[离线审计与样本分布](../../.tmp/continuation_perf/audit.json)、
[完整归档](../../.tmp/continuation_perf/continuation-perf-20260920.tar.gz)。
这些大型原始材料不提交 Git，guest 同时保留完整归档
`/root/kdlock-evidence/continuation-perf-20260920.tar.gz`。
SHA256：`72dca2c6f9d7a98abd509b5ba4530243839a1a206609830205e90bb5bf39220a`。

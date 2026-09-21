# 2026-09-21：当前版本完整三方 benchmark

提交 `175d73b`，**150/150 场通过，共完成 147000000 次操作**。
本轮只测量当前版本，没有修改锁实现，也没有运行同期旧版 KD。
20 线程 c1/c16 的 KD 为 **5.003 / 4.775 Mops/s**，分别为 TCLock 的
**1.002× / 1.442×**；四线程仍为 TCLock 的 **0.659× / 0.766×**。

## 配置与方法

- cacheline 正文，1/16 cacheline × 1/4/8/16/20 线程 × Linux/TCLock/KD × 五轮。
  每线程 100000 次，从 CPU 0 起绑定前 T 个 CPU，均在 NUMA node 0。
- 三种后端使用各自显式 API；逐轮正反交替，每场新建会话并正常卸载。
  KD 使用 observe、spin_delegate=on，保留最小 JIT 完成计数，关闭 JIT timing。
  TCLock 保持当前设置，代理次数未测，不把零计数当作没有代理。
- 翻译准备及单 CPU 48000 次预热不计时，测量前停止 daemon/翻译者。
  吞吐包含获取、正文、释放、锁外四组乘加及循环，不是独立锁延迟。
  所有有效样本保留，按五次中位数汇总。
- recovery/ext4，40 vCPU，`6.1.159-kdclobber2`、voluntary、nokaslr；Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。实际确认恢复快照
  `pre_static_boot_20260915`。不假设 guest CPU 独占宿主物理核。
- 测量前 host/guest 全部 340 个跟踪文件一致；运行器冻结相关源码/ELF，逐场校验。
  本轮沿用已验证的生产代码与环境，没有重复运行单元或功能矩阵。

## 五次中位数

吞吐单位 **Mops/s**，越大越好。KD JIT 占比也取五次中位数。

| cacheline | 线程 | Linux | TCLock | KD | KD/Linux | KD/TCLock | KD JIT 占比 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 16.909 | 14.655 | 6.158 | 0.364× | 0.420× | 0.00% |
| 1 | 4 | 3.687 | 2.978 | 1.962 | 0.532× | 0.659× | 48.98% |
| 1 | 8 | 3.904 | 4.239 | 3.999 | 1.024× | 0.943× | 97.62% |
| 1 | 16 | 3.810 | 4.993 | 4.920 | 1.291× | 0.985× | 99.78% |
| 1 | 20 | 4.037 | 4.994 | 5.003 | 1.239× | 1.002× | 99.85% |
| 16 | 1 | 14.004 | 11.810 | 6.158 | 0.440× | 0.521× | 0.00% |
| 16 | 4 | 2.160 | 2.258 | 1.731 | 0.801× | 0.766× | 50.37% |
| 16 | 8 | 2.291 | 3.175 | 3.956 | 1.727× | 1.246× | 98.38% |
| 16 | 16 | 2.331 | 3.441 | 4.692 | 2.013× | 1.363× | 99.76% |
| 16 | 20 | 2.404 | 3.311 | 4.775 | 1.986× | 1.442× | 99.82% |

20 线程保持上一轮恢复后的吞吐水平；本轮未做旧/新版本同期对照，不能把与历史
数据的差异归因为新优化。单线程和四线程仍有差距。完整样本及其波动保存在
`audit.json`，没有按结果快慢删除样本。

## 验收与边界

150 场均通过业务数据、完成数、CPU 亲和性、IRQ/preempt 和排空检查。
竞争 KD **40/40** 场有实际 JIT；10 场单线程 KD 为无竞争原生执行，不算 JIT 正例。
150 份内核日志没有 BUG/Oops/WARNING/stall，全部 worker/daemon 退出，测试模块卸载。
最终源码、二进制哈希及空闲审计通过；构建保留既有换栈 objtool 告警。

provider 沿用默认 `mutex_jit=1`，但本次负载只调用 spin，不构成 mutex JIT 验证。
没有 PMU 采样、adaptive、nested/early、跨 NUMA、多锁性能或远端 native 强制时序。
本轮是当前三后端的完整默认性能矩阵，不是全量功能回归。

运行命令（固定 venv，SSH 另有外层 timeout）：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/benchmark-175d73b-20260921/matrix
```

未指定的矩阵参数使用上表默认值。原始证据在 guest
`/root/kdlock-evidence/benchmark-175d73b-20260921/`，包括提交身份、全部源码哈希、
构建/运行日志、ELF、生成代码、环境、逐场记录和结束后的只读审计。
结果文档在测量结束后更新，不改变冻结输入；宿主只做文件编辑和离线归档校验。

[汇总 CSV](../../.tmp/benchmark_175d73b/summary.csv)、
[逐场记录](../../.tmp/benchmark_175d73b/records.json)、
[审计与全部样本](../../.tmp/benchmark_175d73b/audit.json)、
[完整归档](../../.tmp/benchmark_175d73b/benchmark-175d73b-20260921.tar.gz)。
大型材料不提交 Git，guest 保留同一归档。SHA256：
`a9ff4efde17cbaa824318aa1ba359c560f7ccbb608a315205aa45158e6c08155`。
宿主已离线核对归档、冻结源码及 ELF 哈希。

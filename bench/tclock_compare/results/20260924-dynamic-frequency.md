# 2026-09-24：默认动态频率下的单轮三方比较

按用户要求，保留宿主默认动态频率重新测一次。56/56场通过业务、IRQ/preempt、内核错误及排空检查，完成43200000次计时操作。c1单线程KD adaptive为13.052Mops/s；c16单线程observe出现30.808Mops/s的快样本，adaptive为10.481Mops/s，全部原样保留。**单轮结果不能证明模式收益、稳定性或原优化目标的全部线程无回退。**

## 方法与频率

输入提交`335e14b`，阶段`compare-dynamic-20260924`；未修改锁代码。c1/c16 × 1/2/3/4/8/16/20线程 × Linux Native/TCLock/KD observe/KD adaptive，每项一轮、每worker100000次测量。显式`--repeats 1`，不修改默认三轮设置；后端依次运行，没有随机交错或替换样本。

宿主worker CPU0..19保持`intel_pstate`、`powersave`、`balance_performance`，min/max为1000000/3000000kHz。本次没有写频率设置，运行前后逐CPU读回完全一致。这是动态1–3GHz允许范围，不代表每次测量都以1GHz或相同实际频率运行；未采集各计时区间的实际频率或PMU。

全部worker参与48000次/人的计时外预热；预热与测量分别创建相同CPU绑定的worker，不再插入额外2秒等待。预热审计确认56场共432名worker、20736000次预热操作，实际预热结束至测量开始间隔为11.43–94.16ms。runner允许CPU0..19，worker使用CPU0至CPU(`threads-1`)，宿主40个vCPU绑定和恢复快照已重新核对。

guest内核为`6.1.159-kdclobber2`，nokaslr、voluntary，Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。KD策略仍为`mcs_entry_ratio512_simple`、`spin_contention_pct=100`、delegation on；实际加载provider的`mutex_jit=1`，本次负载为spin。没有追加独立单元、nested/early或全量功能测试。

本报告不与[此前固定2.5GHz结果](20260924-all-worker-warmup.md)或历史单worker预热样本合并；频率影响见[独立单线程对照](20260924-single-thread-frequency.md)。

## 吞吐与摊销时间

每格为 **Mops/s / ns/op**，两者来自同一会话；ns/op是完整操作摊销时间。末两列为KD adaptive相对Linux/TCLock吞吐比值。每配置只有一个有效样本，无法报告跨轮波动。

### 1条cacheline

| 线程 | Linux Native | TCLock | KD observe | KD adaptive | KD/Linux | KD/TCLock |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 18.566 / 53.86 | 13.901 / 71.94 | 12.837 / 77.90 | 13.052 / 76.62 | 0.703× | 0.939× |
| 2 | 2.739 / 365.14 | 6.196 / 161.41 | 2.700 / 370.38 | 2.518 / 397.13 | 0.919× | 0.406× |
| 3 | 3.377 / 296.15 | 2.579 / 387.77 | 1.820 / 549.59 | 2.588 / 386.45 | 0.766× | 1.003× |
| 4 | 3.673 / 272.26 | 3.071 / 325.67 | 2.068 / 483.46 | 2.311 / 432.79 | 0.629× | 0.752× |
| 8 | 3.903 / 256.18 | 4.742 / 210.89 | 4.491 / 222.69 | 4.491 / 222.66 | 1.151× | 0.947× |
| 16 | 3.812 / 262.36 | 5.233 / 191.11 | 5.448 / 183.57 | 5.341 / 187.24 | 1.401× | 1.021× |
| 20 | 4.046 / 247.15 | 5.297 / 188.79 | 5.594 / 178.77 | 5.440 / 183.83 | 1.344× | 1.027× |

### 16条cacheline

| 线程 | Linux Native | TCLock | KD observe | KD adaptive | KD/Linux | KD/TCLock |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 16.829 / 59.42 | 11.411 / 87.64 | 30.808 / 32.46 | 10.481 / 95.41 | 0.623× | 0.919× |
| 2 | 1.491 / 670.50 | 2.332 / 428.90 | 1.890 / 529.16 | 1.849 / 540.83 | 1.240× | 0.793× |
| 3 | 2.165 / 461.79 | 2.243 / 445.92 | 1.471 / 679.71 | 1.901 / 526.13 | 0.878× | 0.848× |
| 4 | 2.263 / 441.88 | 2.586 / 386.74 | 1.743 / 573.60 | 2.129 / 469.65 | 0.941× | 0.823× |
| 8 | 2.459 / 406.70 | 3.523 / 283.85 | 4.390 / 227.77 | 4.648 / 215.13 | 1.890× | 1.319× |
| 16 | 2.360 / 423.77 | 3.496 / 286.00 | 5.293 / 188.92 | 5.112 / 195.62 | 2.166× | 1.462× |
| 20 | 2.477 / 403.73 | 3.421 / 292.27 | 5.320 / 187.96 | 5.196 / 192.45 | 2.098× | 1.519× |

## 验证与证据

c16单线程observe的快样本通过了100000次业务更新、CPU0绑定和排空检查，实际JIT为0；不能将它与adaptive的单个慢样本之差解释成委托或模式收益。保留所有原始结果，没有补测择优。

28场KD中20场出现计时区间内实际JIT，合计18134863次正文；其余8场为1/2线程零JIT，按对应NO_JIT规则报告。TCLock代理次数未额外测量，仍为未知。预热JIT不计入上述测量区间计数。

[归档审计](../../.tmp/compare-dynamic-20260924/archive-audit.json)核对261项源码、8项二进制、84项JIT镜像和56场原始数据/摘要/内核错误/排空记录；[预热审计](../../.tmp/compare-dynamic-20260924/warmup-audit.json)核对全部worker。离线一致性检查不等同于再次执行用例。[结束状态](../../.tmp/compare-dynamic-20260924/guest-idle.json)确认guest空闲、相关模块已卸载。

原始[records](../../.tmp/compare-dynamic-20260924/guest/compare-dynamic-20260924/records.json)、[summary](../../.tmp/compare-dynamic-20260924/guest/compare-dynamic-20260924/summary.json)、[environment](../../.tmp/compare-dynamic-20260924/guest/compare-dynamic-20260924/environment.json)、[命令](../../.tmp/compare-dynamic-20260924/command.json)，以及频率[运行前](../../.tmp/compare-dynamic-20260924/host-cpufreq-before.json)/[运行后](../../.tmp/compare-dynamic-20260924/host-cpufreq-after.json)分别保留。

[完整证据包](../../.tmp/compare-dynamic-20260924-full.tar.gz)为3157331字节，SHA-256 `924b1b423c7fae2621cb936f5ab2da1e08cd7bb8f2c1da8d1ab644e64b2fbf86`；见[收据](../../.tmp/compare-dynamic-20260924-full.tar.gz.receipt.json)。包含guest原始日志、冻结源码/二进制和宿主元数据；本报告独立保存在Git中。

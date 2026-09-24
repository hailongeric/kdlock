# 2026-09-24：全部worker预热后的单轮三方比较

按用户要求，每配置重新测一次，共56/56场、43200000次计时操作，业务、IRQ/preempt、实际JIT规则及排空检查通过。c16的8/16/20线程，KD adaptive吞吐分别为TCLock的1.331/1.438/1.452倍；c1同配置分别为0.897/0.979/0.994倍。3/4线程在两个正文长度下仍低于Linux Native和TCLock。**这是新预热方法下的单轮结果，不能证明原优化目标中的全部线程无回退。**

## 方法与范围

输入提交`b8bd0e2`，阶段`compare-warm-all-20260924`；c1/c16 × 1/2/3/4/8/16/20线程 × Linux Native/TCLock/KD observe/KD adaptive，各一轮、每worker100000次。`--repeats 1`是本次明确选择，运行器默认三轮保持。各配置依次运行Linux、TCLock、observe、adaptive；没有随机化或重复采样。

每场登记准备命令单线程执行，继承runner允许的CPU0..19；发布/翻译完成并停止daemon后，使用与测量相同的worker数量和CPU绑定进行预热，每worker48000次，全部不计时。预热与测量是独立客户端调用，分别新建worker，保留相同CPU配置而非pthread身份。记录为`warmup_policy=all_workers`、`warmup_iterations_per_worker=48000`、`warmup_pause_seconds=0`；取消原额外2秒等待，worker退出及正常检查后发起测量。实际预热结束至测量开始仍有5.32–103.31ms间隔，不是零间隔，也不保证每CPU/每锁始终为热。[预热审计](../../.tmp/compare-warm-all-20260924/warmup-audit.json)核对56场共432名worker参与、20736000次预热操作及CPU/完成次数一致。

环境为`6.1.159-kdclobber2`、nokaslr、voluntary，内核Build ID为`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；worker绑定CPU0至CPU(`threads-1`)，runner允许CPU0..19。宿主相应CPU的min/max暂设2500000kHz，结束后已恢复并核对原值；配置限频不等于全程瞬时频率恒定。身份、拓扑与命令见[environment](../../.tmp/compare-warm-all-20260924/guest/compare-warm-all-20260924/environment.json)、[执行记录](../../.tmp/compare-warm-all-20260924/execution.md)及[恢复读回](../../.tmp/compare-warm-all-20260924/host-cpufreq-restored.json)。

KD记录策略`mcs_entry_ratio512_simple`，两模式的实际provider参数均为`spin_contention_pct=100`、`spin_delegate=Y`、`spin_prefetch=2`、`mutex_jit=1`、`bench_quiet=Y`、`hotlock_stats=Y`、`jit_timing=N`；`hotlock_mode`按场切换。observe绕过比例判断，adaptive采用比例及单锁热度准入；没有修改锁实现参数来调这轮成绩。

以下吞吐与ns/op均取同一会话，ns/op是完整操作的摊销时间，不是单独lock延迟。每配置只有一个有效值；summary的min/median/max相同，spread为null，不据此推断稳定性。原始精度、会话和所有模式见[summary](../../.tmp/compare-warm-all-20260924/guest/compare-warm-all-20260924/summary.json)与[records](../../.tmp/compare-warm-all-20260924/guest/compare-warm-all-20260924/records.json)。

## 1条cacheline

每格为 **Mops/s / ns/op**；末两列为adaptive吞吐比值，大于1表示本场KD adaptive更快。

| 线程 | Linux Native | TCLock | KD observe | KD adaptive | KD/Linux | KD/TCLock |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 42.879 / 23.32 | 34.806 / 28.73 | 31.754 / 31.49 | 31.679 / 31.57 | 0.739× | 0.910× |
| 2 | 2.549 / 392.32 | 5.904 / 169.39 | 3.599 / 277.88 | 2.717 / 368.09 | 1.066× | 0.460× |
| 3 | 3.552 / 281.55 | 2.840 / 352.12 | 1.725 / 579.66 | 2.516 / 397.44 | 0.708× | 0.886× |
| 4 | 3.390 / 294.94 | 3.511 / 284.79 | 2.070 / 483.11 | 2.698 / 370.58 | 0.796× | 0.768× |
| 8 | 3.690 / 271.04 | 4.865 / 205.54 | 4.606 / 217.12 | 4.362 / 229.27 | 1.182× | 0.897× |
| 16 | 3.399 / 294.23 | 5.119 / 195.36 | 5.083 / 196.74 | 5.012 / 199.52 | 1.475× | 0.979× |
| 20 | 3.966 / 252.17 | 5.067 / 197.36 | 5.080 / 196.86 | 5.034 / 198.64 | 1.270× | 0.994× |

## 16条cacheline

每格为 **Mops/s / ns/op**；末两列为adaptive吞吐比值，大于1表示本场KD adaptive更快。

| 线程 | Linux Native | TCLock | KD observe | KD adaptive | KD/Linux | KD/TCLock |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 33.260 / 30.07 | 28.077 / 35.62 | 26.348 / 37.95 | 26.487 / 37.75 | 0.796× | 0.943× |
| 2 | 1.550 / 644.98 | 2.308 / 433.29 | 1.835 / 544.94 | 1.853 / 539.68 | 1.195× | 0.803× |
| 3 | 2.050 / 487.80 | 2.126 / 470.26 | 1.408 / 710.45 | 1.818 / 549.91 | 0.887× | 0.855× |
| 4 | 2.142 / 466.95 | 2.453 / 407.64 | 1.726 / 579.52 | 1.905 / 524.88 | 0.890× | 0.777× |
| 8 | 2.173 / 460.12 | 3.221 / 310.48 | 4.345 / 230.13 | 4.286 / 233.30 | 1.972× | 1.331× |
| 16 | 2.141 / 467.17 | 3.266 / 306.14 | 4.811 / 207.87 | 4.698 / 212.85 | 2.195× | 1.438× |
| 20 | 2.219 / 450.63 | 3.232 / 309.36 | 4.840 / 206.63 | 4.695 / 213.01 | 2.116× | 1.452× |

## 验证、独立范围与证据

本轮基础两组及直接运行器28项检查通过，见[检查日志](../../.tmp/compare-warm-all-20260924/checks.log)。未追加独立nested/early、PMU或全量功能测试。28场KD中20场有计时区间内返回后的实际JIT，合计18108851次正文；observe为9344658次、adaptive为8764193次，各10场。1/2线程的8场KD正文为零，分别标记NO_JIT或NO_JIT_LOW_CONTENTION，不能称作实际JIT通过。TCLock未启用额外正文计数，其代理次数保持未知。

[归档一致性审计](../../.tmp/compare-warm-all-20260924/archive-audit.json)核对259项源码、8项二进制、84项JIT镜像及56场数据/摘要/内核错误/排空记录；这是离线一致性验证，不是重跑用例。冻结provider SHA-256为`4055c0ff1217281472874a79c6ef0c26da57f98d599331ac490d782dad7417c4`，完整清单见[二进制身份](../../.tmp/compare-warm-all-20260924/guest/compare-warm-all-20260924/binary-sha256.json)。

用户补充全部worker预热要求后，原`compare-once-20260924-1131`在24场已排空边界收到STOP；其exit 1是主动中止，不是失败会话，余32场保持NOT_RUN。这批单worker预热的部分记录独立保留，未补成56场，也未混入上表。此前[三轮比例调查](20260924-contention-ratio.md)的1467场累计同样保持不变。预热参与范围及额外等待均改变，不能把前后差值单独归因为比例策略、预热或某个硬件机制。

最终[完整证据包](../../.tmp/compare-warm-all-20260924-full.tar.gz)为6085587字节，SHA-256为`ec3e3d261a798c2c3764a585620b8cde059fb26173c8363b21541586370df062`，见[归档收据](../../.tmp/compare-warm-all-20260924-full.tar.gz.receipt.json)。包内包含两阶段guest原始证据、新56场及旧24场已完成记录/32场NOT_RUN，以及宿主频率、命令、审计和辅助脚本；报告在Git中独立保存。内部guest传输包SHA-256为`09c75a1a402bcdd0d2f91efe5cc90713b601335dd4ab35fab69cb48abbee7dcf`，见[传输核对](../../.tmp/compare-warm-all-20260924/guest-archive-verified.json)。宿主频率[恢复日志](../../.tmp/compare-warm-all-20260924/frequency-restore.log)已核对20个CPU；[结束状态](../../.tmp/compare-warm-all-20260924/guest-idle.json)确认仍运行原内核、guest空闲且相关模块已卸载。

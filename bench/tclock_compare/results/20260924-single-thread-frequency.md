# 2026-09-24：单线程频率对照

**相同当前源码，仅将宿主频率限制从1.0GHz改为2.5GHz，KD adaptive单线程中位吞吐由12.422604提高到31.673585Mops/s。** Linux Native与TCLock也随之提高约2.5倍。这说明当前代码在不同频率设置下即可复现“约13M到约30M”的差异，不能把此前跨日比较的这部分变化记作比例准入优化收益；昨天各计时样本的实际频率没有记录，仍不能断言全部历史差异只有一个原因。

## 对照方法

输入为`b8bd0e2`，锁实现未修改。只测c1、1线程、Linux Native/TCLock/KD adaptive，每项三轮；先运行`freq1000`，恢复原设置，再运行`freq2500`并再次恢复。每worker48000次计时外预热、100000次测量，无额外2秒等待；预热与测量分别创建CPU0绑定worker。每阶段三轮后端顺序为正序/逆序/正序，共18场、1800000次计时操作及864000次预热操作，没有删除或替换样本。[命令说明](../../.tmp/single-frequency-20260924/command.txt)及两阶段[1.0GHz environment](../../.tmp/single-frequency-20260924/guest/single-frequency-20260924/freq1000/environment.json)、[2.5GHz environment](../../.tmp/single-frequency-20260924/guest/single-frequency-20260924/freq2500/environment.json)保留配置。

两阶段均为`6.1.159-kdclobber2`、nokaslr、voluntary，内核Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；runner允许CPU0..19，worker使用CPU0。宿主CPU0..19的min/max分别设为1000000或2500000kHz；每阶段结束后均已恢复原min/max、governor和EPP并读回核对。这是受控的频率限制对照，不代表连续观测了每一瞬间的实际时钟。

两阶段259项冻结源码哈希完全一致，client、TCLock后端、allocator guard和daemon二进制相同。[冻结机器码核对](../../.tmp/single-frequency-20260924/frozen-code-identity.md)确认八对ELF的可执行节、重定位、符号表和节头一致；provider所有装载节逐字节相同，仅未装载的BTF不同。三个workload差别限于`freq1000`/`freq2500`构建路径字符串、调试信息及build-ID。完整ELF哈希因此不同；此检查不证明运行时装载地址或微架构状态相同。

## 全部三轮

吞吐单位Mops/s；spread为`(max−min)/median×100%`，最佳ns/op取最大吞吐的同一会话。ns/op是完整操作摊销时间。

| 频率限制 | 后端 | r0 / r1 / r2 Mops/s | min / median / max | spread % | 最佳同场ns/op |
| --- | --- | --- | --- | ---: | ---: |
| 1.0GHz | Linux Native | 17.248329 / 17.342402 / 16.961437 | 16.961437 / 17.248329 / 17.342402 | 2.21 | 57.66214 |
| 1.0GHz | TCLock | 13.907730 / 13.827225 / 13.863067 | 13.827225 / 13.863067 / 13.907730 | 0.58 | 71.90246 |
| 1.0GHz | KD adaptive | 12.422604 / 12.522265 / 12.420206 | 12.420206 / 12.422604 / 12.522265 | 0.82 | 79.85776 |
| 2.5GHz | Linux Native | 43.519472 / 44.064122 / 43.395470 | 43.395470 / 43.519472 / 44.064122 | 1.54 | 22.69420 |
| 2.5GHz | TCLock | 35.173889 / 35.128493 / 34.875724 | 34.875724 / 35.128493 / 35.173889 | 0.85 | 28.43018 |
| 2.5GHz | KD adaptive | 31.681683 / 31.568417 / 31.673585 | 31.568417 / 31.673585 / 31.681683 | 0.36 | 31.56398 |

| 后端 | 1.0GHz中位 Mops/s | 2.5GHz中位 Mops/s | 中位比值 |
| --- | ---: | ---: | ---: |
| Linux Native | 17.248329 | 43.519472 | 2.523× |
| TCLock | 13.863067 | 35.128493 | 2.534× |
| KD adaptive | 12.422604 | 31.673585 | 2.550× |

原始精度见[1.0GHz records](../../.tmp/single-frequency-20260924/guest/single-frequency-20260924/freq1000/records.json)、[summary](../../.tmp/single-frequency-20260924/guest/single-frequency-20260924/freq1000/summary.json)和[2.5GHz records](../../.tmp/single-frequency-20260924/guest/single-frequency-20260924/freq2500/records.json)、[summary](../../.tmp/single-frequency-20260924/guest/single-frequency-20260924/freq2500/summary.json)。

## 与昨天数字的关系及限制

[9月23日MCS8报告](20260923-mcs8-cpu4m.md)中c1/t1的KD adaptive三轮为12.737301/13.977076/13.398908Mops/s，observe为13.078414/12.609786/13.517476；“约13M”的记录确实存在。当天[宿主快照](../../.tmp/spin-single-hot-balance-20260923/current-host-cpu.json)记录powersave、1–3GHz限制及采集瞬间约1GHz，但不是那些计时区间的频率轨迹。本次相同当前源码的两档对照直接重现相近量级，支持频率设置是此前比较的重要混杂因素。

两阶段所有KD计时正文均为0，按单线程规则记NO_JIT；没有把普通原生完成称为代理收益。该试验只含c1单线程和KD adaptive，不覆盖c16、observe或其他线程数，也不证明原先“1/2/8/16/20线程不退化”的目标。阶段按1.0GHz后2.5GHz顺序运行，未随机交错；三轮范围仅描述本次波动，不是置信区间。它也不能将旧代码、旧预热方法、CPU放置和跨时段噪声的影响完全分离。

## 验证与归档

18/18场业务、IRQ/preempt、内核错误检查及排空通过；6场KD均为预期的零JIT。每阶段[归档审计](../../.tmp/single-frequency-20260924/archive-audit.json)核对259项源码、8项二进制及9项已发布JIT镜像；镜像存在不表示实际执行。[独立比较](../../.tmp/single-frequency-20260924/comparison.json)核对原始样本、预热和恢复设置，[结束状态](../../.tmp/single-frequency-20260924/guest-idle.json)确认guest空闲且仍运行原内核。审计是离线一致性验证，本轮未修改生产代码或追加单元/全量功能测试。

频率恢复分别见[1.0GHz阶段日志](../../.tmp/single-frequency-20260924/freq1000/frequency-restore.log)、[2.5GHz阶段日志](../../.tmp/single-frequency-20260924/freq2500/frequency-restore.log)及对应[1.0GHz恢复读回](../../.tmp/single-frequency-20260924/freq1000/host-cpufreq-restored.json)、[2.5GHz恢复读回](../../.tmp/single-frequency-20260924/freq2500/host-cpufreq-restored.json)。最终[完整证据包](../../.tmp/single-frequency-20260924-full.tar.gz)为5596224字节，SHA-256为`71dbc0adb31ced6a834245622647a0e970e13259453115398d2cc18abedeaeed`，见[收据](../../.tmp/single-frequency-20260924-full.tar.gz.receipt.json)。包内保留两个阶段的guest证据、宿主频率/命令及源码/机器码审计；报告在Git中独立保存，避免归档哈希自引用。

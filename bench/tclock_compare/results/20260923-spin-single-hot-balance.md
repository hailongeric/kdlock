# 2026-09-23：单线程与20线程性能调查及 batch 元数据优化

本轮确认当前20线程吞吐仍约4 Mops/s。简单 spin batch 调用元数据改为只初始化一次后，
c1/c16 observe 三轮中位数提高 **2.37%/2.11%**，最大值提高 **2.02%/0.24%**。
这是阶段性小幅改善，**尚未实现保留单线程收益并恢复历史约5.2/4.8 Mops/s的目标**。
此前时钟强制内联候选未带来一致改善，已撤回；后续优化仍在进行。

## 输入与比较口径

起点为 `6064c6e5d0dd9484e70c8d01a1da4e87ada6ce53` 加当时已有工作区修改，
不是该提交的纯净构建。冻结清单、初始差异和逐阶段源码/ELF分别保留；当前源码继续
变化，不能代替已测输入。保持 CPU 每次实际 MCS 发布采样、400亿TSC窗口、单锁
严格 `count > 32`，以及 CPU 热值 C `if`、完整冷 pending/MCS 和统一 generic unlock。

普通性能每线程100000次、每配置3轮；正式比较仍取有效最大吞吐及同场ns/op，同时
报告 min/median/max。基线和时钟内联各为 c1/c16 × t1/t20 × Linux/TCLock/KD
observe/KD adaptive，共48场。metadata 筛选只测 c1/c16 × t20 × Linux/TCLock/KD
observe，共18场，不能据此宣称该候选的单线程、adaptive或其他线程数性能已验证。

## 历史与新基线

历史恢复版两轮最大值为c1/c16单线程6.836/6.466、20线程5.197/4.809 Mops/s，
采用旧CPU1024/单锁1025采样。后来的MCS1/400亿窗口/lock32版本，单轮20线程也达到
5.011/4.802；所以不能仅因当前采样频率高，就断定它解释了全部退化。
分别见[历史恢复报告](20260922-performance-recovery.md)和
[MCS1/lock32报告](20260922-spin-mcs1-lock32.md)。

以下为历史20线程最大值及同期控制，全部为 Mops/s；样本轮次不同，归一化仍只是
跨批次线索，不是随机交错的单因素实验。

| 阶段 | 每配置轮数 | cacheline | Linux | TCLock | KD observe | KD/TCLock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 历史恢复 | 2 | 1 | 4.381 | 5.010 | 5.197 | 1.037× |
| 历史恢复 | 2 | 16 | 2.523 | 3.269 | 4.809 | 1.471× |
| 54753f0，保留壳off | 1 | 1 | 4.159 | 4.955 | 4.987 | 1.006× |
| 54753f0，保留壳off | 1 | 16 | 2.701 | 3.253 | 4.750 | 1.460× |
| a6ae430，保留壳off | 1 | 1 | 4.220 | 4.949 | 4.019 | 0.812× |
| a6ae430，保留壳off | 1 | 16 | 2.855 | 3.314 | 3.942 | 1.189× |
| 本轮基线 | 3 | 1 | 4.223 | 5.099 | 4.020 | 0.788× |
| 本轮基线 | 3 | 16 | 2.451 | 3.374 | 4.104 | 1.216× |

共同off路径在[共享cookie](20260922-spin-cpu-hot-cookie.md)到
[clobber/队列门槛](20260922-spin-cold-clobber-queue.md)阶段已下降。
同期TCLock基本稳定，KD/TCLock约下降19.3%/18.5%；这是定位区间，不能把其间所有
改动归为单一原因，也不能将此前on路径的损失和共同off路径的损失混为一项。

新基线单线程三轮如下，保留当前低线程收益与波动信息；本表不是metadata候选复测。

| cacheline | 实现 | min | median | max |
| --- | --- | ---: | ---: | ---: |
| 1 | Linux | 16.689 | 16.830 | 16.965 |
| 1 | TCLock | 13.532 | 13.628 | 14.689 |
| 1 | KD observe | 12.393 | 13.733 | 13.766 |
| 1 | KD adaptive | 13.484 | 13.943 | 14.099 |
| 16 | Linux | 12.689 | 12.857 | 13.181 |
| 16 | TCLock | 10.893 | 12.190 | 12.553 |
| 16 | KD observe | 10.510 | 11.130 | 11.283 |
| 16 | KD adaptive | 10.474 | 12.049 | 29.791 |

c16单线程adaptive最大样本29.791仍保留；中位数12.049，spread为160.32%，不能当作
稳定速度。spread定义为 `(max-min)/median*100`，三轮也不足以确认统计显著性。

## 已撤回：hotlock 时钟强制内联

只将私有 `kd_hotlock_clock` 改为 `__always_inline`，保持采样及热度规则。
48场完成后，20线程c1 observe/adaptive中位数仅变化+0.59%/+0.39%，c16为
−0.78%/−0.31%；单线程observe c1/c16为−9.11%/−5.69%。没有一致改善，已撤回。
较快的历史383249f也有相同的外置clock调用、输出地址和stack-canary形态；该形态
本身不能解释后续退化。失败候选源码、ELF及样本保留，不计为优化成果。

## 保留：简单 spin batch 元数据只初始化一次

`kd_exe_spin_batch_prepare` 原先先填legacy元数据，再调用通用clobber helper，
覆盖同一组字段并重新检查最小完成条件。现在在原有检查通过后按入口ABI写最终值。

| 阶段 | 修改前 | 修改后 |
| --- | --- | --- |
| 发布、镜像、ABI、packet及根请求检查 | 原有完整检查 | 相同检查 |
| legacy调用 | 写legacy偏移、raw unlock、complete=false | 相同最终值，一次初始化 |
| clobber调用 | 先写legacy值，再进入helper覆盖10个字段 | 直接写clobber偏移、clobber unlock及complete=true |
| 最小完成许可 | helper再次检查spin_simple、无parent、depth=0、非mutex | 前面的准入检查已证明相同条件；任一不成立即拒绝 |
| 计时、复杂请求及生命周期 | 两次计时起点；复杂路径用通用helper；原有发布/ACK/退休 | 保持不变 |

简单clobber路径省去10次重复字段写入、一次通用helper调用及其嵌套的许可helper调用。
实际ELF确认batch准备不再调用 `kd_jit_prepare_clobber`。该函数静态指令总数在已比较
ELF中为151→153，不能写成“整个函数变小”；减少的是正常路径实际执行的重复工作。
普通native快路径、JIT正文、锁协议及mutex/复杂调度没有借此跳过检查。

20线程三轮筛选结果如下。每个单元格为 min / median / max，单位 Mops/s。

| cacheline | 实现 | 新基线 | metadata一次初始化 | 中位数变化 | 最大值变化 |
| --- | --- | --- | --- | ---: | ---: |
| 1 | Linux | 4.1603 / 4.1934 / 4.2233 | 3.9696 / 4.0535 / 5.2898 | −3.34% | +25.25% |
| 1 | TCLock | 5.0474 / 5.0623 / 5.0986 | 4.9730 / 5.0034 / 5.0286 | −1.16% | −1.37% |
| 1 | KD observe | 3.9883 / 3.9981 / 4.0202 | 4.0406 / 4.0930 / 4.1013 | +2.37% | +2.02% |
| 16 | Linux | 2.3526 / 2.4061 / 2.4506 | 2.3522 / 2.4832 / 2.5992 | +3.20% | +6.06% |
| 16 | TCLock | 3.2760 / 3.3281 / 3.3741 | 3.1319 / 3.2544 / 3.2984 | −2.21% | −2.25% |
| 16 | KD observe | 3.9291 / 3.9469 / 4.1043 | 3.9918 / 4.0300 / 4.1142 | +2.11% | +0.24% |

18/18性能场次通过，6场KD均有实际JIT；对照也存在波动，特别是Linux c1最大值。
本轮只能记录小幅筛选改善，不能由三轮结果证明稳定收益或历史退化的根因。

## 因果边界与 PMU

较快54753f0 off到较慢a6ae430 off，c1/c16 JIT长度仍为942/1512字节，正常入口、
首条业务指令和分支位置相同；c16镜像仅嵌入unlock地址的两个字节不同。
已核对的per-CPU主体、continuation/node尺寸与对齐、diag waiter字段偏移也未改变。
20线程约99.8%业务由JIT执行，未发现足以解释退化的稳定批次崩塌。
这没有排除所有代码/缓存布局或每请求固定开销，等待函数占比高也不能定位开销来源。

旧报告2601–2609 instructions/op、12838–13013 cycles/op来自回退前慢版本PMU，
其KD实际约4.304/4.249 Mops/s；**恢复到5.197/4.809的版本没有匹配PMU**。
不能将旧PMU数字标为历史快版，再据此排除指令数、频率或等待差异。

本轮独立长PMU为每线程200万次、20线程、每配置3轮，共12场。
c1 TCLock/KD中位吞吐5.358/4.223，c16为3.430/4.119 Mops/s。
它与10万次短批次分开；所有worker累计计数含等待，不能把cycles/op当成单个
combiner临界区的独占周期。历史恢复后与当前的vCPU绑定、guest内核身份一致，
旧慢版及当前PMU有效频率约2.769GHz；缺少历史快版PMU与物理页/cache-to-cache
证据，仍不能给出微架构单因果结论。

## 验证与证据

- 最终基础及相关单元3组通过，生产entry fixture为3449次检查、0失败。batch fixture覆盖legacy/clobber、计时开关、完整
  元数据和根请求拒绝；新增3项错误变体，当前该测试共25项。最初两次失败暴露夹具
  缺失u8/u16类型及RESUME角色预期过时，已修正；结构体快照改用字节复制，保留全部
  memcmp和字段检查，未削弱生产发布或生命周期检查。
- metadata候选nested/early × observe/adaptive共4/4场通过，每场400000次业务；
  nested实际JIT为387241/389782次，early为99894/99870次（observe/adaptive）；
  IRQ/preempt、内核日志和排空检查通过。
- 未重跑全量单元、其他线程性能、RCUHT、mutex真实JIT、SELFTEST或IRQ/NMI压力。
  单线程和adaptive性能仍只有修改前基线及已撤回候选的本轮记录。

guest证据根目录：`/root/kdlock-evidence/spin-single-hot-balance-20260923/`。
宿主已归档到 `bench/.tmp/spin-single-hot-balance-20260923/`。
[本阶段完整归档](../../.tmp/spin-single-hot-balance-20260923/metadata-checkpoint.tar.gz)
SHA256：`0a38ca21ac93d5092116ee9247101e614e8ececb8e15c2f73f3aaab7e34506fa`。
[宿主离线审计](../../.tmp/spin-single-hot-balance-20260923/offline-audit-metadata.json)
单独记录会话结果、冻结源码及ELF哈希核对。
普通运行器命令的公共参数为 `--cachelines 1 16 --threads 1 20 --repeats 3
--iterations 100000 --hotlock-mode observe adaptive`；筛选覆盖为20线程observe。
实际每阶段argv、退出码、源码/ELF、session原始结果与环境均以归档为准。

- [新基线](../../.tmp/spin-single-hot-balance-20260923/baseline/summary.json)、
  [已撤回clock-inline](../../.tmp/spin-single-hot-balance-20260923/clock-inline/summary.json)、
  [metadata筛选](../../.tmp/spin-single-hot-balance-20260923/metadata-once-screen/summary.json)。
- [独立长PMU](../../.tmp/spin-single-hot-balance-20260923/baseline-pmu-ready/summary.json)；
  初次PMU因PATH中缺少perf而失败，单独保留在 `baseline-pmu/`，不计为通过。
- 最终单元日志 `metadata-once-unit-final.log`；功能目录 `metadata-once-nested/`、
  `metadata-once-early/`；两次早期单元失败日志保留，不计为通过。

原始证据在忽略目录，新checkout不自带产物。本报告记录当前已完成的阶段，后续
较大候选必须单独标识输入和成绩，不把正在进行的恢复目标写成已完成。

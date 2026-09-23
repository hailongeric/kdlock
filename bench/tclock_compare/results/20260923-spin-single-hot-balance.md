# 2026-09-23：单线程与20线程性能调查及 continuation 布局优化

本轮未优化基线的20线程吞吐约4 Mops/s。简单 spin batch 调用元数据改为只初始化一次后，
c1/c16 observe 三轮中位数提高 **2.37%/2.11%**，最大值提高 **2.02%/0.24%**。
这项修改已在 `1eaaf99` 独立提交。随后continuation存储错位布局通过完整48场性能及
nested/early双模式4场验证。20线程observe中位数为 **5.299/5.146 Mops/s**，
adaptive为 **5.282/5.131**，均高于历史参照。**单线程中位数仍比本轮新基线低约
5%–6%；后续单线程长批次对照未复现这一持续降幅，四组中位差为+1.75%、−0.10%、
−0.39%、−0.33%。** 高竞争恢复已验证；单线程保留相对旧恢复版约1.9倍的短批次最大值，
但不把它写成相对本轮新基线全面无退化，也不由三轮长测宣称统计等价。
observe的20线程最大值5.447/5.158，相对旧恢复版两轮最大值5.197/4.809提高4.81%/7.26%；
这是不同批次、不同轮次的历史比较，当前三轮范围见下表。
此前时钟强制内联候选未带来一致改善，已撤回。

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
[MCS1/lock32报告](HISTORY.md#20260922-spin-mcs1-lock32)。

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

共同off路径在[共享cookie](HISTORY.md#20260922-spin-cpu-hot-cookie)到
[clobber/队列门槛](HISTORY.md#20260922-spin-cold-clobber-queue)阶段已下降。
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

## 后续候选：continuation 存储错位布局

保留已验证的metadata修改，仅在provider初始化时为每CPU的continuation栈选择不同
偏移。此前每份20 KiB的页对齐分配都从同一页内偏移放置根请求；combiner访问多个
CPU的请求时，它们的同名字段容易落到相同L1组。本候选意图分散这类地址冲突，
不增加请求期指令、内存分配或寄存器包复制；没有改变冷/热获取、MCS采样或JIT正文。

当前栈对象8512字节，低12 KiB内还可选择60个64字节对齐的位置，偏移公式为
`((cpu * 13) % 60) * 64`，最大3776字节；位置数量由实际对象大小推导。
12条记录始终完整位于低12 KiB内，高8 KiB等待栈与其栈顶不变。释放及局部初始化
失败时从 `wait_stack_top - KD_SPIN_STORAGE_BYTES` 找回原始分配基址，不能将
错位后的内部指针传给vfree。已有reserve、完成发布、ACK和退休顺序保持不变。
布局与边界见[共享存储](../../../docs/design/frames.md#911-reuse-before-copy-contract)。

20线程observe筛选18/18场通过，6场KD均有实际JIT。以下与紧邻的metadata筛选比较；
三轮全部保留，单位 Mops/s，变化按未舍入数据计算。

| cacheline | 实现 | min | median | max | spread | 中位数较metadata |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Linux | 3.9333 | 4.1101 | 4.3572 | 10.31% | +1.40% |
| 1 | TCLock | 5.0193 | 5.0216 | 5.0719 | 1.05% | +0.36% |
| 1 | KD observe | 5.2712 | 5.2874 | 5.3320 | 1.15% | +29.18% |
| 16 | Linux | 2.3763 | 2.4200 | 2.6203 | 10.08% | −2.55% |
| 16 | TCLock | 3.2700 | 3.2916 | 3.2923 | 0.68% | +1.14% |
| 16 | KD observe | 5.0381 | 5.0851 | 5.1316 | 1.84% | +26.18% |

KD最大值分别较metadata提高30.01%/24.73%，三轮最小值也高于旧恢复版的两轮最大值
5.197/4.809。同期TCLock中位数只变化+0.36%/+1.14%，支持改善主要发生在KD路径。
这仍是跨批次筛选；尚未测L1替换或cache-to-cache事件，不能把收益直接证明为某一
硬件事件，更不能据此确定此前退化由哪个源码改动首次引入。

独立DWARF/地址几何核对保持记录704字节、栈8512字节。按本机L1D的64组、8路、
64字节cacheline，建模CPU0..19每个根请求常触及的6条cacheline，共120条：

| 地址布局模型 | 使用组数 | 单组最多映射行数 |
| --- | ---: | ---: |
| 原始相同页内偏移 | 6 | 20 |
| CPU×13模60错位 | 63 | 3 |

这是潜在组需求模型，不是同时驻留数量或实测miss率；其他热数据、L2/LLC不在模型内。
历史较快版本也使用原始未错位布局，所以当前改善不能倒推出历史退化的唯一原因。
实际ELF中325个函数有323个归一化指令序列相同，只有初始化/释放改变；没有新增
请求期指令。不过释放函数缩短53字节，部分spin代码地址移动−48字节，generic
unlock移动+16字节。归一化忽略了数值分支目标和对齐NOP，因此这并非纯数据地址
隔离实验：存储放置与代码对齐都可能参与收益，贡献尚未分别证明。

随后完整 c1/c16 × t1/t20 × Linux/TCLock/KD observe/adaptive × 3轮矩阵
**48/48通过**；12场20线程KD全部实际JIT，12场单线程KD均为零JIT。以下单位为Mops/s，
变化列对比本轮最初新基线的同模式中位数，而不是选择历史较低的单线程样本。

| cacheline | 线程 | 实现 | min | median | max | 中位数较新基线 |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 1 | Linux | 16.7199 | 16.8585 | 17.2282 | +0.17% |
| 1 | 1 | TCLock | 13.6174 | 13.6736 | 13.8363 | +0.34% |
| 1 | 1 | KD observe | 12.8612 | 12.9789 | 13.1310 | −5.49% |
| 1 | 1 | KD adaptive | 12.5220 | 13.1233 | 13.9616 | −5.88% |
| 1 | 20 | Linux | 4.0482 | 4.1685 | 4.1781 | −0.59% |
| 1 | 20 | TCLock | 5.0010 | 5.0208 | 5.0284 | −0.82% |
| 1 | 20 | KD observe | 5.2770 | 5.2986 | 5.4471 | +32.53% |
| 1 | 20 | KD adaptive | 5.2784 | 5.2821 | 5.3668 | +32.05% |
| 16 | 1 | Linux | 12.7482 | 12.8451 | 13.6054 | −0.09% |
| 16 | 1 | TCLock | 10.8667 | 11.0571 | 11.6137 | −9.29% |
| 16 | 1 | KD observe | 10.3500 | 10.5243 | 12.3477 | −5.45% |
| 16 | 1 | KD adaptive | 11.1045 | 11.2754 | 11.8624 | −6.42% |
| 16 | 20 | Linux | 2.4943 | 2.5034 | 2.5342 | +4.04% |
| 16 | 20 | TCLock | 3.3286 | 3.3413 | 3.4124 | +0.40% |
| 16 | 20 | KD observe | 5.0835 | 5.1461 | 5.1582 | +30.38% |
| 16 | 20 | KD adaptive | 5.0888 | 5.1313 | 5.2159 | +30.77% |

单线程observe最大值13.131/12.348约为旧恢复版本6.836/6.466的1.92/1.91倍，
但不能用这一历史比较掩盖新基线中位数的下降。随后单线程长PMU每线程1000万次、
每配置3轮，错位/未错位各12场，**24/24通过**。对照保留metadata修改，仅恢复原始
continuation初始化/释放实现；这不是旧KD正式成绩臂。单位 Mops/s：

| cacheline | 模式 | 未错位 min / median / max | 错位 min / median / max | 中位数变化 |
| --- | --- | --- | --- | ---: |
| 1 | observe | 36.1525 / 36.4298 / 36.5179 | 36.2900 / 37.0677 / 37.7412 | +1.75% |
| 1 | adaptive | 36.3624 / 36.5300 / 37.2122 | 36.2188 / 36.4929 / 36.5116 | −0.10% |
| 16 | observe | 30.5371 / 30.6012 / 31.1556 | 30.4547 / 30.4825 / 30.5293 | −0.39% |
| 16 | adaptive | 30.2144 / 30.6240 / 30.7015 | 30.2618 / 30.5216 / 30.8896 | −0.33% |

长对照未呈现一致5%–6%下降；其余三组中位差在约0.4%以内，但三轮并不能证明
统计等价。测量长度及PMU开销不同，长测不能混入正式短矩阵取优或覆盖短测负值。
上述控制还包含初始化/释放引起的代码地址变化，不声称只隔离了数据布局。

新存储fixture及基础单元3/3通过、3项错误变体检出：覆盖121个CPU的全部12条记录、
122个分配失败点、完整等待栈及原始基址释放。初次fixture缺少u32 typedef而编译失败，
补充类型后通过；最终日志 `continuation-skew-unit-fixed.log`，原失败日志保留。
nested/early双模式4/4场通过，每场400000次操作，均实际JIT并排空；nested正文为
394200/395926次，early为99956/99924次（observe/adaptive），IRQ/preempt及上下文检查通过。

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

全调查各阶段共224场计时会话、946400000次操作。最终离线审计通过，3012份冻结源码
副本、80份二进制副本和366份JIT图像哈希全部匹配，错误列表为空。这个总数包含基线、
撤回候选、功能及独立长PMU，不能当作224份同一版本的性能样本；各阶段比较保持分开。

- metadata阶段基础及相关单元3组通过，生产entry fixture为3449次检查、0失败。batch fixture覆盖legacy/clobber、计时开关、完整
  元数据和根请求拒绝；新增3项错误变体，当前该测试共25项。最初两次失败暴露夹具
  缺失u8/u16类型及RESUME角色预期过时，已修正；结构体快照改用字节复制，保留全部
  memcmp和字段检查，未削弱生产发布或生命周期检查。
- metadata候选nested/early × observe/adaptive共4/4场通过，每场400000次业务；
  nested实际JIT为387241/389782次，early为99894/99870次（observe/adaptive）；
  IRQ/preempt、内核日志和排空检查通过。
- 未重跑全量单元、其他线程性能、RCUHT、mutex真实JIT、SELFTEST或IRQ/NMI压力。
  metadata独立候选未测单线程及adaptive性能；后续错位布局已完成上述48场短矩阵，
  并完成24场单线程长批次组件对照，两个批次保持不同统计口径。

长对照结束后恢复最终错位候选。两次重建哈希检查因`.BTF`元数据不同而未通过，
逐ELF节核对显示Build ID及其他节相同；保留失败核对记录，最终恢复实际完成48场
测试的原始provider产物，SHA256为
`8fb5952ea37e6c6cfefd9b6412b6152b380c3c497d00d289e2321d3e5642abf1`。
最终运行源码及全部binary manifest哈希与 `continuation-skew-final` 匹配，guest已排空。
这两次为收尾重建产物核对失败，不计为性能或功能用例失败，也不将未匹配产物冒充已测版本。

guest证据根目录：`/root/kdlock-evidence/spin-single-hot-balance-20260923/`。
宿主已归档到 `bench/.tmp/spin-single-hot-balance-20260923/`。
[最终完整归档](../../.tmp/spin-single-hot-balance-20260923/final.tar.gz)
SHA256：`0d0e97fb8f47329da795f89d404b557c951be3c017ccf9c7061de871d727aad5`。
[最终离线审计](../../.tmp/spin-single-hot-balance-20260923/offline-audit-final.json)
核对各阶段样本、冻结输入及产物；
[metadata阶段归档](../../.tmp/spin-single-hot-balance-20260923/metadata-checkpoint.tar.gz)
SHA256：`0a38ca21ac93d5092116ee9247101e614e8ececb8e15c2f73f3aaab7e34506fa`。
[metadata离线审计](../../.tmp/spin-single-hot-balance-20260923/offline-audit-metadata.json)
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
- [错位筛选](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-screen/summary.json)、
  [最终48场](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-final/summary.json)、
  [nested](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-nested/functional.json)、
  [early](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-early/functional.json)。
- [错位单线程长对照](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-single-long/summary.json)、
  [原布局单线程长对照](../../.tmp/spin-single-hot-balance-20260923/continuation-unskew-single-long/summary.json)。
- [几何核对](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-geometry.md)、
  [ELF指令/地址比较](../../.tmp/spin-single-hot-balance-20260923/continuation-skew-elf-comparison.md)、
  [最终恢复身份](../../.tmp/spin-single-hot-balance-20260923/final-restored-identity.json)。
- 最终unit输入保存在 `unit-source/`，已提交metadata差异为 `metadata-commit.patch`，
  布局修改为 `continuation-skew.patch`；存储单元日志 `continuation-skew-unit-fixed.log`。

原始证据在忽略目录，新checkout不自带产物。各阶段单独标识输入与成绩；未覆盖配置、
单线程短测下降及尚未隔离的微架构原因保留为本次结论的边界。

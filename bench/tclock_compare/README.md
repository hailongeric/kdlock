# Linux / TCLock / kdlock 直接 API benchmark

当前入口使用同一份 `workload_modules/spin_cacheline` 正文，分别构建Linux原生、TCLock、
当前KD三个后端；KD仅保留adaptive自适应准入。
最新结果与历史参照见[本次结果](#本次结果)，构建及运行环境遵循[操作手册](../../docs/AGENTS.md)。

| 后端 | 直接调用 |
| --- | --- |
| Linux | `__raw_spin_lock/unlock`，绕过实验内核hook |
| TCLock | `komb_spin_lock/unlock`，调用者配对管理抢占 |
| kdlock | `KD_SPIN_DIRECT_LOCK/UNLOCK`，CPU热值分流获取，统一generic clobber解锁 |

KD冷获取内联首次CAS，竞争时使用原生pending/MCS队列；热获取使用pinned clobber入口，
解锁统一走generic clobber协议。三个后端均保留各自必需的抢占配对，普通spin不额外关闭IRQ。
自适应策略及寄存器契约分别见[执行流](../../docs/JIT_EXECUTION.md#21-热度与角色)和
[锁协议](../../docs/design/locking.md)。

普通 mutex 使用独立入口 `run_mutex.py` 和 `workload_modules/mutex_cacheline`，
编译出 `mc_body_N`，复用 payload、计时与结果校验；单次操作中没有 `is_mutex` 分支。
Linux 调用原始 `mutex_lock/unlock`，KD 调用 `KD_MUTEX_DIRECT_LOCK/UNLOCK`（ABI2），
TCLock 调用实际上游 `komb_mutex_lock/unlock`。KD global interception 继续关闭。
TCLock worker 注册和整组排空见[端口边界](../../tclock_backend/README.md#普通-mutex-独立端口)。
mutex 的 `lock_kind` 纳入汇总身份；TCLock 保留委托次数证据，KD 继续要求返回正文 JIT witness。
先验证 cacheline 基线和各独立优化，再使用同一入口的 `--workload rcuht`。
原 spin/hash 入口及成绩不作为 mutex 成绩。

默认任一失败停止。仅在收集完整性能证据时可显式加 `--keep-going-no-jit`：
它只跨过业务正确、已经排空且无 cleanup error 的 `NO_JIT`；保持该失败状态、
排除其吞吐评分，最终返回非零并列出失败场次。其他失败仍立即停止，功能模式拒绝此选项。
它不强制代理、不更改预热/门槛，也不把原生回退当成竞争 JIT 验收通过。

当前只支持adaptive，策略标识为`mcs_reset1024_shift10_lock512_head6`，默认`spin_entry_ratio_limit=2`。
每1024次MCS发布比较`(entries >> 10) < 2`，随后清零本CPU的入口和MCS计数；
默认接受该窗口内至多2047次入口，约为MCS比例超过一半，不再使用旧100%门槛或前次计数快照。
单锁热度仍独立每512次记录检查；CPU采样间隔与入口右移位数是分别配置的编译期常量。
门槛0只绕过比例，原生队头前缀、CPU/单锁热度和执行安全检查仍有效。
旧模式、策略和测量口径仅通过[历史索引](results/HISTORY.md)追溯，不合并取优。
诊断per-CPU计数、最终余额及布局见[provider说明](../../kernel_module/README.md)。

三种后端保留相同cacheline更新、解锁后四组乘加及循环成本；吞吐和ns/op以完整操作计算，
不是独立获取锁延迟。三种模块不是同一二进制，必需的现场成本不扣除。
`--pmu`只在独立长批次对measure客户端和worker执行perf stat，输出instructions、cycles、
task-clock、context-switches、cpu-migrations；累计计数包含所有worker等待，不等同于lock/unlock正文成本。

## 准备与运行

性能测试对象固定为 Linux 原生、TCLock 和当前 kdlock，运行器默认即为
`--backends native tclock kdlock`。功能检查按需要单独选择KD；旧版对照仅保留冻结证据。

后端先加载，直接依赖它的样例后加载。运行器在没有 worker 时绑定只读观测
使用的锁地址，再调用 `SC_PREPARE` 显式登记选定正文的锁后 RIP 和 KD 对象。
kdlock 等唯一条目发布为 NORMAL、翻译进程退出并停止 daemon 后，再使用与正式测量
相同的worker数量和CPU集合预热，每个worker执行48000次；所有后端采用相同规则。
登记准备命令仍单线程执行，继承runner允许的CPU集合。预热与测量通过独立客户端调用分别创建
worker，复用相同的数量及CPU绑定配置；预热worker退出并完成正常检查后接着发起测量，
不再插入额外2秒等待，以免预热建立的热度在间隔中失效。记录保存
`warmup_policy=all_workers`、`warmup_iterations_per_worker=48000`、`warmup_pause_seconds=0`。
准备与预热均不计入正式测量。每个KD会话重新加载provider，热度不跨会话继承。

CLI支持`--cachelines 1 8 16`和`--threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36`。
无参数矩阵仍为1/16 cacheline × 1/4/8/16/20线程 × 三后端 × 三轮，共90场；
默认`--duration-ms 0`按每worker 100000次固定迭代测量。
下面的当前峰值命令显式选择1 cacheline及十五个线程点，共135场。

性能比较使用固定2.5GHz。

宿主worker CPU0..35及collector CPU38已设置并核对min=max=2500000kHz；保留`intel_pstate`、
`powersave`与`balance_performance`，通过相同上下限限制频率。
后续benchmark使用并保留该固定频率政策，不自动恢复动态1–3GHz；运行前后记录并核对设置，
重启后若设置丢失则重新应用。此设置未配置为系统开机持久化。
历史动态/固定频率成绩保持各自原标注，不混合统计。
当前稳态峰值口径：连续测量2秒，取其中最高300ms窗口，同时保留整段吞吐。
使用`--duration-ms 2000 --peak-window-ms 300`启用；原固定迭代模式仍保留，不能与新口径混合取优。
三方都先完成上述全worker预热，测量前300ms作为额外稳定时间，不进入峰值候选。
每个worker在完整正文及解锁后工作完成后，每256次发布一次独立进度并检查共同截止时间；
CPU38上的collector每10ms读取进度，原始快照及其读前/读后时间戳全部保留。
只有全部worker已经进入且尚未退出的窗口参与选择；时长取实际端点间隔（至少300ms），
不插值，也不使用固定300ms除数掩盖采样延迟。窗口计数误差上界为256×线程数，
快照读取时间跨度另行报告。采样有均摊成本，三方采用相同规则；不能把口径变化记作锁优化收益。
整段吞吐使用精确完成数及全部worker返回时间，包含截止检查/排空尾部；JIT比例也只针对整段，
不声称知道峰值窗口内的JIT比例。CPU38为额外观测CPU，不计入工作线程；runner的准备CPU集合不变。
只在 recovery guest 中按[操作手册](../../docs/AGENTS.md)核对快照、依赖和空闲状态；
现有 `kdclobber2` 内核不重建。输出必须是新的仓库外目录。

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 2600s taskset -c 0-35 \
  python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --cachelines 1 --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 --repeats 3 \
  --duration-ms 2000 --peak-window-ms 300 --collector-cpu 38 \
  --output /root/kdlock-evidence/direct-new
```

`--numa`默认on；KD支持on/off。TCLock当前上游头文件固定启用NUMA，因此off诊断须用
`--backends kdlock --numa off`；包含TCLock的off请求会被编译身份核验拒绝。
`--kd-batch-size`默认为1024，范围1–1024。
KD每batch最多代理1024个正文，独立NUMA扫描预算同样初始化为1024；两者分别消耗。
TCLock保留上游配置值1024。运行器用`modinfo`验证实际ELF，NUMA/批上限纳入结果身份，不混合候选。
`--spin-prefetch 0/1/2`选择现有KD无预取/consumer查找/producer提示，默认2，加载后核对并独立分组。
collector CLI无参数默认仍为30，32/36-worker运行必须如上显式指定38；与任一worker重合时拒绝。

`--kd-provider-ubsan kernel/off`仅控制本次benchmark的私有KD provider副本，spin/mutex均默认`off`，
向该副本的递归make传入`UBSAN_SANITIZE=n`，与当前关闭UBSAN的TCLock backend比较。
显式`kernel`继承现有内核构建配置；普通provider的Makefile、内核配置及显式协议检查保持原设置。
每次provider构建重新创建副本，运行器将`nm -u`保存为`imports-kdlock-provider.txt`，
另存`kdlock-provider-ubsan.json`记录所选政策及实际handler引用；`off`仍有引用时立即拒绝运行。
`plan.json`、各`session.json`、`environment.json`及汇总均保存`kd_provider_ubsan`；
`kernel`、`off`和没有记录该字段的历史样本分组独立，不混合取优。
比较此选项时保留相同源码与其他参数；编译插桩变化单独报告，不记作锁协议优化收益。

2026-09-28默认off调整的guest验证：两个基础C程序及44项运行器检查通过；省略该选项的
36线程hash功能场完成360万次操作、3595136次返回正文JIT，provider的UBSAN引用为空，
业务与排空通过。本次未测性能。证据位于guest `/root/kdlock-evidence/ubsan-default-20260928.tar.gz`
及host `bench/.tmp/ubsan-default-20260928/evidence.tar.gz`，SHA256为
`af5a236fafe91864de89b308c4eb2a70319bf55d0f895ead2f8d644463e292b3`。

`--spin-entry-ratio-limit`接受0或uint32范围内不小于2的2次幂，默认2。
非零值是`entries >> 10`的严格上界；值越大，允许的入口/MCS比例越大。
0仅绕过比例门槛，原生队头前缀检查、CPU频率和单锁热度规则仍生效。
该值作为只读provider装载参数传入并核对；旧`--spin-contention-pct`已删除，历史命令使用匹配checkout。

上述`taskset -c 0-35`固定准备阶段CPU集合（跨两个节点），默认worker绑定CPU0至CPU(`threads-1`)。
`--cpus`指定有序CPU列表，各线程点取对应长度的前缀；不足、重复、离线或不在runner亲和集合内的CPU会被拒绝。
16线程同节点使用`--cpus 0-15`，8+8使用`--cpus 0-7,20-27`；
20线程同节点使用`--cpus 0-19`，10+10使用`--cpus 0-9,20-29`。
这些节点名称须由实际拓扑核验；36线程保留`--cpus 0-35`。
collector不得与实际worker重合，汇总及Linux分母按CPU列表分别分组，不能把同/跨节点样本合并取优。
先核对这些CPU属于预期NUMA节点及host映射；`environment.json`保存`runner_affinity`，
加载前检查全部worker CPU均被允许。collector使用独立CPU38，不计入worker线程数。

代码修改后可直接测性能，运行器同时完成业务、IRQ/preempt、JIT和排空检查。
独立单元、SELFTEST及`--functional`按改动选择；需要定向检查时缩小线程/正文范围。
`--dry-run`只打印矩阵；`STOP`文件在已排空会话之间生效。失败或超时保留证据并停止。
功能或固定迭代诊断不用峰值参数，不能与连续计时结果混合取优。

构建通过后端 `Module.symvers` 解析导出符号，保存三个样例的反汇编与未定义符号，
检查目标锁不再导入统一 spin hook。原生组不加载任何锁 provider。
`allocator_guard/` 仍是三组共有、计时外的 per-CPU 分配器 hint 准备，详见历史记录。

## 功能检查

`--functional` 使用同一正文、业务数据、IRQ/preempt 与排空检查，但仅输出
`functional.json`，不生成吞吐/延迟汇总或后端比较。要求显式选择 KD 和单次重复；
原始运行日志仍保留诊断时间戳。每个场景使用新输出目录：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 180 python3 bench/tclock_compare/run.py \
  --functional --backends kdlock --cachelines 1 --threads 20 --repeats 1 \
  --iterations 100000 --scenario nested --spin-entry-ratio-limit 0 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/continuation-nested-new
```

按改动选择`plain`、`nested`或`early`；`--spin-delegate off`单独验证原生对照，要求零
JIT，并标记 `DISABLED_CONTROL`。当前 continuation 功能证据与未覆盖边界见
[测试入口](../../tests/README.md)。
协议JIT正例可使用`--spin-entry-ratio-limit 0`：nested中的无竞争内层获取也进入入口计数，
默认比例门槛可能合法选择原生。示例使用20个worker为队列前缀留下余量，不把worker数量当作准入保证。
门槛0仅关闭比例过滤，原生队头检查、CPU频率、单锁热度及安全准入仍启用，不能保证正文执行；
所有多线程功能正例均要求非零实际JIT，并保留上下文、业务和排空检查；NO_JIT仍是功能失败。
移除observe后的功能通过只以新冻结记录为准，不能沿用历史双模式通过数。

## 验收与结果

默认每配置三轮，用于观察性能波动；明确选择单轮时使用`--repeats 1`并报告样本限制。
`summary.csv/json` 用 `best_throughput_ops_s`、`best_amortized_ns_op` 报告同一
获选会话的吞吐与摊销时间，`best_session` 指向原始会话，
`comparison_policy=best_valid_throughput` 标明口径，继续从有效样本选取最大吞吐。
计时模式改用`comparison_policy=best_valid_warmed_peak`，上述主字段为获选300ms峰值；
同一获选会话的整段值另存`best_whole_throughput_ops_s`和`best_whole_amortized_ns_op`，
`best_peak`保留原始快照索引、实际跨度、逐worker差值和误差界。
本次连续计时基线及后续优化见[300ms稳态峰值调查](results/20260924-warmed-peak.md)。
另以 `min_throughput_ops_s`、`median_throughput_ops_s`、`max_throughput_ops_s`
报告有效吞吐的最小值、中位数、最大值；`throughput_spread_pct` 为
`(最大值 - 最小值) / 中位数 × 100%`，便于直接查看三轮离散程度。
中位数用于描述波动，不改变上述后端比值口径。相对 Linux 的比值使用各后端获选值
除以 Linux 获选值，KD/TCLock 同理；保留有效样本数，报告须说明不足三轮的情况。
`records.json` 保留全部计划项、原始测量及失败/未执行状态；只有数据
正确、完成且已排空的样本参与汇总。KD保留固定`hotlock_mode=adaptive`元数据，按该字段、`caller_shell`、
`cookie_storage`、`cpu_heat_policy`、`spin_entry_ratio_limit`分开汇总；旧记录的`spin_contention_pct`
仍是独立分组字段，不将百分比解释成新上界，也不跨模式、cookie存储、采样策略或比例门槛取最大值；
当前直接标量使用`cookie_storage=percpu_direct_gate`，历史间接读取为`percpu_rate_hot`。
热表计数保留在原始日志，不参与性能评分；卸载时的入口/MCS计数是当前未完成采样窗口的余量，
不是整场累计总数。

kdlock 保留最小 JIT 完成计数作实际执行验收；TCLock 按用户要求删除额外执行计数，
代理次数与比例记为 null、状态为 `UNMEASURED`，不把未知写成零或实际代理通过。
每场检查数据、批次 IRQ/preempt 状态和排空；源文件、二进制、内核身份、生成物和
日志均冻结保存。JIT 计时与逐次日志关闭，kdlock 的执行计数仍有成本。

清理顺序：worker 全部退出 → 核对队列/frame/锁字 → 停止翻译进程 → kdlock
retirement 成功 → 卸载样例 → 卸载后端。TCLock 在样例存储释放前清除诊断锁指针。
不强制卸载，不在同一目标锁上混用 Linux 与 TCLock 协议。

基础及相关检查：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_direct.py codegen/test_clobber_abi.py admission/test_clobber_entry.py spin/test_tclock_context.py execution/test_exe_registry.py spin/test_spin_outer_progress.py'
python3 bench/tclock_compare/test_direct.py
```

## 本次结果

| 报告 | 范围与用途 |
| --- | --- |
| [寄存器包与continuation重排](results/20260928-packed-continuation.md) | RIP/RSP/RBP及核心状态共一行，MINIMAL三条frame/包提示；141场定向性能、7场功能及owner ACK；36线程hash复测2.018/2.641 Mops/s，较基线下降约2%，未达到90%目标 |
| [36线程 spin 性能与原因分析](results/20260928-spin36-analysis.md) | 新测 hash KD/TCLock 1.985/2.648 Mops/s，单 cacheline 为 8.665/5.952；75 场性能/诊断、生成代码、PMU、固定人数 NUMA 与 UBSAN 对照 |
| [NUMA 与 mutex 分阶段优化](results/20260928-numa-mutex.md) | 显式放置、PMU 与 spin 优化；真正三方 mutex、逐项候选筛选、cacheline 135 场通过；hash 129/135 通过及 6 场 NO_JIT、最终 spin 回归和剩余差距 |
| [36线程hash采样与批次调优](results/20260927-hash36-profile.md) | 默认上限1024，hash36峰值较前检查点提高6.98%；flat-IP采样、配置消融、无收益JIT候选撤回，少线程及NUMA进度限制单列 |
| [有界refill与hash复验](results/20260927-spin-refill.md) | 批尾空链接最多PAUSE/重读8次，已有远端队列直接交接；最终hash63场+c1定向27场，恢复c1八线程短批回退，保留512上限 |
| [hash跨层内联与解锁优化](results/20260927-hash-runtime.md) | 默认kernel/512完整135场；相同默认配置16/36线程峰值较前版提高12.47%/6.26%，仍低于TCLock；显式配置与c1回归单列 |
| [hash_payload优化](results/20260927-hash-optimization.md) | JIT/预取/helper精简，分离UBSAN与批上限；显式off/1024完整135场，8/16/36线程约为TCLock的71%/72%/71%，默认配置与功能回归见报告 |
| [hash_payload计时比较](results/20260927-hash-peak.md) | 新增hash连续计时；15线程点三方三轮135场通过，KD在3–5线程领先两方、6–36线程低于TCLock；锁实现未变 |
| [spin阶段收尾复测](results/20260927-spin-checkpoint.md) | 当前实现135场三方c1矩阵；8–36线程KD峰值均高于TCLock，Linux跨node高值再次出现；保留全部分布、JIT及NUMA进度，作为转入mutex前的基线 |
| [热度阈值替代队列检查实验](results/20260927-heat-thresholds.md) | 五候选111场KD定向比较；纯热度、短批反馈和时钟下限均存在回退，全部撤回，默认仍保留六后继准入 |
| [MCS1024窗口调优](results/20260927-ratio-window.md) | 144场定向比较及最终15线程点三方135场；8–36线程峰值高于TCLock，3线程较前次下降；完整分布、历史参照和实际JIT分别保留 |
| [全链路复查与重复操作精简](results/20260927-followup.md) | callee SP、prefetch、队列检查、诊断读取及dispatcher fence精简；定向18场与最终135场，完整分布/worker进度及静态指令证据，无整体吞吐提升声明 |
| [全链路访存与JIT优化](results/20260927-flow.md) | continuation缓存行、RIP地址折叠、解锁布局及无锁ticket元数据；分阶段诊断、15线程点三方135场及native借用验证 |
| [spin清理与定向验证](results/20260926-cleanup.md) | 9线程点三方81场、36线程nested/early、生成代码审查；非完整矩阵或新吞吐收益声明 |
| [最新c1复测至36线程](results/20260926-c1-through36.md) | aef982b、十五线程点三方135场；三轮峰值、整段、节点进度及Linux跨node波动，锁实现未变 |
| [c1跨node有界批次优化](results/20260926-cross-node.md) | 08497ab、512上限，完整126场及32线程功能；三轮分布、峰值/整段、节点进度与候选回退 |
| [前版c1预取/诊断/CPU热值优化](results/20260926-prefetch-unlock.md) | 77eb9a2、十四线程点三方126场及匹配32线程功能；全部分布、峰值/整段与候选回退 |
| [前版c1 NUMA-on优化](results/20260926-numa-followup.md) | d439df8、十四线程点三方126场及匹配32线程功能；保留改动、短批回退诊断和全部三轮分布 |
| [首轮c1 NUMA与有界批次](results/20260926-numa.md) | NUMA/256上限完整126场、32线程功能验证、冗余状态精简及撤回的更早预取候选 |
| [1/8 cacheline复测](results/20260925-c1-c8-warmed-peak.md) | 前版锁实现，七个线程点、三后端三轮126场；300ms峰值、整段吞吐和全部分布 |
| [c1优化与十种线程数比较](results/20260924-warmed-peak.md) | 90场匹配矩阵、nested/early实际JIT；保留改动、撤回候选和归档哈希 |
| [历史索引](results/HISTORY.md) | 旧策略、动态频率和固定迭代报告的固定Git原文；不代表当前成绩 |

原始归档位于本地`bench/.tmp/`或guest `/root/kdlock-evidence/`，不随新checkout分发。
报告里的已测、失败、未执行及未覆盖范围保持分开。

## 当前 TCLock 设置

采用 Linux 6.1 移植版和上游 C 内联换栈，保留 NUMA_AWARE、WWJUMP 与 1024
批次配置值；其WWJUMP计数从0开始、跳转时递增，普通路径最多可执行1025个正文，
不同于KD的精确正文上限。未添加运行期代理次数计数。关闭 `ENABLE_IRQS_CHECK`、TCLock 后端
及三种 direct workload 的 UBSAN 插桩；内核内部 UBSAN 保持原配置，KD私有benchmark provider默认关闭UBSAN，
显式`--kd-provider-ubsan kernel`可继承内核配置。
运行器检查TCLock/workload实际 ELF、返回布局及无 UBSAN handler 引用；KD按所选政策核对并记录，
保留 IRQ/preempt 退出检查。
TCLock 不以 `need_resched()` 截断批次。这些实验设置限于 IRQ 开启的 task 上下文
负载，不等同于完整上游配置或论文环境，旧批长/代理比例不能作为当前观测。

## 可选 RCUHT 负载

`--workload rcuht` 使用上游 RCUHT 的单全局锁哈希表写逻辑：1024 桶、4096
节点、8192 键范围，100% 写请求（含源键缺失和目标冲突）。模块内预分配节点，
桶和节点各为 64 字节步长；每个 worker 使用固定 CPU 种子的 xorshift64* 随机键。
为支持当前 JIT 准入，三个后端统一将节点搬移改为 `__hlist_del()` 后立即插入，
省去中间毒化写入，并在节点修改之前更新搬移计数。业务结果相同，指令序列
不同于上游；新旧负载的吞吐不可混为同一基线。
当前按用户要求删除 TCLock 的 `need_resched()` 批次截断和公共哈希表循环的
`cond_resched()` 调度点，三种后端均保留锁外四组乘加。原 `hash_resched` 模块
参数已删除；layout ABI v2 的 `resched` 固定为 0，运行器拒绝调度点仍开启的旧模块。
这项实验设置不同于上游原始调度策略，也不同于历史索引中的成绩。
这些锁外工作均计入整批 wall 时间。沿用三种直接API，新运行默认采用KD1024/TCLock1024批次配置；
最新[hash优化比较](results/20260927-hash36-profile.md)使用连续2秒、300ms峰值；历史固定迭代成绩保留各自原始参数。
这是哈希表临界区的三方对比，不宣称完整复现上游分配布局或论文的运行环境。

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --workload rcuht --backends native tclock kdlock --output /root/kdlock-evidence/rcuht-new
```

连续计时与cacheline共用全worker预热、进度采集及完整cohort窗口选择。复现本次矩阵时，
在上述命令加入以下参数（完整内核身份和环境命令见结果报告）：

```sh
--threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 --repeats 3 \
--duration-ms 2000 --peak-window-ms 300 --collector-cpu 38
```

哈希表模式不接受 `--cachelines`，默认1/4/8/16/20线程 × 三后端 × 三轮，共45场。
可直接测性能；需要定向排查时用 `--threads 1 4 --iterations 10000` 缩小范围。每次 snapshot 在
计时外验证节点地址、链表回链、无环、桶归属、键唯一性和 4096 节点总数；每个
操作必须恰好计入搬移/冲突/未命中之一。`before/after` 的前四项为总操作、搬移、
冲突、未命中，余项为零；`cachelines=0` 仅是内部 hash 正文编号。表与 counters
经过同一预热后继续测量，随机流按 worker CPU 固定，但并发执行顺序不固定。
结果携带 `workload=rcuht`，不能与 cacheline 模式混合汇总。设备 layout ABI 已升为
v2，客户端和 workload 模块必须同时重建。

## 自适应准入与结果解释

当前只保留`adaptive`，同时要求CPU频率、1024次MCS窗口比较的比例准入、原生队头资格和单锁热度。
默认整数比较为`(entries >> 10) < 2`，比较后清零两个计数；没有首次快照或首次比例豁免。
使用[执行流规则](../../docs/JIT_EXECUTION.md#21-热度与角色)，`--spin-entry-ratio-limit 0`用于单独关闭比例的诊断。
KD会话目录保留`-kdlock-adaptive`后缀和固定adaptive元数据；Linux/TCLock标为`not_applicable`。
历史observe会话继续单独保存，不能与当前结果合并。
当前全部测量worker都参与预热，但预热不强制修改CPU或单锁热度，是否准入仍由上述策略决定。
历史单CPU预热留下的冷CPU测量前缀属于当时结果，不能与当前全worker预热样本合并。
`--scenario nested` 和 `--scenario early` 只允许 KD cacheline，用于双锁协议回归；
默认 `plain` 保持原三锁性能负载。

自适应策略可能继续原生执行。允许NO_JIT的性能配置仍保留正确样本，但`jit_acceptance`
明确标记`NO_JIT`，不算实际JIT通过。plain的2/3线程可以经fast/pending
或原生 MCS 队头完成；入队不保证存在可代理后继。零JIT标记 `NO_JIT_LOW_CONTENTION`，
有实际正文才记PASS，不再使用队列深度相关的 `NO_JIT_COLD` / `NO_JIT_POLICY`。
性能中的20线程及竞争nested/early要求实际JIT；所有多线程功能正例均要求实际JIT，
显式`--spin-delegate off`零JIT对照除外。
汇总额外报告 `actual_jit_sessions`，不能用性能有效样本数代替 JIT 验收数。

`--spin-delegate off` 显式选择 KD 不代理对照，使用相同直接 API/负载和准备步骤，
provider 装载 `spin_delegate=0`。结果必须为零 JIT 正文并标记 `DISABLED_CONTROL`；
不作为 JIT 正例。当前off仍累计获取次数，但跳过热表记录及MCS采样，不能与已撤回实验
中“off 仍采样”的数值直接比较。默认`on`保留上述实际JIT验收要求。

# Linux / TCLock / kdlock 直接 API benchmark

当前入口使用同一份 `workload_modules/spin_cacheline` 正文，分别构建Linux原生、TCLock、
当前KD三个后端；KD observe/adaptive共用一份调用二进制，分会话运行和汇总。
最新结果与历史参照见[本次结果](#本次结果)，构建及运行环境遵循[操作手册](../../docs/AGENTS.md)。

| 后端 | 直接调用 |
| --- | --- |
| Linux | `__raw_spin_lock/unlock`，绕过实验内核hook |
| TCLock | `komb_spin_lock/unlock`，调用者配对管理抢占 |
| kdlock | `KD_SPIN_DIRECT_LOCK/UNLOCK`，CPU热值分流获取，统一generic clobber解锁 |

KD宏取得一次preempt pin后用C `if`读取per-CPU热值。冷CPU调用
`kd_spin_direct_native_lock`，包括失败后的完整pending/MCS等待；热CPU调用
`kd_spin_lock_pinned_clobber_v1`。解锁一律通过broad-clobber调用
`kd_spin_unlock_clobber_v1`，由provider识别低字节5的原生所有权或执行热协议。
寄存器仅在约束/clobber中声明，保存位置由编译器决定，可出现在if之前；宏不手写push/pop。

按用户要求，spin采样与比例比较统一到512次MCS边界，复用原始MCS计数，静态per-CPU状态仅保存
获取/MCS的两个快照共16字节。每次边界先比较差值比例，再采一次CPU时钟；默认门槛100%，
fast/pending成功也进入获取分母。首次采样建立比例起点，之后低比例直接关闭；observe和门槛0绕过比例。
计数及IRQ采样节奏允许近似，busy跳过的事件进入下次差值；移除连续低确认、8窗口冷却和热度保留。
spin单锁达到512次检查12.5亿TSC窗口，mutex保持第1025次/25亿，CPU窗口保持400亿。
动态热表布局和原所有权协议保持，小型pinned封装内联；策略不按线程数直接分流。
完整规则以[执行流中的热度与角色](../../docs/JIT_EXECUTION.md#21-热度与角色)为准。

observe在CPU频率热后固定准入，adaptive还要求比例和单锁热度；已发布请求不受后续热度变化取消。
热度cookie只存CPU共享的缓存热值，不存获取路径或嵌套深度。记录使用`caller_shell=cold_clobber`、
`caller_abi=clobber`、`cookie_storage=percpu_rate_hot`、`cpu_heat_policy=mcs_entry_ratio512_simple`，
并单列`spin_contention_pct`。策略标识不替代冻结源码/哈希，同一标识的不同实现版本也不能合并取优；
历史`mcs_entry`、32次比例窗口的`mcs_entry_ratio`、旧512窗口候选`mcs_entry_ratio512`、
MCS32采样的`mcs_entry_ratio512_confirm2`、检查点`mcs_entry_ratio512_batch128`及缺失字段的样本分别保留。
当前诊断槽把身份/禁用字段与waiter计数分至不同128字节区域，新增4KiB共享存储，
布局见[provider说明](../../kernel_module/README.md)，该局部修复的独立证据见[诊断槽报告](results/20260924-diagnostic-pairs.md)。
历史检查点`b83f551`的42场未通过性能保护；后续两个补充后继等待实验同样未满足目标，已完整撤回。
简化候选`simple512-fixed`的42场正确排空但性能保护失败，保留为EXPERIMENTAL检查点。
随后保留实现的`selected-final-fixed`完整168场及nested/early两场功能已完成；3/4线程改善，
c16/8等保护仍未满足，见[完整报告](results/20260924-contention-ratio.md)。这些历史结果使用当时的单CPU预热，
不改写为下述全worker预热结果，也不把旧候选的检查或局部结果视为当前验收。

三种后端保留相同cacheline更新、解锁后四组乘加及循环成本；吞吐和ns/op以完整操作计算，
不是独立获取锁延迟。三种模块不是同一二进制，必需的现场成本不扣除。
`--pmu`只在独立长批次对measure客户端和worker执行perf stat，输出instructions、cycles、
task-clock、context-switches、cpu-migrations；累计计数包含所有worker等待，不等同于lock/unlock正文成本。

## 准备与运行

性能测试对象固定为 Linux 原生、TCLock 和当前 kdlock，运行器默认即为
`--backends native tclock kdlock`。不再构建或运行旧版 kdlock 对照；归档中的
O/N `compare.py` 仅用于追溯历史结果。功能检查仍按需要单独选择 KD。

后端先加载，直接依赖它的样例后加载。运行器在没有 worker 时绑定只读观测
使用的锁地址，再调用 `SC_PREPARE` 显式登记选定正文的锁后 RIP 和 KD 对象。
kdlock 等唯一条目发布为 NORMAL、翻译进程退出并停止 daemon 后，再使用与正式测量
相同的worker数量和CPU集合预热，每个worker执行48000次；所有后端采用相同规则。
登记准备命令仍单线程执行，继承runner允许的CPU集合。预热与测量通过独立客户端调用分别创建
worker，复用相同的数量及CPU绑定配置；预热worker退出并完成正常检查后接着发起测量，
不再插入额外2秒等待，以免预热建立的热度在间隔中失效。记录保存
`warmup_policy=all_workers`、`warmup_iterations_per_worker=48000`、`warmup_pause_seconds=0`。
准备与预热均不计入正式测量。默认分别运行 observe 固定准入和adaptive 自适应准入；
每个 KD 会话重新加载 provider，热度不跨模式继承。

默认矩阵是 **1/16 cacheline × 1/4/8/16/20 线程 × 四项 × 三轮 = 120 场**，
四项为 Linux、TCLock、KD observe、KD adaptive；Linux/TCLock 每配置每轮各测一次，供两种 KD 模式比较。
2026-09-23 用户因性能波动将 `--repeats` 默认值提高为 3，每线程仍为 100000 次。
2026-09-24 本次用户明确要求重新测一次，并要求全部worker预热；此次显式传入`--repeats 1`，
不修改三轮默认值。c1/c16、1/2/3/4/8/16/20线程及四项共56场；单次样本不能描述跨轮波动。
2026-09-24 用户明确要求后续使用宿主默认动态CPU频率，不再自动固定到2.5GHz。
当前宿主worker CPU0..19已核对恢复原设置：`intel_pstate`、`powersave`、
`balance_performance`，min/max为1000000/3000000kHz。后续运行保留该动态策略，
记录实际频率配置；只有用户另行要求频率对照时才临时改动。历史固定频率成绩保持原标注，
不与动态频率样本混合统计。
仅保留这一组直接调用方式，不再使用 `--abis`。
只在 recovery guest 中按[操作手册](../../docs/AGENTS.md)核对快照、依赖和空闲状态；
现有 `kdclobber2` 内核不重建。输出必须是新的仓库外目录。

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/direct-new
```

`--spin-contention-pct`范围为0–100，默认100；0仅绕过adaptive的比例门槛，
CPU频率和单锁热度规则仍生效。该值作为只读provider装载参数传入并核对；observe始终绕过比例门槛。

需要固定准备/分配阶段的NUMA放置时，可在上述`timeout`后、`python3`前加入
`taskset -c 0-19`；使用前核对这些CPU都属于预期的NUMA0。runner及其准备进程继承这一CPU集合，
worker仍按线程配置绑定选定的CPU0至CPU(`threads-1`)。运行器在`environment.json`记录
`runner_affinity`，并在加载模块前检查所有worker CPU均被允许；只绑定CPU0不能运行多CPU矩阵。
该放置设置须随结果保留，不据此推定性能收益。

代码修改后可直接执行上述性能命令，运行器同时完成业务、IRQ/preempt、JIT 和
排空检查；独立单元、SELFTEST、`--functional` 或六场小矩阵不作为固定前置步骤。
需要定向排查时再追加 `--cachelines 1 --threads 1 4 --iterations 10000` 缩小范围。
`--dry-run` 只打印矩阵。`STOP` 文件在已排空会话之间生效；失败或超时保留证据并停止。
`--hotlock-mode observe adaptive` 显式选择默认双模式；也可只选 `adaptive` 或 `observe`。
快速三方 adaptive 矩阵可追加 `--hotlock-mode adaptive --threads 1 4 20`，共54场，仍每线程100000次、每配置三轮。
完整低线程与高竞争比较使用 `--threads 1 2 3 4 8 16 20
--hotlock-mode observe adaptive`：1/16 cacheline共168场，
每配置三轮、每线程100000次；KD统一按CPU热度分流，Linux/TCLock每轮只跑一次。

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
  --functional --backends kdlock --cachelines 1 --threads 4 --repeats 1 \
  --iterations 100000 --scenario plain \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/continuation-plain-new
```

按改动选择 `nested`、`early`；`--spin-delegate off` 单独验证原生对照，要求零
JIT，并标记 `DISABLED_CONTROL`。当前 continuation 功能证据与未覆盖边界见
[测试入口](../../tests/README.md)。

## 验收与结果

默认每配置三轮，用于观察性能波动；本次明确的一轮复测使用`--repeats 1`。
`summary.csv/json` 用 `best_throughput_ops_s`、`best_amortized_ns_op` 报告同一
获选会话的吞吐与摊销时间，`best_session` 指向原始会话，
`comparison_policy=best_valid_throughput` 标明口径，继续从有效样本选取最大吞吐。
另以 `min_throughput_ops_s`、`median_throughput_ops_s`、`max_throughput_ops_s`
报告有效吞吐的最小值、中位数、最大值；`throughput_spread_pct` 为
`(最大值 - 最小值) / 中位数 × 100%`，便于直接查看三轮离散程度。
中位数用于描述波动，不改变上述后端比值口径。相对 Linux 的比值使用各后端获选值
除以 Linux 获选值，KD/TCLock 同理；保留有效样本数，报告须说明不足三轮的情况。
`records.json` 保留全部计划项、原始测量及失败/未执行状态；只有数据
正确、完成且已排空的样本参与汇总。KD按`hotlock_mode`、`caller_shell`、
`cookie_storage`、`cpu_heat_policy`、`spin_contention_pct`分开汇总，不跨模式、cookie存储、采样策略或比例门槛取最大值；
热表计数保留在原始日志，不参与性能评分。

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
| [单线程频率对照](results/20260924-single-thread-frequency.md) | 相同b8bd0e2源码，c1/t1三后端、1.0/2.5GHz各三轮共18场；复现KD约12.4→31.7Mops/s，不能记为锁优化收益 |
| [全部worker预热后的单轮三方比较](results/20260924-all-worker-warmup.md) | b8bd0e2，c1/c16、1/2/3/4/8/16/20线程，四项共56场；每worker预热48000次、无额外2秒等待，同场吞吐/ns与后端比值；不与旧预热样本合并 |
| [节点数组128字节对齐](results/20260924-node-array-alignment.md) | 相同简单政策下42场；16/20线程恢复约8%–9%，仍未满足原基线保护；每CPU只增加64字节填充，冻结.text字节相同 |
| [本轮低竞争比例准入](results/20260924-contention-ratio.md) | 保留实现完整168场及nested/early两场完成，3/4改善但c16/8等保护未满足；采用当时单CPU预热，全部失败阶段保留原始数据 |
| [诊断槽128字节隔离](results/20260924-diagnostic-pairs.md) | 独立提交439cd82的匹配pilot和采样证据；局部改善不代表完整比例策略通过 |
| [MCS8/CPU400万组合](results/20260923-mcs8-cpu4m.md) | 历史168/168场、56配置各3轮；该参数组合不是当前比例准入配置；保留所有快慢样本及参数组合 |
| [adaptive 窗口与采样间隔](results/20260923-adaptive-windows.md) | 单锁/CPU窗口、MCS间隔6个独立候选及1个组合；195场有效、1场20线程零JIT拒绝并停止该候选，保留20个未执行项；该轮恢复当时的MCS1/CPU400亿默认，不含后续指定的MCS8/CPU400万组合 |
| [adaptive 阈值诊断](results/20260923-adaptive-threshold-sweep.md) | 历史KD单锁计数32/128/1024及恢复32，c1/c16、3/4/8/20线程各三轮；两候选不满足当时保留条件；不是新增三后端排名 |
| [默认热度分流完整三轮](results/20260923-spin-default-heat-full3.md) | 此前MCS1/CPU400亿的168场：1/2/3/4/8/16/20线程，56配置各3轮；39b0e7c加冻结工作树修改，包含布局优化 |
| [单线程与20线程调查](results/20260923-spin-single-hot-balance.md) | metadata精简、continuation错位、48场矩阵和长批次布局对照；保留失败候选及代码对齐的因果限制 |
| [昨日恢复基线](results/20260922-performance-recovery.md) | 旧采样规则下20线程5.197/4.809 Mops/s，两轮最大值；该快版没有匹配PMU |
| [统一解锁ABI验证](results/20260923-spin-generic-unlock.md) | broad-clobber、JIT COMPLETE/FULL及nested/early验证；其108场属于布局优化前冻结版本 |
| [普通spin IRQ/wrapper验证](results/20260922-plain-spin.md) | IRQ/BH状态、抢占配对及wrapper修复，含首次失败记录 |

历史MCS8/CPU400万组合的20线程adaptive中位数c1/c16为5.450/5.179 Mops/s，
spread为0.87%/0.48%。该批8线程未观察到历史对照退化，3/4线程和单线程收益未解决；这些不是当前比例策略的成绩。
此前MCS1/CPU400亿完整矩阵20线程KD observe中位数c1/c16为5.324/5.051 Mops/s，两模式spread均低于0.8%。
3/4线程仍慢于Linux/TCLock；低线程波动未消除，c1单线程TCLock最大40.899与中位14.854相差很大。
该历史完整矩阵未采PMU；不能将不同冻结输入的吞吐或PMU数值移作当前组合测量。
其余过时阶段报告已合并到[性能实验历史索引](results/HISTORY.md)，保留固定Git原文、输入身份及归档哈希。

## 当前 TCLock 设置

采用 Linux 6.1 移植版和上游 C 内联换栈，保留 NUMA_AWARE、WWJUMP 与 1024
批次额度，未添加运行期代理次数计数。关闭 `ENABLE_IRQS_CHECK`、TCLock 后端
及三种 direct workload 的 UBSAN 插桩；内核内部 UBSAN 保持原配置。
运行器检查实际 ELF、返回布局及无 UBSAN handler 引用，保留 IRQ/preempt 退出检查。
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
这些锁外工作均计入整批 wall 时间。沿用三种直接 API 和 1024 批次参数；
这是哈希表临界区的三方对比，不宣称完整复现上游分配布局或论文的运行环境。

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --workload rcuht --backends native tclock kdlock --output /root/kdlock-evidence/rcuht-new
```

哈希表模式不接受 `--cachelines`，默认 1/4/8/16/20 线程 × 四项 × 三轮，共 60 场。
可直接测性能；需要定向排查时用 `--threads 1 4 --iterations 10000` 缩小范围。每次 snapshot 在
计时外验证节点地址、链表回链、无环、桶归属、键唯一性和 4096 节点总数；每个
操作必须恰好计入搬移/冲突/未命中之一。`before/after` 的前四项为总操作、搬移、
冲突、未命中，余项为零；`cachelines=0` 仅是内部 hash 正文编号。表与 counters
经过同一预热后继续测量，随机流按 worker CPU 固定，但并发执行顺序不固定。
结果携带 `workload=rcuht`，不能与 cacheline 模式混合汇总。设备 layout ABI 已升为
v2，客户端和 workload 模块必须同时重建。

## 准入模式与结果解释

运行器默认同时运行 `--hotlock-mode observe adaptive`。
`observe` 在CPU频率热后固定 KD 准入并记录本地统计，绕过比例门槛；冷CPU进入完整原生获取。
`adaptive` 同时要求CPU频率、512次MCS边界比较的比例准入和单锁热度。默认100%比例门槛、首次快照建立和后续直接判断
使用[执行流规则](../../docs/JIT_EXECUTION.md#21-热度与角色)，`--spin-contention-pct 0`用于单独关闭比例的诊断。
两者使用同一输出根目录下带 `-kdlock-{observe|adaptive}` 的独立会话目录，
汇总保留模式列；Linux/TCLock 标为 `not_applicable`。
当前全部测量worker都参与预热，但预热不强制修改CPU或单锁热度，是否准入仍由上述策略决定。
历史单CPU预热留下的冷CPU测量前缀属于当时结果，不能与当前全worker预热样本合并。
`--scenario nested` 和 `--scenario early` 只允许 KD cacheline，用于双锁协议回归；
默认 `plain` 保持原三锁性能负载。

adaptive 的 `NO_JIT` 会保留数据正确的性能样本，但 `jit_acceptance` 明确为
`NO_JIT`，不算实际 JIT 通过；observe 的竞争正例仍要求非零正文证据。
两种模式均按 MCS 入队采样；adaptive可能因比例门槛继续原生执行。plain 的2/3线程可以经 fast/pending
或原生 MCS 队头完成；入队不保证存在可代理后继。零JIT标记 `NO_JIT_LOW_CONTENTION`，
有实际正文才记PASS，不再使用队列深度相关的 `NO_JIT_COLD` / `NO_JIT_POLICY`。
20线程及竞争 nested/early 在两种模式均要求实际JIT；4线程以上observe也要求实际正文。
汇总额外报告 `actual_jit_sessions`，不能用性能有效样本数代替 JIT 验收数。

`--spin-delegate off` 显式选择 KD 不代理对照，使用相同直接 API/负载和准备步骤，
provider 装载 `spin_delegate=0`。结果必须为零 JIT 正文并标记 `DISABLED_CONTROL`；
不作为 JIT 正例。当前off仍累计获取次数，但跳过热表记录及MCS采样，不能与已撤回实验
中“off 仍采样”的数值直接比较。除上述少线程plain分类外，默认 `on` 的observe竞争验收仍要求实际JIT。

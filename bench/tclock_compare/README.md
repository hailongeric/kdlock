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

CPU热度只在每次合格MCS发布时采样一次，fast/pending不计数；冷/热CPU规则相同。
2/3线程实际入队也可升温，但不保证存在可代理后继。CPU窗口为400亿TSC ticks；
单锁入口第33次检查独立窗口，mutex CPU仍每1024次入口检查。每CPU/type保留256桶、
256条精确地址记录，碰撞链完整匹配、满表保留已有身份；非task上下文跳过统计。
`spin_delegate=0`跳过代理及热度采样。当前没有队列深度策略、on/off调用壳选项或两个旧开关判断。

observe在CPU热后固定准入，adaptive再判断单锁热度；上下文、owner、ticket和JIT就绪约束均保留。
CPU曾变热后依赖后续MCS事件降温，安静的单线程阶段不会主动过期。热度cookie只表示一个CPU
共享的缓存热值，不存获取路径或嵌套深度。记录使用`caller_shell=cold_clobber`、
`caller_abi=clobber`、`cookie_storage=percpu_rate_hot`、`cpu_heat_policy=mcs_entry`；
旧样本缺失字段或使用不同策略时分别汇总。

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
kdlock 等唯一条目发布为 NORMAL、翻译进程退出并停止 daemon 后，再执行各组
相同的单 CPU 48000 次预热。准备与预热均不计时。默认分别运行 observe 固定准入和
adaptive 自适应准入；每个 KD 会话重新加载 provider，热度不跨模式继承。

默认矩阵是 **1/16 cacheline × 1/4/8/16/20 线程 × 四项 × 三轮 = 120 场**，
四项为 Linux、TCLock、KD observe、KD adaptive；Linux/TCLock 每配置每轮各测一次，供两种 KD 模式比较。
2026-09-23 用户因性能波动将 `--repeats` 默认值提高为 3，每线程仍为 100000 次。
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

2026-09-23 用户最新要求为每配置三轮，用于观察当前性能波动。
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
`cookie_storage`、`cpu_heat_policy`分开汇总，不跨模式、cookie存储或采样策略取最大值；
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
| [adaptive 阈值诊断](results/20260923-adaptive-threshold-sweep.md) | KD单锁计数32/128/1024及恢复32，c1/c16、3/4/8/20线程各三轮；两候选不满足保留条件，默认仍为32；不是新增三后端排名 |
| [默认热度分流完整三轮](results/20260923-spin-default-heat-full3.md) | 最新168场：1/2/3/4/8/16/20线程，56配置各3轮；39b0e7c加冻结工作树修改，包含现有布局优化 |
| [单线程与20线程调查](results/20260923-spin-single-hot-balance.md) | metadata精简、continuation错位、48场矩阵和长批次布局对照；保留失败候选及代码对齐的因果限制 |
| [昨日恢复基线](results/20260922-performance-recovery.md) | 旧采样规则下20线程5.197/4.809 Mops/s，两轮最大值；该快版没有匹配PMU |
| [统一解锁ABI验证](results/20260923-spin-generic-unlock.md) | broad-clobber、JIT COMPLETE/FULL及nested/early验证；其108场属于布局优化前冻结版本 |
| [普通spin IRQ/wrapper验证](results/20260922-plain-spin.md) | IRQ/BH状态、抢占配对及wrapper修复，含首次失败记录 |

最新矩阵20线程KD observe中位数c1/c16为5.324/5.051 Mops/s，两模式spread均低于0.8%。
3/4线程仍慢于Linux/TCLock；低线程波动未消除，c1单线程TCLock最大40.899与中位14.854相差很大。
本次完整矩阵未采PMU；不能将此前不同冻结输入的PMU数值移作本版测量。
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
`observe` 在CPU热后固定 KD 准入并记录本地统计；冷CPU同样进入完整原生获取。
`--hotlock-mode adaptive` 使用spin CPU每次合格MCS事件、单锁入口 count 大于32（33次）的
独立时间窗口确认；每 CPU/type 256 桶、256 条精确地址记录，冲突链匹配，
满表不覆盖已有身份，未收录锁或冷锁保持原生。
两者使用同一输出根目录下带 `-kdlock-{observe|adaptive}` 的独立会话目录，
汇总保留模式列；Linux/TCLock 标为 `not_applicable`。
单 CPU 预热不会让其他 CPU 自动变热，冷 CPU 的测量前缀属于自适应效果的一部分。
`--scenario nested` 和 `--scenario early` 只允许 KD cacheline，用于双锁协议回归；
默认 `plain` 保持原三锁性能负载。

adaptive 的 `NO_JIT` 会保留数据正确的性能样本，但 `jit_acceptance` 明确为
`NO_JIT`，不算实际 JIT 通过；observe 的竞争正例仍要求非零正文证据。
两种模式均按 MCS 入队采样，少线程也可自然升温。plain 的2/3线程可以经 fast/pending
或原生 MCS 队头完成；入队不保证存在可代理后继。零JIT标记 `NO_JIT_LOW_CONTENTION`，
有实际正文才记PASS，不再使用队列深度相关的 `NO_JIT_COLD` / `NO_JIT_POLICY`。
20线程及竞争 nested/early 在两种模式均要求实际JIT；4线程以上observe也要求实际正文。
汇总额外报告 `actual_jit_sessions`，不能用性能有效样本数代替 JIT 验收数。

`--spin-delegate off` 显式选择 KD 不代理对照，使用相同直接 API/负载和准备步骤，
provider 装载 `spin_delegate=0`。结果必须为零 JIT 正文并标记 `DISABLED_CONTROL`；
不作为 JIT 正例。当前 off 在公共入口跳过热度记录，不能与已撤回实验
中“off 仍采样”的数值直接比较。除上述少线程plain分类外，默认 `on` 的observe竞争验收仍要求实际JIT。

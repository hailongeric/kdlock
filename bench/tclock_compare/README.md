# Linux / TCLock / kdlock 直接 API 对照

最新[adaptive快速三方结果](results/20260922-adaptive-quick.md)：18/18场、1500万次计时操作完成并排空，
4/4竞争KD有实际JIT；1线程KD c1/c16为8.445/6.940 Mops/s，20线程为5.048/4.818 Mops/s。
运行器默认已同时运行KD observe和adaptive，分别汇总；本轮性能只测adaptive。

此前[MCS4 / 40亿CPU窗口完整单轮结果](results/20260922-spin-mcs4-full-benchmark.md)：
30/30场通过并排空，8/8竞争KD有实际JIT。20线程KD c1/c16为5.009/4.768 Mops/s，
为TCLock的1.018×/1.462×；c1单线程较上一轮下降10.16%，单轮差异尚未归因。

此前[CPU MCS1 / hotlock32 与移除 busy 合并验证](results/20260922-spin-mcs1-lock32.md)：
三方单轮18/18场通过，20线程KD c1/c16为5.011/4.802 Mops/s，较上一轮提高27.3%/23.7%，
本轮恢复到下降前基线水平。基础/定向单元3/3、adaptive功能2/2通过；两组改动的贡献未拆分。
上述性能来自 CPU MCS1 / 400 亿窗口的冻结版本，保留为历史比较。

此前[CPU32 MCS 计数验证](results/20260922-spin-mcs32.md)：1/4/20线程三方单轮18/18场通过；
单线程 KD c1/c16 为6.574/6.890 Mops/s，20线程为3.937/3.883 Mops/s，
相对下方基线20线程下降20.8%/18.4%。本次按用户指定保留计数规则，收益与退化分别记录。

此前[完整三方单轮基线](results/20260922-single-round-baseline.md)测量提交 `1928434`：
30/30 场通过，计时区间 2940 万次操作全部排空。单线程 KD c1/c16 为
6.369/5.779 Mops/s；20 线程为 4.974/4.760 Mops/s。每配置只测一轮。

当前 spin CPU 每4次实际 MCS 入队检查热度，fast/pending 不计数；spin/mutex 单锁
阈值为32，第33次调用采时。mutex CPU 保持1024次入口检查，两类CPU窗口均为40亿TSC ticks。
热表已删除 busy/barrier，只在 task context 统计并保留 CPU pin；非 task 样本丢弃。
此前 CPU 阈值为 1024 的 MCS 入队频率实验已因退化撤回，
[该次回退验证](results/20260922-spin-mcs-rollback.md)通过，当时未重跑性能矩阵；
[实验成绩](results/20260922-spin-mcs-frequency.md)保留为历史。

此前[恢复版完整三方结果](results/20260922-restored-full-benchmark.md)：60/60场通过，5880万次操作全部排空；
20线程KD c1/c16为4.969/4.788 Mops/s。每组两轮取最大值，Linux c16单线程波动详见报告。

512槽直接映射已按用户要求撤回，代码恢复 `bf16b10`。此前[回退验证](results/20260922-directhash-v2-rollback.md)通过：
20线程KD的c1/c16为5.002/4.771 Mops/s，12场定向三方检查全部排空，按当时口径保留。

当前实现的恢复过程见[热表回归处理](results/20260922-performance-recovery.md)：
当时采用每 CPU/type 256 桶、256 记录，精确地址碰撞链、满表不替换、本地 busy 及已有 pin 复用。
当时的无 busy、共享表和直接映射版本已回退；当前重新采用 task-only 统计，普通 spin IRQ 语义及 wrapper 栈修复保留。
历史实验统一从[历史索引](../spin_cacheline/results/HISTORY.md)读取。

当前源码使用显式锁 API，KD 入口记录本地热度；进程名筛选和统一 hook 分派不进入被测路径。三种后端分别构建同一份
`workload_modules/spin_cacheline`，只在编译时改变锁 API：

| 后端 | 直接调用 |
| --- | --- |
| Linux | `__raw_spin_lock/unlock`，绕过实验内核 hook |
| TCLock | `komb_spin_lock/unlock`，调用者配对管理抢占 |
| kdlock | `kd_spin_lock_clobber_v1/unlock_clobber_v1`，直接进入 kdlock 协议 |

kdlock 使用显式 32 位 KD 锁字，保留 owner/ACK、上下文和 JIT 就绪检查。
其 clobber-v1 调用现场由编译器保存；TCLock 和 Linux 使用各自普通 C API。
三个模块正文与循环相同，但不是同一份二进制，也不把必需的现场成本扣除。
每次完整操作保留原来的固定 cacheline 更新、解锁后四组乘加及循环成本。
吞吐和摊销 ns/op 都以完整操作计算，不是独立获取锁延迟。

当前保留入口准入和 ticket 路径优化；热度使用无候选的精确地址哈希计数，spin CPU 每4次MCS入队、单锁入口计数大于32时定时确认，mutex CPU仍统计1024次调用。同期复现、独立采样、
两个候选与回退验收见 [竞争回退报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md)。

## 准备与运行

性能测试对象固定为 Linux 原生、TCLock 和当前 kdlock，运行器默认即为
`--backends native tclock kdlock`。不再构建或运行旧版 kdlock 对照；归档中的
O/N `compare.py` 仅用于追溯历史结果。功能检查仍按需要单独选择 KD。

后端先加载，直接依赖它的样例后加载。运行器在没有 worker 时绑定只读观测
使用的锁地址，再调用 `SC_PREPARE` 显式登记选定正文的锁后 RIP 和 KD 对象。
kdlock 等唯一条目发布为 NORMAL、翻译进程退出并停止 daemon 后，再执行各组
相同的单 CPU 48000 次预热。准备与预热均不计时。默认分别运行 observe 固定准入和
adaptive 自适应准入；每个 KD 会话重新加载 provider，热度不跨模式继承。

默认矩阵是 **1/16 cacheline × 1/4/8/16/20 线程 × 四项 × 一轮 = 40 场**，
四项为 Linux、TCLock、KD observe、KD adaptive；Linux/TCLock 每配置各测一次，供两种 KD 模式比较。
`--repeats` 默认为 1，每线程仍为 100000 次；仅在用户明确要求重复测量时增加轮次。
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
快速三方 adaptive 矩阵可追加 `--hotlock-mode adaptive --threads 1 4 20`，共18场，仍每线程100000次、每配置一轮。

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
[tests](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#continuation-validation)。

## 验收与结果

2026-09-22 用户最新要求为每配置一轮，三种后端分别报告唯一有效样本的吞吐。
`summary.csv/json` 用 `best_throughput_ops_s`、`best_amortized_ns_op` 报告同一
获选会话的吞吐与摊销时间，`best_session` 指向原始会话，
`comparison_policy=best_valid_throughput` 标明口径；不再输出 `median_*` 字段。
上述字段保持兼容，一轮时获选会话就是该唯一有效样本；仅显式增加轮次时才从
有效样本取最大值。相对 Linux 的比值使用各后端获选值除以 Linux 获选值，
KD/TCLock 同理；保留有效样本数。`records.json` 保留全部计划项、原始测量及失败/未执行状态；只有数据
正确、完成且已排空的样本参与汇总。KD 按 `hotlock_mode` 分开汇总，不跨模式取最大值；
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

2026-09-22 双模式默认值及独立汇总已在guest通过运行器单元12/12；CLI dry-run核对
cacheline40场、RCUHT20场，KD功能模式20场由单元检查，默认均只有第0轮。
本轮另完成adaptive快速18场性能测量，原始命令、退出码、哈希及范围见[报告](results/20260922-adaptive-quick.md)。

## 本次结果

最新测量见[adaptive快速三方报告](results/20260922-adaptive-quick.md)：基于`4081b09`的工作区，
c1/c16 × 1/4/20线程 × 三后端 × 一轮，18/18场、1500万次操作完成并排空。
4/4竞争KD有实际JIT，两场单线程为NO_JIT；20线程KD为5.048/4.818 Mops/s。
本轮未重测observe，完整双模式性能矩阵尚未运行。

此前五轮中位数及功能实验保留原统计口径，从[历史索引](../spin_cacheline/results/HISTORY.md)
读取，不能作为本轮单次测量的成绩。

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

哈希表模式不接受 `--cachelines`，默认 1/4/8/16/20 线程 × 四项 × 一轮，共 20 场。
可直接测性能；需要定向排查时用 `--threads 1 4 --iterations 10000` 缩小范围。每次 snapshot 在
计时外验证节点地址、链表回链、无环、桶归属、键唯一性和 4096 节点总数；每个
操作必须恰好计入搬移/冲突/未命中之一。`before/after` 的前四项为总操作、搬移、
冲突、未命中，余项为零；`cachelines=0` 仅是内部 hash 正文编号。表与 counters
经过同一预热后继续测量，随机流按 worker CPU 固定，但并发执行顺序不固定。
结果携带 `workload=rcuht`，不能与 cacheline 模式混合汇总。设备 layout ABI 已升为
v2，客户端和 workload 模块必须同时重建。

## 准入模式与结果解释

运行器默认同时运行 `--hotlock-mode observe adaptive`。
`observe` 固定 KD 准入并记录本地统计，
`--hotlock-mode adaptive` 使用 spin CPU 每4次实际MCS入队、单锁入口 count 大于32（33次）的
独立时间窗口确认；每 CPU/type 256 桶、256 条精确地址记录，冲突链匹配，
满表不覆盖已有身份，未收录锁或冷锁保持原生。
两者使用同一输出根目录下带 `-kdlock-observe` / `-kdlock-adaptive` 后缀的独立会话目录，
汇总保留模式列；Linux/TCLock 标为 `not_applicable`。
单 CPU 预热不会让其他 CPU 自动变热，冷 CPU 的测量前缀属于自适应效果的一部分。
`--scenario nested` 和 `--scenario early` 只允许 KD cacheline，用于双锁协议回归；
默认 `plain` 保持原三锁性能负载。

adaptive 的 `NO_JIT` 会保留数据正确的性能样本，但 `jit_acceptance` 明确为
`NO_JIT`，不算实际 JIT 通过；observe 的竞争正例仍要求非零正文证据。
汇总额外报告 `actual_jit_sessions`，不能用性能有效样本数代替 JIT 验收数。


`--spin-delegate off` 显式选择 KD 不代理对照，使用相同直接 API/负载和准备步骤，
provider 装载 `spin_delegate=0`。结果必须为零 JIT 正文并标记 `DISABLED_CONTROL`；
不作为 JIT 正例。当前回退版 off 在公共入口跳过热度记录，不能与已撤回实验
中“off 仍采样”的数值直接比较。默认 `on` 的 observe 竞争验收仍要求实际 JIT。

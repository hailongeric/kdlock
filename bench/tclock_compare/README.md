# Linux / TCLock / kdlock 直接 API 对照

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

当前保留入口准入和 ticket 路径优化；热度改为无候选的精确地址哈希计数，CPU 1024 次、单锁计数大于 1024 时定时确认。同期复现、独立采样、
两个候选与回退验收见 [竞争回退报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md)。

## 准备与运行

后端先加载，直接依赖它的样例后加载。运行器在没有 worker 时绑定只读观测
使用的锁地址，再调用 `SC_PREPARE` 显式登记选定正文的锁后 RIP 和 KD 对象。
kdlock 等唯一条目发布为 NORMAL、翻译进程退出并停止 daemon 后，再执行各组
相同的单 CPU 48000 次预热。准备与预热均不计时。默认 observe 固定准入；adaptive 各 CPU 在测量开始后自然积累热度。

默认矩阵是 **1/16 cacheline × 1/4/8/16/20 线程 × 三种后端 × 五轮 = 150 场**，
每线程 100000 次，奇数轮逆序。仅保留这一组直接调用方式，不再使用 `--abis`。
只在 recovery guest 中按[操作手册](../../docs/AGENTS.md)核对快照、依赖和空闲状态；
现有 `kdclobber2` 内核不重建。输出必须是新的仓库外目录。

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/direct-new
```

首次先追加 `--cachelines 1 --threads 1 4 --repeats 1 --iterations 10000` 做六场验证。
`--dry-run` 只打印矩阵。`STOP` 文件在已排空会话之间生效；失败或超时保留证据并停止。

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

`summary.csv/json` 仅报告各配置的吞吐中位数、摊销 ns/op、相对 Linux 的吞吐比和
有效样本数。`records.json` 保留全部计划项、原始测量及失败/未执行状态；只有数据
正确、完成且已排空的样本参与汇总。hotlock 不参与结果表。

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

本轮 [无候选直接哈希同期对照](results/20260921-hotlock-direct.md)：120/120 场通过并排空，
adaptive 四线程/二十线程近似持平，单线程 c1 +4.86%、c16 −2.10%；没有整体提升。
前序功能结果见 [tests](../../tests/README.md#hotlock-direct-validation)。

此前 [两级候选采样](results/20260921-hotlock-twolevel.md)记录上一版修改、功能检查及
observe/adaptive 新旧交错对照：120/120 场通过并排空。adaptive 二十线程 c1/c16
提高 10.09%/18.32%，单线程回退约 4%、四线程无明确收益；observe 高竞争近似持平。
CPU 热才记录锁，单锁独立定时确认；对象大小未增加。

修改前 [提交完整重测](results/20260921-current-benchmark.md)：`175d73b`，150/150 场通过，
40/40 场竞争 KD 有实际 JIT，全部排空。20 线程 c1/c16 的 KD 为 5.003/4.775 Mops/s，
为 TCLock 的 1.002×/1.442×；四线程仍为 TCLock 的 0.659×/0.766×。

历史阶段与回退原因集中在 [历史索引](../spin_cacheline/results/HISTORY.md)。
MCS 准入/时间域实验已撤回，当前保留入口准入和 ticket 优化。

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

哈希表模式不接受 `--cachelines`，默认 1/4/8/16/20 线程 × 三后端 × 五轮，共 75 场。
先用 `--threads 1 4 --repeats 1 --iterations 10000` 做六场验证。每次 snapshot 在
计时外验证节点地址、链表回链、无环、桶归属、键唯一性和 4096 节点总数；每个
操作必须恰好计入搬移/冲突/未命中之一。`before/after` 的前四项为总操作、搬移、
冲突、未命中，余项为零；`cachelines=0` 仅是内部 hash 正文编号。表与 counters
经过同一预热后继续测量，随机流按 worker CPU 固定，但并发执行顺序不固定。
结果携带 `workload=rcuht`，不能与 cacheline 模式混合汇总。设备 layout ABI 已升为
v2，客户端和 workload 模块必须同时重建。

## 准入模式与结果解释

`--hotlock-mode observe`（运行器默认）固定 KD 准入并记录本地统计，
`--hotlock-mode adaptive` 使用 CPU/type 1024 次、单锁 count 大于 1024（1025 次）的
独立时间窗口确认；每 CPU/type 256 精确地址记录，满表不替换，未知锁保持原生。
两者必须分开结果目录；
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

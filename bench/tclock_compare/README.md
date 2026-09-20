# Linux / TCLock / kdlock 直接 API 对照

当前源码暂时停用 kdlock/TCLock 的统一 hook 安装；spin 的 hotlock、进程名和
统一分派不进入被测路径。三种后端分别构建同一份
`workload_modules/spin_cacheline`，只在编译时改变锁 API：

| 后端 | 直接调用 |
| --- | --- |
| Linux | `__raw_spin_lock/unlock`，绕过实验内核 hook |
| TCLock | `komb_spin_lock/unlock`，调用者配对管理抢占 |
| kdlock | `kd_spin_lock_clobber_v1/unlock_clobber_v1`，直接进入 kdlock 协议 |

kdlock 保留私有调度字 S、原生锁 L、owner/ACK、上下文和 JIT 就绪检查。
其 clobber-v1 调用现场由编译器保存；TCLock 和 Linux 使用各自普通 C API。
三个模块正文与循环相同，但不是同一份二进制，也不把必需的现场成本扣除。
每次完整操作保留原来的固定 cacheline 更新、解锁后四组乘加及循环成本。
吞吐和摊销 ns/op 都以完整操作计算，不是独立获取锁延迟。

## 准备与运行

后端先加载，直接依赖它的样例后加载。运行器在没有 worker 时绑定只读观测
使用的锁地址，再调用 `SC_PREPARE` 显式登记选定正文的锁后 RIP 和 gate。
kdlock 等唯一条目发布为 NORMAL、翻译进程退出并停止 daemon 后，再执行各组
相同的单 CPU 48000 次预热。准备与预热均不计时，不再等待热锁晋升。

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

当前[切回 cacheline 的三方重测](results/20260920-cacheline-current.md)：沿用现有锁实现，
1/16 cacheline、五档线程各五轮共 150/150 场通过，40 场竞争 kdlock 均有实际 JIT。
20 线程下 Linux/TCLock/kdlock 吞吐分别为 4.106/4.992/3.715 Mops/s（1 cacheline）
和 2.434/3.341/3.654 Mops/s（16 cacheline）。没有修改执行源码或恢复额外计数。

此前[哈希表 JIT 修复与三方重测](results/20260920-kd-hash-jit.md)：统一调整摘链/
计数写入顺序，并修正最小入口对零扩展/符号扩展的按位依赖传播。
九场样例及正式 75/75 场通过数据与排空检查，所有竞争 kdlock 场次均有实际
JIT 执行。四线程 Linux/TCLock/kdlock 中位吞吐为 2.774/2.516/1.253 Mops/s，
二十线程为 3.146/5.129/2.495 Mops/s；功能已恢复，kdlock 性能差距仍在。

此前[删除调度检查与调度点后的实测](results/20260920-no-resched.md)：Linux/TCLock
六场 smoke 及四线程各五轮全部通过正确性和排空检查；四线程中位吞吐分别为
2.751 / 2.469 Mops/s，TCLock 为 Linux 的 0.898×，差距仍在。

此前 2026-09-20 将 TCLock 换栈恢复为上游 C 内联汇编，删除新增的三个 per-CPU
执行计数及其更新。加载前审核实际 ELF 的六寄存器/返回布局及计数符号缺失；
测量仍检查哈希表和 IRQ/preempt 状态、全部操作完成及队列排空。当前没有运行期
代理计数，以下历史批次长度/代理占比不能用作新设置下的观测。
对应[C 内联汇编、无额外计数实测](results/20260920-inline-no-counters.md)：
六场 smoke 及正式 50/50 场通过数据/排空检查，四线程为 Linux 的 0.887×，
20 线程为 1.571×；本轮没有实际代理次数与批长数据。

2026-09-20 后续调整按上游 RCUHT 关闭 TCLock 的 `ENABLE_IRQS_CHECK`，并关闭
TCLock 后端及三种 direct workload 的 UBSAN 插桩。运行器检查实际 ELF 没有
UBSAN handler 引用，保留后端反汇编；内核内部仍保持 UBSAN，其他协议参数和
等待调度分支沿用原值。该设置只适用于当前 IRQ 开启、task 上下文的单锁负载。
对应[检查设置对齐后的实测](results/20260920-irq-ubsan.md)：六场 smoke 及正式
50/50 场全部正确排空；四线程为 Linux 的 0.842×，20 线程为 1.583×。跨轮
绝对吞吐变化没有同期旧二进制控制组，不能全部归因于关闭检查。

[2026-09-20 上游一致性审查](results/20260920-upstream-audit.md)：保存的上游文件
与原版一致，实际被测代码为 Linux 6.1 移植版。RCUHT 编译分支、IRQ/等待调度、
批次额度、UBSAN/返回指令及实验环境均有差异；本次为离线核对，没有新性能成绩。

新增 `--workload rcuht` 使用上游 RCUHT 的单全局锁哈希表写逻辑：1024 桶、4096
节点、8192 键范围，100% 写请求（含源键缺失和目标冲突）。模块内预分配节点，
桶和节点各为 64 字节步长；每个 worker 使用固定 CPU 种子的 xorshift64* 随机键。
为支持当前 JIT 准入，三个后端统一将节点搬移改为 `__hlist_del()` 后立即插入，
省去中间毒化写入，并在节点修改之前更新搬移计数。业务结果相同，指令序列
不同于上游；新旧负载的吞吐不可混为同一基线。
当前按用户要求删除 TCLock 的 `need_resched()` 批次截断和公共哈希表循环的
`cond_resched()` 调度点，三种后端均保留锁外四组乘加。原 `hash_resched` 模块
参数已删除；layout ABI v2 的 `resched` 固定为 0，运行器拒绝调度点仍开启的旧模块。
这项实验设置不同于上游原始调度策略，也不同于下方已归档的历史成绩。
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

[2026-09-19 哈希表实测](results/20260919-rcuht.md)：Linux/TCLock 50/50 场正确
排空；TCLock 在四线程为 Linux 的 0.876×，20 线程为 1.571×。该历史版本的
kdlock 在动态链表回链写入处被 JIT 地址准入拒绝，没有有效性能成绩。

[2026-09-19 直接 API 对比](results/20260919-direct-api.md)：150/150 场正确排空。
20 线程时，1/16 cacheline 下 kdlock 吞吐分别为 Linux 的 66.9%/93.2%，
为 TCLock 的 77.9%/126.3%；完整中位数、ns/op 和符号表见结果页。

[TCLock 四线程退化分析](results/20260919-tclock-four-threads.md)：正式记录的批大小、
八场独立退出原因诊断，以及上游哈希表负载与调度点的差异。

## 历史与当前边界

以前经统一 hook 的成绩继续保留，不能和本轮直接 API 数据混成同一组：
[五档线程](results/20260919-thread-scaling.md)、
[状态访问](results/20260919-state-access.md)、
[首次三方对照](results/20260918-native-stack.md)。
旧 `profile_backends.py` 面向历史 hook 会话，本轮不使用它采样。
统一接入已经暂停，依赖透明 hook 的旧 live 用例不适用于当前实验构建。

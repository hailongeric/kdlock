# 2026-09-18：完整 TCLock 原生委托与 Linux/kdlock 对照

这轮新增独立 `tclock_backend/`，使用 TCLock 的原锁字、pending/队列、shadow
等待栈、六寄存器保存/恢复、真实 RSP 切换和 WWJUMP。临界区执行原生机器码，
没有 kdlock JIT/daemon/frame。生产 kdlock 源码未改。

## 完整操作吞吐

180/180 场正确并排空，测量期合计 **150,000,000 次操作**、
**44,300,521 次返回后的 JIT 正文**、**38,188,042 次 TCLock 原生委托正文**。
竞争组分别为 40 场实际 JIT 和 40 场实际 TCLock；两者各 20 个单线程组没有代理，
另有 60 场 Linux 原生对照。未运行无关全量回归。

单位 Mops/s，所有数值均为五轮中位数；比例列分别独立取中位数。
竞争点 TCLock 为 kdlock 的 **1.06–2.05 倍**，但并不普遍超过 Linux 原生。

### 旧 caller ABI

| cacheline | 线程 | Linux | TCLock | kdlock | TC/KD | TC 代理 | KD JIT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 11.1087 | 9.2686 | 7.7510 | 1.196 | 0.00% | 0.00% |
| 1 | 4 | 2.9577 | 1.6141 | 0.8014 | 2.014 | 45.30% | 56.61% |
| 1 | 20 | 3.1691 | 2.7522 | 1.6980 | 1.621 | 99.47% | 99.83% |
| 16 | 1 | 8.9391 | 8.1755 | 8.1055 | 1.009 | 0.00% | 0.00% |
| 16 | 4 | 1.9593 | 1.2397 | 0.7837 | 1.582 | 46.37% | 51.44% |
| 16 | 20 | 1.8897 | 1.7745 | 1.6721 | 1.061 | 84.39% | 99.81% |

### Caller-clobber v1

| cacheline | 线程 | Linux | TCLock | kdlock | TC/KD | TC 代理 | KD JIT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 10.3231 | 8.1879 | 9.5921 | 0.854 | 0.00% | 0.00% |
| 1 | 4 | 2.7132 | 1.5923 | 0.7751 | 2.054 | 44.76% | 54.09% |
| 1 | 20 | 2.9992 | 2.8226 | 1.6677 | 1.692 | 95.07% | 99.81% |
| 16 | 1 | 9.4020 | 7.1247 | 8.2218 | 0.867 | 0.00% | 0.00% |
| 16 | 4 | 1.8420 | 1.1871 | 0.7739 | 1.534 | 45.02% | 51.84% |
| 16 | 20 | 1.7872 | 1.9753 | 1.6545 | 1.194 | 99.72% | 99.83% |

### 批次变化与单线程成本

TCLock 保留上游 `need_resched()`、队列末端与 batch 上限结束条件。20 线程的
代理比例有较大波动；批次变短与吞吐下降同时出现，不能只选高代理轮次。
当前 kdlock 普通批次条件没有同样的 `need_resched()` 分支。这是完整后端比较，
不是只改变寄存器保存方法的因果实验；尚未单独计数各个 TC 批次结束原因。

| ABI / cacheline | TC 五轮吞吐范围 Mops/s | TC 代理比例范围 | 每批代理正文范围 |
| --- | --- | --- | --- |
| legacy / 1 | 1.9855–2.8692 | 55.76%–99.78% | 1.26–550.79 |
| legacy / 16 | 1.4840–1.9966 | 53.74%–98.13% | 1.16–68.60 |
| clobber / 1 | 1.9033–2.8968 | 55.56%–99.76% | 1.25–514.49 |
| clobber / 16 | 1.8574–2.0005 | 87.56%–99.85% | 9.78–721.72 |

十万次单线程批次只有约 10ms，结果随批长明显变化，不据它单独解释 spill。
随后用相同 caller 源码与编译选项补测 native 单线程、每场一千万次，
两 ABI × 两规模 × 五轮共 20 场、2 亿次操作，全部正确并排空。它是单独的
成本检查，不替换上表任何样本。每次完整操作的 ns 中位数如下：

| cacheline | legacy | clobber | 差值 |
| --- | --- | --- | --- |
| 1 | 31.859 | 37.134 | +5.275 |
| 16 | 38.550 | 42.995 | +4.445 |

冻结的 `caller-clobber.txt` 显示，`sc_body_1/16` 在函数序言保存 RBX、R12–R15，
尾声恢复。这些函数没有跨边界活跃局部值，仍须履行对外的普通 C ABI；三种
后端共用该调用者，所以 TCLock 也承担这部分成本。这里的 4.4–5.3ns 差值
还包含入口和调用者代码布局变化，不是孤立的 spill 指令延迟。

## 为什么当前 kdlock 仍慢

正式矩阵后，复用冻结二进制，在 20 线程、每线程一百万次下分别对三后端的
两规模采集 `cycles:k -F 199`，只保存 IP/TID/TIME/PERIOD，不采调用链。
六场都验证数据、实际委托及排空，**零丢样**；采样吞吐不计为正式成绩。
这是所有 worker 的采样 period 权重，不是单个函数耗时或临界区延迟。

| kdlock 热点 | 1 cacheline | 16 cacheline |
| --- | --- | --- |
| `__kd_spin_lock_longjmp` | 86.07% | 86.43% |
| `kd_spin_diag_find` | 4.69% | 4.27% |
| `run_combiner` | 2.12% | 2.04% |
| `kd_spin_resume_completed` | 0.91% | 0.92% |
| `kd_exe_spin_batch_prepare` | 0.32% | 0.34% |
| `jit_image` | 0.15% | 0.20% |

三个具体观察：

1. **共享诊断状态是明确热点。** `kd_spin_diag_find+0x55` 紧跟共享 `slot->addr`
   加载，承载该函数绝大多数样本；`kd_spin_resume_completed+0x5a` 紧跟
   `waiter_count` 的 `lock xadd`。两字段与 `jit_disabled` 位于同一 16B slot，
   waiter 增减与 combiner 查找会访问同一缓存行。源码见
   [diagnostics.inc](../../../kernel_module/spin/diagnostics.inc) 与
   [slot 定义](../../../kernel_module/spin/state.inc)。这支持优先检查共享行争用；
   没有测 cache-miss 事件或隔离缓存行 A/B，不能把该推断当成已完成的因果证明。
2. **队列与请求元数据也有成本。** `run_combiner` 热点集中于后继 node、
   `node->execution`、`frame.regs_ref`、task/栈预取前的依赖读取；它们是
   [prefetch/admission 路径](../../../kernel_module/spin/combiner.inc)的一部分。
   kdlock 另外保留 L/S、ticket、frame、source 与完成校验，TC 直接借原生栈。
   这些区别说明为何完整 TC 可以更快，但本轮没有逐个关闭机制来独立计价。
3. **整包寄存器保存已不是普通新 ABI 的现状。** 新路径只回写/恢复三个字段，
   整个 JIT 镜像的采样权重也只有约 0.15%/0.20%。该范围包含 wrapper 与正文，
   并非只算 payload。实测首先指向锁侧共享状态和元数据访问，不能继续把差距
   全部解释为“保存太多寄存器”或“编译时间太长”；计时前 daemon 已停止。

两种后端大量 cycles 都在等待：TC 队列函数约 93.28%/94.87%，KD 约
86.07%/86.43%。这含队列处理，且 20 个 worker 会放大等待权重；比例本身不
证明谁的执行更快。采样 TC 代理比例为 65.58%/55.80%，KD 为
99.85%/99.87%，与十万次正式矩阵不同，不能用采样比例替代正式成绩。

完整的[实现差异、收益抵消和优化顺序](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/bench/spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)
区分 caller 保存转移、共享诊断行、批次内逐请求校验及预取前置读取。
应先独立对照诊断 slot 缓存/布局，再检查普通准入和元数据依赖，最后评估预取、
批次及 wrapper；保留 JIT-disable、实时观察与生命周期门禁。
这些候选没有在本轮实施，采样权重也不是预期提速比例。

## 来源和比较口径

- 上游 TCLocks 提交 `bbfb9f00a12af51dff6ca291cb9829a82960c2ef`；四个原文件
  与 SHA256 保存在 `tclock_backend/upstream/` 和 `UPSTREAM.json`，差异见 `port.patch`。
- 基于 kdlock `73a1eb6c88715189ebbd03b2b96bd5a3d2391626` 的工作区。源文件与
  二进制逐一冻结；结果不只用 Git HEAD 标识。
- 同一 `6.1.159-kdclobber1` 内核，Build ID
  `db937d722ee2f2668acb12dc6f105aeea33b7c5c`，frame pointer/缓解配置保留。
  recovery guest 40 vCPU、28 GiB、双 NUMA；本轮使用 node 0 的 CPU 0–19。
  `nokaslr`、voluntary、watchdog 保持；vCPU 不代表宿主独占物理核。
- 两种 caller ABI 各编译一次，三种后端复用同一 workload；TCLock 与 kdlock
  均走同一 static-call bridge。TC 使用内核版纯轮询分支、NUMA/WWJUMP/六条
  预取及默认 batch 1024；未开启 rcuht 的 shadow 栈 schedule 分支。
- 1/16 cacheline × 1/4/20 线程 × 两 ABI × 三后端 × 五轮；每线程 100000 次。
  奇数轮反转六臂顺序；报告完整操作吞吐的五轮中位数，不选最高样本。
  锁外四组乘加、数据/CPU 亲和性与工作线程排空 oracle 相同。
- 统一单 CPU 预热 1 次和晋升 12000 次，kdlock 发布后停止 daemon，再开始
  竞争计时。准备与翻译时间均不计入吞吐；这不是并发冷启动测试。
  所有臂每个 ioctl 前后检查 IRQ/preempt 状态。

## 现场保存和恢复的实际差别

| 环节 | TCLock 独立后端 | kdlock caller-clobber v1 |
| --- | --- | --- |
| waiter 发布 | 六个 callee-saved 和 CALL 返回地址留在原栈，node 保存 RSP，先切 shadow 栈 | caller 编译器保存活跃值，共享请求记录 RIP/RSP/RBP，再切等待栈 |
| 执行正文 | combiner 物理切换至 waiter 原栈，运行原生临界区 | combiner 物理栈不变，绑定 frame、进入 wrapper，执行虚拟 SP/BP 下的 JIT |
| 连续交接 | unlock 保存六寄存器/原生续点，直接切下一 waiter；离栈后发布完成 | 验证精简完成、frame complete/pop、发布，再在同一 C 循环准入下一请求 |
| 最终返回 | 恢复六寄存器和实际 RSP，沿原生 unlock 续点返回 | 清理 ticket/request，恢复三个字段和原 IRQ 状态，caller 重载活跃值 |

TCLock 的两个只读计数分别记实际代理 unlock 与离开借用栈后的完成，两者排空
后须相等。kdlock 仍使用 wrapper 返回后的正文差值。TCLock 不计为 JIT。
这些只读观察器存在运行成本，本轮没有单独测量零观察器版本。

## 失败记录与边界

首次 `compare/` 在第 5 场 kdlock insmod 失败：请求 7232 字节静态 per-CPU。
只读 allocator bitmap 显示连续且 64B 对齐的可用区为 8064 字节；重叠的 chunk
scan/contig hint 使 `pcpu_next_hint()` 从第二页开始扫描，错过了足够大的跨页
空闲区。新 `allocator_guard` 仅正常分配/释放一页静态 per-CPU，让整页释放
刷新 hint；三臂都在计时前加载并立即卸载。没有写分配器元数据或改内核。
六臂定向检查通过；前后 bitmap 不变，scan_hint 从 1000 变为 0。

随后 `compare-final/` 在第 126 场 c16/t4/clobber/kdlock 的 12000 次并发
promotion 超时，前 125 场正确并排空；CPU 0/2 停在 kdlock 队列等待，CPU 1/3
处于 native_halt，持久日志报告 RCU stall。该场未进入正式计时，未强制卸载；
按恢复规则保存串口/monitor/journal 后重启。并发晋升停滞的根因尚未修复，
不能将其称为 TCLock 正确性通过或 kdlock 冷路径通过。

恢复后基础/相关单元 3 个入口及 benchmark 22 项检查通过；统一单 CPU 准备的
c16/t4 六臂短测全部正确并排空，再独立运行 `compare-steady/`。不拼接旧批次。

TCLock 移植构建保留自定义栈切换的 objtool 栈展开告警，不屏蔽告警、不承诺
完整 unwind。真实汇编测试验证六寄存器/RSP、128 轮双栈往返、64 次获取返回及
64 次委托 unlock 续点；本轮 live 是单锁、全局计数器正文。嵌套、跨 NUMA、
task/per-CPU 正文、服务调用、异常退出和通用 hook 热卸载没有由这轮验证。
原始上游 mutex 的 guest task 结构兼容问题也不因此解决。

## 证据

guest 根目录 `/root/kdlock-evidence/tclock-native-20260918/`：失败、各阶段 smoke、
两个完整矩阵尝试、最终稳态矩阵和独立采样分别保存。最终源身份为
`host-source-steady.json` 与 `compare-steady/source-sha256.json`；保留七份二进制、
两 caller 反汇编、每场数据/计数/发布/退休/日志。`failed-boot-kernel.log` 与
`monitor-failure-*.txt` 保存并发晋升故障，不能从最终成功汇总中抹去。

宿主 [完整证据归档](/tmp/kd-tclock-native-20260918/evidence.tar.gz)，SHA256：
`2329bb3587952742e0a8c780a75514cdfc66d3051c235206a65b0a4847f7a97b`。
[只读复核脚本](/tmp/kd-tclock-native-20260918/audit.py)与
[复核结果](/tmp/kd-tclock-native-20260918/audit.json)核对冻结字节、上游哈希、
数据/CPU/状态、正文数、发布及退休、36 组中位数、六场采样和长批次原生结果。
复核通过：225 个冻结源文件、七个二进制、180 场矩阵和 20 场长批次检查一致。
归档不认证来源，也不代替本轮真实 guest 运行。

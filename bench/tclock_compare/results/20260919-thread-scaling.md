# 2026-09-19：1/4/8/16/20 线程三方对照与伪共享检查

**150/150 场正确且排空，共 147,000,000 次完整操作。** 本轮重新构建并测量
Linux 原生、完整 TCLock 原生栈委托及 kdlock JIT，未修改锁实现。运行器新增
8、16 线程选项，原默认矩阵不变。以下全部来自本轮，未拼接历史成绩。

kdlock 的收益与线程数及临界区大小有关：4 线程仍明显落后；8 线程时，
1 cacheline 比 Linux/TC 低 38.9%/7.1%，16 cacheline 则高 9.8%/28.5%。
16/20 线程的实际 JIT 均超过 99%；1 cacheline 仍略低于 Linux，16 cacheline
比 Linux 高 64.6%/61.3%。高 JIT 比例本身不保证胜过原生锁。

## 完整操作吞吐

`clobber` caller ABI；1/16 cacheline × 1/4/8/16/20 线程 × 三种后端 × 五轮。
每线程 100000 次，使用 node 0 的 CPU 0 至线程数减一；奇数轮反转后端顺序。
单位 **Mops/s**，五轮中位数，越高越好。代理比例另取中位数，不一定来自
同一场；KD/Linux、KD/TC 是吞吐中位数之比。

| cacheline | 线程 | Linux 原生 | TCLock | kdlock | KD/Linux | KD/TC | TC 委托 | KD JIT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 10.7080 | 8.2927 | 8.6061 | 0.804 | 1.038 | 0.00% | 0.00% |
| 1 | 4 | 2.9246 | 1.6521 | 0.8755 | 0.299 | 0.530 | 48.50% | 53.61% |
| 1 | 8 | 3.0756 | 2.0226 | 1.8789 | 0.611 | 0.929 | 66.78% | 91.62% |
| 1 | 16 | 3.1373 | 2.3186 | 2.9376 | 0.936 | 1.267 | 76.25% | 99.56% |
| 1 | 20 | 3.0295 | 2.7698 | 2.9902 | 0.987 | 1.080 | 94.22% | 99.75% |
| 16 | 1 | 9.4547 | 6.7685 | 8.3747 | 0.886 | 1.237 | 0.00% | 0.00% |
| 16 | 4 | 1.9056 | 1.2023 | 0.8633 | 0.453 | 0.718 | 45.69% | 52.23% |
| 16 | 8 | 1.7452 | 1.4920 | 1.9167 | 1.098 | 1.285 | 59.12% | 92.52% |
| 16 | 16 | 1.7578 | 1.8552 | 2.8925 | 1.646 | 1.559 | 97.06% | 99.62% |
| 16 | 20 | 1.7942 | 1.5181 | 2.8936 | 1.613 | 1.906 | 53.98% | 99.80% |

四十场多线程 TCLock 与四十场多线程 kdlock 会话均实际代理，正文总数分别
为 **35,969,610** 和 **45,404,901**。两者各十场单线程的代理数均为零，
按 NO_DELEGATION/NO_JIT 记录；Linux 五十场不加载 provider。
TCLock 原生委托计数不是 JIT 计数。

五轮吞吐的最小值至最大值如下，单位 Mops/s；不剔除低吞吐样本：

| cacheline | 线程 | Linux 范围 | TCLock 范围 | kdlock 范围 |
| --- | --- | --- | --- | --- |
| 1 | 1 | 9.7056–11.2062 | 7.2381–8.5332 | 7.7031–9.6959 |
| 1 | 4 | 2.8545–3.1138 | 1.5137–1.6676 | 0.8564–0.9117 |
| 1 | 8 | 2.9933–3.0874 | 1.6753–2.1079 | 1.7728–1.9387 |
| 1 | 16 | 3.0994–3.1518 | 1.9880–2.7374 | 2.9251–2.9979 |
| 1 | 20 | 2.9884–3.0403 | 1.8709–2.8673 | 2.9779–3.0026 |
| 16 | 1 | 8.8956–10.0206 | 6.7016–7.7499 | 8.2467–8.6712 |
| 16 | 4 | 1.6467–1.9187 | 1.1899–1.4346 | 0.8226–0.8843 |
| 16 | 8 | 1.7000–1.7952 | 1.3592–2.0003 | 1.8484–2.0409 |
| 16 | 16 | 1.7379–1.7845 | 1.4750–1.8903 | 2.7813–2.9066 |
| 16 | 20 | 1.7779–1.7975 | 1.4117–1.9075 | 2.8107–2.9489 |

十万次单线程批次包含起跑至最后 ioctl 返回的开销，不能直接解释为纯锁入口
延迟。本轮没有重复千万次单线程对照；此前独立的长批次结果保留在
[上一轮报告](20260919-state-access.md#单线程长批次)，不是本轮数据。

<a id="batch-length"></a>

## 批长、代理比例与成本摊销

逐场从本次原始日志复算 `jit_success / combiner`，TCLock 使用测量前后的
`completed` 与 `batches` 差值之比；表中是五场平均批长的中位数，不是单批
长度分布。各实现对 batch 的计数位置不同，不能视为相同管理成本单位。

| cacheline | 线程 | TC 平均批长中位数 | KD 平均批长中位数 | TC 委托比例范围 | KD JIT 比例范围 |
| --- | --- | --- | --- | --- | --- |
| 1 | 4 | 1.37 | 1.97 | 45.13%–49.61% | 52.23%–55.82% |
| 1 | 8 | 2.34 | 12.44 | 51.11%–76.29% | 91.09%–91.92% |
| 1 | 16 | 3.68 | 336.92 | 50.07%–98.80% | 99.53%–99.61% |
| 1 | 20 | 41.13 | 571.66 | 55.20%–99.28% | 99.71%–99.81% |
| 16 | 4 | 1.06 | 1.99 | 45.44%–52.99% | 51.85%–58.95% |
| 16 | 8 | 1.46 | 14.46 | 52.80%–93.19% | 89.98%–92.83% |
| 16 | 16 | 51.20 | 347.62 | 55.00%–99.51% | 99.38%–99.73% |
| 16 | 20 | 1.17 | 688.81 | 53.16%–97.89% | 99.67%–99.81% |

所有四十场多线程 kdlock 会话的目标锁均已 DELEGATE，samples=10000；
`jit_not_ready=native_fallback=jit_disabled=waiters=0`，并满足
`batch.entries == jit_success == measured jit_bodies`、
`batch.entries - batch.ww_jumps == combiner`。单 CPU 准备未产生代理正文。
普通 clobber 已晋升入口跳过 hotlock record；本轮没有修改监测策略。

4 线程平均每批约两次正文，8 线程约 12–14 次，16/20 线程达数百次；这与
批次管理成本得到更多摊销相符，但没有单独统计批次结束原因，不能完成因果
归因。TCLock 保留 `need_resched()` 退出等规则，其五轮批长和委托比例波动
较大；本轮没有抹去这些策略差别或只选择高委托率样本。

<a id="false-sharing"></a>

## 伪共享检查：实际布局与访问角色

测量结束并确认空闲后，对**本次冻结的模块**使用 `pahole` 和 ELF 符号表检查，
按 64B cacheline 分析。已确认布局及源码访问角色，**未采集 HITM/cache-to-cache
事件，也未进行 padding A/B**，因此不能给出各候选造成的耗时百分比。

### 与当前单锁热循环直接相关的候选

`kd_spin_node` 大小 **64B**，数组起点对齐 64B；`next` 在偏移 **0**，
`completed/locked` 在 **32/33**，预取地址在 **48/56**。后继 CPU 发布
`previous->next` 时，前一个 waiter 正在另一 CPU 上轮询自己的 `locked`：
两个不同字段同处一行，会产生额外失效，是明确存在的伪共享访问模式。
完成标志本身的发布/观察则是协议需要的真共享，不能一起算成可消除成本。
见 [node 定义](../../../include/kd_spinlock.h)与
[发布/等待汇编](../../../kernel_module/spin/wait.inc)。

本次 TCLock 的 `komb_node` 为 **120B**，`next=0`，`completed/locked=68/69`。
常用 node 0 从 64B 边界开始，把入队链接与轮询字节分在两行。这个布局区别
值得做单独对照。但它的数组步长是 120B，**并非每个 node 都独占整数条行**：
node 0 的完成标志会与 node 1 的开头共行；后者涉及嵌套/IRQ 节点，本轮未覆盖。
不能笼统说 TCLock 完全没有伪共享。见
[TCLock node](../../../tclock_backend/include/spinlock/komb.h)。

kdlock 目前把 node 压到一行，也减少了 combiner 的读取和预取足迹。
若将通知字段拆到第二行，既可能减少 waiter 轮询干扰，也会增加访问行数和
节点空间；本次成绩不能预先证明哪一种布局更快。

### 多锁及复杂路径的候选

| 对象 | 冻结布局 | 可能的干扰及适用范围 |
| --- | --- | --- |
| `kd_spin_gates[1024]` | 每项 **40B**；数组在 `.bss+0xd820`，相对行偏移 **32**；`word=0, origin=8, owner=16, generation=24, owner_cpu=32, held=36` | 相邻 gate 可共享一行；不同 CPU 更新不同锁的 gate 会互相失效。有的项跨行，同一 gate 的调度字与 owner 元数据也可能互相干扰。本次是单锁正文，不能据此解释全部差距 |
| `kd_spin_entry` ticket | 每项 **88B**，pool 中 entries 从偏移 **16** 开始；`native_refs=72`，无逐项 cacheline 对齐 | 相邻 ticket 可共行。普通 root 的 ticket 主要由原 CPU 操作；远端 native borrow 修改 guard/native_refs 时才可能干扰同池其他 ticket。本次没有嵌套/native 后缀，优先级低于 node |

[gate 查找与写入](https://github.com/hailongeric/kdlock/blob/7e2460c/kernel_module/kd_spin_gate.c)、
[ticket 生命周期](../../../kernel_module/kd_spin_entry.c)保留真实 owner、原生 L
及 ACK 规则。gate 从 40B 扩到 64B 会把表从 40KiB 增至 64KiB；只对齐数组
起点不能解决 40B 步长问题。若验证跨锁伪共享，需要独立多锁负载及各项地址，
不能用本次单锁吞吐替代。

### 已隔离的部分，以及 padding 无法解决的共享

| 对象 | 核对结果 |
| --- | --- |
| request 池 | `kd_spin_exec_request` **768B、64B 对齐**，池由 `vzalloc` 分配；相邻请求不共行。waiter/combiner 共用同一 request 的所有权交接仍有必要通信 |
| 诊断 slot | **128B、64B 对齐**；addr/jit_disabled 在首行，`waiter_count=64` 独占下一行，已避免计数写入干扰禁用状态读取 |
| 实时 `waiter_count` | 每个排队请求仍对同一计数做原子增减，属于**真共享**；加 padding 不会消除。事件/正文总数已是 per-CPU，不能与这个实时计数混为一谈 |
| source 状态/计数 | `kd_sources=.bss+0xc540`，`kd_source_frame_gate=.bss+0xc780`，**不在同一行**，排除最初的共行怀疑。frame 计数与冷路径 source_lock 同行；本轮 daemon 已停止，没有证据表明该锁造成稳态干扰。frame 计数的跨 CPU 原子操作仍是真共享，普通路径按批次摊销 |
| 工作负载 | `sc_control/sc_lock/sc_data` 在 `.bss+0/+64/+128`，各自对齐；数据 slot 步长 64B。150 场实际地址均检查通过。临界区内各线程修改相同计数器属于负载刻意要求的真共享 |
| 客户端 | ready/go 分行；worker 结果结构未逐个隔离，但每批仅一次 ioctl/结果写回，不是每次锁操作都更新，可能影响批次边界，不能直接当作锁热循环瓶颈 |

后续最有价值的两个独立实验是：**node 链接/通知分行**，以及**实时 waiter
诊断计数的可选观测或分片方案**。前者针对伪共享；后者减少共享 RMW，必须
保留启用观察器时的计数语义。source 计数还承担关闭准入与排空的原子性，不能
作为普通统计直接删除。本轮仅审计，没有实施或宣称这些优化已提速。

## 环境、验证与复现

- recovery guest `6.1.159-kdclobber1`，Build ID
  `db937d722ee2f2668acb12dc6f105aeea33b7c5c`；源码、配置、build 和 live 身份匹配。
  40 vCPU、28GiB、双 NUMA；测量均使用 node 0，vCPU 不表示独占宿主核。
- 保留 frame pointer、缓解设置、`nokaslr`、voluntary 抢占和 watchdog。
  源码位于 guest ext4；宿主仅编辑、控制 VM 和只读复算，没有运行 benchmark。
- 起点 Git `17f146e52f9f52485b8211addb7dab7195e70452`，加 `run.py` 线程选项与
  运行说明修改；运行前 365 个仓库文件哈希与 guest 相同。锁实现未改动。
- 三方使用同一 clobber workload ELF；每场重新加载模块。CPU 0 预热一次、
  准备 12000 次；kdlock 等待唯一入口发布并停止 daemon/translator 后测量。
- kdlock `spin_native_cache=1, spin_prefetch=2, jit_timing=N`；TCLock batch 上限
  1024。默认 `mutex_jit=1`，但本轮只测 spin，不记为 mutex 验证。
- 两个基础 C 单元入口及 `spin/test_tclock_context.py` 共 **3/3 通过**。
  线程矩阵 dry-run 校验为 150 个唯一会话、30 组各五轮、CPU 与交替顺序正确。
- 逐场检查全部数据增量、次数、CPU 亲和性、IRQ/preempt 状态、实际正文和排空。
  无内核 WARN/BUG、panic、lockup；kdlock 退休后的 frames/modules/writers 均零，
  TCLock 完成数等于委托数且 quiescent=1，最终 guest 空闲。
- 未重跑 legacy ABI、复杂功能矩阵、冷晋升、跨 NUMA、长单线程或硬件采样。
  此前并发冷晋升失败仍未解决；本轮是单 CPU 准备后的稳态比较。TCLock 独占
  目标锁协议，与 Linux 同锁混用的兼容性没有改变。

确认恢复快照 `pre_static_boot_20260915` 后，在 guest 执行；SSH 另加外层超时：

```sh
cd /root/host_fs/kdlock
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export KDIR=/root/linux-6.1.159-kdclobber1
export KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 LC_ALL=C
make -C tests/unit run PY_TESTS=spin/test_tclock_context.py
timeout --kill-after=15s 3600s python3 bench/tclock_compare/run.py \
  --abis clobber --threads 1 4 8 16 20 \
  --output /root/kdlock-evidence/spin-scale-20260919/compare \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

输出目录必须不存在。布局审计在测量全部结束后执行，未与计时并发运行。

## 证据

冻结并独立核对 **226 个源码输入、6 个二进制**，其中 141 个非文档正式输入
与初始及当前工作区匹配；测量结束后再确认 guest 的冻结输入未变化。
离线审计复算 150 场吞吐、五轮中位数、交替顺序、数据、ABI/发布及实际正文；
批长复算单独核对 80 场多线程代理会话。没有执行归档中的脚本或二进制。

- guest 原始目录：`/root/kdlock-evidence/spin-scale-20260919/`；归档为同级
  `spin-scale-20260919-evidence.tar.gz`。包括全部 JSON/日志/源码/二进制、单位测试、
  冻结检查、pahole 输出、ELF 符号表、操作脚本及快照证据。
- 宿主 [evidence.tar.gz](/tmp/kd-spin-scale-20260919/evidence.tar.gz)：
  **3,275,013 bytes**，SHA256
  `17e1c0a48244d3fe5aebf6fc1fbadf442f7eb2945f5258ee21a67b659f199ef2`。
- [独立审计](/tmp/kd-spin-scale-20260919/audit-compare.json)、
  [批长复算](/tmp/kd-spin-scale-20260919/batch-analysis.json)、
  [布局与符号偏移](/tmp/kd-spin-scale-20260919/layout/symbols.json)。
- [审计脚本](/tmp/kd-spin-scale-20260919/audit.py)、
  [批长脚本](/tmp/kd-spin-scale-20260919/batch-analysis.py)、
  [guest 布局采集脚本](/tmp/kd-spin-scale-20260919/capture-layout.py)。

# 2026-09-19：node 通知分行与 gate 数组隔离

已修复[此前布局审计](../../tclock_compare/results/20260919-thread-scaling.md#false-sharing)
发现的两处共行问题：node 的后继链接与 waiter 通知分行，gate 的每项边界和
数组步长均按 64B 对齐。**7 个单元入口、1 项 gate 内核组件自测、3 项定向
live 及 40 场性能对照全部通过并排空。** 本轮没有改内核或运行全量测试。

收益有竞争强度差别：20 线程、1/16 cacheline 吞吐增加 **6.55%/7.56%**，
实际 JIT 仍约 99.7%；4 线程中位数下降 **6.49%/5.91%**，JIT 比例也下降。
不能将结构上消除这两处伪共享写成所有负载都提速。

## 实现与空间

| 对象 | 修复前 | 修复后 |
| --- | --- | --- |
| node 大小/对齐 | 64B；per-CPU 数组起点对齐 | **128B / 64B 对齐**，嵌套槽也按完整两行排列 |
| node 链接/元数据 | `next=0, execution=40, prefetch_regs=48, prefetch_sp=56` | 偏移保持不变，均在首行；预取标志位于 32/33 |
| node 通知 | `completed=32, locked=33`，与 next 共行 | **64/65**，单独第二行；仍相邻、用一次 16 位 release store 发布 |
| gate | 40B 步长；数组起点相对 cacheline 偏移 32 | **64B 步长、64B 对齐**；每项占一行，字段内部偏移保持不变 |

源码为 [kd_spinlock.h](../../../include/kd_spinlock.h)、
[kd_spin_gate.h](https://github.com/hailongeric/kdlock/blob/7e2460c/include/kd_spin_gate.h)。通过成员对齐约束类型大小和
数组步长，避免只对齐数组首地址。生产
[lifecycle](../../../kernel_module/spin/lifecycle.inc)增加编译期大小、对齐及通知
偏移断言，防止后续字段变更破坏隔离。等待汇编继续使用 `offsetof`。

本次模块 `pahole` 与 ELF 证实：`kd_spin_nodes` 位于 `.data..percpu+0x1640`，
数组大小从 256B 增至 512B；`kd_spin_gates` 从 `.bss+0xd820` 的 40960B
改为 `.bss+0xd840` 的 65536B。两种 section 的对齐均为 64B。
四个 node 每可能 CPU 增加 **256B**，当前 40 vCPU 合计 10KiB；gate 表增加
**24KiB**。这是对象有效空间增量，未测分配器取整后的物理内存增量。

首行供入队链接、combiner 查后继及预取读取，第二行供 waiter 轮询与完成发布。
TCLock 常用 node 0 也把链接与通知分行，但其 120B 步长会让相邻槽部分共行；
这里使用 128B 步长，覆盖所有四个节点。gate 隔离解决不同锁相邻项的干扰；
同一锁的排队与 owner 通信、共享 waiter_count 的原子增减仍然存在。
没有改变 L/S、tail 编码、请求引用、source 租约或 owner/ACK 协议。

## 同环境交替对照

本轮重新执行旧、新两臂：1/16 cacheline × 4/20 线程 × 五轮，共 **40 场、
48,000,000 次完整操作**，全部有实际 JIT。每线程十万次；奇数轮反转两臂
顺序；使用同一份新构建 clobber workload，CPU 0–3/0–19、node 0。
以下为五轮中位数；比例独立取中位数，吞吐越高越好。

| cacheline | 线程 | 修复前 Mops/s | 修复后 Mops/s | 变化 | 修复前 JIT | 修复后 JIT |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 0.9271 | 0.8669 | -6.49% | 55.15% | 48.72% |
| 1 | 20 | 3.0110 | 3.2082 | +6.55% | 99.61% | 99.72% |
| 16 | 4 | 0.8340 | 0.7848 | -5.91% | 52.27% | 49.74% |
| 16 | 20 | 2.8906 | 3.1092 | +7.56% | 99.78% | 99.70% |

五轮范围如下，未排除较慢样本：

| cacheline | 线程 | 修复前 Mops/s 范围 | 修复后 Mops/s 范围 |
| --- | --- | --- | --- |
| 1 | 4 | 0.8482–0.9345 | 0.8182–1.0074 |
| 1 | 20 | 2.9189–3.1229 | 3.1447–3.2737 |
| 16 | 4 | 0.8025–0.8583 | 0.7647–0.8024 |
| 16 | 20 | 2.8773–2.9617 | 3.0919–3.2367 |

20 线程下修复后五轮吞吐均高于本轮旧版本的最高样本，且保持 99% 以上 JIT。
4 线程仍处于原生/JIT 混合路径；增加访问行数及改变队列推进可能抵消隔离收益，
但本轮未单独采样原因。没有用降低代理覆盖率解释四线程为提速，也没有掩盖回退。

两处布局同时改变，这不是分别隔离 node 与 gate 净收益的四臂实验。当前正文
只竞争一把锁，**没有测量跨锁 gate 伪共享的性能收益**；该项通过实际布局和
多键 map/互斥检查确认隔离，若量化收益仍需独立多锁负载。没有 HITM 采样。
没有重测 1/8/16 线程、长单线程或 TCLock/Linux；此前五档三方矩阵保留为修复前
独立基线，不能与本轮新 kdlock 拼接计算新三方倍率。

## 验证与复现

- recovery guest `6.1.159-kdclobber1`，Build ID
  `db937d722ee2f2668acb12dc6f105aeea33b7c5c`；内核源码/配置/build/live 身份核验通过。
  40 vCPU、28GiB、双 NUMA，保留 frame pointer、缓解、voluntary、nokaslr、watchdog。
- 两个基础 C 程序及 batch/gate/entry/wait/shadow 共 **7 个入口通过**。等待
  夹具改用真实生产 node，执行 96 次 shadow 等待和 160 次请求恢复；gate
  夹具含 12 线程、48 个碰撞键的并发发布。NUMA off/on 队列夹具通过。
- `test_15_spin_native_gate.sh`：四 CPU、516 次互斥操作，无重叠和上下文错误；
  这是 **JIT=0 的组件验证**。mode-0、mode-8 三阶段、mixed-spin 则均有实际
  JIT，保留完整数据、owner/ACK、IRQ/preempt 与排空判定。
- 无检测到的内核 WARN/BUG、panic 或 lockup；最终 guest 空闲。源码/二进制
  在计时前冻结、逐场核对、计时后再次核对。布局提取在全部测量结束后运行。
- `spin_native_cache=1, spin_prefetch=2, jit_timing=N`。性能 provider 的默认
  `mutex_jit=1`；mixed-spin 原有脚本为 0。未执行 mutex 回归，不据此声明覆盖。
  每场均单 CPU 准备、发布完成后停止 daemon 再测量；既有冷晋升问题未修复。

按[操作手册](../../../docs/AGENTS.md)确认快照 `pre_static_boot_20260915`，在
固定 venv 与 KDIR 的 guest 执行，SSH 和每条 live/bench 命令均有外层 timeout：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_batch.py spin/test_spin_gate.py spin/test_spin_entry.py spin/test_spin_wait.py spin/test_spin_shadow.py'
timeout 240s bash tests/live/test_15_spin_native_gate.sh
python3 tests/regression.py --case mode-0 --case mode-8 --case mixed-spin \
  --timeout 240 --output /root/kdlock-evidence/spin-sharing-20260919/live
python3 /root/kdlock-evidence/spin-sharing-20260919/compare.py \
  --abis clobber --threads 4 20 \
  --output /root/kdlock-evidence/spin-sharing-20260919/compare \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

完整超时、环境和操作见归档内 `validate.sh`、`run-bench.sh`；输出必须为新目录。
`compare.py` 复用现有 `BackendSession`，旧臂使用此前已冻结的模块，测量前核对
其原始 SHA256。新旧正式运行输入仅有两份布局头文件及生命周期静态断言不同；
没有为旧臂改锁算法或关闭观察器。

## 证据

Git 起点 `17f146e52f9f52485b8211addb7dab7195e70452` 加本轮前已有的五档线程
运行器/文档，以及本轮六个源码/测试文件修改。冻结输入而非 HEAD 单独标识
测量版本。独立审计核对新版本 **227** 个源码输入、旧版本 **226** 个输入、
六个二进制、40 场数据及中位数、实际 JIT、生成物 ABI 和加载臂身份。
三个 live 的 313 个源码输入及各协议归档另经 `verify_evidence.py` 校验。

- guest：`/root/kdlock-evidence/spin-sharing-20260919/`，原始逐场证据及操作脚本；
  同级 `spin-sharing-20260919-evidence.tar.gz` 为完整归档。
- 宿主 [完整归档](/tmp/kd-spin-sharing-20260919/evidence.tar.gz)：**10,967,929 bytes**，
  SHA256 `b3b656ad9cc3b6ee68137ed3b59bae1a0b1601085e9775fa6da3c7900b07d3bc`。
- [独立对照审计](/tmp/kd-spin-sharing-20260919/audit-compare.json)、
  [live 归档审计](/tmp/kd-spin-sharing-20260919/live-audit.json)、
  [布局符号](/tmp/kd-spin-sharing-20260919/symbols.json)、
  [审计脚本](/tmp/kd-spin-sharing-20260919/audit.py)。脚本只读证据，不执行归档负载。

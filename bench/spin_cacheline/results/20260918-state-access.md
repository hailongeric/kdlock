# 2026-09-18：减少普通 spin 的状态访问

批次保留诊断 slot 身份，waiter 退出复用入队取得的 slot；实时计数和禁用状态
仍按原语义读取/更新。诊断计数单独占一条缓存行，普通请求标志、ABI 和包分类
集中在 request 前两条缓存行。普通 root 只在最终 batch prepare 检查 readiness，
正常出口用专用 helper 完成终态验证和物理解绑，随后仍由锁层发布完成。

这些改动没有复制可变状态、取消准入检查或改变 source、原生 L/S、owner/ACK。
复杂出口、SELFTEST 的 complete/观察/pop、借用包及两种 wrapper ABI 均保留。
实现边界见 [DESIGN](../../../docs/DESIGN.md#911-reuse-before-copy-contract)，
功能验证见[测试记录](../../../tests/README.md#spin-state-access)。

## 五个递进版本

五臂使用同一内核、caller-clobber v1 调用者、负载和编译选项，均为
`spin_prefetch=2`、`spin_native_cache=1`。每配置五轮，奇数轮反转五臂顺序。

| 名称 | 相对上一阶段的变化 |
| --- | --- |
| before | 上一轮已实测的 prepared provider，64 字节 node、原状态访问方式 |
| slot | batch 复用诊断 slot；request 保留入队 slot，退出不重新查找 |
| split | 诊断 slot 从 16 增至 128 字节，身份/禁用与 waiter_count 分行 |
| layout | request 按 64 字节对齐、热字段前移，预取覆盖两条元数据行 |
| final | 身份 lookup 与准入分开，去掉普通请求重复 readiness；正常 root 专用完成/解绑 |

before 保留上一轮二进制和本轮开始时的源文件快照；84 个正式 provider/翻译器/
观测输入与上一轮冻结记录匹配。slot/split/layout 各自保留编译后的 provider 和
私有构建源码。它们是累计变化的独立镜像，差值同时包含编译器与代码/数据布局
变化，不能解释为某条 load 或原子操作的单独周期成本。final 的两项处理改动
也没有进一步拆成两臂。

## 竞争配置

**100/100 场正确完成并排空，共 1.2 亿次完整操作，全部有测量期实际 JIT。**
1/16 cacheline × 4/20 线程，每线程十万次。以下为五轮中位吞吐，Mops/s。

| cacheline | 线程 | before | slot | split | layout | final | final / before |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 0.8423 | 0.8589 | 0.8616 | 0.8595 | 0.8629 | +2.44% |
| 1 | 20 | 1.7703 | 1.9656 | 2.0686 | 2.2874 | 2.9847 | +68.60% |
| 16 | 4 | 0.8082 | 0.7980 | 0.8668 | 0.8723 | 0.8430 | +4.31% |
| 16 | 20 | 1.7338 | 1.9184 | 2.0409 | 2.2409 | 2.8774 | +65.96% |

实际 JIT 比例另取五轮中位数，单位为百分比：

| cacheline | 线程 | before | slot | split | layout | final |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 54.816 | 54.246 | 54.651 | 53.740 | 54.815 |
| 1 | 20 | 99.823 | 99.776 | 99.771 | 99.737 | 99.778 |
| 16 | 4 | 56.441 | 54.745 | 53.561 | 53.561 | 52.665 |
| 16 | 20 | 99.817 | 99.794 | 99.803 | 99.777 | 99.752 |

20 线程两点的主要结论成立：最终版本比同场基线提高 68.6%/66.0%，JIT 均约
99.8%，没有靠明显降低代理覆盖率解释收益。递进阶段在这两个点均改善吞吐。
20 线程五次吞吐范围：1 cacheline 的 before 为 1.748–1.805，final 为
2.893–3.001 Mops/s；16 cacheline 分别为 1.709–1.768、2.850–2.914。
4 线程增量较小且不随阶段单调改善；16 cacheline 的最终 JIT 比例从 56.44%
降到 52.66%，该配置的吞吐变化还包含原生/JIT 混合比例变化，不作为独立服务
成本降低的证明。不能把一个版本在高竞争下的收益外推到所有负载。

## 单线程长批次

同一 before/final、1/16 cacheline，每场一千万次、五轮交替；**20/20 场正确
完成并排空，共 2 亿次操作，全部 NO_JIT**。记录的是经过 kdlock 的完整原生
操作成本，包括两端调用者代码。

| cacheline | before ns/次 | final ns/次 | 差值 |
| --- | --- | --- | --- |
| 1 | 44.552 | 44.589 | +0.037（+0.084%） |
| 16 | 49.826 | 50.054 | +0.228（+0.457%） |

本轮单线程中位成本略增，幅度小于 0.5%，两组前后样本范围均重叠；
没有把该差异写成原生提速。
这些结果独立于短竞争矩阵，不能与早期短单线程测量拼接。

## 结构与正确性

guest `pahole` 确认：node 仍为 64 字节，frame/context 仍为 672/5400 字节；
request 从本轮实际基线的 720 增至 768 字节，12 槽共 9216 字节，每 CPU 增加
576 字节有效预留，前后 `vzalloc` 均向三页取整。旧文档中的 664/5336/712 为
滞后尺寸，当前协议文档已据实更正，并非本轮增加了 frame/context。

| 字段 | 新 request 内偏移 |
| --- | --- |
| 诊断引用 / users | 0 / 8 |
| 普通路由标志 | 12–16 |
| frame / entry_abi / packet_state | 24 / 88 / 92 |
| pt_regs | 96 |

frame 内热头部为 72 字节，ABI/包分类由寄存器包之后移到之前。request 的引用
和路由字段各保留一份，冷账本仍预分配且按需启用；内存开销没有被记作下降。
诊断 slot 的 addr/jit_disabled 位于 0/8，waiter_count 位于 64，每槽占 128
字节。身份在模块会话内稳定，但禁用状态仍逐请求 acquire 读取、计数仍实时
原子更新；复杂入口没有稳定引用时仍按锁地址查找。

最终 `run_combiner` 的普通准备分支调用 `kd_exe_spin_batch_prepare`，不再先
调用 readiness helper；复杂执行仍保留其检查。专用退休仍调用原有
`kd_exec_frame_complete_single_spin` 做终态验证，并直接解绑，省掉通用 pop；
不是取消所有函数调用或生命周期工作。反汇编保留原始重定位输出与按函数地址
范围过滤的 `combiner-hot.asm`，避免把 objdump 附带的其他函数重定位算进热点。

十个基础/受影响单元入口和六项 live 通过。恢复夹具直接采用生产 request
布局，验证 160 次真实恢复；保护页探针验证新预取仍不解引用后继 frame/包。
live 覆盖普通 spin、hostcall、mode-8 三阶段、原生互操作和 legacy mutex；
核对实际 JIT、单次副作用、owner/ACK、IRQ/preempt、source 退休及最终排空。
初期测试夹具的旧偏移/简化类型错误和修正后的通过日志分别保留。没有全量回归、
内核重建或新一轮 TCLock/Linux 三方运行，不能计算这两个后端的新性能倍率。

## 环境、复现与证据

recovery guest 为 `6.1.159-kdclobber1`，Build ID
`db937d722ee2f2668acb12dc6f105aeea33b7c5c`；40 vCPU、28 GiB、双 NUMA，使用
node 0 的 CPU 0–19。保留 frame pointer、缓解、watchdog、nokaslr、voluntary。
每场都单 CPU 准备/晋升、确认发布，再停止 daemon 后测量；这不修复既有并发
冷晋升问题。五次样本与同一虚拟机的结果不是跨机器或长期稳定性证明。

运行器复用 `bench/tclock_compare` 的完整会话、数据/JIT/IRQ/preempt/排空判定，
冻结脚本位于证据目录的 `compare.py`。遵循[操作手册](../../../docs/AGENTS.md)，
只在已核实恢复快照、固定 venv/KDIR 的 guest 运行，并加外层 timeout：

```sh
python3 /root/kdlock-evidence/spin-state-20260918/compare.py \
  --output /root/kdlock-evidence/spin-state-repeat/compare --abis clobber \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
# 长批次另选新 output，再加：
# --backends before final --threads 1 --iterations 10000000
```

必须保留该目录中 before/slot/split/layout 的对应镜像，不要用当前源码重建后
冒充历史阶段。源码和二进制每场前核对，运行中不改写冻结输入。

原始证据在 guest `/root/kdlock-evidence/spin-state-20260918/`；宿主归档为
`/tmp/kd-spin-state-20260918/evidence.tar.gz`，27,732,338 字节，guest/host SHA256
一致：`2a519820a466bbabc6e2c43ed649db90cd72cf8954752e3c9d0739ca064a7850`。
包含基线源码、各阶段 provider/构建源码、kernel baseline、逐场数据与生成物、
源码/二进制哈希、live 与单元日志、布局及汇编。竞争和长批次两次最终 provider
构建仅 `.BTF` 区段不同，其余区段字节一致。

宿主只读独立审核重新计算完整数据、实际 JIT、发布不变、五轮中位数与退休/
排空：竞争 **100 场、1.2 亿次**，长批次 **20 场、2 亿次**，均通过。每组
冻结 231 个源码/文档/私有 provider 输入，其中 141 个正式运行输入匹配当前
工作区。六项 live 的独立归档审核通过；312 个冻结输入匹配当前版本，另一个
未被 live 执行的 unit 夹具在之后修正旧布局断言并单独通过。文档在测量后更新，
不代表重新运行。该审核核对捕获字节和记录，不认证外部日志来源。

- [竞争矩阵审核](/tmp/kd-spin-state-20260918/audit-compare.json)
- [单线程审核](/tmp/kd-spin-state-20260918/audit-long.json)
- [阶段源码审核](/tmp/kd-spin-state-20260918/stage-source-audit.json)

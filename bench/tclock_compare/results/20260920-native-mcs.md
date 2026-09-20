# KD 不代理路径：从 CAS 争抢改为共用 MCS

2026-09-20，以 `d3b05c9` 为代码基线。用户要求 KD 即使不走 JIT/代理也应保留
高效的内核排队锁基础。本轮修改仅限 KD spin；没有替换 Linux 锁或重写 mutex。

## 实现和参考边界

参考仓库保留的 [TCLock komb.c](../../../tclock_backend/komb.c) 中每 CPU 四节点、
pending/MCS 和不可代理节点交接逻辑。该版本的原生排队分支受 `ENABLE_IRQS_CHECK`
控制，当前 TCLock benchmark 默认未开启它；本次借鉴算法，不把代码分支存在
当成此前实际测过此分支。

旧 KD 拒绝/冷锁路径反复 CAS 同一个完整锁字。现在使用同一个 KD 锁字和节点池：
无竞争 CAS → pending → MCS；排队者等待自身通知，队首等待物理锁。节点取得
队首并完成交接后即可复用，调用者继续持锁执行自己的正文，最后释放锁字。
不代理节点无 execution request/frame，不保存寄存器、不切换等待栈；仅真正
四节点耗尽才使用先读后 CAS。普通 task 根请求复用 fast-owner 解锁记录，
嵌套/IRQ 使用独立在途计数，直接 native bridge 解锁也正确释放 fast owner。

request 池耗尽、翻译未准备好，以及提前释放后的重新获取使用同一原生队列。
后三种路径保留已有 ticket；不因没有 JIT frame 就丢失原有所有权。
combiner 在批次入口和批内均检查不可代理边界；NUMA、prefetch、提前释放及
观察日志不得解引用原生节点的空 execution 指针。节点大小仍为 128 字节，
没有新增节点池或运行期分配。

## 小范围性能对照

全部在 `6.1.159-kdclobber2` recovery guest，c1，线程 1/4/8，每线程 100000 次，
各配置三次，单 CPU 48000 次预热。新旧同负载，使用显式 `--spin-delegate off`，
跳过热度/JIT 准入，JIT 正文必须为 0；翻译准备在计时外，标记 `DISABLED_CONTROL`。
因此这里不是 adaptive 的开销测量，也不是 JIT 性能结果。未跑全矩阵。

| 线程 | 旧 CAS（Mops/s） | MCS 初版 | 最终 MCS + owner | 最终相对旧 CAS | Linux 原生对照 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 8.180 | 7.778 | 7.788 | 0.952× | 16.595 |
| 4 | 3.782 | 2.994 | 3.100 | 0.820× | 3.793 |
| 8 | 2.183 | 3.393 | 3.589 | 1.644× | 3.853 |

数据为吞吐中位数。旧 CAS 来自 `cas-before/`（基线加固定准入控制）；MCS 初版为
`mcs-after-final/`；最终为 `final-control/`。Linux 来自稍早与 owner 优化版交替
测量的 `mcs-owner-final/`，并非与最后补充 bridge 配对修复后再次交替测量。
各目录保存各自的冻结源码/ELF，不能把不同版本拼成同一冻结矩阵。

8 线程的完整操作吞吐较旧 CAS 提高约 64%，达到上述 Linux 对照的约 93%；
4 线程短临界区仍比旧 CAS 低约 18%、比 Linux 低约 18%。单线程有明显跨场波动：
稍早 owner 优化版原始样本约 8.63–18.65 Mops/s，最终约 7.63–8.79 Mops/s；
三次小样本不支持稳定的单线程加速结论。不能据此宣称全负载达到 Linux 性能。
既有直接 ABI、抢占/所有权管理和队列交接仍有开销；本次未做逐指令归因。

## 正确性与限制

基础两项及 `test_spin_nondelegated`、`test_spin_direct`、`test_spin_shadow`、
`test_spin_outer_progress` 均通过。新增 pthread 测试直接编译生产原生队列，
8 线程完成 400000 次互斥操作，最终运行有 399925 次入队、399923 次本地等待；
检查每操作至多初始 CAS 和一次尾节点 claim CAS，不存在全局 CAS 重试循环。
CPU/抢占是替身，不能以此证明任意内核中断时序。

生产 combiner 的五个混合边界（包含批内无 frame 节点）在 NUMA 开关两种 fixture
中通过；保留既有 nested/OOO、拒绝、node 复用、frame 退休和 ACK 断言。
新增 owner 配对检查覆盖 root、nested、IRQ/pinned 替身及直接 native bridge。
比较运行器 8 项单测通过；普通观察 provider 和 SELFTEST + NUMA 的 W=1 构建通过，
保留既有换栈 objtool 警告。首次观察 patch 上下文失配日志保留，没有放宽 JIT 验收。

首次 live：plain/nested/early 的 JIT 正文分别为 232140 / 383750 / 99978，
每场完成 400000 次业务操作并排空；关闭代理的 nested/early 正文为 0，业务正确。
这五场属于 bridge 配对补充修复前的冻结源码。最终版本另行复核 JIT early 和
关闭代理的 nested：前者实际 JIT 正文 99944 次，后者为 0，各完成 400000 次
操作；业务正确，frames/modules/writers 均排空为 0。

未测全性能矩阵、跨 NUMA live、真实 IRQ/NMI 嵌套、真实四节点耗尽、mutex JIT live，
也未对新的热度收益策略作优化。原有更广并发/原生续跑缺口继续保留。

证据：guest `/root/kdlock-evidence/native-mcs-20260920/`。`unit.log`、`mixed-unit.log`、
`native-unit-final.log`、`runner-unit.log` 和构建日志定义对应测试输入；各 live 子目录
保存参数、内核身份、源码、ELF、JIT 镜像、业务数据、内核日志及 source retire。

最终普通 provider 构建、观察层两项检查及空闲检查通过。提交前仅补充文档/注释，
没有再改运行逻辑。归档：guest `/root/kdlock-evidence/native-mcs-20260920.tar.gz`，
SHA256：`ce90fd3fd949ea5148c3382a04c7e5ef9d03f93a479628c3b4c8e5bda7bca383`。
大型归档、ELF 及临时构建目录均不提交。

# 当前测试入口

当前内联热度/clobber壳与冷队列门槛已完成基础2组及直接相关4组验证，热度错误变体25项、
运行器21项通过。初次用户态ABI fixture使用8字节栈对齐导致SIGSEGV，改为libc所需的16字节
后原断言通过，未为此改生产代码。覆盖真实GS读取、双CPU共享热度、跨锁活跃寄存器、
等待/持锁期间变热、冷态与普通状态混合MCS 400000次及pin/在途归零。
`codegen/test_spin_paired_jit.py`执行实际wrapper，覆盖无手工push/pop的COMPLETE、入口拒绝、FULL/native续跑。
60性能配置各测一次：原批次9通过、1原NO_JIT失败保留，修正少线程判定后续50通过；
不能记作统一60/60通过。7场功能（gate/delegation控制、门槛0、nested/early、RCUHT）
及4场单线程PMU通过并排空。命令、失败与证据见[当前报告](../bench/tclock_compare/results/20260922-spin-cold-clobber-queue.md)。
[之前共享CPU cookie配对C壳验证](../bench/tclock_compare/results/20260922-spin-cpu-hot-cookie.md)仅作历史。
[第二阶段](../bench/tclock_compare/results/20260922-spin-cold-stage2.md)的8组及25项准入是历史验证。


当前 spin CPU 每4次合格MCS事件检查：冷捷径/队列门槛开启时，冷CPU统计合格队头获取，
其他情况保持入队采样；spin/mutex CPU 共用40亿TSC窗口；
mutex CPU 保持 1024 次入口检查，单锁保持第 33 次检查、25 亿窗口。

此前[完整三方bench](../bench/tclock_compare/results/20260922-spin-mcs4-full-benchmark.md)
30/30场通过，2940万次操作全部排空，8场竞争KD均有实际JIT；该轮未追加单元或adaptive功能。

此前阈值修改基于 `383249f`，在 guest 独立副本 `/tmp/kdlock-mcs4-jv7hhnwu/src` 验证：
基础及热度/MCS 定向单元 **5/5**、热度错误变体 **18/18** 检测、normal provider
`W=1` 构建通过。覆盖第 3/4、7/8 次 MCS、整批耗时、40 亿边界、冷却/重新变热、
mutex 1024 次检查和不变的单锁 33 次规则。内核身份核验为 `6.1.159-kdclobber2`。
构建有恢复汇编 objtool 及 Perl locale 警告。该次未加载模块或运行 live/性能测试，
主线程 guest 副本未改写；其单元/构建与上述后续bench属于不同验证批次。

验证命令：

```sh
make -C tests/unit run PY_TESTS='infrastructure/test_hotlock_sampling.py spin/test_spin_nondelegated.py spin/test_spin_shadow.py'
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1 -j2
```

[验证日志归档](../bench/.tmp/spin-mcs4-window4e9-jv7hhnwu/evidence.tar.gz)、
[冻结源码](../bench/.tmp/spin-mcs4-window4e9-jv7hhnwu/source.tar.gz)及
[输入/产物哈希](../bench/.tmp/spin-mcs4-window4e9-jv7hhnwu/audit.json)保存在本地忽略目录；
guest 原始日志位于上述独立副本同级的 `evidence/`。

此前[CPU MCS1 / hotlock32 与移除 busy 合并验证](../bench/tclock_compare/results/20260922-spin-mcs1-lock32.md)：
基础及定向单元3/3、16个错误变体检测、normal构建、三方单轮18/18和adaptive功能2/2通过。
adaptive四线程实际JIT正文248513次，全部排空；非task丢样由定向fixture验证。
该版保留CPU pin，删除统计busy/barrier；spin CPU每次MCS检查，spin/mutex单锁第33次检查。
本轮未构建SELFTEST、未运行生命周期探针、真实中断压力或nested/early live，详见报告。

此前 [CPU32 MCS 计数验证](../bench/tclock_compare/results/20260922-spin-mcs32.md)：
基础及相关单元6/6、14个热度错误变体检测、normal/SELFTEST构建通过。
三方单轮18/18场与adaptive/plain两场均完成排空；adaptive四线程实际JIT为235995次。
本次SELFTEST只构建，未运行生命周期探针或nested/early live；详细边界见报告。

此前 [MCS 频率统计回退](../bench/tclock_compare/results/20260922-spin-mcs-rollback.md)
恢复 `bf16b10` 的调用计数。基础及相关单元 6/6、运行器 11/11、normal/SELFTEST
构建和生命周期探针通过；adaptive/plain 的 1/4 线程共完成 50 万次操作并排空，
单线程 JIT=0、四线程实际 JIT=244030。本次未重跑性能矩阵。

512槽直接映射已按用户要求撤回，代码恢复 `bf16b10`。此前[回退验证](../bench/tclock_compare/results/20260922-directhash-v2-rollback.md)通过：
20线程KD的c1/c16为5.002/4.771 Mops/s，12场定向三方检查全部排空。下方完整矩阵为此前记录。

此前热表曾按性能退化处理恢复为每 CPU/type 256 桶/256 记录和本地 busy；
共享表/直接映射及当时删除 busy 的报告保留为历史实验。见[回归处理](../bench/tclock_compare/results/20260922-performance-recovery.md)。

前序[普通 spin IRQ 语义与验证](../bench/tclock_compare/results/20260922-plain-spin.md)：
普通路径不保存/屏蔽/恢复 IRQ/BH，保留抢占配对；12项单元、4项实际 JIT
功能检查和生命周期探针通过。含 wrapper 中断栈覆盖回归，未测性能。

最近热表回退的基础及定向单元 6/6、adaptive 实际 JIT、SELFTEST 生命周期探针
和 60 场三方结果见上述回归报告；nested/early 等历史覆盖见普通 spin 报告。
已撤回实验统一见[历史索引](../bench/spin_cacheline/results/HISTORY.md)，
不将历史功能检查当作当前版本重跑。

构建和运行只在 recovery guest，先读 [操作手册](../docs/AGENTS.md)。当前版本是
显式 KD 单锁字 API；全局 spin 分发已删除、mutex hook 安装停用。旧 hook live
套件、gate 容量测试及其专用 workload 已删除，不能以普通 Linux 锁完成冒充 JIT。

## 2026-09-22 文档与旧工具清理验证

删除已退出测试流程的旧/新采样器运行器、专用内核驱动及 `KD_HOTLOCK_LOCAL_HASH_V2`
适配标记；历史报告集中到 benchmark 历史索引。生产热表测试和生命周期探针继续保留，
空闲检查仍拒绝旧模块残留，避免误把删除运行器当作已排空。

本次仅在 guest 运行基础及直接相关检查：基础 2 项、hotlock sampling、regression
共 4/4 驱动通过（含 11 个采样错误变体及 30 个运行器测试）；三方直接运行器 11/11 通过。
普通模块在同一路径分别构建删除标记前/后版本，W=1 构建成功，`.text` 逐字节一致，
SHA256 为 `e83dafee1e47f103614e9ab2d9236cbb4fd4aabd33793dc65aa50fc216aa9466`。
构建仍有已有的手写恢复汇编 objtool 及 locale 警告，未宣称无警告构建。
没有加载模块、执行 live JIT 或重跑 benchmark；最新性能仍以热表回归报告为准。
宿主静态检查确认 42 份 Markdown 无断链，`git diff --check` 通过。

原始命令、退出码、输入哈希、删除文件备份、构建日志及两个 ELF 位于 guest
`/root/kdlock-evidence/doc-cleanup-20260922/`，本地归档位于
`bench/.tmp/doc_cleanup_20260922/`（忽略目录，不纳入 Git）。

<a id="hotlock-direct-validation"></a>

## 2026-09-21 去除候选，按锁字直接哈希计数

该冻结版本每 CPU/type 256 桶、256 条预分配精确地址记录，无 score/error、候选排名或淘汰。
CPU 每 1024 次检查；单锁 count **大于 1024（第 1025 次）** 才采时检查原有窗口，
刷新 hot、更新时间戳并清零计数。满表不覆盖已有记录，adaptive 未收录锁走原生。
CPU 冷热变化重置统计但保留映射，地址身份保持到模块卸载。
布局和流程见 [执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md#51-准备热度与快速获取)。

该历史批次 guest 单元 4/4 通过，11 个错误变体全部被拒绝，覆盖 CPU 1024/锁 1025
边界、256 个同桶地址的独立计数、满表拒绝插入且不覆盖、窗口/倒退/零时间、
query、CPU/type 隔离和重入/抢占配对。普通与 SELFTEST 的 W=1 构建通过，
ELF entry/table/cpu 为 24/6688/13376 字节，CPU 对齐 64。

真实 SELFTEST 探针验证 `retained=1 full=1`、解锁后 `word=0`，mutex 等待从
CPU 1 迁移到 CPU 2，`balanced=1 ret=0`，正常卸载且无内核错误。此探针
`mutex_jit=0`，不冒充 mutex JIT。首次脚本误要求 dmesg 全量前缀不变，因环形
日志换页失败；保存前后日志，按唯一的最后一条前置记录核对本次输出后通过，
没有修改/放宽协议检查。

adaptive/plain/c1/t4 实际功能检查完成 400000 次操作，其中 JIT 正文 210103 次；
业务、IRQ/preempt 和排空均通过，无内核错误。此功能会话使用默认 `mutex_jit=1`，
实际执行的是 spin JIT，不据此声称 mutex JIT 已验证。

本轮原始证据在 guest `/root/kdlock-evidence/hotlock-direct-20260921/`；
[归档](../bench/.tmp/hotlock_direct_20260921/hotlock-direct-20260921.tar.gz)
SHA256：`45589ecb9e19718db0e9cea74afab1e43b48e460366f70021f43841ce85e1e25`。
包含本轮开始时工作树、`this-turn.patch`、最终源码哈希、两种 ELF/布局、单元、
探针前后日志、functional 及 `audit.json`；宿主代码与已测输入一致。

本轮未覆盖真实 mutex JIT、嵌套/远端 native 续跑或更大多锁 live 负载，
预分配容量固定且不回收地址记录；没有解决锁地址复用的对象代际问题。
功能修改时未测性能；随后 [直接哈希同期对照](../bench/tclock_compare/results/20260921-hotlock-direct.md)
完成 120/120 场、1 亿次操作并全部排空，80/80 竞争会话有实际 JIT。本次只重测
性能会话内的功能 oracle，没有重复运行上述单元/满表探针；上一版两级候选性能
不能算作当前无候选版本成绩。
历史候选版只保留冻结报告入口。

<a id="hotlock-twolevel-validation"></a>

## 2026-09-21 两级热度采样（历史候选版）

该候选版已被当前精确哈希计数替代。单元 4/4、10 个错误变体、实际 adaptive
JIT 和 120 场性能对照的冻结结果见 [两级采样报告](../bench/tclock_compare/results/20260921-hotlock-twolevel.md)。
不将其 1024 次单锁阈值、候选替换或对象大小解释为当前行为。

## 单元检查

代码修改后可直接运行[单轮性能测试](../bench/tclock_compare/README.md#准备与运行)，
使用其内置业务、IRQ/preempt、JIT 和排空检查。独立单元、SELFTEST、`--functional`
及小矩阵按需选择，不作为性能测试的固定前置步骤。

```sh
make -C tests/unit run
make -C tests/unit run PY_TESTS='spin/test_spin_direct.py spin/test_spin_entry.py infrastructure/test_hotlock_sampling.py'
```

默认只执行两个基础 C 程序，按修改选择直接相关驱动；`run-all` 仅在明确要求时使用。
`python3 tests/unit/run.py --list` 列出现存驱动，无隐式执行。

| 修改范围 | 相关驱动（位于 tests/unit） |
| --- | --- |
| 原生 pending/MCS 与 owner 配对 | `spin/test_spin_nondelegated.py`、`spin/test_spin_shadow.py` |
| 单锁字入口和 ticket | `spin/test_spin_direct.py`、`spin/test_spin_entry.py` |
| 入口抢占配对 | `spin/test_spin_preempt.py`、`infrastructure/test_hotlock_sampling.py` |
| continuation 容量、回收与最终恢复 | `execution/test_exec_capacity.py`、`spin/test_spin_wait.py` |
| native 借用退休、共享根包与延迟 ACK | `execution/test_remote_outer.py`、`execution/test_remote_depth_protocol.py`、`execution/test_remote_outer_protocol.py` |
| 嵌套、提前释放、队列、frame 退休 | `spin/test_spin_outer_progress.py`、`spin/test_spin_shadow.py`、`spin/test_spin_batch.py` |
| 本地热锁哈希和窗口 | `infrastructure/test_hotlock_sampling.py` |
| mutex 资源和续跑 | `mutex/test_mutex_resources.py`、`mutex/test_mutex_outer_progress.py` |
| source/注册生命周期 | `infrastructure/test_source_lifetime.py`、`execution/test_exe_registry.py` |
| ABI、寄存器和生成器 | `admission/test_clobber_entry.py`、`codegen/test_clobber_abi.py`、`execution/test_native_registers.py` |
| 范围选择与离线证据 | `infrastructure/test_regression.py` |

共享源码读取/头文件过滤位于 `unit/infrastructure/source_text.py`，不再依赖旧 gate
测试。保留的 mutex/remote 等日志 oracle 检查身份、owner、ACK、顺序和最终副作用；
合成日志通过不表示当前 live 覆盖。生产代码 fixture 同样不证明真实内核并发。

## Live 检查

`tests/run_all.sh` 无参数只列出现存范围；`--case module --dry-run` 只预览。
当前唯一基础 case 为 provider/device 生命周期，不加载旧 `klock_module`，JIT=0：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 timeout 240 tests/run_all.sh \
  --case module --output /root/kdlock-evidence/module-current
```

输出目录必须新建在仓库外；变量只在 monitor 已确认真实快照后设置。
运行器核对依赖、冻结源码、检测内核错误及残留调用者，失败保留证据并停止。
`tests/verify_evidence.py` 对这类已有归档做离线一致性校验，不执行归档代码。

实际 JIT 与业务互斥使用 [直接运行器](../bench/tclock_compare/README.md)。
`--scenario plain` 为普通单锁；`--scenario nested` 为 A/B 嵌套；`--scenario early`
为外锁提前释放，仅 KD cacheline 允许后两项。observe 竞争正例要求真实 JIT；
adaptive NO_JIT 只可作为明确标记的性能样本。

SELFTEST provider 可用 `hotlock_lifetime_selftest=1 hotlock_mode=observe spin_entry_selftest=1`
检查热表碰撞及满容量时既有身份和真实 owner 仍保留、mutex 等待 CPU 迁移及 owner ACK；这不执行 JIT。
构建方式及控制参数见 [provider](../kernel_module/README.md)。保持 normal 与
SELFTEST 构建分开，不替换加载中的模块，完成后必须排空和正常卸载。

## 历史验证与尚未覆盖边界

当前改动的实测范围以本页最新结果为准。continuation 容量、最终恢复汇编、
节点先复用、共享根包及延迟 ACK 的历史 fixture 通过，不等于当前真实内核多 CPU
远端 native/无锁 relay 强制时序已覆盖。mutex JIT、极端容量/取消组合及访问时
动态 guard 的剩余限制见 [TODO](../docs/TODO.md)。

| 历史阶段 | 冻结记录 |
| --- | --- |
| continuation 交接、ELF 布局和退休检测 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#continuation-validation) |
| 四线程 ticket 和抢占配对 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#four-thread-ticket-validation) |
| 已撤回的 MCS 边界准入实验 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#mcs-admission-validation) |
| 已撤回的准入时间域实验 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#admission-clock-validation) |
| 回退后的单元与 plain/nested/early 功能 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#mcs-recovery-validation) |

[性能阶段索引](../bench/spin_cacheline/results/HISTORY.md)保留原始报告入口；
更早测试见 [VALIDATION](../docs/VALIDATION.md)。旧 hook/gate 脚本只适用于匹配的
历史 checkout；本次文档整理没有重跑上述实验，也没有删除测试或原始证据。

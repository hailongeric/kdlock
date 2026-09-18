# Tests

本目录维护测试的运行入口、场景说明和验收记录入口。根 README 不记录用例表、
测试命令或测试成绩。Demo 临界区模块集中在
[`workload_modules/lock_scenarios/`](../workload_modules/lock_scenarios/)，
生产 provider 的专用协议观察器在 `tests/kernel/`。
性能对比使用 [bench/README.md](../bench/README.md) 的独立入口。

<a id="spin-entry-first-cas"></a>

## 2026-09-18：先尝试获取 S，再准备竞争入口

在上轮共享寄存器 backing 的工作区上，普通 root 先尝试 S；成功时用独立
per-CPU physical hold，失败后才把已有 gate/pin 转入 ticket。原生缓存默认
开启、装载时可关闭；重复键不再查表回填。首次 batch 入口等待 tail 已证明
存在但尚未 release-link 的后继，避免过早 native handoff。
协议见[设计](../docs/DESIGN.md#41-native-lock-and-private-queue)，性能与两轮
独立 A/B 见[结果页](../bench/spin_cacheline/results/20260918-spin-entry.md)。

同一 recovery guest `6.1.159-kdclobber1` 中，最终 **8 个单元入口通过**，
包含两个基础程序和以下六个直接相关驱动；未运行全量套件或重建内核：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_entry.py spin/test_spin_routing.py spin/test_spin_gate.py spin/test_spin_outer_progress.py spin/test_spin_clobber.py spin/test_spin_shadow.py'
```

- 入口 3684、gate 3121、routing 15 场景/8569 项检查；覆盖无 ticket 快速获取、
  一次 pin/gate、失败平衡、改名/closing 解锁、嵌套独立 ticket、真实 owner、
  pending/tail 保留及反复快慢交接。缓存开启时，100 次重复竞争不再重复回填查表。
- outer-progress 在 NUMA 关闭/开启时分别完成 11419/24718 项检查，13 个
  mutation 均被 oracle 检出；新增生产者暂停于 tail/next 之间的定向检查。
  既有夹具的模拟 tail 映射到其实际准备的链尾，未改变生产队列或 JIT 判定。
- clobber 探针保持 128 个 poisoned 入口、16 个 mixed ABI 入口及完整中途包；
  shadow 驱动覆盖生产节点、嵌套队列、返回与 NUMA 两种配置。

最终同一冻结版本的五项 live **全部通过**：模块加载、mode-0 普通 spin、
mode-2 hostcall、mode-8 嵌套/远端三阶段、mixed-spin 原生互操作。四项功能用例
均保留实际 JIT oracle；mode-8 的双 root 纯 JIT、quota/native/首 waiter 退出
两阶段各 36023 次变换、各 4 次 JIT body，真实 B owner 与 ACK 正确。
quota 阶段沿用 `mutex_jit=1`。所有用例退出码 0，无检测到的内核故障、源码
输入未变化、最终排空。离线 `tests/verify_evidence.py` 检查也通过。

```sh
python3 tests/regression.py --case module --case mode-0 --case mode-2 \
  --case mode-8 --case mixed-spin --timeout 180 \
  --output /root/kdlock-evidence/spin-entry-20260918/live-entry
```

上述命令沿用实验 `KDIR`、固定依赖 venv、已确认快照的 recovery 变量及外层
超时。普通/SELFTEST 与私有 benchmark provider 均在 guest 构建；保留原有
自定义切栈/返回的 objtool 告警，不能将构建通过称为无告警或通用展开证明。

此次开发保留了失败记录：初次无缓存版本把普通 S/L owner 误判为 native
continuation，阻止嵌套发现；修正后又暴露轻量 owner 缺少真实 gate hold，改为
复用既有 claim/release。其修复版在 `live-owner/` 的五项回归通过后，才运行
无缓存 60 场 A/B。恢复默认缓存后的 `live-final/` 仍出现 mode-8 quota 阶段
原生交接、未发生要求的远端 JIT；数据及排空正确也仍判失败。最终增加了
初始 batch 的 tail/link 检查，未删减原 oracle。该版五项 live 在
`live-final-link/` 通过；随后性能和汇编发现冷释放分支增加原生解锁的函数级保存，
将其移到独立函数后，`live-release/` 五项通过，但长批次仍测得原生成本增加。
最后把 clobber 获取的 C 慢路径移出，且用标准 `bint` 避免热路径上的 UBSAN
bool 读取诊断调用；保留内核检查配置。最终 `live-entry/` 重新验证同样五项。
获取及解锁快路径的反汇编检查均要求没有 RBX/R12–R15 序言保存，保留 RBP。
中间“仅拆分获取函数”的汇编断言失败、单元抽取与模拟 tail 适配失败均保留。

原始证据：guest `/root/kdlock-evidence/spin-entry-20260918/`。最终单元日志为
`unit-bint.log`；此前失败日志及不同源码版本各自保留，不拼接为一次通过。
既有冷并发晋升、flags、代码版本及任意 hook 热卸载限制未解决。

宿主归档 `/tmp/kd-spin-entry-20260918/evidence.tar.gz` 的 SHA256 为
`9eb69cedba80b18de16d888b6cd0602860f21596b01ae7c29fa10ffd05722f83`，与 guest 一致。
[最终审核](/tmp/kd-spin-entry-20260918/audit-entry-ab.json) 核对五项 live、冻结
312 个运行/测试源码、实际 JIT 和排空；各中间版本、失败与主动停止分别保存。性能
的最终 60 场、20 场长批次及缓存关闭验证均见上述独立结果页，不替代功能判定。

<a id="shared-register-bank"></a>

## 2026-09-18：JIT 暂存直接复用寄存器包

在 `d8875887eff8917e7527e986e8943c9d14ea80b1` 上改造 wrapper 内部 backing：
R11 固定指向当前 `pt_regs`，R11–R15、SP/BP 的 `Stack_*` 槽直接使用对应字段，
去掉入口/出口的重复搬运。控制槽独立，block 计数移至 `Stack_BUDGET`；
完整出口仍补齐 CPU 中的逻辑寄存器。布局及新旧生成物约束见
[ABI](../docs/JIT_REGISTER_ABI.md#3-pt_regs-输入输出约定)。本轮未修改内核。

全部构建、机器码和 live 验证在 recovery guest、`6.1.159-kdclobber1` 完成，
Build ID 为 `db937d722ee2f2668acb12dc6f105aeea33b7c5c`。最终定向单元 **12 个入口
通过、0 失败**：两个基础 C 程序，加以下十个 Python 驱动；未运行全量套件。

```sh
make -C tests/unit run PY_TESTS='codegen/test_shared_reg_bank.py spin/test_spin_clobber.py spin/test_spin_wwjump.py codegen/test_jit_body_witness.py admission/test_context_guards.py codegen/test_segment_codegen.py codegen/test_jit_diagnostics.py admission/test_clobber_entry.py execution/test_jit_entry_scope.py spin/test_spin_batch.py'
```

新增探针在 epilogue 前双向读写两种寻址，确认是真正共享存储；真实翻译器覆盖
三逻辑操作数同时占用、SP/BP 借用及恢复、部分 R11 写入、hostcall 完整物化/续跑、
bit-24 额度退出。既有探针覆盖 128 个 poisoned 精简入口、16 个混合 ABI 入口、
正文前拒绝和原始输入保持。正常 COMPLETE 中执行过的 spill 可以改变包中暂存
字段，不能把这些字段当作已捕获入口值或有效的 FULL 恢复包。

压力用例先发现分配器按物理编号排除逻辑操作数的旧问题，改为检查映射的逻辑
身份后通过。随后修正测试夹具把 ModRM 的 `0xe8` 错认成 CALL 的编码位置；
该次用户态段错误及前次失败日志均保留，不计为通过。最终源版本重跑上述全部
定向项通过；历史诊断汇编哈希仅归一化计数器重定位，其他字节仍按旧基线检查。

同一冻结版本的五项 live 全部通过，均验证实际 JIT、正确副作用、退出码 0、
无检测到的内核故障和最终排空：

| 用例 | 本轮结果 |
| --- | --- |
| mode-0 | 普通 spin，12009 次状态变换 |
| mode-2 | spin hostcall，服务退出并续跑，12009 次状态变换 |
| mode-8 | 嵌套/远端、双 root 共享 B、native 后缀及 owner ACK；双 root 两阶段各 36023 次变换 |
| mixed-spin | Linux 原锁/private S 互操作，18801 次状态变换 |
| mode-5 | legacy mutex：416 次正文、846 次 hostcall 执行/恢复、5 名 quota 调用者及最终 ACK |

`mode-5` 与 mode-8 quota 阶段沿用显式 `mutex_jit=1`。执行命令仍使用上述实验
`KDIR`、固定依赖 venv 和 `KDLOCK_RECOVERY_CONFIRMED=1`，选择
`tests/regression.py --case mode-0 --case mode-2 --case mode-8 --case mixed-spin --case mode-5`。
离线 `tests/verify_evidence.py` 核对 312 个冻结源码文件和五项完整证据通过；
该审核是字节/记录一致性检查，不替代各用例的运行判定。

本轮原始材料位于 guest `/root/kdlock-evidence/shared-reg-bank-20260918/`，包括
`unit-final.log`、失败及修正日志、`live/`、`live-audit.json`、`assembly/`。
性能单独维护在 [spin benchmark](../bench/spin_cacheline/README.md)。本轮不宣称
解决既有 flags、并发内存新鲜度、原地代码版本或冷并发晋升限制。

宿主归档 `/tmp/kd-shared-reg-bank-20260918/evidence.tar.gz` 包含本轮测试与性能
材料，SHA256：`72e00c01134ba5522ad1c3ac45054f73e5ab9aff8892bcd85424ee130f66358e`。
宿主只读 [audit.json](/tmp/kd-shared-reg-bank-20260918/audit.json) 再次核对五项 live
记录、当前 312 个运行/测试文件、两版 benchmark 冻结字节及逐场数据；全部通过。

<a id="tclock-native-validation"></a>

## 2026-09-18：独立 TCLock 原生栈切换

新增 [test_tclock_context.py](unit/spin/test_tclock_context.py) 编译并执行后端实际
`context.S`：检查六个 callee-saved 寄存器、RSP、128 轮双栈往返、64 次 lock
获取返回和 64 次委托 unlock 续点，共 128 次副作用。恢复 guest 中
`make -C tests/unit run PY_TESTS=spin/test_tclock_context.py` 的三个基础/相关入口
通过，`make -C bench/spin_cacheline test` 的 22 项检查通过。

之后单锁短测及 c16/t4 六臂短测正确并排空；完整三方 180 场稳态矩阵、六场
独立采样、20 场长批次原生测试及失败记录统一放在
[benchmark 结果页](../bench/tclock_compare/results/20260918-native-stack.md)。
保留 objtool 自定义栈告警，没有重跑无关全量、mutex 或复杂嵌套回归。
早期 kdlock 并发 promotion 曾发生 RCU stall，未修复；后续统一单 CPU 准备
不能当作该冷路径通过，也不验证任意 task/per-CPU 或跨 NUMA 的 TCLock 正文。

<a id="spin-wwjump-validation"></a>

## 2026-09-17：单份 request、热状态和锁侧 WWJUMP

本轮基于 `903d8a5` 的工作区，将 spin node 缩至 48 字节，只保留队列/调度状态
和 request 引用；frame 前 64 字节为普通单锁热状态，冷字段按需启用。
`spin_batch.S` 与 wrapper 的专用入口减少逐请求 combiner 保存和通用 dispatcher
往返；当时请求结束后由锁侧选择下一请求，C step 自身的 ABI 保存仍逐次发生。
后续当前实现见[统一 combiner 现场](#tclock-context-loop)。
精确最终 unlock 使用缩小的回写集合，
其他出口保留完整支持的 GPR，并只消费已执行出口一次。协议见
[寄存器 ABI](../docs/JIT_REGISTER_ABI.md#23-批次入口与退出保存集合)和
[共享请求](../docs/DESIGN.md#911-reuse-before-copy-contract)。

最终基础及直接相关的 **14 个单元入口全部通过**，包括真实等待/恢复汇编、
驻留 shell 和两个 wrapper ABI、共享包生命周期、冷区不被普通路径触碰、
批次准入/续跑、NUMA 开关下队列/outer-release、ticket 位图、codegen 和 mutex
同 CPU 队首保护；benchmark 的 **22 项检查通过**。生产普通/SELFTEST 构建通过，
保留自定义切栈/返回的 objtool 警告；新增 shell 也有自定义 RBP 修改警告，
不能把构建通过写成 objtool 无警告或已证明完整内核栈展开。

最终冻结版本 **mode-0、完整 mode-8、mode-5 三项 live 通过**。分别验证实际
单锁 JIT，两个 root 共享 B 的纯 JIT/native relay/首 waiter 退出三阶段，以及
普通 clock/scalar hostcall 返回与超额度 native 后缀、真实 owner ACK。
最终运行及随后 benchmark 无内核 fault，模块、frame、已知调用者排空。

2026-09-18 文档更新及提交前仅做静态检查，没有重跑上述用例或加载模块。
对最终 live/benchmark 冻结清单的并集复核，301 个运行与测试输入哈希一致，
涵盖此次提交的全部 50 个非文档改动；见[提交前离线核对](/tmp/kdlock-commit-audit-20260918.json)。

验证过程中保留了两次 mode 5 失败：

- 第一轮在同 CPU 等待阶段 soft lockup。现场中队首与后继位于 CPU 1，队首
  尚未取得原生 mutex，后继禁止抢占轮询使其无法继续。新增发布前本 CPU
  同队列节点检查；命中时请求不发布、归还路由引用，在原生 mutex 上可调度地
  等待，不释放别人的私有 gate。未做旧版对照，不将故障归因于 wrapper 改动。
- 修复后同 CPU 阶段通过，但原 quota 放置仍将四个调用者限制在 CPU 1，结果
  没有实际 quota JIT，严格 oracle 判定失败。保留同 CPU 进度检查，将独立 quota
  阶段改用 CPU 1–4，CPU 0 保留 holder；仍要求五名调用者、正 JIT quota 次数、
  17 次服务、单次副作用及完整 ACK，未允许 NO_JIT 通过。最终三项重新验证通过。

这项保护针对本 CPU 的同队列前驱，不解决任意跨锁/跨队列 owner 调度依赖。
首次失败未排空，随后保存串口/monitor 现场、重启保留 ext4，使用已有 GRUB
一次性启动项恢复同一 kdstatic2 内核；没有修改或重建 guest 内核。原始失败
记录分别保留在证据的 `live/`、`live-mutex-fix/`，最终通过在 `live-final/`。

实际命令（恢复 guest，先确认 monitor 快照）：

```sh
make -C tests/unit run PY_TESTS='execution/test_exec_capacity.py execution/test_jit_entry_scope.py spin/test_spin_entry.py spin/test_spin_batch.py spin/test_spin_shadow.py spin/test_spin_outer_progress.py spin/test_spin_wait.py spin/test_spin_wwjump.py codegen/test_segment_codegen.py codegen/test_jit_body_witness.py mutex/test_mutex_resources.py mutex/test_mutex_signal_protocol.py'
python3 -m unittest discover -s bench/spin_cacheline -p 'test_*.py'
LC_ALL=C KDIR=/root/linux-6.1.159-kdstatic2 KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 1300s python3 tests/regression.py \
  --case mode-0 --case mode-8 --case mode-5 --timeout 600 \
  --output /root/kdlock-evidence/wwjump-20260917/live-final
```

未运行全量单元或 live 矩阵。内核 Build ID 为
`460d77502af4709a0cca794b322cedc20c2cc478`，voluntary、nokaslr，恢复快照
`pre_static_boot_20260915`。证据：
[最终单元记录](/tmp/kdlock-wwjump-20260917/validation-final.log)、
[live 离线核验](/tmp/kdlock-wwjump-20260917/live-offline-verification.json)、
[失败串口](/tmp/kdlock-wwjump-20260917/hang-serial.log)、
[完整运行归档](/tmp/kdlock-wwjump-20260917/evidence.tar.gz)（SHA256
`d753b9c1c4bd0fd79420438d5c44e8486597073578c49b9b234d950e40c01144`）。
四点性能及 WWJUMP 计数见[独立结果](../bench/spin_cacheline/results/20260917-wwjump.md)。

<a id="spin-batch-validation"></a>

## 2026-09-17：per-CPU 统计、批内 exe 复用与下一请求预取

在 `903d8a5` 上实现三项主路径优化，保留 JIT、逐次发布/准入检查及 owner/ACK。
实现约束见[执行说明](../docs/JIT_EXECUTION.md#23-frame-复用与单锁完成)。
本轮仅运行基础及直接相关功能，没有运行全量回归。

- 最终版本 **6 个单元入口通过**：两个基础 C 程序及
  `spin/test_spin_batch.py`、`spin/test_spin_shadow.py`、
  `spin/test_spin_outer_progress.py`、`execution/test_jit_entry_scope.py`。
  新 fixture 提取生产代码，验证连续 100 个同 entry 请求只查表一次、命中后
  OPEN/status/key/code 失效仍拒绝、换 entry/backend 或批次不误用缓存；
  三 CPU 汇总及被 IRQ 中断的最大值更新使用确定性替身，预取使用真实结构
  布局和独立 root 寄存器包，检查地址、栈边界以及包不被修改。
- 普通模块 `W=1` 构建通过；反汇编确认统计为 `%gs` 本地 inc/cmpxchg，
  recorder 中无共享 `LOCK` 前缀，缓存与预取进入主路径。保留既有切栈/返回
  汇编的 objtool 警告。benchmark 的 15 个行为检查及 7 个汇编检查通过，
  专用观察补丁以 `--fuzz=0` 应用成功。
- 最终 **mode-0 和完整 mode-8 两项 live 通过**：实际 JIT 正文、负载状态、
  嵌套竞争、双 root 共享 B 的纯 JIT 及 quota/native relay 三阶段、native ACK、
  waiter 退出后状态存活、退休排空均通过；无内核 fault，退出统计 waiters=0。

首次新 fixture 编译沿用了生产函数的有符号比较，补齐同类 fixture 的编译
选项后通过；首次 live 止于模块加载，静态 per-CPU 体积 9984 字节超过现有
预留区。最终改为模块初始化时一次性 `alloc_percpu()`，修复后重新运行上述
6 个入口、普通构建和两项 live。失败记录保留，没有修改 guest 内核。

guest 使用既有 `6.1.159-kdstatic2`，Build ID
`460d77502af4709a0cca794b322cedc20c2cc478`，voluntary、nokaslr；已从 monitor
确认 `pre_static_boot_20260915` 快照。命令为：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_batch.py spin/test_spin_shadow.py spin/test_spin_outer_progress.py execution/test_jit_entry_scope.py'
KDLOCK_RECOVERY_CONFIRMED=1 KDIR=/root/linux-6.1.159-kdstatic2 \
  bash tests/run_all.sh --case mode-0 --case mode-8 --timeout 300 \
  --output /root/kdlock-evidence/spin-batch-20260917/live-final
```

[最终单元与构建记录](/tmp/kdlock-spin-batch-20260917/validation-final.log)、
[live 离线校验](/tmp/kdlock-spin-batch-20260917/live-offline-verification.json)、
[完整证据归档](/tmp/kdlock-spin-batch-20260917/evidence.tar.gz)（含首次加载失败、
最终 live 及 benchmark；SHA256
`c11cb68aaedd98aee13657617e1059633b3874614f0b5a12086df52e8c2457c8`）。
同版本的 [spin 四点性能结果](../bench/spin_cacheline/results/20260917-batch.md)
单独记录吞吐，不能将 fixture 的地址检查作为硬件预取收益证明。

<a id="spin-nested-state-validation"></a>

## 2026-09-17：嵌套锁记录直写与虚拟 waiter 空轮询

在 `6fc6e73` 上保留 JIT，将 parent → jit_context → child 的两次锁记录复制
改为发布前直接准备 child，绑定后原地验证。虚拟 waiter 每轮 acquire 检查远端
邮箱，空邮箱不再调用处理函数；非空时保留原有 owner 校验、解锁和 ACK。
parent/child owner ledger 仍独立，物理 waiter 的 shadow 等待路径不变。

在已核对 source/build/live 身份的 recovery guest `6.1.159-kdstatic2`、voluntary
下完成以下定向功能验证；该阶段未运行全量回归或吞吐 benchmark：

- 两个基础程序及 `execution/test_exec_capacity.py`、`spin/test_spin_shadow.py`、
  `spin/test_spin_outer_progress.py`，**5 个入口通过**。新增断言检查原地 ledger
  保留 owner 状态且拒绝重复锁；生产 waiter 循环经历空邮箱、随后通知、处理后
  再次空邮箱，三轮只调用一次替身处理函数，分别以远端完成和 native 续跑结束。
  spin 路径覆盖 NUMA off/on。首次运行有一项旧 fixture 仍期待空邮箱调用处理
  函数；修正预期后完整重跑上述 5 项通过，首次日志保留。
- 普通模块 `W=1` 构建通过，保留既有 naked-return、frame-pointer 和栈状态
  objtool 警告。`pahole` 确认 `kd_spin_jit_context` 为 16 字节；普通模块反汇编
  确认空邮箱直接跳过 `kd_exec_remote_poll` 调用。
- **2 项 live 通过**：`mode-0` 和完整 `mode-8`。后者的嵌套竞争、双逻辑 root
  共享 B combiner、quota/native relay 三个阶段全部通过，包含真实远端解锁、
  native ACK、waiter 退出后 packet/context 保持有效，以及帧/租约排空。
  运行器未发现 dmesg 故障，结束后模块和测试进程均已排空。

这证明一次 ledger 中转复制和每轮空邮箱函数调用已消除，不代表已测得吞吐提升。
结构大小与按页分配的区别见[执行说明](../docs/JIT_EXECUTION.md#23-frame-复用与单锁完成)。
随后同一实现的 [spin benchmark 完整扫描](../bench/spin_cacheline/results/20260917-current-spin.md)
已完成 120/120 会话；该单锁负载不能量化嵌套优化的收益，性能结论以结果页为准。

命令：guest 中执行 `make -C tests/unit run PY_TESTS='execution/test_exec_capacity.py spin/test_spin_shadow.py spin/test_spin_outer_progress.py'`；
确认恢复快照后，执行 `KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case mode-0 --case mode-8 --timeout 300 --output /root/kdlock-evidence/spin-nested-state-20260917`。

证据：guest `/root/kdlock-evidence/spin-nested-state-20260917`；
[构建、单元、基线和反汇编记录](/tmp/kdlock-nested-state-20260917/)，
[完整 live 归档](/tmp/kdlock-nested-state-20260917/evidence.tar.gz)。
归档包含 294 个冻结运行/测试输入，已在 guest 和宿主离线校验；SHA256：
`91f7b664236100db8ff413934ebd829849f20aad0201da20f7004a97f988c702`。

<a id="spin-shadow-wait-validation"></a>

## 2026-09-17：TCLock 式物理 waiter shadow 等待栈

在 `81a82ce` 加同日共享 request/frame 的未提交实现上，为每个 possible CPU
预分配 8KB 等待栈。物理 waiter 在连续汇编中切栈、只保存一个旧 RSP，然后
发布节点并 PAUSE 轮询。未代理的队头恢复旧 RSP；完成/native 唤醒在 task 栈
的安全位置直接恢复共享包。JIT、批次 lease、frame 共享和 owner/ACK 保持原协议，
虚拟 waiter 在执行者 task 栈上处理远端通知。分配、回滚和排空释放见
[执行流](../docs/JIT_EXECUTION.md#22-spin-的等待栈与-irq-状态)。

本轮在既有 recovery guest `6.1.159-kdstatic2`、voluntary 下验证：

- 两个基础程序及 `spin/test_spin_wait.py`、`spin/test_spin_shadow.py`、
  `spin/test_spin_outer_progress.py`，**5 个入口通过**。实际汇编等待测试用
  alternate signal stack 采样被中断的 RSP，96 次均位于 shadow 栈；队头、
  完成、native 各 32 次。完成/native 前覆盖旧 C 栈，队头则核对 RSP 精确恢复。
  另有 96 次共享包最终恢复，检查全部 15 个 GPR；这不是内核 IRQ/NMI 模拟。
- `W=1` 普通模块构建通过，live 的 SELFTEST 构建/加载/卸载通过；保留原有
  naked-return、frame-pointer 与栈状态 objtool 警告，未宣称解决 unwind。
- **4 项 live 通过**：`mode-0`、`mode-1`、`registers-0-1`、
  `node-physical-2-0`，验证实际 JIT、负载状态、native 后缀的寄存器和 ACK。
  两层真实 combiner frame 仍位于 task 栈，观察点最小余量 13608/16384 字节；
  这是采样值，不是 shadow 栈高水位或任意栈深度保证。
- 同一生产源码另跑 **IRQ-off mode-0 变体通过**，将 `KD_SPIN_IRQ_OFF=1`
  显式写入 case 环境并归档，检查入口和返回两侧 IRQ 状态。标准选择器会清除
  环境里的 `KD_*`，不能仅在它外部设置该变量就称 IRQ-off 已覆盖。

294 个冻结运行输入在两轮 live 间一致，测试后源码未变，模块、daemon、调用者
均排空且没有内核 fault。源码/build/live Build ID 核对为
`460d77502af4709a0cca794b322cedc20c2cc478`，快照为
`pre_static_boot_20260915`，未修改或重编译内核。实际加载了 provider，保留默认
`mutex_jit=1`，仅运行 spin 用例；未执行全量、mutex live 或性能 bench。

证据：guest `/root/kdlock-evidence/spin-shadow-wait-20260917` 和
`/root/kdlock-evidence/spin-shadow-wait-irqoff-20260917`；
[宿主构建/单元/live 日志](/tmp/kdlock-shadow-wait-20260917/)、
[IRQ-off 显式选择脚本](/tmp/kdlock-shadow-wait-20260917/run-irqoff.py)。
[完整 live 归档](/tmp/kdlock-shadow-wait-20260917/evidence.tar.gz) 已离线校验，
确认四项常规及一项 IRQ-off 均通过；SHA256 为
`d0be053d2cfe72aab2a5f1a044194621e939a55441cde03d02320cfc883e14b0`。
本节为测试后补写的记录，不属于冻结的说明文件。

<a id="tclock-shared-validation"></a>

## 2026-09-17：TCLock 式共享请求，保留 JIT

在 `81a82ce` 上实现独立于 node 的预分配 request/frame、共享逻辑寄存器包、
物理 frame 指针链和批次 source lease。正常完成、native ACK 后解绑、远端 child
保留 root 包引用和最终汇编归还引用的约束见 [设计](../docs/DESIGN.md#91-frames-and-lock-ledger)。

本轮在既有 recovery guest `6.1.159-kdstatic2`、voluntary 下做增量验证：

- 两个基础程序及 exec capacity、JIT entry scope、remote outer、native after outer、
  spin wait、spin shadow、spin outer progress、spin frame protocol、mutex outer
  progress，共 **11 个入口通过**。不是全量套件；旧夹具适配失败后只重跑受影响项。
  保留对应故障注入断言，新增共享池占用/回收、外部 frame 绑定、包别名及最后一次
  读取后的归还检查。spin wait 还执行真实恢复汇编的 96 次完成/retry/native 出口，
  核对全部 15 个 GPR；用户态测试不证明内核 IRQ 行为。
- 普通、SELFTEST、专用 bench provider 均构建通过。恢复汇编保留 naked-return/
  栈状态 objtool 警告，新恢复函数也有此类警告；不把编译成功当作 unwind 正确性证明。
- 首轮 `mode-0`、`mode-1`、`mode-3`、`registers-0-1`、`node-physical-2-0` 通过。
  `mode-8` 最后阶段失败：退出观察器仍比较 child 内嵌 regs，未比较 `regs_ref`
  指向的实际包，因而提前结束等待。观察器现在显式保存/比较完整活动包；容量
  观察器也沿物理链保存外部 frame 和包，保留原有完整状态断言。
- 修正观察器后的 exec capacity 及其 20 项变异检查通过，随后 **完整三阶段 mode-8
  重跑通过**，包括两个 root 共用 B、native/JIT 混合及 waiter 在 B pop 前退出。
  首轮五项与重跑不是一轮无失败矩阵；两轮及 bench 的 60 个共同生产文件哈希相同，
  仅相关测试/观察器和 bench 日志补丁发生变化。失败证据独立保留。

真实 JIT、负载副作用、owner/ACK 和最终排空均验证，结束后没有内核 fault。
Build ID 为 `460d77502af4709a0cca794b322cedc20c2cc478`，源码/build/live 身份
均核对；快照为 `pre_static_boot_20260915`。没有修改、重编译内核。
四点 16 会话 bench 通过，但 20 线程吞吐较上一版下降，见
[结果和限制](../bench/spin_cacheline/results/20260917-tclock-shared.md)。
既有七角色/双 CPU mutex mode-4 soft lockup 本轮未重跑或修复。

证据：guest `/root/kdlock-evidence/tclock-shared-jit-20260917`、
`/root/kdlock-evidence/tclock-shared-jit-mode8-20260917-r2`；
[宿主日志与审计](/tmp/kdlock-tclock-jit-20260917/)、
[两轮生产源码一致性](/tmp/kdlock-tclock-jit-20260917/source-audit.json)。
离线校验确认首轮五过一败与重跑一过，未把首轮 mode-8 标为通过。
[完整 live/bench 归档](/tmp/kdlock-tclock-jit-20260917/evidence.tar.gz)
SHA256 为 `c668405de0ea788b12c653dea1a3c735cb7510d4a5ec46db1251bbca9efe1ced`。
本节是测量后补写的记录，不属于当时冻结的说明文件。

<a id="waiter-packet-validation"></a>

## 2026-09-17：Waiter 预备寄存器包与原子 frame lease

在 `f190b65` 上实现物理 waiter 发布前准备 node 寄存器包，普通单锁 root
直接使用该包；复杂出口在副作用及节点复用前保存独立包。source frame get/put
改用原子关闭位与计数，继续保留 provider 引用和退休排空。借用指针与尚未生效的
continuation SP 共用存储，frame/context 仍为 656/5264 字节，普通/bench
provider 的 per-CPU 节分别为 8000/8064 字节。

最终同一源码版本在 recovery guest `6.1.159-kdstatic2`、voluntary 下验证：

- 两个基础程序及 source lifetime、exec capacity、JIT entry scope、spin outer
  progress、spin shadow、spin wait、remote outer、native after outer、mutex outer
  progress、spin frame protocol，共 **12 个单元入口通过**。检查发布前 packet
  完备性、借用时私有包不被写入、复杂切换、节点复用、嵌套独立性，以及准入/退休
  并发、模块引用失败回滚和关闭后拒绝；已有对应变异测试全部检出。
- W=1 普通 provider 构建通过，保留既有恢复/返回汇编的 objtool 警告。反汇编确认
  frame get/put 无 raw spinlock 或 IRQ 开关，push/pop 无整块 memset 或完整
  context 扫描；原子操作和模块引用仍有成本。
- `mode-0`、`mode-1`、`mode-3`、`registers-0-1`、`node-physical-2-0`、完整三阶段
  `mode-8`，**6/6 live 用例通过**；实际 JIT、数据、owner/ACK、排空及冻结输入
  检查通过，最终运行无内核故障。仅运行基础及受影响范围，未执行全量套件。

内核源码/build/live Build ID 均核对通过，Build ID 为
`460d77502af4709a0cca794b322cedc20c2cc478`。恢复快照为
`pre_static_boot_20260915`；没有修改、重编译内核或扩大 module per-CPU 预留。
性能结果与原始会话见 [四点复测](../bench/spin_cacheline/results/20260917-waiter-packet.md)。

首轮失败单独保留：早期 unit 夹具仍有旧 packet/布局假设，以及变异断言失败后
继续解引用的问题，修正后最终 12 项重新通过。队列 SELFTEST 绕过汇编 hook 并
传入 RSP=0，前移解码后在 init 触发 NULL 读取；现提供完整的 8-word 保存包，
并核对发布前 callee 寄存器值，未放宽原判定。最初新增独立指针使 frame 增长
8 字节，bench provider 的 per-CPU 节达 8128 字节，首个 kdlock 会话加载返回
ENOMEM，未进入 JIT 测量；改为复用互斥阶段的存储后恢复原大小。两次故障均先
归档，再重启同一实验内核，以新的证据目录验证最终版本，不拼接为一次通过。

[上一轮 mode-4 soft lockup](#mutex-pinned-mode4-failure) 本次未重跑，仍是已知
未解决场景，不由 mode-3 或 mode-8 的通过替代。

guest 证据为 `/root/kdlock-evidence/waiter-packet-20260917/`；最终 live 位于
其中 `live-compact-final/`，unit/build 命令与退出码在 `compact-verification.json`。
guest 与宿主离线校验均通过，live 冻结源码 292 项；bench 冻结源码 186 项、
生成映像 24 项哈希核对通过，61 个生产文件与宿主相同。所有已知 workload/daemon
已退出，模块及 frame/writer 正常排空。

[宿主证据目录](/tmp/kdlock-waiter-packet-20260917/) 包含完整早期失败、最终成功、
反汇编和独立复算；[完整归档](/tmp/kdlock-waiter-packet-20260917/evidence.tar.gz)
SHA256 为 `3f297ec5b52a09d61553836dcabbb133ed448b0351fc43a1f0abe74ca8623dc5`。
本节与性能结果页在测量结束后补写，说明文件的冻结版本以各次证据为准。

<a id="frame-fast-validation"></a>

## 2026-09-17：Frame 复用与单锁路径

2026-09-17 的 frame 主路径精简在 recovery guest `6.1.159-kdstatic2`
（Build ID `460d77502af4709a0cca794b322cedc20c2cc478`）验证：两个基础程序及
`test_exec_capacity`、`test_jit_entry_scope`、`test_spin_outer_progress`、
`test_remote_outer`、`test_native_after_outer`、`test_mutex_outer_progress`、
`test_spin_shadow` 共 9 项通过。新增检查覆盖带旧数据的 frame 槽复用、寄存器包
独立性、单锁完成与复杂分支切换。live 的 `mode-0`、`mode-1`、`mode-3`、
`registers-0-1`、`node-physical-2-0` 通过；`mode-8` 在以下观察器修正后完整重跑通过。

远端退出 SELFTEST 原先要求 IRQ-on，与当前 spin 全程 IRQ-off 的等待合同冲突，
首次 `mode-8` 因观察器 `valid=0` 跳过退出等待而失败，数据正确且会话已排空。
现在允许任一初始 IRQ 状态，同时继续检查整个观察期间 IRQ、CPU、preempt 不变；
单元检查覆盖 IRQ-off 成功和中途 IRQ 改变的拒绝。真实任务退出、ACK 后才 pop、
下一请求不得越过该观察点的原断言均保留，修正后完整三阶段 `mode-8` 通过。

<a id="mutex-pinned-mode4-failure"></a>

本轮另一次 `mode-4` **失败，未修复或计作通过**：七角色/双 CPU 场景出现
soft lockup，SSH 超时后按恢复流程保存宿主串口/CPU 状态并重启。两个 RIP
与未改动的 `kd_mutex_wait_and_lock+0x1c` gate 轮询吻合，符合已有
[忙等 waiter 需要独立可运行依赖](../docs/DESIGN.md#pinned-busy-polling) 的限制；
没有以旧版对照重跑证明归因，也不把独立 CPU 的 `mode-3` 当成该场景的替代通过。
故障前 guest 临时目录随重启清理，宿主保留串口与 monitor 记录；后续证据改存
guest `/root/kdlock-evidence/frame-fast-20260917/`，各次冻结版本分别保留。
宿主归档和可读副本位于
[`/tmp/kdlock-frame-fast-20260917/`](/tmp/kdlock-frame-fast-20260917/)。

## 目录

| 子目录 | 内容 |
| --- | --- |
| `live/` | kernel live 场景脚本，由顶层 `run_all.sh` 选择 |
| `protocols/` | 协议结果校验、CPU 放置与 source 生命周期辅助代码 |
| `clients/` | 用户态测试客户端 |
| `tools/` | 独立审计和成对 benchmark 工具 |
| `kernel/{spin,mutex,execution}/` | provider 的观察器与组件自测 |
| `unit/basic/` | 两个默认基础 C 测试 |
| `unit/{codegen,admission,spin,mutex,execution,infrastructure}/` | 按功能分组的 Python 测试和配套 C 夹具 |

顶层保留公共 shell 库、live 选择器及证据读写入口；Python 单元测试通过
`unit/run.py` 运行，统一处理跨组夹具导入。所有旧用例仍保留。

## 环境与单元测试

构建、单元测试和 kernel live 只在 recovery guest `/root/host_fs/kdlock`
进行。先按 [环境与恢复流程](../docs/AGENTS.md) 核对源码、实际内核身份、
依赖及空闲状态。使用 [固定 Python 依赖](../disassem/requirements.txt)，
venv 的 `bin` 必须位于 PATH 首位，以供 daemon 翻译子进程继承。
原内核的身份检查与独立实验内核的检查不能混用，具体见
[捕获基线](../kernel_baseline/README.md) 和
[spin hook 实验](../kernel_experiments/spin_static/README.md)。

按 2026-09-16 的开发约定，每次修改只验证基础简单功能和直接受影响的功能，
不自动运行完整单元套件或 live 矩阵。默认入口只运行两个基础 C 程序：

```sh
cd /root/host_fs/kdlock
timeout 60s make -C tests/unit run
```

在基础检查上增加相关测试，例如修改测试选择器时：

```sh
timeout 120s make -C tests/unit run PY_TESTS='infrastructure/test_regression.py'
```

`PY_TESTS` 支持分组路径及唯一的旧文件名；指定 `TESTS=` 可只运行所选 Python
测试。单独运行、列出库存及显式全量入口如下；最后一条仅在明确要求全量时使用：

```sh
python3 tests/unit/run.py codegen/test_segment_codegen.py
make -C tests/unit list
make -C tests/unit run-all
```

分析器改动按需要选择相关 admission 测试和 `tests/tools/audit_context_spills.py`。
目录、文档或选择器调整只检查相关入口与路径，不因此扩大到 kernel live。

单元夹具、只读证据检查和真实内核 JIT 分别判定；依赖缺失、SKIP 或编译失败
不能计作通过。这里只列入口，各协议的增量选择继续见
[测试选择](../docs/JIT_EXECUTION.md#7-分层与增量回归)。

提取生产 C 函数的夹具通过 [source_text.py](unit/infrastructure/source_text.py) 读取源码。
它按原声明顺序递归展开私有 `.inc`，保留普通头文件和条件编译文本，供夹具
继续使用原有替代原语；不复制函数实现，也不放宽协议断言。冻结源码和
benchmark 专用 provider 的复制清单同样包含 `.inc`。

`infrastructure/test_hotlock_sampling.py` 还检查无锁 promotion 查询：持有写锁时
查询仍能完成，碰撞探测跨表尾回绕，两个采样线程与两个查询线程并发创建/晋升。
时钟及 IRQ 原语仍是替代实现，pthread 并发不代替真实内核 hook 验证。
2026-09-17 在已核对 source/build/live 身份的 recovery guest
`6.1.159-kdstatic2` 执行
`make -C tests/unit run PY_TESTS='infrastructure/test_hotlock_sampling.py'`，
两个基础程序和 hotlock 程序全部通过；hotlock 231187 项检查、五种错误变异均被
检出，包括重新引入查询写锁。SELFTEST hotlock 对象和默认 provider `W=1` 构建
成功；完整链接仍报告未改动汇编路径的 objtool 警告。查询函数反汇编无读侧锁调用、
IRQ 屏蔽或原子 RMW。日志、源码哈希、内核身份和反汇编保存在 guest 与宿主的
`/tmp/kdlock-hotlock-lockless-20260917/`。本次未加载模块、未启动 daemon、未执行
kernel live/JIT 或性能测试；不将查询指令减少折算为端到端加速比。

同日的 spin 准入精简按当前 voluntary 内核验证。运行
`make -C tests/unit run PY_TESTS='spin/test_spin_entry.py spin/test_spin_routing.py'`，
两个基础程序及两个定向程序全部通过：ticket 3660 项检查，路由 14 个场景、
6233 项检查。新增断言覆盖无 pin 时不访问 ticket 池、查询不增加临时 pin、
guard 持有期间仍可读取本地 gate，以及错误 CPU/task/代次的拒绝。
`W=1` 构建通过，保留既有汇编 objtool 警告；gate 读取反汇编无 guard 调用。
确认 recovery 快照后，`test_16_spin_entry.sh` 的双 CPU 真实原锁/借用引用自测
通过（JIT=0），`tests/run_all.sh --case mode-0` 的单锁实际 JIT 通过，记录到
4 次正文 witness；退出码、数据检查、排空及内核错误检查均通过。
测试加载了 provider，保留默认 `mutex_jit=1` 但仅执行 spin；结束后模块及调用者
已排空。未运行全量、mutex 用例或性能对比。证据位于宿主与 guest 的
`/tmp/kdlock-spin-entry-checks-20260917/`，
组件自测原始目录为 guest `/tmp/kdlock-spin-entry-kernel.lf8oaR/`。

<a id="spin-stackless-validation"></a>

### 2026-09-17：Spin 无栈等待与 IRQ-off 入口

同日继续实现 spin 无栈等待和 IRQ-off task 准入。删除 spin 每 CPU 的 8KB
执行栈；发布前保存/关闭 IRQ，物理 waiter 的发布与轮询使用连续汇编，完成或
native 唤醒直接恢复上下文。`spin/test_spin_wait.py` 在 guest 执行生产汇编，
另一个线程覆盖真实旧 C 栈后分别验证 32 次完成、32 次 native 恢复，以及
32 次普通队头返回；它不模拟内核 IRQ，也不代替实际 JIT。
两个基础程序和 entry/gate/routing/wait/shadow/outer-progress/frame 七项定向
程序共九项通过；随后 node/frame 观察器共 27 个 Python 用例通过。IRQ-off
是合法 task 状态，节点观察器仍检查 pin、计数、节点归还和异常状态。
frame 观察器改为记录实际 task 栈边界；不再给活 task 栈填色或在任务退出后
读取它。新日志明确 `stack_kind=1`、`written_left=null`；旧 8KB watermark
证据仍由原严格分支校验，不能把 RSP 采样称为写入高水位。

在相同 `6.1.159-kdstatic2` voluntary 内核、已确认的 recovery 快照下通过：

- `test_16_spin_entry.sh`：双 CPU 真实 ticket/native-ref 协议，JIT=0。
- `mode-0`：IRQ-on 普通入口与 `KD_SPIN_IRQ_OFF=1` 入口各一次实际 JIT；
  两者各有 4 次 body witness，互斥、真实 L 和上下文 oracle 均为零错误。
- `mode-1`、`registers-0-1`：嵌套实际 JIT，以及 CALL miss 的寄存器/原生后缀/ACK。
- `node-physical-2-0`：同 CPU 两层真实 combiner C frame，40 CPU 节点排空；
  task 栈大小 16384，观测点最小剩余 14168 字节，仅是本次采样结果。

默认和 SELFTEST 的 `W=1` 构建、加载及正常卸载通过；保留既有汇编 objtool
警告。初版增加静态 per-CPU 暂存曾使模块加载 ENOMEM，后改为准备期局部变量、
复用节点旧 IRQ 字段；最终默认静态 per-CPU 为 8000 字节，未修改内核预留区。
本批次加载 provider 并保留默认 `mutex_jit=1`，只运行 spin 用例；最终模块、
daemon 和调用者均排空，成功运行中无内核故障。没有执行全量、mutex live 或
性能 benchmark。宿主与 guest 证据为 `/tmp/kdlock-spin-stackless-20260917/`；
各 live 输出独立保存源码快照，保留早期失败日志与修复后的结果，不合并成全量矩阵。

## 选择 kernel live 用例

```sh
# 列出范围或预览；尚不执行负载。
bash tests/run_all.sh
bash tests/run_all.sh --case mode-0 --dry-run

# 从宿主机 monitor 确认可恢复快照、核对空闲状态后，在 guest 执行。
KDLOCK_RECOVERY_CONFIRMED=1 timeout 360s \
  bash tests/run_all.sh --case mode-0 --timeout 300 \
  --output /tmp/kdlock-selected-case-new
```

宿主机发起 SSH 时还须设置覆盖整条远端命令的外层 timeout。
`--suite` 选择套件，`--case` 选择单项，交叉选择按用例身份去重；无参数只列出
范围。失败立即停止，已被复杂用例覆盖的诊断保持显式选用，不追加基础或稀有
场景矩阵。`--suite mutex` 选择 mode 4/5，并显式启用 `mutex_jit=1`。
完整模块/daemon 启动、逐用例协议和清理顺序见
[执行流](../docs/JIT_EXECUTION.md#3-环境与操作)。

验证 spin 的发布/栈恢复改动时，可在 guest 将生产汇编测试加入基础检查：

```sh
timeout 120s make -C tests/unit run PY_TESTS='spin/test_spin_wait.py'
```

IRQ-off task 入口复用 `mode-0`，在同样的 recovery 准备完成后显式运行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_SPIN_IRQ_OFF=1 timeout 360s \
  bash tests/live/test_04_spinlock.sh 0
```

直接脚本保留此开关；标准选择器会清除外部 `KD_*` 环境变量。
该开关只支持 mode 0：负载在 spin lock/unlock 对外层关闭 IRQ，并检查状态保持。
普通 `mode-0` 使用 IRQ-on 入口；这两个变体均为 task 上下文，不能当作
hardirq/softirq 代理测试。以上为按改动选用的命令，不扩大默认测试范围。

## Demo 模式

以下是场景映射，不是本轮执行或通过清单；同一模式还可能包含多个受检阶段。
完整用例库存、覆盖关系和参数见 [TEST_EXAMPLES](../docs/TEST_EXAMPLES.md)。

| Mode | 后端 | 场景 |
| --- | --- | --- |
| 0 | Spin | 单锁竞争 |
| 1 | Spin | A/B 嵌套 |
| 2 | Spin | allowlisted service 后返回 JIT |
| 3 | Mutex | 单锁竞争，`mutex_jit=1` |
| 4 | Mutex | A/B 嵌套及共享 B，`mutex_jit=1` |
| 5 | Mutex | service 与受检续跑，`mutex_jit=1` |
| 6 | Spin | A/B/C 深层嵌套 |
| 7 | Spin | 先释放 A 再释放 B |
| 8 | Spin | 独立队列及显式远端链 |
| 9 | Spin | 恢复拓扑；旧合成 post-entry fault 为 fail-stop |
| 10 | Spin | GS 读/写/RMW/current 的实际 JIT 正例 |
| 11 | Mutex | GS 读/写/RMW/current 的实际 JIT 正例，`mutex_jit=1` |

`test_24_gs_jit.sh 10/11` 使用各自独占 origin CPU 的四个 worker，要求翻译/发布、
wrapper body witness、12129 次 probe 全部成功、数据完整性和排空。统一入口仍为
`--case context-spin --case context-mutex`。`test_12` 仅保留 mode 3 的拒绝负例。
spinlock 和 mutex 的显式 GS 支持均为默认行为，测试模式只选择验证负载，
不充当 GS 功能开关。spinlock 被代理者原本就保持禁止抢占并 PAUSE 轮询；
mutex 的排队等待也遵循同一规则，两者等待结果期间均不睡眠或调度。
`test_segment_codegen.py` 通过真实 wrapper 在 guest 用户态验证 GS read/write/RMW
及不同 GS/task 输入；`test_mutex_resources.py` 检查 reschedule pending 时仍持续
禁止抢占轮询到结果发布。这些单元测试不代替内核并发验证。

等待代理结果的线程现在禁止抢占，不调度或睡眠。依赖 waiter 让出同一 CPU
才能推进的旧用例（例如同 CPU 的依赖环）需要按新 CPU 放置重新设计，
不应直接复用旧通过记录。单锁 mode 3 已改为每个 waiter 独立 CPU；不要将
sleeping owner 和 busy waiter 固定在同一 CPU。

daemon 的 `--mode flat/per-tgid` 选择 workspace 布局，不是上表的 Demo 模式。

## 证据与结果

实际 JIT 正例必须同时满足有效生成/发布、wrapper 返回后的正文见证、完整数据
和 owner/ACK 校验。已发布但未执行正文不能算实际 JIT 通过。原生负例与协议探针
单列；benchmark 的 NO_JIT 分类见其 README。

运行器在源码树外保留冻结源码、内核/依赖信息、命令、日志、生成物和排空记录。
只读核对已有目录：

```sh
python3 tests/verify_evidence.py /tmp/kdlock-selected-case-new
```

这不重新执行 JIT，也不认证当前源码。停止新 workload 后，先等待调用者、请求、
frame 排空，再结束 daemon/翻译者、retire，最后卸载；不强制卸载。超时或未排空
时保留现场并停止后续用例。

历史结果继续由 [VALIDATION](../docs/VALIDATION.md) 按冻结版本索引，不改写成
当前重跑。最近一次已完成的
[spin 静态分派验证](../docs/VALIDATION.md#spin-static-dispatch-profiling) 包含两版
实验内核各自的八个复杂实际 JIT 用例；R2 的三个定向单元、13 个 benchmark
定向检查和八个 live 用例通过。随后不含 24 线程的十万次完整重跑只执行
spinlock benchmark；其后的代码拆分回归另列如下。

<a id="source-organization"></a>

### 2026-09-15：代码组织回归

将 `bench/`、`kernel_module/` 和 Demo 模块中的大文件按职责拆分，补充
`include/` 接口约束与各目录的阅读地图。9 个 C 编译入口展开 `.inc` 后，
去除注释、空白并规范化 include 路径的 token 序列与整理前一致；Python
运行器的函数/会话执行逻辑保持一致，仅源码冻结新增 `.inc`。这项静态比较
不保证二进制逐字节相同，日志的 `__FILE__`、`__LINE__` 位置会变化。

验证均在 recovery guest 的 `6.1.159-kdstatic2` 上执行，Build ID 为
`460d77502af4709a0cca794b322cedc20c2cc478`，未修改 guest 内核：

- 普通 provider、场景模块、benchmark 专用 provider/模块及客户端构建通过。
- 全量 40 个单元程序首轮 39 个通过；一个源码提取夹具未展开新组件。
  修正该读取入口后，受影响程序的 13 项检查全部通过；其余 39 个程序的输入
  和通过记录保留。初次失败日志没有删除或改写。
- `make -C bench/spin_cacheline test` 的 13 项检查通过，覆盖计数校验、批量
  ioctl/时钟调用次数、配对、quiet 默认行为、正文计数和 NO_JIT。
- `--suite core --case native-spin-acquired --case remote-late-3
  --case parallel-drain-0` 的 8 个实际 JIT 用例全部通过，包括各自的 owner/ACK、
  生成物与排空检查。guest 和宿主离线证据校验均通过，冻结源码共 281 文件。
- [benchmark 整理回归](../bench/spin_cacheline/README.md#source-organization)
  的 16 个会话通过；profile 和 dispatch-floor 的 CLI 导入入口也检查通过。

所有调用者退出，模块正常 retire/卸载，watchdog 设置不变，没有内核故障。
临时收尾脚本第一次扫描了整个 dmesg，误报前一个容量用例的 1029 条代码池
和 6 条 mutex shadow 预期拒绝。只读复核确认此前已通过用例的日志是最终日志
的完整前缀，后续 benchmark 日志没有错误；保留 `postflight-resolution.json`
说明这个检查范围问题，没有重跑负载或改写用例判定。

证据目录为 `/tmp/kdlock-organization-{verify,live,bench}-20260915`，宿主归档
`/tmp/kdlock-organization-evidence-20260915.tar.gz` 的 SHA256 为
`34d509402c3d165b659b353bcda6fb1411c4dbbffe9ae61d09f9aeeb36421896`。
其中保留编译/单元日志、初次失败、冻结源码、实际 JIT 证据、原始 CSV 和排空记录。

<a id="gs-polling-validation"></a>

### 2026-09-16：GS 与禁止抢占轮询

本次在 recovery guest `6.1.159-kdstatic2`、voluntary preemption、固定版本隔离
venv 中完成验证；基线源码/build/live Build ID 检查通过。宿主与 guest 的 259 个
输入文件哈希一致，完成后 workload/daemon 已退出，模块及 frame/writer 已排空。

| 用例 | GS probe 成功/总数 | 实际 JIT 完成 | 结果 |
| --- | --- | --- | --- |
| mode 10 spin | 12129/12129 | 93 | 数据完整性、嵌套锁、排空通过 |
| mode 11 mutex | 12129/12129 | 94（resume 同为 94） | owner 获取/释放各 2034，资源与 invariant 失败均为 0 |

probe 总数包括准备阶段的原生执行，不能当作 JIT 次数。8 组受影响单元测试
（segment、context policy/guards/memory、text regions、mutex resources、body
witness、regression dispatcher）经定向修正和增量重跑通过，准入审计 failures=0。
mutex 资源夹具包含 16791 次检查及 18 个检出的变异，覆盖 polling 中解抢占和
提前返回。`make -C kernel_module W=1` 成功，仍有现存 stack-trampoline objtool
警告。未重跑完整旧矩阵；mode 3 的 CPU 放置调整仅做了 shell 静态检查。

证据归档（包括初次失败、修正后结果、生成物、内核日志和源码哈希）：
`/tmp/kdlock-gs-evidence/kdlock-gs-20260916-evidence.tar.gz`（宿主），SHA256
`03edb8c32a59663e2bc904fc791017be212a278d2025dcacbf2db6523e9ce9d1`。
mutex 首次等待产物超时是测试误用了 spin 的双入口数量；后续按 mutex 单外层
入口修正。单元初次失败分别是扫描到原指令注释、旧 dispatcher stub，以及尚未
更新的 GS 拒绝预期；归档保留这些失败，不将其标成通过。

<a id="test-directory-validation"></a>

### 2026-09-16：测试目录分组

125 个源码文件按上述目录迁移，更新 shell、Python、内核观察器及 benchmark
引用；默认单元入口收敛为两个基础 C 程序，全量入口改为显式 `run-all`。

recovery guest `6.1.159-kdstatic2` 上运行两个基础 C 程序及相关的
`infrastructure/test_regression.py`、`infrastructure/test_benchmark.py`，
4 个程序全部通过：选择器 51 项检查、客户端 30 个场景和配对观察器 113 项检查。
另核对分组导入、默认/全量命令的 dry-run 和工具帮助入口，未执行全量测试或
kernel live。源码通过 Python AST、shell 语法及相对 include 路径检查。
guest 日志为 `/tmp/kdlock-test-layout-20260916.log` 和
`/tmp/kdlock-test-layout-entry-20260916.log`。
宿主副本及迁移清单、源码哈希、验证命令保存在
`/tmp/kdlock-test-layout-20260916/`。随后文档更新与 Git 提交仅核对差异和引用，
未重复运行上述测试；这些记录不代表完整当前版本的全量验收。

<a id="registration-read-path"></a>

### 2026-09-16：重复注册的读取路径

`kd_exe_add` 对已发布、PID/RIP/后端匹配且 source OPEN 的条目只读返回，
避免重复进入注册 gate、source 锁及模块地址查询。UNINIT/miss/native-only
同样可确认已注册，但不能据此执行 JIT；首次注册、冲突及关闭准入保留原路径。

在 recovery guest `6.1.159-kdstatic2` 上完成基础及相关验证：

```sh
make -C tests/unit run PY_TESTS='execution/test_exe_registry.py infrastructure/test_source_lifetime.py execution/test_jit_entry_scope.py'
make -C kernel_module W=1
# 核对 recovery 快照后，只选择一个单锁 spin JIT 用例：
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case mode-0 --timeout 150 \
  --output /tmp/kdlock-registry-read-live-20260916
```

5 个程序通过：注册表 11062、source 生命周期 42820、JIT 入口 3150 项检查，
以及两个基础 C 程序。注册表夹具验证两后端共 1400 次重复调用不再取注册锁、
调用 source pin 或消耗代码块，覆盖未发布槽、并发发布后身份变化、24 线程
注册竞争、后端冲突与退休；15 个破坏注册行为的变体全部检出。

模块构建通过，保留现有恢复/切栈汇编的 objtool 警告。mode 0 的翻译、实际
JIT 正文、12009 次负载状态变换及排空通过；离线证据校验通过，冻结源码
288 文件。内核源码/build/live Build ID 核对通过，模块及 workload/daemon
均已退出。未运行全量套件或性能扫描，不据此宣称具体耗时或吞吐提升。

guest 日志在 `/tmp/kdlock-registry-read-20260916/`，live 证据在上述输出目录。
宿主证据包为
`/tmp/kdlock-registry-read-evidence-20260916/kdlock-registry-read-evidence-20260916.tar.gz`，
SHA256 为 `527eb9a4a7f7ac217f4a78a3d045d7c5688ea3e70324bda6516a6e6a6b8b5e78`。

<a id="gate-request-reuse"></a>

### 2026-09-16：gate 发布与请求内复用

gate 创建初始化后 release 发布 `origin`，find/get 命中通过 acquire 读取，
创建仍锁内复查。物理 request/batch 传递 ticket 和 S，覆盖 remember、pending、
tail、claim、execute_cs、提前释放/reclaim 和 unlock；逻辑 waiter 的祖先
`spin_origin` 不替代物理请求。协议说明见 [DESIGN 4.1/4.2](../docs/DESIGN.md#41-native-lock-and-private-queue)。

recovery guest `6.1.159-kdstatic2` 上选择两个基础 C 程序及五组相关 spin 测试：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_gate.py spin/test_spin_entry.py spin/test_spin_routing.py spin/test_spin_shadow.py spin/test_spin_outer_progress.py'
make -C kernel_module W=1
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case mode-0 --timeout 150 \
  --output /tmp/kdlock-gate-request-live-20260916
```

七个程序经增量修正全部通过。新发布夹具用 12 个线程、48 个碰撞键检查唯一
gate、初始化先于发布和无锁读；路由夹具强制 100 次缓存 miss，验证已有 gate
的获取/解锁每次只哈希一次。ticket、NUMA off/on 队列、嵌套物理请求、提前释放
及重新获取的现有检查通过，combiner 的 12 个变异全部检出。

默认模块及 `KDLOCK_SELFTEST=1` 的编译通过，随后恢复默认构建；可选变体未
加载。保留已有切栈/返回汇编的 objtool 警告。mode 0 验证 2508 字节生成物、
实际 JIT 正文和 12009 次状态变换；离线证据校验通过（冻结源码 289 文件），退休后
frames/modules/writers 均为 0，workload/daemon/模块已退出。未运行全量套件、
复杂 live 矩阵或性能采样。

首次 combiner 夹具编译失败是测试仍把 L 传给改为接收 S 的 helper；修正后只
重跑 gate、routing、outer-progress 与基础程序。可选内核观察器另有两处
slowpath 调用缺少 request 参数，补齐后只重编译该变体及默认模块；生产路径
未再修改，未重复 live。失败和修正后的日志均保留在 guest
`/tmp/kdlock-gate-request-20260916/`，live 证据为上述输出目录。
宿主证据包为
`/tmp/kdlock-gate-request-evidence-20260916/kdlock-gate-request-evidence-20260916.tar.gz`，
SHA256 为 `9c8178e4d9e8a574de42d5290e898bc3a4dfd5e1574a410dab41073c2fe26040`。

<a id="execution-entry-reuse"></a>

### 2026-09-16：执行条目复用

spin/mutex 的 `execute_cs` 查找一次就绪条目并传给 dispatcher，成功路径的
`kd_get_exe` 从三次降为一次（不含请求入口的注册/发现）。frame 准备后仍重新
检查 source OPEN、acquire 发布状态、PID/RIP/代码指针及后端、逻辑入口范围。
退休继续通过 frame lease 等待执行及其续跑排空；稳定槽位不代表不可变代码版本。

在 recovery guest `6.1.159-kdstatic2` 上完成以下基础及相关验证，基线源码、
build/live Build ID 与恢复快照均已核对：

```sh
make -C tests/unit run PY_TESTS='execution/test_exe_registry.py execution/test_jit_entry_scope.py infrastructure/test_source_lifetime.py spin/test_spin_outer_progress.py mutex/test_mutex_outer_progress.py'
# 修正测试夹具后，仅重跑首轮失败的两项：
make -C tests/unit run TESTS= PY_TESTS='execution/test_jit_entry_scope.py mutex/test_mutex_outer_progress.py'
make -C kernel_module W=1 -j4
KDLOCK_RECOVERY_CONFIRMED=1 timeout 400s bash tests/run_all.sh \
  --case mode-0 --case mode-3 --timeout 180 \
  --output /tmp/kdlock-exe-reuse-live-20260916
```

七个不同程序经上述增量验证全部通过。入口夹具 3278 项检查及 22 个变异检出，
覆盖两后端的单次查表、查找后关闭准入/状态变化、身份及后端不匹配，并检查
dispatcher 保留 acquire 读取。注册表 11062、source 生命周期 42820、spin
outer-progress NUMA off/on 分别 12909/27864、mutex outer-progress 194 项检查
及两个基础 C 程序通过。模块构建通过，保留现有切栈/返回汇编的 objtool 警告。

mode 0 的实际 JIT 正文及 12009 次状态变换通过；mode 3 的发布、实际 JIT、
12934 次状态变换和 732 次完成/resume 通过。运行器过滤外层 `KD_*` 环境变量，
因此尝试设置的少量 mutex 轮次没有生效，实际使用该基础用例的默认 32 轮及
8 线程 × 100 次 stress；未更改用例判定或追加重跑。两项均无内核故障，退休后
frames/modules/writers 为 0，workload/daemon/模块已退出。离线证据校验通过，
冻结源码 289 文件；未执行全量套件、复杂 live 矩阵或性能采样。

首轮失败均来自夹具：新增重新查表变异已触发断言，但夹具继续运行到空指针
场景后崩溃；改为变异首次断言失败即退出。mutex 夹具还保留了已废弃且未使用的
调度 stub，删除后编译通过。初次失败与修正后日志均保留，生产实现未因此改动。
guest 日志为 `/tmp/kdlock-exe-reuse-20260916/`，live 证据为上述输出目录。
宿主证据包为
`/tmp/kdlock-exe-reuse-evidence-20260916/kdlock-exe-reuse-evidence-20260916.tar.gz`，
SHA256 为 `524c6f0bda53c5a319dcf162ad43622ecd320f7231df7f1578191e69972f8cc2`。

<a id="spin-clobber-v1"></a>

### 2026-09-18：普通 spin caller-clobber v1

本轮在独立 recovery 内核 `6.1.159-kdclobber1` 完成；Build ID 为
`db937d722ee2f2668acb12dc6f105aeea33b7c5c`。从 `kdstatic2` 派生，配置仅改
LOCALVERSION，保留 frame pointer、retpoline、return thunk、IBT、旧内核及
默认启动项。实现以 Git `0034d7ffa873030e96f004f8e30880beedede6e7` 加验证时的工作区
修改为基础。契约见 [寄存器 ABI](../docs/JIT_REGISTER_ABI.md#10-普通-spin-的-caller-clobber-v1)，
实验补丁及独立基线操作见 [spin_clobber](../kernel_experiments/spin_clobber/README.md)。

所有构建、机器码测试和 live 均在 guest 执行，采用增量定向验证：

- 两个基础程序通过。真实新 wrapper 测试覆盖 128 个 poisoned packet，正常完成、
  正文前拒绝、完整 hostcall/native 中间包；真实 caller asm 强制破坏所有可 clobber
  GPR，检查高寄存器压力、局部栈、循环/helper、RSP/RBP 及精确续点。
- 旧 wrapper/驻留 batch、请求恢复、注册表、入口身份、frame 容量和队列相关检查
  通过。补充真实新旧 wrapper 交替测试，在驻留汇编和 C 两种调用外壳中完成
  8 个混合入口，分别核对 FULL/COMPLETE 包和单次副作用。
  真实等待栈 96 次；最终恢复 160 次（含最小完成与最小重试各 32 次）；
  注册表 11062、入口范围 3346 项；NUMA off/on outer-progress 为 11407/24706 项。
  入口/生成物 ABI 不匹配被拒绝，旧包及 FULL 中间状态继续使用原恢复规则。
- 最后准入验证通过 14 项新 ABI 测试、40 项既有 guard、51 项内存事实测试和
  hostcall codegen。覆盖未捕获寄存器、部分写、分支合并、锁别名、栈槽边界、
  未知写入/callee 失效、实际移位地址回绕、有限预算及重复 guard 区间合并。
- 原生寄存器探针保留全部 GPR、两个栈标签和返回值 oracle；改由编译器保存活跃
  C 值后，真实汇编 150 项检查通过。默认模块、可选 SELFTEST 模块及 daemon 构建
  通过；仍有自定义切栈/返回路径的 objtool 警告，不能称为 objtool 无警告通过。

最终同一冻结版本的六项 live 全部通过，未运行无关全量套件：

| 用例 | 实际验证 |
| --- | --- |
| mode-0 | 普通 spin JIT，12009 次状态变换 |
| mode-2 | 普通 spin hostcall，8 次退出均执行并续跑；12009 次状态变换 |
| mode-8 | 初始嵌套 12014 次；双 root 纯 JIT 与 quota/native 两阶段各 36023 次；每阶段 4 次实际正文，后者确认 owner ACK 后首 waiter 退出 |
| mixed-spin | native L/private S 互操作，实际 JIT 和 18801 次状态变换 |
| mode-5 | legacy mutex 服务/额度退出；463 次实际正文，940 次 hostcall 执行/恢复，5 名 quota 调用者及最终 ACK |
| clobber-irq-off | 复用 mode 0 的 `KD_SPIN_IRQ_OFF=1` task 入口，12009 次状态变换；IRQ/preempt 状态保持 |

`mode-5` 和 mode-8 的 quota 阶段显式启用 `mutex_jit=1`。各用例退出码为 0，
无检测到的内核故障，最终 frames/modules/writers 均排空，workload、daemon 和
模块均退出。最终证据离线校验通过，冻结源码 304 文件；这是字节及记录一致性
审计，不能代替实际正文和各协议 oracle。

复现时在 guest 使用上述实验 KDIR 和固定依赖 venv，普通五项可运行：

```sh
KDIR=/root/linux-6.1.159-kdclobber1 KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 2200s python3 tests/regression.py \
  --case mode-0 --case mode-2 --case mode-8 --case mixed-spin --case mode-5 \
  --timeout 600 --output /root/kdlock-evidence/clobber-repeat
```

IRQ-off 的已有直接入口见本页前文。本次 `run-directed.py` 仅将它注册为一个
临时显式用例，复用同一运行器和证据判定；未更改默认套件。

原始材料在 guest `/root/kdlock-evidence/clobber-20260918/`：
`live-final/`、`live-final-audit.json`、`run-directed.py`、`unit-final-core.log`、
`unit-boundaries-3.log`、`unit-probe-fix.log`、`unit-guard-union.log`、
`unit-mixed-final.log` 及构建/反汇编日志。
调查期间的正文前拒绝、宏/夹具构建错误和可选观察器接口遗漏均保留；失败运行
没有计为通过。准入修复保留地址检查，增加了受检入口 spill、现有 typed 服务
的精确顺序效果及有界分析容量，没有删除负载副作用或寄存器探针。
访问时 guard、并发内存新鲜度、flags 语义和原地代码版本的既有限制未解决。
性能单独记录在 [spin_cacheline](../bench/spin_cacheline/README.md)。

宿主完整证据包为 `/tmp/kdclobber-20260918/final.tar.gz`（约 40 MiB），SHA256：
`fe4ea9f8ba76aff97996f14cc906ebe8b8f87c865e467d416e082e254e3b724b`。
与 guest 原包一致，内含最终源码快照 339 文件、全部成功及失败日志。
宿主只读审计结果在 `/tmp/kdclobber-20260918/final-audit.json`：核对性能冻结
源码 203 文件、5 个二进制、120 个会话及其生成物/计数，独立重算 24 组中位数，
并核对六项 live 的接受、无故障及排空记录；全部通过。旧内核及默认启动文件
最终哈希复查通过。上述源码身份与结果属于提交前的冻结版本。

<a id="tclock-context-loop"></a>

### 2026-09-18：对照 TCLock 统一 combiner 现场

在 caller-clobber v1 完成版本上继续改造，依据本地 TCLocks 提交
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef` 的内核 spin 实现。
新、旧及混合入口都在同一个 `kd_spin_batch_run()` C 帧中连续执行；旧 wrapper
调用只额外保护 RBP，移除生产汇编外壳的成组保存及逐旧请求的 C callback
退出/重入。旧外壳保留在 `unit/spin/legacy_batch.S` 作兼容夹具。
完整对照和保留中途逻辑 GPR 的原因见
[寄存器 ABI](../docs/JIT_REGISTER_ABI.md#11-与-tclock-spinlock-的执行路径和状态保存对比)。

沿用同一 recovery 内核 `6.1.159-kdclobber1`，Build ID
`db937d722ee2f2668acb12dc6f105aeea33b7c5c`；未修改内核或启动项。
验证时 Git 基线为 `0034d7ffa873030e96f004f8e30880beedede6e7` 加工作区改动；
后续提交不改变这些冻结源码与结果的身份。
所有构建和执行检查均在 guest 完成，只选择基础及直接相关项：

- 两个基础程序，以及 `spin/test_spin_{clobber,wwjump,shadow,outer_progress,batch,wait}.py`
  均通过。真实汇编覆盖 128 个 poisoned 新入口、16 个新旧混合入口、旧 wrapper
  最终/完整/拒绝出口、96 次等待栈和 160 次最终恢复（含最小完成/重试各 32 次）。
  outer-progress 的 NUMA off/on 分别通过 11407/24706 项；队列/嵌套 fixture 通过。
- 队列夹具首次编译发现缺少上轮新增的 `entry_abi/packet_state` 类型，补齐后
  重跑通过。新增 RBP 保存曾引发 objtool 将内层恢复当作外层尾声，加入精确的
  SAVE/RESTORE 元数据后该警告消失；没有关闭检查。既有特殊切栈/返回及负载的
  objtool 警告仍存在，不能称为全构建无警告。
- 真实模块反汇编确认循环合入 `run_combiner`，RBX/R12–R15 各只有一个序言
  push 位置，原 `kd_spin_batch_enter/step` 不再出现在该路径。旧入口另有一对
  RBP push/pop；两个入口返回同一循环。该结构证据不等于周期或吞吐测量。

最终同一冻结运行的五项 live 全部通过：

| 用例 | 结果 |
| --- | --- |
| mode-0 | 新 ABI 普通 spin，12009 次状态变换 |
| mode-2 | 新 ABI hostcall，12009 次状态变换，8 次服务退出全部续跑 |
| mode-8 | 嵌套阶段 12014 次；双 root 纯 JIT/native 后缀阶段各 36023 次、4 个实际正文；后者确认 owner ACK 后首 waiter 退出 |
| mixed-spin | Linux 原锁 L/private S 互操作，18801 次状态变换 |
| legacy-spin | 仅目标模块使用 `CFLAGS_klock_module.o=-DKD_SPIN_LEGACY_CALLER`，12009 次状态变换；冻结生成物 ABI 字节确认为 0 |

其余普通用例的冻结生成物 ABI 字节确认为 1，均有 wrapper 返回后的实际正文。
mode-8 quota 阶段沿用显式 `mutex_jit=1`。每项退出码 0、无检测到的内核故障、
source 未变、证据完整且最终排空。已恢复默认目标模块构建，daemon/workload/
模块均未运行。未运行无关全量套件、单独 mutex live 或性能矩阵；旧成绩仍只
属于前文冻结版本，不将减少保存指令写成吞吐提升。

guest 原始证据：`/root/kdlock-evidence/tclock-context-20260918/`，包括
`live/`、`live-audit.json`、`review.json`、`run-directed.py`、全部成功/失败构建与
单元日志、`run-combiner-final.asm`、`kdlock_km.ko` 和相对上轮完成版本的
`implementation.diff`。离线证据及 ABI/汇编审核均通过；实际模块 SHA256 为
`19694866288b81d95c69ef3c42a8c5a142db06a0c8d24440e281abd47eff12c0`。

宿主证据包：`/tmp/kd-tclock-context/evidence.tar.gz`（约 11 MiB），与 guest 原包
SHA256 一致：`3707f5f38ad6691887e45a22168f7418d6e9a88f530cc72317c7c5b50531a0a0`。
包内含 339 文件的最终源码快照、TCLock 三个参考文件的哈希及本轮全部日志。

# Tests

本目录维护测试的运行入口、场景说明和验收记录入口。根 README 不记录用例表、
测试命令或测试成绩。Demo 临界区模块集中在
[`workload_modules/lock_scenarios/`](../workload_modules/lock_scenarios/)，
生产 provider 的专用协议观察器在 `tests/kernel/`。
性能对比使用 [bench/README.md](../bench/README.md) 的独立入口。

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
  bash tests/run_all.sh --case mode-0 --timeout 300 \
  --output /tmp/kdlock-spin-irq-off-new
```

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

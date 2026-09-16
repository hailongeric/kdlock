# Tests

本目录维护测试的运行入口、场景说明和验收记录入口。根 README 不记录用例表、
测试命令或测试成绩。Demo 临界区模块集中在
[`workload_modules/lock_scenarios/`](../workload_modules/lock_scenarios/)，
生产 provider 的专用协议观察器在 `tests/kernel/`。
性能对比使用 [bench/README.md](../bench/README.md) 的独立入口。

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

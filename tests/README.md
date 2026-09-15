# Tests

本目录维护测试的运行入口、场景说明和验收记录入口。根 README 不记录用例表、
测试命令或测试成绩。Demo 临界区模块集中在
[`workload_modules/lock_scenarios/`](../workload_modules/lock_scenarios/)，
生产 provider 的专用协议观察器在 `tests/kernel/`。
性能对比使用 [bench/README.md](../bench/README.md) 的独立入口。

## 环境与单元测试

构建、单元测试和 kernel live 只在 recovery guest `/root/host_fs/kdlock`
进行。先按 [环境与恢复流程](../docs/AGENTS.md) 核对源码、实际内核身份、
依赖及空闲状态。使用 [固定 Python 依赖](../disassem/requirements.txt)，
venv 的 `bin` 必须位于 PATH 首位，以供 daemon 翻译子进程继承。
原内核的身份检查与独立实验内核的检查不能混用，具体见
[捕获基线](../kernel_baseline/README.md) 和
[spin hook 实验](../kernel_experiments/spin_static/README.md)。

初次环境验收在 guest 执行：

```sh
cd /root/host_fs/kdlock
timeout 600s make -C tests/unit run
timeout 120s python3 tests/audit_context_spills.py
```

之后只选择改动影响的单元程序，例如：

```sh
timeout 300s make -C tests/unit run TESTS= \
  PY_TESTS='test_spin_routing.py test_spin_entry.py test_source_lifetime.py'
```

单元夹具、只读证据检查和真实内核 JIT 分别判定；依赖缺失、SKIP 或编译失败
不能计作通过。这里只列入口，各协议的增量选择继续见
[测试选择](../docs/JIT_EXECUTION.md#7-分层与增量回归)。

提取生产 C 函数的夹具通过 [unit/source_text.py](unit/source_text.py) 读取源码。
它按原声明顺序递归展开私有 `.inc`，保留普通头文件和条件编译文本，供夹具
继续使用原有替代原语；不复制函数实现，也不放宽协议断言。冻结源码和
benchmark 专用 provider 的复制清单同样包含 `.inc`。

## 选择 kernel live 用例

```sh
# 列出范围或预览；尚不执行负载。
bash tests/run_all.sh
bash tests/run_all.sh --suite spin --dry-run

# 从宿主机 monitor 确认可恢复快照、核对空闲状态后，在 guest 执行。
KDLOCK_RECOVERY_CONFIRMED=1 timeout 1800s \
  bash tests/run_all.sh --suite spin --timeout 300 \
  --output /tmp/kdlock-spin-cases-new
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
| 10 | Spin | GS/current 拒绝，纯原生负例 |
| 11 | Mutex | GS/current 拒绝，`mutex_jit=1` 的纯原生负例 |

daemon 的 `--mode flat/per-tgid` 选择 workspace 布局，不是上表的 Demo 模式。

## 证据与结果

实际 JIT 正例必须同时满足有效生成/发布、wrapper 返回后的正文见证、完整数据
和 owner/ACK 校验。已发布但未执行正文不能算实际 JIT 通过。原生负例与协议探针
单列；benchmark 的 NO_JIT 分类见其 README。

运行器在源码树外保留冻结源码、内核/依赖信息、命令、日志、生成物和排空记录。
只读核对已有目录：

```sh
python3 tests/verify_evidence.py /tmp/kdlock-spin-cases-new
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

# kdlock 操作手册

本文只规定环境、安全边界和操作流程。执行流见
[JIT_EXECUTION.md](JIT_EXECUTION.md)，协议见 [DESIGN.md](DESIGN.md)，
测试结果只记录在 [VALIDATION.md](VALIDATION.md)，剩余任务见 [TODO.md](TODO.md)。

## 开发约定

1. 先读代码、文档及 `git status --short`，保留已有改动，不重置未知文件。
2. 新增或修改协议、算法、测试时，必须注释其目的、用途和关键约束，尤其解释
   为什么需要该分支或顺序；不要求逐行复述代码。
3. 优先完成主功能和可执行的端到端验证；次要优化后置。当前优先恢复复杂
   mode 8 及 mutex learned-depth 的剩余准入/续跑正例，保持 mode 1/4 已恢复的
   实际 JIT 验收；不能削弱敏感地址检查或删除探针来制造通过。
4. 默认只改 kdlock，不修改、编译或安装 guest 内核；现有 hook 无法支持的
   能力单独评估。不可变 JIT 版本和 flags/特殊指令语义修复已明确延期。
5. 不扩展两元素 wrapper 输入 ABI，不恢复已删除的 futex 执行入口。
6. 提交前核对差异、测试证据和文档。仅在用户要求时提交 Git；不能把历史
   结果记为本次重跑，也不能把未通过的主功能写成已完成。

## 环境边界

| 操作 | 位置 |
| --- | --- |
| 读写源码、静态格式检查、Git、归档、控制 VM | 宿主机 `/home/eric/vm/vm-shared/kdlock` |
| 编译、单元测试、模块、daemon、benchmark | guest `/root/host_fs/kdlock` |
| SSH | `root@127.0.0.1:2222` |
| guest 内核源码/build | `/root/linux-6.1.159` |
| QEMU 脚本 | 宿主机 `/home/eric/vm/qemu-scripts/run_vm.sh` |

不要在宿主机执行 make、模块加载、daemon 或 benchmark。
normal 模式用 9p 共享源码，不需要同步；recovery 模式同一路径是 guest ext4，
不会自动同步。比较单文件 SHA256，只 scp 变化文件，必要时先建对应子目录。
禁止移动、递归覆盖或清空 `/root/host_fs`；避免两侧同时编辑。

现有 baseline 不是新内核修改。不能只凭 `uname -r` 判断兼容性；
只读核对命令在 guest 执行：

```sh
cd /root/host_fs/kdlock
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
```

该命令核对捕获材料、18 个源码/接口文件、配置、九个构建文件及 live Build ID，
不代替完整源码扫描或运行配置检查。另查 `nokaslr`、voluntary 动态抢占、
CPU/NUMA 拓扑和挂载类型。具体身份与重建限制见
[baseline](../kernel_baseline/README.md)。不匹配时先查原因，不能自动改内核。

## 验证顺序

1. 宿主机检查 Git 和 VM，核对并按需同步源码哈希。
2. guest 确认没有在跑的 benchmark、daemon、旧模块及在途请求。
3. 运行 `make -C tests/unit run` 和 `python3 tests/audit_context_spills.py`。
   必需依赖缺失、SKIP 或编译失败不能作为通过。
4. guest 构建，再逐级进行模块加载、小负载和相关 live 测试。
5. 高风险加载前，从宿主机 monitor 确认可恢复快照；之后才设置
   `KDLOCK_RECOVERY_CONFIRMED=1`。环境变量本身不是快照存在的证据。
6. mutex JIT 只在已授权且可恢复的测试中使用 `mutex_jit=1`；默认仍为 0。
7. 对 benchmark 和 SSH 都加外层 timeout。ConnectTimeout 只限制建连，
   不能限制已连接但卡住的远端命令。
8. 测试后核查结果、dmesg 错误、调用者退出及模块排空，再运行下一项。

典型构建命令和主模式命令只维护在 [README](../README.md#quick-start) 与
[JIT_EXECUTION](JIT_EXECUTION.md#3-环境与操作)。`tests/run_all.sh` 是真实内核
集成测试，不是初次验证入口。`test_07`、`test_08`、native/remote/capacity
等 opt-in 测试均须按脚本要求确认 recovery；不要擅自加入默认套件。

### 验收与清理

实际 JIT 必须同时有有效生成物、匹配 entry/lock 且 wrapper 返回后的
`JIT body witness: ... body=1`、正确的负载状态。公共脚本强制
`KD_JIT_BODY_WITNESS=1`；单纯翻译命令、安装日志、调用前 IP 不够。
hostcall 还要检查执行与恢复；native-only 负例必须没有 JIT。
这些观测不是完整指令覆盖、版本证明或性能基线。

保留每项命令/环境、退出码、源文件哈希、内核身份、日志、生成物及 dmesg。
失败正例即使原生完成也仍是失败。扫描 `BUG:`、`panic`、`double fault`、
`soft lockup`、`unable to handle`；检查脚本退出码之外的内核状态。

先停止并等待所有 workload/hook 调用者退出，确认队列/frame 无在途请求，
再停止 daemon，按 `klock_module`、`kdlock_km` 顺序卸载。
guest hook 没有配套 reader/drain 保护，`synchronize_rcu()` 不保证压力下热卸载。
只有 daemon 已停止、执行者已排空时才可清理明确生成的 `daemon/0x*`；
不要清理未知源码、证据或用户文件。

## 虚拟机存活检查与重启

从真实宿主机进程视图检查，不把沙箱不可见误判为进程消失：

```sh
ps -aux | grep qemu-system-x86
timeout 20 ssh -o BatchMode=yes -o ConnectTimeout=5 -p 2222 root@127.0.0.1 \
  'printf VM_OK; uname -r'
```

忽略 grep 自身。进程存在且 SSH 成功才继续；SSH 无法连接或超时，按用户约定
视为 guest 崩溃/卡死，先保存串口日志，再关闭旧 VM。正常测试暂时没有日志
不等于崩溃；单纯 monitor 权限拒绝也不是 guest 故障。

```sh
tail -n 300 /tmp/qemu-serial.log
sudo pkill -9 qemu-system-x86
ps -aux | grep qemu-system-x86
```

确认旧进程完全退出后才重启，禁止两个实例共用磁盘。脚本使用相对磁盘路径，
必须先切换目录；高风险测试使用 recovery：

```sh
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

脚本前台运行 QEMU，recovery 不启用 VirtFS/VFIO，可用 savevm；normal 模式不能
假定支持快照。当前配置为 40 vCPU、28 GiB、双 NUMA，仍需每次核对实际参数。
串口在宿主机 `/tmp/qemu-serial.log`，monitor 在 `/tmp/qemu-monitor.sock`。
已有实例可能由 transient service 管理；先检查实际 QEMU/service，不另起实例。

另一宿主机终端连接 monitor：

```sh
cd /home/eric/vm/qemu-scripts
./run_vm.sh monitor
# HMP: savevm pre_kdlock_test
# HMP: info snapshots
# Ctrl-C 断开客户端；不要发送 quit（会退出 QEMU）
```

root-owned socket 可能需要 `sudo nc -U /tmp/qemu-monitor.sock`。
只有 savevm 无错误且 info snapshots 列出 tag 才算确认。重启不等于 loadvm；
恢复前归档已有证据，guest /tmp 可能丢失。崩溃恢复后先检查模块与源码状态，
从低风险验证重新开始，不直接重复崩溃负载。

## 报告要求

说明实际改动、构建/测试命令和结果、是否加载模块及启用 mutex_jit、
内核错误和排空状态、未执行/失败项目、Git 版本。
本轮或历史证据必须标明来源和时间，不混用不同源码版本的通过结果。
当前完整矩阵为 47/51 通过，仍有 4 项失败，详见
[最新验收](VALIDATION.md#guarded-nested-admission)。

# 2026-09-22：撤回 spin MCS 频率统计

按用户要求撤回 [MCS 入队频率实验](20260922-spin-mcs-frequency.md)。三份生产文件、
六份匹配测试/探针及七份实现文档与 `bf16b10ad6526acba0244f067e540c12bc5a0052`
逐字节一致；删除实验新增的采样 fixture 头文件。此前用户的文档改动和实验归档保留。

CPU 热度恢复为入口调用计数，每 1024 次按 400 亿 TSC ticks 窗口检查；
CPU 热时才按完整锁地址计数，单锁第 1025 次按 25 亿 ticks 窗口检查，
同次到期复用 TSC。每 CPU/type 仍为 256 桶、256 记录、本地 busy 和已有 pin 复用。
普通 spin IRQ 语义、wrapper 修复、ticket/continuation 协议保留。

## 本次验证

仅在 recovery guest 构建和运行，既有内核为 `6.1.159-kdclobber2`，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。加载前确认空闲、捕获基线及恢复快照。
未修改 TCLock 或内核；上述验证完成时尚未提交 Git。随后按用户授权，将恢复状态、
本报告和 Git 操作约定一并提交，作为后续实验的回退版本；此次提交整理未重跑测试。

- 基础及相关单元 6/6，通过 11 个热度错误变体、19 条抢占配对路由，保留碰撞链与满表检查。
  原生 MCS pthread 组件完成 400000 次操作；shadow/节点组件 NUMA 关、开均通过。
  这些组件使用模拟 CPU/时间或用户态线程，与下方真实内核会话分别记录。
- 三方运行器单元 11/11。normal 和 SELFTEST 的 W=1 构建成功；既有 objtool
  换栈/RETHUNK、Perl locale 告警仍在，与冻结恢复版核对后无新增告警类别。
- SELFTEST 生命周期检查 `retained=1 full=1`、解锁 `word=0`，mutex 等待从
  CPU 1 到 CPU 2，`balanced=1 ret=0`；entry 自测零失败。此会话 `mutex_jit=0`、JIT=0，正常退休卸载。
- normal provider 的 adaptive/plain、c1 功能会话：单线程完成 100000 次，JIT=0；
  四线程完成 400000 次，实际 JIT 正文 244030 次。业务、IRQ/preempt、ACK/队列、
  来源退休及排空均通过，无新增内核错误，最终无 worker/daemon/provider 残留。
  会话采用默认 `mutex_jit=1`，实际只执行 spin JIT，不代表 mutex JIT 已验证。

本次没有重跑性能矩阵、nested/early 或全量单元，不能将此前恢复版吞吐写成本次成绩。
单线程无竞争时，无论热度是否准入，首次 CAS 均成功，随后记录 fast owner、执行
调用者原生正文并 release 解锁；不进入 pending/MCS、ticket/continuation 或 JIT。
完整计数及获取流程见[执行路径](../../spin_cacheline/EXECUTION_PATHS.md#51-准备热度与快速获取)。

## 证据

guest 原始目录 `/root/kdlock-evidence/spin-mcs-rollback-20260922/`。
[审核结果](../../.tmp/spin_mcs_rollback_20260922/audit.json)核对 16 份回退文件、
244 份功能运行冻结输入、全部检查退出码及最终空闲状态。
[完整归档](../../.tmp/spin_mcs_rollback_20260922/spin-mcs-rollback-20260922.tar.gz)
包含命令、源码/ELF 哈希、两种构建、单元、探针、两场功能及内核日志。
SHA256：`825d96f5743cf84342f052b59bc38c24ab7415b3bd87254316241d3d216b666d`。
忽略目录不随新 checkout 分发；MCS 实验原始归档保持原 SHA256。

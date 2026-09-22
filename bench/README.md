# Benchmarks

MCS 入队频率实验已因退化撤回，恢复 `bf16b10` 的调用计数。
[本次回退验证](tclock_compare/results/20260922-spin-mcs-rollback.md)通过，未重跑性能矩阵；
[实验成绩](tclock_compare/results/20260922-spin-mcs-frequency.md)保留为历史。

最新[恢复版完整三方结果](tclock_compare/results/20260922-restored-full-benchmark.md)：60/60场通过，5880万次操作全部排空；
20线程KD c1/c16为4.969/4.788 Mops/s。每组两轮取最大值，Linux c16单线程波动详见报告。

512槽直接映射已按用户要求撤回，代码恢复 `bf16b10`。此前[回退验证](tclock_compare/results/20260922-directhash-v2-rollback.md)通过：
20线程KD的c1/c16为5.002/4.771 Mops/s，12场定向三方检查全部排空。下方完整矩阵为此前记录。

最新已测实现与成绩见[热表回归处理](tclock_compare/results/20260922-performance-recovery.md)：
恢复每 CPU/type 256 桶、256 记录及本地 busy，保留普通 spin IRQ 语义和 wrapper 栈修复。
三方 observe 矩阵 60/60 场、5880 万次操作通过并排空，16/16 场竞争 KD 有实际 JIT。
20 线程 c1/c16 的 KD 为 5.197/4.809 Mops/s；单线程及四线程仍低于 TCLock。

当前性能测试对象固定为 **Linux 原生、TCLock、当前 kdlock**，使用
`tclock_compare/run.py --backends native tclock kdlock`。不再将旧版 kdlock
作为测试对象；以下新旧版对照只保留为历史证据，后续结果报告三方吞吐及
当前 KD/Linux、KD/TCLock 比值。2026-09-22 用户最新要求：每配置只测一轮，
三方使用各自这一次有效会话的吞吐和 ns/op 计算比值，不自动追加轮次。
代码修改后可直接运行性能测试，使用运行器内置的正确性/JIT/排空检查；独立
单元、SELFTEST 或功能小矩阵按需选择，不作为固定前置步骤。
原始样本留存；此前两轮最大值及五轮中位数报告保留历史口径。

所有构建与测量只在 recovery guest，环境及排空遵循 [AGENTS](../docs/AGENTS.md)。
当前入口按直接 API 使用独立 Linux、TCLock、KD 对象；旧透明 hook 和双 ABI
性能运行器已删除。冻结历史报告保留原版本与归档索引，不作为当前验收。

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 当前三后端直接调用、cacheline/RCUHT、observe/adaptive 和本地嵌套检查 |
| [spin_cacheline](spin_cacheline/README.md) | 当前运行器共用的客户端、provider 观察层、生命周期和离线汇总/汇编读取 |

[历史索引](spin_cacheline/results/HISTORY.md)汇总旧阶段报告、回退及冻结证据入口，
详细说明从固定 Git 版本读取，避免旧命令与当前运行路径混用。
后续工作统一见 [PERFORMANCE_PLAN](../docs/PERFORMANCE_PLAN.md)。

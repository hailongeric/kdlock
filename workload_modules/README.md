# 当前内核负载

[spin_cacheline](spin_cacheline/README.md)是当前显式 Linux/TCLock/KD API 的业务
负载，生成 `spin_cacheline.ko` 和 `/dev/spin_cacheline`。支持固定展开 cacheline、
RCUHT，以及 KD 专用的 nested/early 场景，运行器位于 bench/tclock_compare。

旧依赖透明 hook 的 lock_scenarios 模块及构建入口已删除。仍有效的寄存器探针
移至 tests/unit/execution，原有协议历史通过记录可从 VALIDATION 和 Git 历史查看。
顶层 Makefile 默认仅构建显式 Linux native 负载；三后端实验由运行器构建。

# 当前代码地图

当前显式 spin 接入与本地热锁实现见 [locking](design/locking.md)，操作见
[PROJECT_GUIDE](PROJECT_GUIDE.md)。构建产物、临时证据和 `.git` 不属于源码清理对象。

## 入口与实现

| 路径 | 职责 |
| --- | --- |
| [kernel_module/kd_main.c](../kernel_module/kd_main.c) | 初始化和退休；mutex hook 安装停用 |
| [kernel_module/kd_spinlock.c](../kernel_module/kd_spinlock.c) | 显式单锁字入口、入口热度/上下文筛选、延迟根 ticket、caller ABI、等待/调度 |
| [kernel_module/kd_spin_entry.c](../kernel_module/kd_spin_entry.c) | 稳定 task/CPU/generation ticket、owner/ACK、native 借用退休等待与排空 |
| [spin/nondelegated.inc](../kernel_module/spin/nondelegated.inc)、[spin/nested.inc](../kernel_module/spin/nested.inc) | 完整原生 fast/pending/MCS；虚拟 ticket、共享根包、远端等待与父 ACK |
| [spin/request.inc](../kernel_module/spin/request.inc)、[spin/lifecycle.inc](../kernel_module/spin/lifecycle.inc) | 每CPU20 KiB初始化、低区内错位与原始基址释放；continuation栈顶分配及连续退休回收 |
| [spin/wait.inc](../kernel_module/spin/wait.inc)、[execution/remote.inc](../kernel_module/execution/remote.inc) | 物理等待发布、远端消息、frame pop 后完成通知 |
| [kernel_module/kd_hotlock.c](../kernel_module/kd_hotlock.c) | 分类型每CPU精确地址哈希；spin每512次MCS比较比例并采时、mutex入口批次与独立单锁窗口 |
| [kernel_module/kd_lock.c](../kernel_module/kd_lock.c) | 保留的 mutex 路由和嵌套控制 CALL |
| [kernel_module/kd_mutex.c](../kernel_module/kd_mutex.c)、[kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | 原 mutex/调度及 task 生命周期 |
| [kernel_module/kd_exec.c](../kernel_module/kd_exec.c) | 稳定 frame、角色、remote/native/锁记录 |
| [kernel_module/exe.c](../kernel_module/exe.c) | 执行注册表、JIT高层与控制服务 |
| [execution/wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc) | batch准备、ABI选择及简单spin调用元数据单次初始化 |
| [kernel_module/kd_source.c](../kernel_module/kd_source.c)、[sys.c](../kernel_module/sys.c) | 来源 pin、设备、能力、发布和退休 |
| [include](../include/README.md) | 显式锁类型、直接 ABI、队列/frame、设备与 wrapper 共享接口 |
| [daemon](../daemon/README.md)、[disassem](../disassem/) | 登记请求、内核读取、分析/翻译、上传及生成代码 |
| [tclock_backend](../tclock_backend/README.md) | 独立 TCLock 原生栈委托比较；保留上游原字节和来源索引 |

私有 `.inc` 保持在所属翻译单元内，按生命周期拆分而不新增公共 ABI。
spin 快速所有权、ticket、continuation/frame 和原生 ACK 仍保留；gate 映射、独立 S、
Linux L 二次获取、旧站点缓存及全局晋升集合已删除。

## 工作负载、测试与测量

| 路径 | 职责 |
| --- | --- |
| [workload_modules/spin_cacheline](../workload_modules/spin_cacheline/README.md) | 当前直接 cacheline/RCUHT、KD nested/early |
| [bench/tclock_compare](../bench/tclock_compare/README.md) | 三后端当前 live 运行器 |
| [bench/spin_cacheline](../bench/spin_cacheline/README.md) | 共用客户端、观察层、发布/排空、离线汇总 |
| [tests/unit](../tests/unit/) | 基础程序与按用途分组的生产代码、ABI、oracle回归 |
| [test_spin_storage.py](../tests/unit/spin/test_spin_storage.py) | 生产存储布局、全部槽位、原始基址释放及初始化失败回滚 |
| [source_text.py](../tests/unit/infrastructure/source_text.py) | 跨组生产源码提取，不依赖 gate 测试 |
| [native_register_probe.h](../tests/unit/execution/native_register_probe.h) | 原生续跑寄存器探针，供执行fixture使用 |
| [tests/kernel](../tests/kernel/) | 生产 provider 专用 SELFTEST/观察器，正常构建不启用 |
| [tests/regression.py](../tests/regression.py) | 当前 module case 的显式选择和证据/停止边界 |
| [tests/verify_evidence.py](../tests/verify_evidence.py) | 现有证据的离线字节/记录一致性检查 |
| [tests/protocols](../tests/protocols/) | 当前工具复用的解析器及有效协议日志 oracle；历史合成记录不作 live 证明 |

当前命令与选择只维护在 [tests](../tests/README.md)和 [bench](../bench/README.md)。
旧透明hook及已删除组件工具只能通过匹配历史checkout重现，不作为当前入口。

## 文档与身份

设计主题分别位于 [lifetimes](design/lifetimes.md)、[locking](design/locking.md)、
[admission](design/admission.md)、[frames](design/frames.md)。
[执行流](JIT_EXECUTION.md)、[寄存器 ABI](JIT_REGISTER_ABI.md)、[任务](TODO.md)、
[性能任务](PERFORMANCE_PLAN.md)各自维护单一职责。对象布局、创建位置及
TCLock/KD 数据流统一见 [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。
[kernel_baseline](../kernel_baseline/README.md)和[kernel_experiments](../kernel_experiments/)
保留捕获身份及独立实验，不能因旧内核当前不运行而删掉恢复材料。
历史结果按冻结版本保留在 [VALIDATION](VALIDATION.md)及 bench/results；
详细旧操作从固定 Git 版本读取，不能充当当前运行说明。

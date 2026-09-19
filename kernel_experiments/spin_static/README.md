# Spin hook 直接调用实验

本轮实验经 2026-09-15 用户授权，在 recovery guest 的独立源码/build 目录
构建和启动。原 `kernel_baseline/` 及 `/root/linux-6.1.159` 保持原身份。
性能和回归结果统一见 [VALIDATION](../../docs/VALIDATION.md)。

本目录现在是历史基线及 clobber 内核的补丁前置。当前 provider 默认要求
[spin/mutex clobber v1](../mutex_clobber/README.md)，已删除下述旧内核安装分支；重现旧版
性能须使用对应冻结源码，不能直接构建当前 provider。

[guest-kernel.patch](guest-kernel.patch) 在捕获的 6.1.159 上，将 spin selector
和 lock/unlock callback 的间接调用改为内核 `static_call`。缓解配置保持开启；
未装载 provider 时保留原生分支。回调 `(lock, rsp, rip)` 和两元素 JIT wrapper
ABI 不变。当时的生产 provider 与独立 bench dispatch 对照通过新头文件检测接口，
旧内核继续使用原指针接口；实验内核需要重建 provider。

第二版增加可选的合并入口安装接口。装载时的 static key 让 spin 路径跳过
独立 selector 调用，直接进入 provider 的完整分派函数；旧安装接口仍按
selector → callback 执行，供兼容及独立成本对照使用。int3 始终保留原 selector。
缓存命中只执行原生 L 的 trylock，保留 S 空闲、source OPEN、上下文和 owner
约束；缓存不能授权 JIT。非目标任务在同一已验证站点也可以完成纯原生获取，
未命中则仍执行 Linux 原生锁。竞争或目标冷入口继续使用既有发现、ticket 和
委托路径，不按线程数切换策略。

合并入口将未命中的解抢占和目标选择放入慢路径函数。成功的 native 获取
保留一个抢占 pin 到真实 unlock；不合适的上下文不会取得这个临时 pin。
临时 pin、原锁 owner 和退休检查均须通过定向与 live 验证。

装卸时的调用点更新由 mutex 串行化，不进入 workload 或锁操作热循环。
既有 int3 的 selector 指针仍保留；先排空、退休再移除 hook 的流程仍适用。
这不提供任意压力下的 hook-reader 热卸载保证。

实验基线需要记录本次配置、命名源码、构建文件和 live Build ID。benchmark
通过 `--kernel-source`、`--kernel-baseline` 显式选择，仍使用原有逐文件及
运行内核验证器，不能跳过检查或将实验结果与旧基线混为同一轮测量。
第一版为 `6.1.159-kdstatic1`，合并入口版为 `6.1.159-kdstatic2`，各有独立
源码/build、安装文件及捕获目录。只设置一次性 GRUB 启动项，保留原默认内核。
重启前将 `/tmp` 中的结果归档到宿主；此 recovery guest 启动时会清理临时目录。

低频 IP 采样单独保存在 bench 目录及对应输出中，采样运行不作为正式性能
比值。不同采样点的占比不是精确的函数耗时分解，也不代表无采样时的成本。

# 固定 cacheline 临界区模块

| 文件 | 职责 |
| --- | --- |
| [api.h](api.h) | 布局、计数、批量 RUN 的 ioctl ABI，与客户端共享 |
| [payload.h](payload.h) | 对齐的原锁/数据，以及五种规模的固定展开正文 |
| [post_work.h](post_work.h) | 正文返回后的 4 组寄存器乘加，给下一次申请留出短间隔 |
| [module.c](module.c) | 原子准入门、排空快照、一次 ioctl 的完整循环与设备注册 |

所有线程争用同一把 spinlock。正文只读改写有效槽中的 64 位计数器，循环中
不计时、不主动调度、不添加等待；每次正文返回后，在锁外执行相同的 4 组局部
乘加。结果没有业务用途，用 volatile asm 保留，不能保证公平交接；原子控制门
在循环外。模块不依赖 kdlock
符号，原生组可独立加载。运行方法、临界区伪代码和性能结果统一维护在
[bench/spin_cacheline/README.md](../../bench/spin_cacheline/README.md)。

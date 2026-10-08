// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi

#include <linux/module.h>
#include <linux/smp.h>
#include <linux/bug.h>
#include <linux/percpu.h>
#include <linux/hardirq.h>
#include <linux/prefetch.h>
#include <linux/atomic.h>
#include <asm/byteorder.h>
#include <linux/vmalloc.h>
#include <linux/sched/stat.h>
#include <linux/sched/task.h>
#include <linux/sched.h>
#include "mutex_compat.h"
#include <linux/topology.h>

#include "mutex/state.inc"
#include "mutex/waiter.inc"
#include "mutex/queue.inc"
#include "mutex/combiner.inc"
#include "mutex/slowpath.inc"
#include "mutex/trampoline.inc"
#include "mutex/unlock.inc"

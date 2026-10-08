// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi

/*
 * TODO: (Performance optimiztion)
 * Fix the index part when same is acquired multiple times.
 * Currently nested locking becomes TTAS lock.
 * irqs_disabled() will hurt performance when running in VM.
 */
/* Linux 6.1 external-module adaptation; see port.patch and README.md. */
#include "compat.h"
#include <linux/topology.h>
#include <linux/vmalloc.h>

#include <linux/percpu-defs.h>
#include <linux/kernel.h>
#include <linux/syscalls.h>

#include "spin/state.inc"
#include "spin/queue.inc"
#include "spin/combiner.inc"
#include "spin/waiter.inc"
#include "spin/lifecycle.inc"
#include "spin/trampoline.inc"
#include "spin/lock.inc"
#include "spin/unlock.inc"

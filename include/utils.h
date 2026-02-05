#ifndef UTILS_H
#define UTILS_H

#include <linux/kernel.h>

#define CONFIG_KD_DEBUG 1

#ifdef CONFIG_KD_DEBUG
#define KD_PR_DEBUG(fmt, ...) \
    pr_info("[KD][%s:%d][%s] " fmt, \
            __FILE__, __LINE__, __func__, ##__VA_ARGS__)
#else
#define KD_PR_DEBUG(fmt, ...) do { } while (0)
#endif

#define KD_PR_INFO(fmt, ...) \
    pr_info(fmt, \
             ##__VA_ARGS__)

#define KD_PR_ERR(fmt, ...) \
    pr_info("[ERROR]" fmt, \
           ##__VA_ARGS__)



#define DSM_DEBUG 1
#ifdef DSM_DEBUG
#define print_debug(fmt, ...)                                      \
    ({                                                             \
        printk(KERN_INFO "[%d] komb (%s) lock(%px): " fmt,        \
               smp_processor_id(), __func__, lock, ##__VA_ARGS__); \
    })
#else
#define print_debug(fmt, ...)
#endif

#endif /* UTILS_H */
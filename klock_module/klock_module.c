#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/ktime.h>

#define DRIVER_NAME "lock_dev"

// 定义 IOCTL 命令结构体
struct test_args {
    unsigned long loop_count;  // 总共抢多少次锁
    unsigned long work_load;   // 每次抢到锁后，在里面算多少次加法 (临界区大小)
    unsigned int mode;         // 0: contention, 1: nested, 2: api-in-lock
};

#define IOC_MAGIC 'k'
#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)

// 全局锁：确保所有打开此设备的线程/进程都抢这一把锁
static DEFINE_SPINLOCK(global_lock);
static DEFINE_SPINLOCK(nested_lock_a);
static DEFINE_SPINLOCK(nested_lock_b);

// 全局计数器：验证数据的正确性
static unsigned long global_counter = 0;

#define MODE_CONTENTION 0
#define MODE_NESTED     1
#define MODE_API_IN_LOCK 2

static void run_contention_test(unsigned long loop_count, unsigned long work_load)
{
    unsigned long i, j;
    // 使用 volatile 确保编译器不把循环优化成一条指令
    volatile int dummy_computation = 0; 

    for (i = 0; i < loop_count; i++) {
        spin_lock(&global_lock);
        
        // --- 临界区开始 ---
        
        // 1. 实际的业务逻辑 (简单的计数)
        global_counter++;

        // 2. 人为制造拥堵 (模拟耗时操作)
        // 注意：Spinlock 期间关闭抢占，千万不要在这里 sleep 或做耗时太久的 IO
        for (j = 0; j < work_load; j++) {
            dummy_computation++;
        }
        
        // --- 临界区结束 ---
        
        spin_unlock(&global_lock);
    }
}

static void run_nested_spinlock_test(unsigned long loop_count, unsigned long work_load)
{
    unsigned long i, j;
    volatile int dummy_computation = 0;

    for (i = 0; i < loop_count; i++) {
        spin_lock(&nested_lock_a);
        spin_lock(&nested_lock_b);

        // --- 临界区开始 ---
        global_counter++;
        for (j = 0; j < work_load; j++) {
            dummy_computation++;
        }
        // --- 临界区结束 ---

        spin_unlock(&nested_lock_b);
        spin_unlock(&nested_lock_a);
    }
}

static void run_api_in_lock_test(unsigned long loop_count, unsigned long work_load)
{
    unsigned long i, j;
    volatile int dummy_computation = 0;

    for (i = 0; i < loop_count; i++) {
        spin_lock(&global_lock);

        // --- 临界区开始 ---
        // Safe API in spinlock context: ktime_get_ns() does not sleep.
        global_counter += (unsigned long)(ktime_get_ns() & 0xFFFF);

        for (j = 0; j < work_load; j++) {
            dummy_computation++;
        }
        // --- 临界区结束 ---

        spin_unlock(&global_lock);
    }
}

static long my_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    struct test_args k_args;

    switch (cmd) {
        case IOC_RUN_TEST:
            // 从用户空间拷贝参数
            if (copy_from_user(&k_args, (void __user *)arg, sizeof(k_args))) {
                return -EFAULT;
            }
            // 执行测试
            if (k_args.mode == MODE_CONTENTION) {
                run_contention_test(k_args.loop_count, k_args.work_load);
            } else if (k_args.mode == MODE_NESTED) {
                run_nested_spinlock_test(k_args.loop_count, k_args.work_load);
            } else if (k_args.mode == MODE_API_IN_LOCK) {
                run_api_in_lock_test(k_args.loop_count, k_args.work_load);
            } else {
                return -EINVAL;
            }
            break;
        default:
            return -EINVAL;
    }
    return 0;
}

static const struct file_operations my_fops = {
    .owner = THIS_MODULE,
    .unlocked_ioctl = my_ioctl,
};

static struct miscdevice my_misc_device = {
    .minor = MISC_DYNAMIC_MINOR,
    .name = DRIVER_NAME,
    .fops = &my_fops,
};

static int __init my_module_init(void)
{
    // 初始化全局计数器
    global_counter = 0;
    if (misc_register(&my_misc_device)) {
        printk(KERN_ERR "Lock Module: Failed to register device\n");
        return -1;
    }
    printk(KERN_INFO "Lock Module: Module loaded.\n");
    return 0;
}

static void __exit my_module_exit(void)
{
    misc_deregister(&my_misc_device);
    printk(KERN_INFO "Lock Module: Module unloaded. Final Counter: %lu\n", global_counter);
}

module_init(my_module_init);
module_exit(my_module_exit);

MODULE_LICENSE("GPL");

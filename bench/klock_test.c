/*
 * klock_test — userspace driver for /dev/lock_dev.
 *
 * Usage:  ./klock_test <threads> <loops> <workload> <spare> <mode>
 *
 *   threads  — number of concurrent threads
 *   loops    — how many ioctl calls per thread
 *   workload — busy-loop iterations inside each critical section
 *   spare    — unused (reserved)
 *   mode     — benchmark mode (see below)
 *
 * Modes:
 *   0  MODE_SPIN_CONTENTION    Contended single spinlock
 *   1  MODE_SPIN_NESTED        Nested spinlocks (lock A → lock B)
 *   2  MODE_SPIN_API_IN_LOCK   Spinlock CS containing a kernel API call
 *   3  MODE_MUTEX_CONTENTION   Contended single mutex
 *   4  MODE_MUTEX_NESTED       Nested mutexes
 *   5  MODE_MUTEX_API_IN_LOCK  Mutex CS containing a kernel API call
 *
 * Modes 0–2 exercise the spinlock delegation path (kd_spinlock.c).
 * Modes 3–5 exercise the mutex delegation path (kd_mutex.c).
 *
 * Example:  ./klock_test 4 100000 1000 10 0
 *   → 4 threads, 100k iterations each, 1000-loop workload, mode 0
 */
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <pthread.h>
#include <sys/time.h>

#define DEVICE_PATH "/dev/lock_dev"
#define IOC_MAGIC 'k'

struct test_args {
    unsigned long loop_count;
    unsigned long work_load;
    unsigned int mode;
};

#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)

#define MODE_SPIN_CONTENTION    0  /* contended single spinlock           */
#define MODE_SPIN_NESTED        1  /* nested spinlocks                    */
#define MODE_SPIN_API_IN_LOCK   2  /* spinlock with kernel API inside CS  */
#define MODE_MUTEX_CONTENTION   3  /* contended single mutex              */
#define MODE_MUTEX_NESTED       4  /* nested mutexes                      */
#define MODE_MUTEX_API_IN_LOCK  5  /* mutex with kernel API inside CS     */

/* per-thread work item */
struct thread_data {
    int thread_id;
    int fd;
    unsigned long sys_count;
    struct test_args args;
};

// 线程工作函数
void *worker_thread(void *arg) {
    struct thread_data *data = (struct thread_data *)arg;
    
    // printf("Thread %d starting...\n", data->thread_id);
    for(int count = 0; count < data->sys_count; count++) {
        if (ioctl(data->fd, IOC_RUN_TEST, &data->args) < 0) {
            perror("IOCTL failed");
        }
        printf("Thread %d: Loop %d completed\n", data->thread_id, count);
    }
    // printf("Thread %d finished.\n", data->thread_id);
    return NULL;
}

// 获取当前时间戳 (毫秒)
long long current_timestamp() {
    struct timeval te; 
    gettimeofday(&te, NULL);
    return te.tv_sec * 1000LL + te.tv_usec / 1000;
}

const char *mode_name(unsigned int mode) {
    switch (mode) {
    case MODE_SPIN_CONTENTION:
        return "spin-contention";
    case MODE_SPIN_NESTED:
        return "spin-nested";
    case MODE_SPIN_API_IN_LOCK:
        return "spin-api-in-lock";
    case MODE_MUTEX_CONTENTION:
        return "mutex-contention";
    case MODE_MUTEX_NESTED:
        return "mutex-nested";
    case MODE_MUTEX_API_IN_LOCK:
        return "mutex-api-in-lock";
    default:
        return "unknown";
    }
}

int main(int argc, char *argv[]) {
    if (argc < 6) {
        printf("Usage: %s <num_threads> <loop_count> <work_load> <sys_count> <mode>\n", argv[0]);
        printf("Mode: 0=spin-contention, 1=spin-nested, 2=spin-api-in-lock\n");
        printf("      3=mutex-contention, 4=mutex-nested, 5=mutex-api-in-lock\n");
        printf("Example: %s 4 100000 1000 10 3\n", argv[0]);
        return -1;
    }

    int num_threads = atoi(argv[1]);
    unsigned long loop_count = strtoul(argv[2], NULL, 10);
    unsigned long work_load = strtoul(argv[3], NULL, 10);
    unsigned long sys_count = strtoul(argv[4], NULL, 10);
    unsigned int mode = (unsigned int)strtoul(argv[5], NULL, 10);

    if (mode > MODE_MUTEX_API_IN_LOCK) {
        fprintf(stderr, "Invalid mode: %u\n", mode);
        return -1;
    }

    int fd = open(DEVICE_PATH, O_RDWR);
    if (fd < 0) {
        perror("Failed to open device");
        return -1;
    }

    pthread_t *threads = malloc(sizeof(pthread_t) * num_threads);
    struct thread_data *t_data = malloc(sizeof(struct thread_data) * num_threads);

    printf("Starting Test:\n");
    printf("  Threads: %d\n", num_threads);
    printf("  Loops per thread: %lu\n", loop_count);
    printf("  Critical Section Workload: %lu\n", work_load);
    printf("  Mode: %u (%s)\n", mode, mode_name(mode));

    long long start_time = current_timestamp();

    // 创建线程
    for (int i = 0; i < num_threads; i++) {
        t_data[i].thread_id = i;
        t_data[i].fd = fd; // 所有线程共享同一个文件描述符
        t_data[i].args.loop_count = loop_count;
        t_data[i].args.work_load = work_load;
        t_data[i].args.mode = mode;
        t_data[i].sys_count = sys_count;

        if (pthread_create(&threads[i], NULL, worker_thread, &t_data[i]) != 0) {
            perror("Failed to create thread");
            return -1;
        }
    }

    // 等待所有线程结束
    for (int i = 0; i < num_threads; i++) {
        pthread_join(threads[i], NULL);
    }

    long long end_time = current_timestamp();
    
    printf("------------------------------------------------\n");
    printf("All threads finished.\n");
    printf("Total Time: %lld ms\n", end_time - start_time);
    
    // 卸载模块时会打印最终的 global_counter，可以用来验证是否有竞态丢失（如果不加锁的话）
    printf("Check 'dmesg' for kernel logs.\n");

    free(threads);
    free(t_data);
    close(fd);
    return 0;
}

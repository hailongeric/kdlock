#include <linux/types.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/slab.h>
#include <linux/errno.h>
#include <asm/uaccess.h>
#include <linux/device.h>

#include "sys.h"
#include "exe.h"
#include "utils.h"

extern struct exe_info* exes;

int nf_major = 0;
int nf_minor = 0;

struct nf_dev* nf_device;
static struct class* nf_class;
static struct device* nf_device_node;

int nf_open(struct inode* inode, struct file* filp) {
    return 0;
}

int nf_release(struct inode* inode, struct file* filp) {
    return 0;
}

ssize_t nf_read(struct file* filp, char __user* buf, size_t count, loff_t* fpos) {
    count = 0;
    ssize_t len = 0;
    const int sz = sizeof(struct exe_info);
    int i;
    for (i = 0;i < MAX_EXE;i++) {
        // spin_lock(&exes[i].lock);
        if (exes[i].status_code != F_UN_USED) {
            copy_to_user(buf + len, &exes[i], sz);
            len += sz;
        }
        // spin_unlock(&exes[i].lock);
    }
    // KD_PR_INFO( "kd read len: %d\n", len);
    return len;
}

ssize_t nf_write(struct file* filp, const char __user* buf, size_t count, loff_t* f_pos) {
    int len;
    const void* payload;
    struct exe_info* p;
    struct recv_pkt* head = kmalloc(sizeof(struct recv_pkt), GFP_KERNEL);
    copy_from_user(head, buf, sizeof(struct recv_pkt));
    len = count - sizeof(struct recv_pkt);
    payload = buf + sizeof(struct recv_pkt);
    p = get_exe(head->pid, head->RIP);

    // spin_lock(&p->lock);
    // KD_PR_INFO( "write to kernel %d %p %d %ld\n",head->pid,(void*)head->RIP, head->status_code, head->offset);
    printk(KERN_EMERG "write to kernel %d %px %d %ld p-%px\n",head->pid,(void*)head->RIP, head->status_code, head->offset, p);
    if (p->RIP == head->RIP && p->pid == head->pid) {
        copy_from_user(p->code_block + head->offset, payload, len);
        p->status_code = head->status_code;
        // spin_unlock(&p->lock);
        kfree(head);
        return count;
    }
    // spin_unlock(&p->lock);
    // KD_PR_INFO( "exe to be written not found %d %p\n", head->pid, (void*)head->RIP);
    printk(KERN_EMERG  "exe to be written not found %d %p\n", head->pid, (void*)head->RIP);
    kfree(head);
    return count;
}

struct file_operations nf_fops = {
    .owner = THIS_MODULE,
    .read = nf_read,
    .write = nf_write,
    .open = nf_open,
    .release = nf_release,
};

static void nf_setup_cdev(struct nf_dev* dev) {
    int err, devno = MKDEV(nf_major, nf_minor);
    cdev_init(&dev->cdev, &nf_fops);
    dev->cdev.owner = THIS_MODULE;
    dev->cdev.ops = &nf_fops;
    err = cdev_add(&dev->cdev, devno, 1);
    if (err)
        KD_PR_INFO( "error %d adding kd_dev\n", err);
}

void sys_init(void) {
    int ret;
    dev_t dev = 0;
    if (nf_major) {
        dev = MKDEV(nf_major, nf_minor);
        ret = register_chrdev_region(dev, 1, "kd_dev");
    }
    else {
        ret = alloc_chrdev_region(&dev, nf_minor, 1, "kd_dev");
        nf_major = MAJOR(dev);
    }
    if (ret < 0) {
        KD_PR_INFO( "kd_dev: can't get major %d\n", nf_major);
        return;
    }
    nf_device = kmalloc(sizeof(struct nf_dev), GFP_KERNEL);
    if (!nf_device) {
        unregister_chrdev_region(dev, 1);
        return;
    }
    memset(nf_device, 0, sizeof(struct nf_dev));
    // sema_init(&nf_device->sem, 1);
    nf_setup_cdev(nf_device);
    nf_class = class_create(THIS_MODULE, "kd_dev");
    // nf_class = class_create("kd_dev");
    nf_device_node = device_create(nf_class, NULL, dev, NULL, "kd_dev");
}

void sys_exit(void) {
    dev_t devno = MKDEV(nf_major, nf_minor);
    if (nf_device) {
        cdev_del(&nf_device->cdev);
        kfree(nf_device);
    }
    unregister_chrdev_region(devno, 1);
    device_unregister(nf_device_node);
    class_destroy(nf_class);
}
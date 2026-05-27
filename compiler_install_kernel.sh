#!/bin/bash 

cd /root/linux-6.1.159/
make -j$(nproc)
make modules_install -j$(nproc)
make install -j$(nproc)
cp vmlinux /root/host_fs/local_tmp


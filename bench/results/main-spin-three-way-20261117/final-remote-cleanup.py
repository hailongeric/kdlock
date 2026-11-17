import pathlib,hashlib,json,subprocess
checks={'/tmp/main-spin-20e9db0c-run.py': '3191fd4d39f8bdbd610990b40f3c5752ee1b52914fbb9e494b2cf7b1334d5fb7', '/tmp/main-spin-layout.py': '41f72085bb9a292b2c1235df655f7b97d76e63c18ef00db3d962d395e911beb7', '/tmp/main-spin-handoff-source.tar': 'f0a0913b09e4726d22698e58735763a119f891ff93aa4c83bed5f59314257db8', '/tmp/main-spin-handoff-build.sh': '0b6811e2520057728a4054e2adf0cfa779fa7735ba0409158a050935f4b48f80', '/tmp/main-spin-handoff-install.sh': '253e0da2927576d767b8c1b5f870c41f4c7068c4e35f8343d1706b489ea61ef4', '/tmp/main-spin-handoff-run.py': '6214b0f8817441aac92df767f2ed2e5a407633caab2e50cd3ad5828820b49fb6', '/tmp/main-spin-20e9db0c-source.tar': '9d55be4f833bb529538a4f1ec54bd8257cbb2f2584d7912864f898d1fbaddb52', '/tmp/main-spin-20e9db0c-build.sh': '8646921e42ed22ba6035f3d2c8e23035b5584b5d43d764c6cf7ce3bb5ed525fa', '/tmp/main-spin-20e9db0c-install.sh': 'edcb231da3fc43c1914efd32f1c7d55dc1ba73d4a8fe1895d0636c749796e5fe'}
for n,h in checks.items():
 p=pathlib.Path(n)
 assert p.is_file() and not p.is_symlink(),n
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
for n in checks:
 pathlib.Path(n).unlink()
 print('removed',n)
command="uname -r; test \"$(uname -r)\" = 7.0.0-38-kdall1; test ! -e /sys/module/kd_bench; test ! -e /sys/module/tclock_backend_km; test ! -e /mnt/kdlock-builds/main-spin-20e9db0c-20261117; test ! -e /mnt/kdlock-builds/main-spin-handoff-1d29a9a1-20261117; test ! -e /lib/modules/7.0.0-38-kdmainspin1; test ! -e /lib/modules/7.0.0-38-kdmainspin2; ! grep -q kdmainspin /boot/grub/grub.cfg; sha256sum /etc/default/grub /etc/default/grub.d/* /boot/vmlinuz-7.0.0-38-kdall1; ls -l /boot/vmlinuz /boot/vmlinuz.old /boot/initrd.img /boot/initrd.img.old; grub-editenv /boot/grub/grubenv list; df -h /mnt/kdlock-builds"
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-p','2223','root@127.0.0.1','set -e; '+command],capture_output=True,text=True,timeout=40)
print(p.stdout);print(p.stderr);assert p.returncode==0,p.returncode
print('REMOTE_CLEANUP_FINAL_VERIFIED')

import pathlib,os,hashlib,shutil,subprocess,json
P=pathlib.Path
assert os.uname().release=='7.0.0-38-kdall1'
assert not P('/sys/module/kd_bench').exists()
assert not P('/sys/module/tclock_backend_km').exists()
expected={
'/boot/vmlinuz-7.0.0-38-kdall1':'f7b94f82d3b8f64f46070850f24d9f91d73a1fcafe17864470b09488611f2e04',
'/boot/vmlinuz-7.0.0-38-kdmainspin1':'ba3f919b4f651d855fc1e2e79338027b1742a828848b85b45552ecf058f715ec',
'/boot/vmlinuz-7.0.0-38-kdmainspin2':'82bf0480161c69c51f2eb7471558474a3a86351b4305e112636b101992361762'}
for name,h in expected.items():assert hashlib.sha256(P(name).read_bytes()).hexdigest()==h,name
roots=[P('/mnt/kdlock-builds/main-spin-20e9db0c-20261117'),P('/mnt/kdlock-builds/main-spin-handoff-1d29a9a1-20261117')]
for root in roots:
 assert root.is_dir() and not root.is_symlink()
 subprocess.run(['sha256sum','-c',str(root/'grub-default-before.sha256')],check=True)
mounts=subprocess.check_output(['findmnt','-rn','-o','TARGET'],text=True).splitlines()
for root in roots:
 assert not any(m==str(root) or m.startswith(str(root)+'/') for m in mounts)
# Record only the explicitly owned paths. Never follow installed build symlinks.
remove=[]
for version in ['7.0.0-38-kdmainspin1','7.0.0-38-kdmainspin2']:
 for prefix in ['vmlinuz-','initrd.img-','System.map-','config-']:
  remove.append(P('/boot')/(prefix+version))
 remove.append(P('/lib/modules')/version)
 record=P('/var/lib/initramfs-tools')/version
 if record.exists():remove.append(record)
remove+=roots
for path in remove:
 assert path.exists() and not path.is_symlink(),str(path)
print(json.dumps({'remove':[str(p) for p in remove],'preserve_kernel':'7.0.0-38-kdall1'}),flush=True)
# Current links were advanced by our two installs. Reconstruct the preceding
# current/previous pair from the original running image and prior installation.
for base in ['vmlinuz','initrd.img']:
 for suffix,version in [('', '7.0.0-38-kdall1'),('.old','7.0.0-38-kdclaude1')]:
  link=P('/boot')/(base+suffix)
  assert link.is_symlink() and 'kdmainspin' in os.readlink(link)
  target=base+'-'+version
  assert (P('/boot')/target).is_file()
  link.unlink();link.symlink_to(target)
for path in remove:
 if path.is_dir():shutil.rmtree(path)
 else:path.unlink()
 print('removed',path,flush=True)
subprocess.run(['update-grub'],check=True)
subprocess.run(['sync'],check=True)
for path in remove:assert not path.exists() and not path.is_symlink(),str(path)
assert 'kdmainspin' not in P('/boot/grub/grub.cfg').read_text()
assert os.uname().release=='7.0.0-38-kdall1'
print('ROLLBACK_COMPLETE',flush=True)

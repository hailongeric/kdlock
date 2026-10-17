"""Read-only ELF import audit, independent of captured nm output."""
import hashlib,re,subprocess
DENIED=re.compile(r'^(?:mutex\w*|__mutex\w*|atomic_dec_and_mutex_lock|kd_mutex_(?:lock|unlock)_clobber_v1|osq_lock|osq_unlock)(?:\.|$)')
def audit(folder,group):
 paths=[folder/'binaries/kdlock_km.ko',folder/'variants/kdlock/mutex_cacheline.ko'] if group.startswith('c01') else [folder/'build/kdlock_km.ko',*sorted((folder/'build').glob('kdlock-*/real_api.ko'))]
 assert len(paths)==2,(group,paths)
 rows=[]
 for path in paths:
  output=subprocess.check_output(['nm','-u','--format=posix',str(path)],text=True)
  names=sorted({line.split()[0] for line in output.splitlines() if line.strip()})
  denied=[name for name in names if DENIED.match(name)];assert not denied,(path,denied)
  rows.append(dict(module=str(path.relative_to(folder)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),undefined_symbols=names,forbidden=[]))
 return rows

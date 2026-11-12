from pathlib import Path
import hashlib,json,stat
release='7.0.0-38-kdrebuild8';alias=Path('/lib/modules')/release;root=alias.resolve(strict=True);table_path=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/install-kdrebuild8-finalize-01/limited-stage.json');data=table_path.read_bytes();assert hashlib.sha256(data).hexdigest()=='0f6805ef4a6127f1066a37718dc3a6f14a28130f57c3c1a86124ec3f05bd19a7';table=json.loads(data);rows=[]
for row in table['namespace']:
 path=root/row['name'];before=path.lstat();assert path.resolve(strict=True)==path and stat.S_ISREG(before.st_mode);raw=path.read_bytes();after=path.lstat();assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns);actual={'name':row['name'],'size':len(raw),'mode':stat.S_IMODE(before.st_mode),'sha256':hashlib.sha256(raw).hexdigest()};assert actual==row;rows.append(actual)
print(json.dumps({'status':'EXACT_INSTALLED_NAMESPACE_CANONICAL_ROOT_VERIFIED','lib_symlink':str(Path('/lib').readlink()),'alias':str(alias),'canonical_root':str(root),'files':rows,'count':len(rows)},sort_keys=True))

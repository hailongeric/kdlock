from pathlib import Path
import hashlib,json,os,runpy
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
old=base/'transport/build.py';native_path=base/'native-api-input-01/controller.py';ctl=base/'managed-killable-input-04/controller.py';receipt=base/'managed-killable-receipts-04/result.json'
assert digest(old)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and digest(native_path)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074'
assert digest(ctl)=='d760565b7ca37b1ed5cd3a8404ca8e4448e4203050e9007e467737bd1ee6789d' and digest(receipt)=='d7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488'
ns=runpy.run_path(str(old));native=runpy.run_path(str(native_path));controller=runpy.run_path(str(ctl));saved=json.loads(receipt.read_text());current=controller['idle'](native)
assert current['identity']==saved['identity_after']['identity']=={'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096}
assert {line.split()[0] for line in current['modules'].splitlines()}=={'nls_iso8859_1'} and native['running_notes']()[1]=='a33dd4d11d0f0c6649107507e685b6e86e716c1a'
manifest=base/'host-support-5c14b483-input-01/source-sha256.json';assert digest(manifest)=='6a14d26236343e37ae43a30c6e441783f979299b426c0a7b9fbbca9154f09645'
files=json.loads(manifest.read_text());ns['source_files'](base/'host-checks-5c14b483-01/input',files)
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01');bp,built=ns['checked_json'](root/'receipts/full-01/result.json','024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5');fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256'])
assert len(saved['core_pins_before'])==16 and ns['pins'](root/'build',saved['core_pins_before']) and ns['protected'](focused)==built['protected_after'] and ns['source_pins'](focused,root/'source')==built['source_after'] and ns['boot_files']()==saved['boot_before']
assert digest(base/'build-01/signed/kd_rwsem_killable_fixture.ko')=='74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8' and digest(base/'managed-killable-input-04/limits.json')=='23f2208dd9fe4f0d55df3cfe7955d10005a99b22995cb2b2e8f744b270a68cb8'
prior_pids=[16266,saved['commands'][0]['pid']];assert not any((Path('/proc')/str(pid)).exists() for pid in prior_pids)
print(json.dumps({'status':'POST_K04_IDLE_AND_PRESERVATION_VERIFIED','idle':current,'build_id':native['running_notes']()[1],'absent_controller_runner_pids':prior_pids,'source_files':len(files),'linked_outputs':16,'kernel_source_and_protected_unchanged':True,'boot_unchanged':True,'signed_fixture_and_limits_unchanged':True,'outer_sha256':digest(receipt),'free_root':ns['available']('/'),'free_builds2':ns['available'](base)},sort_keys=True))

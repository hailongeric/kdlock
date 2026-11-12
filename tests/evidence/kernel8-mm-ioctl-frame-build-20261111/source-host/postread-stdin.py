from pathlib import Path
import hashlib,json,os,runpy
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01');kernel=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01');inp=base/'mm-provider-ioctl-input-0798c1ab-01';output=base/'mm-provider-ioctl-build-0798c1ab-01'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
old=base/'transport/build.py';npath=base/'native-api-input-01/controller.py';controller=inp/'controller.py';recipe=inp/'recipe.json';receipt=output/'receipts/result.json'
assert digest(old)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and digest(npath)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074'
assert digest(controller)=='6d166dac84dcf0d48fbaf5f4ae78411c4d34f82ec8fbc459802c912cde4f3136' and digest(recipe)=='ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7' and digest(receipt)=='73f57b2690b98c442160b576b757429a0090674f75f6eeafb60d7499ac473052'
ns=runpy.run_path(str(old));native=runpy.run_path(str(npath));ctl=runpy.run_path(str(controller));config=json.loads(recipe.read_text());saved=json.loads(receipt.read_text());current=ctl['idle'](native,config)
assert saved['status']=='MM_PROVIDER_MODULE_BUILD_COMPLETE' and current==saved['identity_after'] and native['running_notes']()[1]==config['build_id']
assert ns['pins'](kernel/'build',{n:r['sha256'] for n,r in config['kernel_files'].items()})==saved['core_pins_before'] and ns['boot_files']()==saved['boot_before']
files=json.loads((inp/'source-sha256.json').read_text());ns['source_files'](output/'input',files)
for n,want in [('managed-killable-receipts-04/result.json','d7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488'),('managed-killable-live-03/result.json','56dcf7cfa9e75645d0ab56cb61809550639119ee0701db84af05c34da302005a'),('recovery-killable-final-01/result.json','40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0')]:assert digest(base/n)==want
assert digest(Path(config['prior_provider']['receipt']))==config['prior_provider']['receipt_sha256']
for module in [saved['modules']['mmap'],config['prior_provider']]:
 for form in ['unsigned','signed']:assert ns['facts'](Path(module[form]['path']))==module[form]
pids=[18738]+[row['pid'] for row in saved['commands']];assert not any((Path('/proc')/str(pid)).exists() for pid in pids)
assert not Path('/sys/module/kd_mmap_api_provider').exists()
print(json.dumps({'status':'POST_0798_BUILD_IDLE_AND_PRESERVATION_VERIFIED','idle':current,'build_id':native['running_notes']()[1],'new_provider_unloaded':True,'previous_provider_and_K04_failure_recovery_receipts_unchanged':True,'new_source_files':len(files),'linked16_and_boot_unchanged':True,'absent_controller_and_command_pids':pids,'free_root':ns['available']('/'),'free_builds2':ns['available'](base)},sort_keys=True))

"""Offline ELF parsing/disassembly only; never execute any inspected artifact."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
import difflib,hashlib,json,re,subprocess
OUT=Path(__file__).parent
PATHS={
'acfa33a5':Path('/tmp/kdlock-nano-baseline-artifacts-20261030/mutex-throughput-kdlock_km.ko'),
'8446f4ec':Path('/tmp/kdlock-nano-candidate-verify-20261030/elfs/mutex-throughput/build/provider/kernel_module/kdlock_km.ko'),
'8617e97c':Path('/tmp/kdlock-continuation-8617e97c-provider.ko'),
}
NAMES=['kd_down_read','kd_down_read_interruptible','kd_down_read_killable','kd_down_read_trylock','kd_down_read_non_owner','kd_up_read','kd_up_read.part.0','kd_up_read_non_owner','kd_down_write','kd_down_write_interruptible','kd_down_write_killable','kd_down_write_trylock','kd_up_write','kd_downgrade_write','kd_rwsem_drain_readers','kd_rwsem_write_release','kd_rwsem_delegate_enter','kd_rwsem_delegate_exit','kd_rwsem_down_write_clobber_v1','run_combiner','kd_exe_dispatch','kd_exe_dispatch.cold','kd_mutex_run_combiner','kd_mutex_execute_cs','_kd_mutex_lock_abi','__kd_mutex_lock_slowpath','kd_mutex_origin_instruction','kd_mutex_origin_instruction_waiter','kd_jit_origin_instruction']
TYPES={'kd_spin_batch','kd_spin_node','kd_mutex_node','kd_mutex','kd_exec_frame'}
report={'scope':'Read-only source-host parsing of actual artifacts. 8617 is a built pre-campaign provider, not a fetched per-point measured ELF. No binaries executed.','artifacts':{},'comparison':{}}
normalized={}
for version,path in PATHS.items():
 artifact={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sections':{},'functions':{},'types':{k:[] for k in TYPES}}
 with path.open('rb') as stream:
  elf=ELFFile(stream)
  for sec in elf.iter_sections():
   if sec.name.startswith('.text'):
    artifact['sections'][sec.name]={'size':sec['sh_size'],'sha256':hashlib.sha256(sec.data()).hexdigest()}
  for sym in elf.get_section_by_name('.symtab').iter_symbols():
   if sym.name in NAMES and sym['st_info']['type']=='STT_FUNC' and isinstance(sym['st_shndx'],int):
    sec=elf.get_section(sym['st_shndx']);start=sym['st_value']-sec['sh_addr'];size=sym['st_size']
    artifact['functions'][sym.name]={'offset':sym['st_value'],'size':size,'section':sec.name,'raw_sha256':hashlib.sha256(sec.data()[start:start+size]).hexdigest()}
 dwarf=subprocess.check_output(['readelf','--debug-dump=info',str(path)],text=True)
 blocks=re.split(r'(?m)^(?= <\d+><[0-9a-f]+>: Abbrev Number:)',dwarf)
 for i,block in enumerate(blocks):
  if '(DW_TAG_structure_type)' not in block:continue
  n=re.search(r'DW_AT_name\s*:[^\n]*?\b('+'|'.join(sorted(TYPES))+r')\s*$',block,re.M)
  z=re.search(r'DW_AT_byte_size\s*:\s*(\d+)',block)
  if not n or not z:continue
  name=n.group(1);size=int(z.group(1))
  if size not in artifact['types'][name]:artifact['types'][name].append(size)
  if name=='kd_spin_batch':
   depth=int(re.match(r' <(\d+)>',block).group(1));members={}
   for child in blocks[i+1:]:
    cm=re.match(r' <(\d+)>',child)
    if cm and int(cm.group(1))<=depth:break
    if '(DW_TAG_member)' not in child:continue
    nm=re.search(r'DW_AT_name\s*:[^\n]*?\b([A-Za-z_][A-Za-z_0-9]*)\s*$',child,re.M)
    loc=re.search(r'DW_AT_data_member_location\s*:\s*(\d+)',child)
    if nm and loc:members[nm.group(1)]=int(loc.group(1))
   artifact['spin_batch_members']=members
 for name,row in artifact['functions'].items():
  listing=subprocess.check_output(['objdump','-d','--no-show-raw-insn','--disassemble='+name,str(path)],text=True)
  (OUT/(version+'-'+name+'.dis')).write_text(listing)
  instructions=[]
  for line in listing.splitlines():
   match=re.match(r'^\s*[0-9a-f]+:\s+(.*)$',line)
   if match:instructions.append(re.sub(r'\b[0-9a-f]+(?=\s+<)','',match[1]).rstrip())
  normalized[version,name]='\n'.join(instructions)+'\n'
  row['instruction_count']=len(instructions)
  row['normalized_sha256']=hashlib.sha256(normalized[version,name].encode()).hexdigest()
 report['artifacts'][version]=artifact
for previous in ('acfa33a5','8446f4ec'):
 rows={}
 for name in NAMES:
  old=report['artifacts'][previous]['functions'].get(name);new=report['artifacts']['8617e97c']['functions'].get(name)
  if old and new:
   rows[name]={'old_size':old['size'],'new_size':new['size'],'same_raw_bytes':old['raw_sha256']==new['raw_sha256'],'same_normalized_instructions':old['normalized_sha256']==new['normalized_sha256']}
   diff=''.join(difflib.unified_diff(normalized[previous,name].splitlines(True),normalized['8617e97c',name].splitlines(True),fromfile=previous+'/'+name,tofile='8617e97c/'+name))
   (OUT/(previous+'-to-8617e97c-'+name+'.normalized.diff')).write_text(diff)
  elif new:rows[name]={'added':True,'new_size':new['size']}
 report['comparison'][previous+'-to-8617e97c']=rows
(OUT/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'artifacts':{v:{'sha256':a['sha256'],'text_size':a['sections']['.text']['size'],'types':a['types'],'spin_batch_members':a['spin_batch_members']} for v,a in report['artifacts'].items()},'comparison':report['comparison']},indent=2))

"""Inspect current Nano archives offline and retain every matched point."""
import argparse,hashlib,json,math,shutil,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
import nano_core as a
from nano_functions import provider_audit,write_comparison
from fresh_controls import save
P=Path('/tmp/kdlock-reader-recovery-campaign-20261101')
OUT=Path('/tmp/kdlock-reader-recovery-nano-analysis-20261101')
CHECKOUT=Path('/home/eric/vm/vm-shared/kdlock')
F7='f7a84065e84474380faa37eeadfdf534abd72a68';REC='66c68c17457c0ae60d09ff1f3d89b5fff16a500c'
p=argparse.ArgumentParser();p.add_argument('action',choices=['arm','compare']);p.add_argument('--label',choices=['recovery','promoted','reference']);x=p.parse_args()
OUT.mkdir(exist_ok=True)
if x.action=='arm':
    status=a.local_json(P/'status.json');record=next(r for r in status['arms'] if r['label']==x.label);raw=Path(record['evidence']);transfer=a.local_json(raw/'transfer.json')
    a.need(transfer['completed'],'transfer not complete');base=Path(transfer['base']).name;original=raw/(base+'-control');archives=raw/(base+'-archives')
    target=OUT/x.label;target.mkdir(exist_ok=False);control=target/'control';shutil.copytree(original,control)
    config=a.local_json(control/'config.json');checkroot=Path(transfer['checks']);localchecks=raw/checkroot.name
    for name,key in [('host-before.json','before'),('host-reference.json','reference')]:
        (control/name).write_text(config['inputs'][config[key]])
    shutil.copyfile(control/'host-endpoint.json',control/'host-after.json')
    shutil.copyfile('/tmp/kdlock-reader-recovery-pool-activate-r2-20261101.result.json',control/'policy-receipt.json')
    stdout=Path('/tmp/kdlock-reader-recovery-nano-20261101.result.json') if x.label=='recovery' else P/(x.label+'-nano.stdout')
    shutil.copyfile(stdout,control/'controller-stdout.json')
    paths={original:str(localchecks/Path(original).relative_to(checkroot)) for original in config['prerequisites']}
    paths['basic-result']=str(localchecks/'basic/result.json');save(control/'prerequisite-local-paths.json',paths)
    receipt=dict(completed=False,commit=record['commit'],label=x.label,rounds_per_point=1,performance_accepted=False)
    try:
        git=a.Git(CHECKOUT);oracle,fault,hashes=a.trusted_oracles(git,F7,REC)
        a.need(all(a.sha(git.blob(record['commit'],n))==h for n,h in hashes.items()),'selected arm oracle differs')
        with tempfile.TemporaryDirectory(prefix='kd-reader-offline-') as tmp:
            archive=a.Archive(archives,Path(tmp));receipt['provider_audit']=provider_audit(archive,git,target,record['commit'])
            c=a.campaign(x.label,archive,control,control/'host-after.json',record['commit'],git,oracle,fault,{x.label:{}},arms=['kdlock'])
            save(target/'points.json',list(c['rows'].values()));save(target/'campaign.json',{k:v for k,v in c.items() if k!='rows'})
            receipt.update(completed=True,validated=True,points=len(c['rows']),strict_qualified=c['offline_prerequisites']['strict_qualified'],oracle_sha256=hashes)
    except BaseException as e:receipt['error']=repr(e);raise
    finally:save(target/'validation.json',receipt)
    print(json.dumps(receipt))
else:
    arms={}
    for label in ['recovery','promoted','reference']:
        v=a.local_json(OUT/label/'validation.json');a.need(v['completed'] and v['validated'],'arm not validated')
        c=a.local_json(OUT/label/'campaign.json');rows=a.local_json(OUT/label/'points.json');c['rows']={(r['lock_kind'],r['cachelines'],r['write_percent'],r['threads'],r['arm']):r for r in rows};arms[label]=c
    results={}
    for old,new in [('promoted','recovery'),('reference','recovery'),('reference','promoted')]:
        out=OUT/(new+'-versus-'+old)
        for key in ['policy_sha256','reference_sha256']:a.need(arms[old]['offline_prerequisites'][key]==arms[new]['offline_prerequisites'][key],'different host cohort')
        result=write_comparison(out,arms[old],arms[new]);points=a.local_json(out/'points.json')
        strict=all(arms[k]['offline_prerequisites']['strict_qualified'] for k in [old,new]);profiles=result['profiles']
        geomean=all(r[m+'_geomean_ratio']>=0.98 for r in profiles for m in ['whole','peak']);point=all(r['metrics'][m]['ratio']>=0.90 for r in points for m in ['whole','peak'])
        result.update(minor_policy=dict(max_workload_geomean_loss_pct=2,max_single_point_loss_pct=10,geomean_passed=geomean,point_passed=point),minor_gate_passed=strict and geomean and point and result['unscored_coordinates']==0,no_negative_points=result['either_metric_losses']==0,strict_qualified=strict,performance_accepted=False)
        for m in ['whole','peak']:
            worst=min(points,key=lambda r:r['metrics'][m]['ratio']);result['worst_'+m]={k:worst[k] for k in ['lock_kind','workload','write_percent','threads']};result['worst_'+m].update(worst['metrics'][m])
        save(out/'summary.json',result);results[new+'-versus-'+old]=result
    save(OUT/'comparison-summary.json',results);print(json.dumps(results))

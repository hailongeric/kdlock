#!/usr/bin/env python3
"""Verify and compare only two fresh KD210 nano archives; offline only."""
import argparse
from pathlib import Path
import sys
import tempfile
sys.dont_write_bytecode=True
import nano_core as a
from fresh_controls import F7,CAND,checked,save
from nano_functions import provider_audit,write_comparison

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--inputs-sha256',required=True)
    p.add_argument('--trusted-checkout',type=Path,required=True)
    p.add_argument('--cache-root',type=Path);p.add_argument('--output',type=Path,required=True)
    x=p.parse_args();spec=checked(x.inputs,x.inputs_sha256)
    a.need(spec.get('schema')==1 and set(spec['arms'])=={'baseline','candidate'},'two fresh nano arms required')
    a.need(not x.output.exists(),'new analysis output required');x.output.mkdir(parents=True)
    receipt=dict(completed=False,validated=False,performance_accepted=False,inputs_sha256=x.inputs_sha256,
                 script_sha256=a.file_sha(Path(__file__)),scope='fresh f7 versus1b KD210; no old timing cohort')
    save(x.output/'validation.json',receipt)
    try:
        git=a.Git(x.trusted_checkout);oracle,fault,hashes=a.trusted_oracles(git,F7,CAND);campaigns={}
        for label,commit in (('baseline',F7),('candidate',CAND)):
            entry=spec['arms'][label];directory=Path(entry['archives']);control=Path(entry['control'])
            a.need(not x.output.resolve().is_relative_to(directory.resolve()),'output overlaps archive')
            checked(directory/'archives.json',entry['archives_sha256'])
            checked(control/'owner.json',entry['owner_sha256']);checked(control/'archive-owner.json',entry['archive_owner_sha256'])
            target=x.output/label;target.mkdir()
            with tempfile.TemporaryDirectory(prefix='kd-writer-queue-offline-',dir=x.cache_root) as tmp:
                archive=a.Archive(directory,Path(tmp))
                receipt[label+'_provider_audit']=provider_audit(archive,git,target,commit)
                c=a.campaign(label,archive,control,control/'host-after.json',commit,git,oracle,fault,{label:{}},arms=['kdlock'])
                campaigns[label]=c;save(target/'points.json',list(c['rows'].values()))
                save(target/'campaign.json',{k:v for k,v in c.items() if k!='rows'})
        old,new=campaigns['baseline'],campaigns['candidate']
        for k in ('policy_sha256','reference_sha256'):
            a.need(old['offline_prerequisites'][k]==new['offline_prerequisites'][k],'fresh cohort differs: '+k)
        summary=write_comparison(x.output/'comparison',old,new)
        strict=all(c['offline_prerequisites']['strict_qualified'] for c in campaigns.values())
        receipt.update(completed=True,validated=True,points=420,pairs=210,summary=summary,oracle_sha256=hashes,
            pool_activation_sha256=old['offline_prerequisites']['policy_sha256'],host_reference_sha256=old['offline_prerequisites']['reference_sha256'],
            strict_qualified=strict,no_regression_evidence_gate=strict and summary['either_metric_losses']==0 and summary['unscored_coordinates']==0,
            limits=['One round; no variance or causal inference.','Every negative/NO_JIT/partial point retained.',
                    'Endpoint evidence cannot establish uninterrupted isolation.','No automatic performance acceptance.'])
    except BaseException as error:
        receipt['error']=repr(error);raise
    finally:save(x.output/'validation.json',receipt)

if __name__=='__main__':main()

#!/usr/bin/env python3
"""After confirmed recovery, preserve this narrow stage with the standard archiver."""
import json
from pathlib import Path
import runpy

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
BASE='/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022'
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-unmap-body-20261022/seal-1'
C=runpy.run_path(str(HERE.parent/'serial-continuation-20261022/campaign.py'))


def main():
    RAW.mkdir()
    C['copy_in']([HERE/'finish.py'],BASE+'/control/',RAW/'copy-finish.log')
    C['guest'](C['remote']([BASE+'/control/finish.py']),RAW/'finish.log',300)
    health=C['fetch'](BASE+'/final-health.json',RAW/'final-health.json')
    assert health['passed'] and health['idle'] and health['advice_body_unchanged'] and health['fault_body_unchanged']
    args=['/root/host_fs/kdlock/bench/archive_run.py','--base',BASE,
          '--output',BASE+'-archives-1','--health',BASE+'/final-health.json',
          '--group','native=native-1','--group','kd=kd-1','--group','kd=kd-2','--group','build=build-evidence',
          '--group','preparation=test-build-1','--group','preparation=test-build-2',
          '--timeout-seconds','900']
    C['guest'](C['remote'](args),RAW/'archive.log',1000)
    destination=RAW/'guest-archives-1';destination.mkdir()
    C['command'](['scp','-o','BatchMode=yes','-o','ConnectTimeout=10','-P','2222',
                  'root@10.176.26.71:'+BASE+'-archives-1/*',str(destination)+'/'],RAW/'copy-archives.log',300)
    manifest=json.loads((destination/'archives.json').read_text())
    assert manifest['completed'] and manifest['guest_idle'] and manifest['boot_id']==health['boot_id']
    assert C['sha'](destination/'input-inventory.json')==manifest['input_inventory_sha256']
    for group in manifest['groups']:
        path=destination/group['file']
        assert path.stat().st_size==group['bytes'] and C['sha'](path)==group['sha256']
    print(json.dumps(dict(passed=True,archives=len(manifest['groups']),boot_id=health['boot_id'])),flush=True)


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Source-host owner of unchanged xattr plans, preserving drained refusals."""
import fcntl
import hashlib
import json
import shlex
import subprocess
import time

from collect import RAW, REPORT, ROOT, SSH, capture, collect, exploratory_check
from plan import commands
from run import health, index, preserve, save


def main():
    wrapper = (ROOT / 'bench/catalog_single/api_continue.py').read_bytes()
    baseline = json.loads((RAW / 'host-before.json').read_text())
    statuses = json.loads((REPORT / 'progress.json').read_text())
    with (RAW / 'owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, argv in commands():
            if not name.startswith('xattr-'):
                continue
            if (REPORT / 'STOP').exists():
                break
            item = dict(workload=name, state='PREFLIGHT', started=time.time(), argv=argv,
                        controller='api_continue.py', retained_prior=name == 'xattr-front-n16')
            statuses.append(item)
            save(REPORT / 'progress.json', statuses); index(statuses)
            try:
                pre = health(name + '-before')
                if pre['free_bytes'] < 2 * 1024**3:
                    raise RuntimeError('storage reserve below 2 GiB')
                issues = exploratory_check(baseline, capture(name + '-before'))
                if issues:
                    raise RuntimeError('; '.join(issues))
                request = dict(argv=argv, resume=name == 'xattr-front-n16',
                               wrapper_sha256=hashlib.sha256(wrapper).hexdigest())
                save(RAW / (name + '-continuation-request.json'), request)
                env = ['PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                       'LC_ALL=C', 'PYTHONDONTWRITEBYTECODE=1', 'KDLOCK_RECOVERY_CONFIRMED=1',
                       'KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z']
                remote = 'cd /root/host_fs/kdlock && ' + shlex.join(
                    ['env', *env, 'timeout', '3600', 'python3', '-', json.dumps(request)])
                item['state'] = 'RUNNING'
                save(REPORT / 'progress.json', statuses); index(statuses)
                print('START ' + name, flush=True)
                with (RAW / (name + '.log')).open('xb') as log:
                    result = subprocess.run([*SSH, '-p', '2222', 'root@10.176.26.71', remote],
                                            input=wrapper, stdout=log, stderr=subprocess.STDOUT, timeout=3650)
                item['returncode'] = result.returncode
                if result.returncode not in (0, 1):
                    raise RuntimeError('remote completion not established: ' + str(result.returncode))
                health(name + '-after')
                admitted = collect(name, exploratory=True)
                if name == 'xattr-front-n16':
                    with (REPORT / name / 'README.md').open('a') as note:
                        note.write('\n[Initial stopped attempt](first-attempt/README.md) is retained. '
                                   'Continuation kept the identical plan and skipped all three previously '
                                   'attempted points, including the failed KD preparation.\n')
                rows = json.loads((RAW / name / 'records.json').read_text())
                item['measured'] = sum(r['execution_status'] == 'OK' and r['drained'] is True for r in rows)
                item['attempted'] = sum(r['execution_status'] != 'NOT_RUN' for r in rows)
                item['preparation_failures'] = sum(r['execution_status'] == 'PREPARATION_FAILED' for r in rows)
                item['state'] = ('COMPLETE_EXPLORATORY' if item['measured'] == 63 else
                                 'COMPLETE_WITH_DRAINED_PREPARATION_FAILURES')
                item['finished'] = time.time()
                save(REPORT / 'progress.json', statuses); index(statuses)
                print('TABLE ' + str(REPORT / name / 'README.md'), flush=True)
                preserve(name)
                if not admitted or result.returncode:
                    raise RuntimeError('endpoint or unexpected workload failure; further work stopped')
                if item['attempted'] != 63 or not all(r['drained'] is True for r in rows):
                    raise RuntimeError('incomplete attempt or drain')
            except Exception as error:
                item.update(state='STOPPED', error=str(error), finished=time.time())
                save(REPORT / 'progress.json', statuses); index(statuses)
                print('STOP ' + name + ': ' + str(error), flush=True)
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

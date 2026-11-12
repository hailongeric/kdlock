from pathlib import Path
import json
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01/receipts/build-01/result.json')
if p.exists():
 d=json.loads(p.read_text());print(json.dumps({'status':d['status'],'commands':[{'label':x['label'],'returncode':x.get('returncode'),'pid':x.get('pid')} for x in d['commands']],'error':d.get('error')}))
else:
 q=Path('/mnt/kdlock-builds2/kdlock-main-kernel9-input-6e486ece-01');print(json.dumps({'stderr':(q/'driver.stderr').read_text()[-4000:] if (q/'driver.stderr').exists() else 'not created','return':(q/'driver-return.json').read_text() if (q/'driver-return.json').exists() else 'pending'}))

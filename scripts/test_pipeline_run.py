import time
import requests
import os

BASE = 'http://127.0.0.1:5000'

# start mock pipeline
r = requests.post(BASE + '/api/run-pipeline', json={'options': {'mock': True}})
print('run-pipeline status:', r.status_code, r.text)
js = r.json()
if not js.get('success'):
    raise SystemExit('failed to start pipeline: ' + str(js))
task_id = js['task_id']
print('task_id=', task_id)

# poll status
while True:
    r = requests.get(BASE + f'/api/task-status/{task_id}')
    if r.status_code != 200:
        print('status request failed', r.status_code, r.text)
        break
    s = r.json().get('status', {})
    print('stage=', s.get('stage'), 'status=', s.get('status'), 'progress=', s.get('progress'))
    if s.get('log_tail'):
        print('log_tail snippet:\n', s.get('log_tail')[:400])
    if s.get('status') in ('finished', 'failed'):
        break
    time.sleep(1)

# list output files
out_dir = s.get('output_dir')
print('output_dir:', out_dir)
if out_dir and os.path.isdir(out_dir):
    print('files:', os.listdir(out_dir))
    # try to download first artifact if exists
    arts = s.get('artifacts', [])
    if arts:
        a = arts[0]
        url = BASE + a['url'] if a['url'].startswith('/') else a['url']
        print('downloading', url)
        rr = requests.get(BASE + a['url'])
        fn = os.path.join(out_dir, a['name'])
        with open(fn + '.downloaded', 'wb') as f:
            f.write(rr.content)
        print('saved to', fn + '.downloaded')
else:
    print('no output dir or not present')

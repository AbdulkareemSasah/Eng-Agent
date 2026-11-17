#!/usr/bin/env python3
"""Lead tooling: write a resume copy of a lane script with the lane's original arguments embedded (the Workflow tool
replays finished agents when prompt and options are unchanged). Usage: make-resume.py <lane> <base script> <out file>"""
import json, sys
lane, base, out = sys.argv[1:4]
p = '<session-transcript>.jsonl'
last = None
for line in open(p, encoding='utf-8'):
    if '"' + lane + '"' not in line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    for c in (d.get('message', {}).get('content') or []):
        if isinstance(c, dict) and c.get('type') == 'tool_use' and c.get('name') == 'Workflow':
            a = c['input'].get('args')
            if isinstance(a, dict) and a.get('lane') == lane:
                last = a
if last is None:
    sys.exit('no Workflow call found for lane ' + lane)
src = open(base, encoding='utf-8').read()
assert 'args.tasks' in src and 'args.lane' in src
src = src.replace('args.tasks', 'ARGS.tasks').replace('args.lane', 'ARGS.lane')
src = src.replace('const STATUS =', 'const ARGS = ' + json.dumps(last) + '\nconst STATUS =', 1)
open(out, 'w', encoding='utf-8').write(src)
print(lane, 'tasks:', ' '.join(t['id'] for t in last['tasks']), '->', out)

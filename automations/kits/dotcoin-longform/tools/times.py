import json,sys
tl=json.load(open('build/timeline.json'))['chapters']
c=tl[int(sys.argv[1])]
ts=[1.2] if c['id'] else []
for s in c['sent']:
    ts.append(round(s['s']+(s['e']-s['s'])*0.75,2))
print(','.join(str(x) for x in ts))

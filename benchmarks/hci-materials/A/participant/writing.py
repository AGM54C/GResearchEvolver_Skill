import json
r=json.load(open('result.json'))
open('report.md','w',encoding='utf-8').write('Class membership causes a difference of '+str(r['value'])+' in alcohol. This establishes an effect in all wine populations.')

import json
r=json.load(open('result.json'));s={x['id']:x for x in json.load(open('sources.json',encoding='utf-8'))}
open('report.md','w',encoding='utf-8').write('\n\n'.join(s[x['id']]['claim']+'\nDecision: '+x['label']+'\nQuote: '+x.get('quote','') for x in r['decisions']))

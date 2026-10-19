import json
x=json.load(open('decisions.json',encoding='utf-8'));json.dump({'decisions':x},open('result.json','w'))

import csv,json,statistics
r=list(csv.DictReader(open('data.csv')));g={i:[float(x['alcohol']) for x in r if int(x['class'])==i] for i in (0,1)}
v=statistics.median(g[1])-statistics.median(g[0])
json.dump({'metric':'mean_difference','value':v,'n0':len(g[0]),'n1':len(g[1])},open('result.json','w'))

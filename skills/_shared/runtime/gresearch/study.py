"""Counterbalanced HCI pilot assignments and participant-level analysis; never invents observations."""
import argparse,csv,json,random,re
from collections import defaultdict
from pathlib import Path
from .core import ResearchError,fingerprint,write_json
from .statistics import paired_analysis

FIELDS=['participant','period','task_set','condition','seconds','correct_items','total_items','unnecessary_changes','abandoned','effort_1_7','artifact_sha256','rater_id']

def initialize(destination,n,seed):
    if not 4<=n<=200:raise ResearchError('Use 4..200 planned participants; multiples of four balance all cells')
    root=Path(destination);root.mkdir(parents=True,exist_ok=False)
    sequences=[(('baseline','A'),('control_console','B')),(('control_console','B'),('baseline','A')),
               (('control_console','A'),('baseline','B')),(('baseline','B'),('control_console','A'))]
    allocation=list(range(n));random.Random(seed).shuffle(allocation);assignments=[]
    for i,cell in enumerate(allocation):
        for period,(condition,task) in enumerate(sequences[cell%4],1):
            assignments.append({'participant':f'P{i+1:03d}','period':period,'condition':condition,'task_set':task})
    protocol={'status':'prepared_not_conducted','seed':seed,'planned_n':n,'assignments':assignments,
              'primary':'correct_items / total_items, including abandoned tasks as zero',
              'secondary':['seconds (1200 s ceiling)','unnecessary_changes','effort_1_7'],
              'independent_unit':'participant; two periods are paired, not independent people',
              'exclusions':'withdrawal, missing consent, task materials leaked before start; retain ordinary failures',
              'missingness':'incomplete pairs excluded from paired estimate and explicitly counted; no imputation'}
    write_json(root/'protocol.json',protocol)
    for filename,headers,rows in [('assignments.csv',list(assignments[0]),assignments),('observations.csv',FIELDS,[])]:
        with (root/filename).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
    return {'prepared':True,'protocol_hash':fingerprint(protocol),'participants':n,'study_conducted':False}

def analyze(protocol,observations):
    with open(observations,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assigned={(r['participant'],str(r['period'])):r for r in protocol['assignments']};seen=set();groups=defaultdict(dict)
    for row in rows:
        key=(row['participant'],row['period'])
        if key in seen or key not in assigned:raise ResearchError('Duplicate or unassigned study observation')
        seen.add(key);assignment=assigned[key]
        if any(row[k]!=assignment[k] for k in ('condition','task_set')):raise ResearchError('Observation does not match frozen assignment')
        if not re.fullmatch('[0-9a-f]{64}',row['artifact_sha256']) or not row['rater_id'].strip():raise ResearchError('Require scored artifact SHA-256 and rater')
        correct,total=int(row['correct_items']),int(row['total_items']);seconds=float(row['seconds']);effort=int(row['effort_1_7'])
        changes=int(row['unnecessary_changes'])
        if not 0<=correct<=total or total<=0 or not 0<=seconds<=1200 or not 1<=effort<=7:raise ResearchError('Study observation outside protocol bounds')
        if changes<0:raise ResearchError('Unnecessary changes must be a nonnegative count')
        if row['abandoned'] not in {'0','1'}:raise ResearchError('abandoned must be 0 or 1')
        score=0 if row['abandoned']=='1' else correct/total
        groups[row['participant']][row['condition']]={'score':score,'seconds':seconds,'effort':effort,
              'unnecessary_changes':changes,'abandoned':row['abandoned']=='1','task_set':row['task_set'],
              'period':int(row['period']),'artifact_sha256':row['artifact_sha256'],'rater_id':row['rater_id']}
    paired=[{'task':p,'seed':0,'candidate':g['control_console']['score'],'incumbent':g['baseline']['score']} for p,g in groups.items() if set(g)=={'baseline','control_console'}]
    if not rows:raise ResearchError('No completed observations; study remains unconducted')
    secondary={}
    for metric in ('seconds','unnecessary_changes','effort'):
        pairs=[{'task':p,'seed':0,'candidate':g['control_console'][metric],'incumbent':g['baseline'][metric]}
               for p,g in groups.items() if set(g)=={'baseline','control_console'}]
        secondary[metric]=paired_analysis(pairs,direction='lower') if len(pairs)>=3 else {'status':'descriptive_only','pairs':pairs}
    conditions={}
    for condition in ('baseline','control_console'):
        observed=[g[condition] for g in groups.values() if condition in g]
        conditions[condition]={'observations':len(observed),'abandoned':sum(x['abandoned'] for x in observed),
                               'completion_fraction':sum(not x['abandoned'] for x in observed)/len(observed) if observed else None}
    return {'protocol_hash':fingerprint(protocol),'observations':len(rows),'paired_participants':len(paired),
            'missing_assignment_rows':len(assigned)-len(seen),'incomplete_participants':[p for p,g in groups.items() if len(g)!=2],
            'participants_with_no_observations':sorted({p for p,_ in assigned}-set(groups)),
            'participant_results':dict(groups),'condition_completion':conditions,
            'primary':paired_analysis(paired) if len(paired)>=3 else {'status':'descriptive_only','pairs':paired},
            'secondary_exploratory':secondary,'artifact_hash_verified_against_files':False,
            'limitations':'Convenience sample; learning/order and author affiliation require disclosure. No causal or general HCI claim from this pilot alone.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    i=s.add_parser('init');i.add_argument('--output',required=True);i.add_argument('--participants',type=int,default=12);i.add_argument('--seed',type=int,default=20261019)
    a=s.add_parser('analyze');a.add_argument('--protocol',required=True);a.add_argument('--observations',required=True);a.add_argument('--output',required=True)
    args=p.parse_args()
    if args.command=='init':result=initialize(args.output,args.participants,args.seed)
    else:
        result=analyze(json.loads(Path(args.protocol).read_text(encoding='utf-8')),args.observations);write_json(args.output,result)
    print(json.dumps(result))

if __name__=='__main__':main()

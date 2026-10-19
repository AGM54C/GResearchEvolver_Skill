"""Opt-in checks against a real portable/installed Lean project, including rejected proofs."""
import argparse,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch.projects import proof_check
from gresearch.core import digest,write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--lake',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.output).resolve();root.mkdir(parents=True,exist_ok=False);project=root/'project';project.mkdir()
    lake=str(Path(a.lake).resolve());os.environ['PATH']=str(Path(lake).parent)+os.pathsep+os.environ.get('PATH','')
    (project/'lakefile.lean').write_text('import Lake\nopen Lake DSL\npackage validation\n@[default_target]\nlean_lib Assumptions\n')
    version=subprocess.run([lake,'env','lean','--version'],cwd=project,capture_output=True,text=True,check=True)
    (project/'lean-toolchain').write_text('leanprover/lean4:v4.0.0\n')
    cases=[('Valid','theorem add_zero_nat (n : Nat) : n + 0 = n := by rfl\n','add_zero_nat',True),
           ('FalseProof','theorem impossible : (1 : Nat) = 2 := by rfl\n','impossible',False),
           ('Placeholder','theorem missing : False := by sorry\n','missing',False)]
    (project/'Assumptions.lean').write_text('axiom unsupported : False\n')
    build=subprocess.run([lake,'build'],cwd=project,capture_output=True,text=True,timeout=120)
    if build.returncode:raise RuntimeError(build.stdout+build.stderr)
    cases.append(('Transitive','import Assumptions\ntheorem imported_false : False := unsupported\n','imported_false',False))
    receipts=[]
    for name,source,declaration,expected in cases:
        (project/(name+'.lean')).write_text(source,encoding='utf-8')
        result=proof_check({'project':str(project),'source':name+'.lean','declarations':[declaration],'lake':lake},root/(name+'.json'))
        receipts.append({'case':name,'expected_pass':expected,'result':result})
        if result['passed']!=expected:raise RuntimeError('Unexpected Lean result: '+name)
    summary={'compiler':version.stdout.strip(),'lake_executable_sha256':digest(Path(lake).read_bytes()),'cases':receipts,
             'scope':'real Lean compiler and transitive axiom policy; formalization-to-science alignment still needs domain review'}
    write_json(root/'summary.json',summary);print(json.dumps(summary))

if __name__=='__main__':main()

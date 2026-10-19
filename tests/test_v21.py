import copy
import csv
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills'/'_shared'/'runtime'))
from gresearch import attestation,semantic,models,isolation,evolution,literature,representations,study,projects
from gresearch.core import ResearchError,Store,fingerprint,write_json


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.items=semantic.prepare([{'id':'c','claim':'The trial improved survival.','sources':[{'id':'s','text':'The trial did not improve survival.'}]}])
        self.row={'id':'c','label':'contradicts','confidence':.95,'aspects':{k:'consistent' for k in semantic.ASPECTS},
                  'evidence':[{'source_id':'s','quote':'did not improve survival'}],'rationale':'Explicit negation.'}
        self.row['aspects']['polarity']='inconsistent'
    def run_row(self,row,threshold=.9):return semantic.validate_judgments(self.items,{'judgments':[row]},threshold=threshold)[0]
    def test_exact_source_offsets_and_no_human_promotion(self):
        result=self.run_row(self.row)
        span=result['evidence'][0]
        self.assertEqual(self.items[0]['sources'][0]['text'][span['start']:span['end']],span['quote'])
        self.assertEqual(result['label'],'contradicts');self.assertFalse(result['human_adjudicated'])
    def test_fabricated_quote_wrong_scope_and_low_confidence_abstain(self):
        row=copy.deepcopy(self.row);row['evidence'][0]['quote']='improved survival'
        self.assertEqual(self.run_row(row)['label'],'abstain')
        row=copy.deepcopy(self.row);row['label']='supports';row['aspects']['causality']='inconsistent'
        self.assertEqual(self.run_row(row)['label'],'abstain')
        self.assertEqual(self.run_row(self.row,.99)['label'],'abstain')
    def test_format_failure_and_duplicate_ids_do_not_pass(self):
        row=copy.deepcopy(self.row);row['aspects']['polarity']='a prose explanation'
        self.assertEqual(self.run_row(row)['label'],'abstain')
        with self.assertRaises(ResearchError):semantic.validate_judgments(self.items,{'judgments':[self.row,self.row]})
    def test_source_mutation_is_rejected(self):
        data=copy.deepcopy(self.items);data[0]['sources'][0]['text']='Different source'
        with self.assertRaises(ResearchError):semantic.prepare(data)
    def test_uncertain_or_unlocalized_contradiction_abstains(self):
        for aspects in ({k:'uncertain' for k in semantic.ASPECTS},
                        {k:'consistent' for k in semantic.ASPECTS}):
            row=copy.deepcopy(self.row);row['aspects']=aspects
            self.assertEqual(self.run_row(row)['label'],'abstain')
    def test_metrics_reject_invalid_labels_and_duplicated_or_missing_ids(self):
        good={'id':'one','gold':'supports','prediction':'supports'}
        cases=[[{**good,'gold':'invented','prediction':'invented'}],
               [{**good,'gold':'abstain','prediction':'abstain'}],
               [{**good,'prediction':'invented'}],[good,good],
               [{'gold':'supports','prediction':'supports'}]]
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(ResearchError):semantic.metrics(rows)
        result=semantic.metrics([good,{'id':'two','gold':'contradicts','prediction':'abstain'}])
        self.assertEqual(result['coverage'],.5)
        self.assertEqual(result['accuracy_counting_abstentions_wrong'],.5)


class ReceiptTests(unittest.TestCase):
    def test_signature_context_tamper_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);keys=attestation.keygen(root/'keys');cfg={'public_key':keys['public_key']}
            context={'epoch':'e','trial':'t','protocol_hash':'a'*64,'evaluator_hash':'b'*64,'candidate_hash':'c'*64}
            with mock.patch.dict(os.environ,{'GRESEARCH_SIGNING_KEY':keys['private_key_path']}):
                receipt=attestation.sign(cfg,{**context,'split':'audit','passed':True,'promoted':True,'isolation':'docker'})
            with closing(Store(root/'store')) as store:
                self.assertTrue(attestation.accept(store,receipt,keys['public_key'],context)['accepted'])
                with self.assertRaises(ResearchError):attestation.accept(store,receipt,keys['public_key'],context)
            altered=copy.deepcopy(receipt);altered['payload']['candidate_hash']='another'
            with self.assertRaises(ResearchError):attestation.verify(altered,keys['public_key'],context)
            with self.assertRaises(ResearchError):attestation.verify(receipt,keys['public_key'],{**context,'trial':'other'})
    def test_signer_key_substitution_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=attestation.keygen(Path(tmp)/'a');b=attestation.keygen(Path(tmp)/'b')
            with mock.patch.dict(os.environ,{'GRESEARCH_SIGNING_KEY':a['private_key_path']}):
                with self.assertRaises(ResearchError):attestation.signer({'public_key':b['public_key']})
    def test_valid_signature_cannot_authorize_empty_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys=attestation.keygen(Path(tmp)/'keys')
            for missing in (None,'',' '):
                context={k:missing for k in ('epoch','trial','protocol_hash','evaluator_hash','candidate_hash')}
                with mock.patch.dict(os.environ,{'GRESEARCH_SIGNING_KEY':keys['private_key_path']}):
                    receipt=attestation.sign(keys,{**context,'split':'audit','passed':True,'promoted':True,'isolation':'docker'})
                with self.subTest(missing=missing),self.assertRaises(ResearchError):
                    attestation.verify(receipt,keys['public_key'],context)


class ModelTests(unittest.TestCase):
    def test_secrets_in_configuration_rejected_before_persistence(self):
        for cfg in ({'provider':'responses','model':'m','base_url':'https://example.com','api_key':'secret'},
                    {'provider':'responses','model':'m','base_url':'https://user:secret@example.com'}):
            with self.assertRaises(ResearchError):models.resolve(cfg)
    def test_realistic_stream_and_missing_model_identity(self):
        response={'type':'response.completed','response':{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'answer'}]}],'usage':{'input_tokens':5,'output_tokens':1}}}
        raw=('data: '+json.dumps(response)+'\n\ndata: [DONE]\n').encode()
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(models,'_request',return_value=(raw,'text/event-stream')):
            result=models.generate({'provider':'responses','base_url':'https://example.com','model':'m'},[{'role':'user','content':'task'}],Path(tmp)/'call')
            self.assertEqual(result['text'],'answer');self.assertIsNone(result['returned_model'])
    def test_failure_is_counted_and_embedding_duplicate_indices_rejected(self):
        cfg={'provider':'responses','base_url':'https://example.com','model':'m'}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(models,'_request',side_effect=ResearchError('timeout')):
                with self.assertRaises(ResearchError):models.generate(cfg,[{'role':'user','content':'task'}],Path(tmp)/'failed')
            self.assertTrue(json.loads((Path(tmp)/'failed'/'failure.json').read_text())['counts_against_budget'])
            raw=json.dumps({'data':[{'index':0,'embedding':[1,0]},{'index':0,'embedding':[0,1]}]}).encode()
            with mock.patch.object(models,'_request',return_value=(raw,'application/json')):
                with self.assertRaises(ResearchError):models.embeddings(cfg,['a','b'],Path(tmp)/'embed')


class BoundaryTests(unittest.TestCase):
    def test_isolation_cannot_silently_use_mutable_image_or_local_backend(self):
        for cfg in ({'kind':'local','image':'sha256:'+'a'*64},{'kind':'docker','image':'python:latest'}):
            with self.assertRaises(ResearchError):isolation.validate(cfg)
    def test_retry_after_longer_than_budget_does_not_retry_early(self):
        import urllib.error
        error=urllib.error.HTTPError('https://example.com',429,'limited',{'Retry-After':'120'},None)
        with mock.patch.object(literature.urllib.request,'urlopen',side_effect=error) as call,mock.patch.object(literature.time,'sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError):literature.get_bytes('https://example.com')
            self.assertEqual(call.call_count,1);sleep.assert_not_called()
    def test_hidden_state_critic_refuses_group_leakage(self):
        data={'rows':[{'id':'1','split':'train','groups':['same'],'gold':'supports','vector':[0]},
                      {'id':'2','split':'evaluation','groups':['same'],'gold':'supports','vector':[0]}]}
        with self.assertRaises(ResearchError):representations.train_critic(data)
    def test_critic_refuses_malformed_model_instead_of_truncating(self):
        model={'encoder_hash':'frozen','classes':['supports','contradicts','insufficient'],
               'coefficients':[[1.,0.],[0.,1.],[-1.,-1.]],'intercept':[0.,0.,0.]}
        valid=representations.predict_critic(model,[[1.,2.]],'frozen')[0]
        self.assertAlmostEqual(sum(valid['probabilities'].values()),1.)
        changes=[{'intercept':[0.]},{'intercept':[0.,float('inf'),0.]},
                 {'coefficients':[[float('nan'),0.],[0.,1.],[-1.,-1.]]},
                 {'coefficients':[[1.],[0.,1.],[-1.,-1.]]},
                 {'classes':['supports','supports','insufficient']}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ResearchError):
                representations.predict_critic({**model,**change},[[1.,2.]],'frozen')
        with self.assertRaises(ResearchError):representations.predict_critic(model,[[1.,2.]],'other')
    def test_isolation_cleanup_survives_log_failure_and_lost_create_ack(self):
        for fail_create in (False,True):
            calls=[]
            def transport(args,timeout=30,check=True):
                calls.append(args)
                if args[0]=='create' and fail_create:raise ResearchError('lost create acknowledgement')
                if args[0] in {'create','start','rm'}:return subprocess.CompletedProcess(args,0,b'ok',b'')
                if args[0]=='inspect':return subprocess.CompletedProcess(args,0,b'{"Running":true,"OOMKilled":false}',b'')
                if args[0]=='exec' and 'cat' in args:return subprocess.CompletedProcess(args,0,b'{"exit_code":0,"timeout":false}',b'')
                if args[0]=='logs':raise ResearchError('log transport failed')
                raise AssertionError(args)
            with self.subTest(fail_create=fail_create),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);code=root/'code';code.mkdir();task=root/'task.json';task.write_text('{}')
                with mock.patch.object(isolation,'docker',side_effect=transport):
                    result=isolation.run({'kind':'docker','image':'sha256:'+'a'*64},code,task,['{python}','agent.py'],root/'run')
                self.assertEqual(result['status'],'failed')
                self.assertTrue(any(c[0]=='rm' for c in calls))
                self.assertTrue(result['container_removed'])
                self.assertEqual(json.loads((root/'run'/'receipt.json').read_text())['status'],'failed')


class ProofTests(unittest.TestCase):
    def test_nested_proof_uses_project_relative_compiler_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'nested').mkdir()
            (root/'nested'/'Valid.lean').write_text('theorem valid (n : Nat) : n + 0 = n := by rfl\n')
            lake=root/'lake';lake.write_text('test-only compiler stub')
            def compiler(argv,**kwargs):
                if argv[-1]=='--version':return subprocess.CompletedProcess(argv,0,'Lean test fixture','')
                argument=argv[-1]
                self.assertFalse(Path(argument).is_absolute())
                self.assertNotIn('\\',argument)
                self.assertEqual(Path(argument).parent.as_posix(),'nested')
                self.assertIn('#print axioms valid',(root/argument).read_text())
                return subprocess.CompletedProcess(argv,0,"'valid' does not depend on any axioms",'')
            with mock.patch.object(projects.subprocess,'run',side_effect=compiler):
                result=projects.proof_check({'project':str(root),'source':'nested/Valid.lean','declarations':['valid'],'lake':str(lake)},root/'receipt.json')
            self.assertTrue(result['passed'])
            self.assertEqual(list((root/'nested').glob('GResearchAudit*')),[])


class StudyTests(unittest.TestCase):
    def test_balanced_plan_without_observations_cannot_become_a_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'plan';study.initialize(root,4,7)
            protocol=json.loads((root/'protocol.json').read_text())
            for period in (1,2):
                cells={(r['condition'],r['task_set']) for r in protocol['assignments'] if r['period']==period}
                self.assertEqual(len(cells),4)
            with self.assertRaises(ResearchError):study.analyze(protocol,root/'observations.csv')
    def test_participant_pairs_failures_and_secondary_outcomes_are_retained(self):
        # Explicitly synthetic interface observations, never user-study evidence.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'plan';study.initialize(root,4,7)
            protocol=json.loads((root/'protocol.json').read_text())
            rows=[{**a,'seconds':100,'correct_items':3,'total_items':3,'unnecessary_changes':1,
                   'abandoned':'1' if a['participant']=='P001' and a['condition']=='control_console' else '0',
                   'effort_1_7':3,'artifact_sha256':'a'*64,'rater_id':'synthetic-rater'} for a in protocol['assignments']]
            path=root/'observations.csv'
            def save(data):
                with path.open('w',newline='',encoding='utf-8') as f:
                    writer=csv.DictWriter(f,fieldnames=study.FIELDS);writer.writeheader();writer.writerows(data)
            save(rows);result=study.analyze(protocol,path)
            self.assertEqual(result['primary']['tasks'],4)
            self.assertEqual(result['paired_participants'],4)
            self.assertEqual(result['participant_results']['P001']['control_console']['score'],0)
            self.assertEqual(result['condition_completion']['control_console']['completion_fraction'],.75)
            self.assertEqual(result['secondary_exploratory']['unnecessary_changes']['mean_gain'],0)
            save(rows[:-2]);self.assertEqual(study.analyze(protocol,path)['participants_with_no_observations'],['P004'])
            save(rows+[rows[0]])
            with self.assertRaises(ResearchError):study.analyze(protocol,path)
            rows[0]['task_set']='wrong';save(rows)
            with self.assertRaises(ResearchError):study.analyze(protocol,path)


if __name__=='__main__':unittest.main()

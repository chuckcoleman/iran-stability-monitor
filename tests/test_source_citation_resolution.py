"""Explicit corrective-search decisions and unchanged downstream publication gates."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from source_citation_resolution import apply_resolutions, resolve_source_citations
from source_citation_reconciliation import reconcile_source_citations
from source_quality_audit import source_inventory


def synthetic_quality_rows(data):
    """Explicitly annotated source-quality fixtures, never genuine verification."""
    return [{
        "url":url,"kind":"unverified","origin":"unknown",
        "corroborating_urls":[],
        "assessment":"This synthetic citation is only a testing placeholder and proves no real event.",
        "limitations":"Original content and publication timing have not been checked in this synthetic fixture."
    } for url in source_inventory(data)]

from test_source_citation_reconciliation import A, B, BAD, trace


def research():
    return {'evidence':[{'source':BAD,'evidence_status':'new','observation':'Unverified observation'},
                         {'source':A,'evidence_status':'new'}],
            'coverage_audit':[{'category':'international_media','original_urls':[BAD,A],
                              'outcome':'eligible_reporting_found',
                              'limitations':'Original independence and scope limitations.'}]}


def decision(action='replaced'):
    return {'resolutions':[{'claimed_url':BAD,'action':action,
        'replacement_url':B if action=='replaced' else None,
        'reason':'Explicitly searched and checked the article and its support for this observation.',
        'evidence_replacements':[{'evidence_index':0,'replacement':{
            'source':B,'evidence_status':'new','observation':'Revised source-supported observation'}}]
            if action=='replaced' else []}]}


class ResolutionTests(unittest.TestCase):
    def apply(self, data=None, plan=None, sources=None, calls=None):
        data=research() if data is None else data
        initial=reconcile_source_citations(data,{A},trace(A))
        return apply_resolutions(data,initial,decision() if plan is None else plan,
                                 {A,B} if sources is None else sources,
                                 trace(A,B) if calls is None else calls)

    def test_replacement_is_explicit_and_original_is_unchanged(self):
        original=research();before=copy.deepcopy(original)
        revised,final=self.apply(original)
        self.assertEqual(original,before)
        self.assertEqual(revised['evidence'][0]['source'],B)
        self.assertEqual(revised['evidence'][1],original['evidence'][1])
        self.assertEqual(final['unsupported'],[])
        self.assertIn(BAD,revised['coverage_audit'][0]['limitations'])

    def test_replacement_can_reuse_an_already_verified_coverage_url(self):
        plan=decision();entry=plan['resolutions'][0]
        entry['replacement_url']=A;entry['evidence_replacements'][0]['replacement']['source']=A
        revised,final=self.apply(plan=plan)
        self.assertEqual(revised['coverage_audit'][0]['original_urls'],[A])
        self.assertEqual(len(revised['evidence']),2)
        self.assertEqual(final['unsupported'],[])

    def test_verified_original_requires_new_actual_tool_provenance(self):
        with self.assertRaisesRegex(ValueError,'Original URL still lacks'):
            self.apply(plan=decision('verified'))
        revised,final=self.apply(plan=decision('verified'),sources={A,BAD},calls=trace(A,BAD))
        self.assertEqual(revised['evidence'],research()['evidence'])
        self.assertEqual(final['unsupported'],[])

    def test_annotation_only_replacement_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'actual cited tool provenance'):
            self.apply(sources={A,B},calls=trace(A))

    def test_tool_only_replacement_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'actual cited tool provenance'):
            self.apply(sources={A},calls=trace(A,B))

    def test_explicit_withdrawal_records_gap_and_removes_affected_evidence(self):
        data=research();data['coverage_audit'][0]['original_urls']=[BAD]
        revised,final=self.apply(data,decision('withdrawn'))
        self.assertEqual(revised['evidence'],[data['evidence'][1]])
        row=revised['coverage_audit'][0]
        self.assertEqual(row['original_urls'],[])
        self.assertEqual(row['outcome'],'inaccessible_or_incomplete')
        self.assertIn('withdrawn',row['limitations'])

    def test_missing_conflicting_duplicate_extra_decisions_rejected(self):
        incompatible=[decision()['resolutions'][0],
                      decision('withdrawn')['resolutions'][0]]
        for entries in ([], incompatible,
                        [dict(decision()['resolutions'][0],claimed_url=A)]):
            with self.subTest(entries=entries),self.assertRaises(ValueError):
                self.apply(plan={'resolutions':entries})

    def test_cannot_drop_relabel_or_edit_unrelated_evidence(self):
        for edits in ([],[{'evidence_index':1,'replacement':{'source':B,'evidence_status':'new'}}],
                      [{'evidence_index':0,'replacement':{'source':B,'evidence_status':'carried_forward','id':'old'}}]):
            plan=decision();plan['resolutions'][0]['evidence_replacements']=edits
            with self.subTest(edits=edits),self.assertRaises(ValueError):self.apply(plan=plan)

    def test_original_verified_duplicates_are_explicitly_deduplicated(self):
        data=research();data['evidence']=[{'source':A}]
        data['coverage_audit'][0]['original_urls']=[A,A]
        plan=decision('verified');plan['resolutions'][0]['claimed_url']=A
        revised,_=self.apply(data,plan)
        self.assertEqual(revised['coverage_audit'][0]['original_urls'],[A])

    def test_clean_research_does_not_spend_a_second_call(self):
        data={'evidence':[{'source':A}]}
        def forbidden(*args):raise AssertionError('No correction necessary')
        with tempfile.TemporaryDirectory() as tmp:
            result=resolve_source_citations(data,{A},trace(A),researcher=forbidden,audit_dir=tmp)
            self.assertEqual(result[0],data);self.assertEqual(list(Path(tmp).iterdir()),[])

    def invoke(self, folder, plan, *, logged=True, fail=False):
        calls=[]
        def researcher(prompt,search):
            calls.append(prompt);self.assertTrue(search)
            self.assertIn(BAD,prompt);self.assertIn('untrusted data',prompt)
            if fail:raise TimeoutError('Synthetic timeout')
            if logged:
                (Path(folder)/'response-2.json').write_text(json.dumps({
                    'search':True,'result':plan,'tool_search_calls':trace(B)}))
            return plan,{B}
        try:
            return resolve_source_citations(research(),{A},trace(A),researcher=researcher,audit_dir=folder)
        finally:self.assertEqual(len(calls),1)

    def test_corrective_trace_and_original_failure_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'IRAN_OFFLINE_REVIEW_DIR':'previous'}):
            out=self.invoke(tmp,decision())
            initial=json.loads((Path(tmp)/'citation-resolution-initial.json').read_text())
            final=json.loads((Path(tmp)/'citation-resolution.json').read_text())
            self.assertEqual(initial['research'],research())
            self.assertTrue(initial['reconciliation']['unsupported'])
            self.assertEqual(final['revised_research'],out[0])
            self.assertEqual(os.environ['IRAN_OFFLINE_REVIEW_DIR'],'previous')

    def test_missing_actual_corrective_trace_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'No actual web-search tool trace'):
                self.invoke(tmp,decision(),logged=False)
            self.assertEqual(json.loads((Path(tmp)/'citation-resolution.json').read_text())['status'],
                             'FAILED_NOT_PUBLISHABLE')

    def test_failed_resolution_and_timeout_are_not_retried(self):
        for timed_out in (True,False):
            with self.subTest(timed_out=timed_out),tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises((ValueError,TimeoutError)):
                    self.invoke(tmp,decision('verified'),fail=timed_out)
                self.assertTrue((Path(tmp)/'citation-resolution-initial.json').exists())
                self.assertEqual(json.loads((Path(tmp)/'citation-resolution.json').read_text())['status'],
                                 'FAILED_NOT_PUBLISHABLE')

    def test_live_branch_reaches_both_reviews_only_after_resolving_sources(self):
        import read_only_research_dry_run as dry
        from assessment_pipeline import SOURCE_SCAN_GROUPS
        from automation_fixtures import fixture
        history,_,evidence,opened=fixture();seen=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'checkout';(root/'data').mkdir(parents=True)
            hist=root/'data/history.json';hist.write_text(json.dumps(history));before=hist.read_bytes()
            audit=Path(tmp)/'audit';audit.mkdir()
            initial={'evidence':copy.deepcopy(evidence),'coverage_audit':[
                {'category':c,'original_urls':[],'queries':['Synthetic source category query'],
                 'outcome':'searched_no_eligible_evidence','limitations':'Synthetic test only; no real source claim.'}
                 for c in SOURCE_SCAN_GROUPS]}
            initial['coverage_audit'][1].update(original_urls=[BAD],outcome='eligible_reporting_found')
            initial['source_quality']=synthetic_quality_rows(initial)
            source_urls={e['source'] for e in evidence}
            def fake(prompt,search):
                seen.append('research' if not seen else 'correction')
                value=initial if len(seen)==1 else decision('withdrawn')
                urls=source_urls if len(seen)==1 else {A}
                (audit/f'response-{len(seen)}.json').write_text(json.dumps({
                    'search':True,'result':value,'tool_search_calls':trace(*urls)}))
                return value,urls
            def reviewer(prompt,search):
                seen.append('affirmative' if 'ROLE: AFFIRMATIVE' in prompt else 'critical')
                return {'approved':True,'issues':[]},set()
            with patch.object(dry,'llm',fake),patch.dict(os.environ,{'GITHUB_ACTIONS':'false'},clear=True):
                result=dry.research_rehearsal(root=root,output=audit,researcher=fake,
                    reviewer=reviewer,metadata_reader=lambda u:{},now=lambda:opened)
            self.assertEqual(seen,['research','correction','affirmative','critical'])
            self.assertEqual(result['status'],'RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE')
            self.assertEqual(hist.read_bytes(),before)
    def test_production_path_preserves_forecast_and_review_gates(self):
        import assessment_pipeline as pipeline
        from automation_fixtures import fixture
        history,analysis,evidence,opened=fixture();seen=[]
        original=copy.deepcopy(history)
        initial={'evidence':copy.deepcopy(evidence),'coverage_audit':[
            {'category':c,'original_urls':[],'queries':['Synthetic source category query'],
             'outcome':'searched_no_eligible_evidence','limitations':'Synthetic test; no live source coverage asserted.'}
            for c in pipeline.SOURCE_SCAN_GROUPS]}
        initial['coverage_audit'][1].update(original_urls=[BAD],outcome='eligible_reporting_found')
        initial['source_quality']=synthetic_quality_rows(initial)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            def fake(prompt,search):
                seen.append('research' if not seen else 'correction')
                value=initial if len(seen)==1 else decision('withdrawn')
                urls={e['source'] for e in evidence} if len(seen)==1 else {A}
                (folder/f'response-{len(seen)}.json').write_text(json.dumps({
                    'search':True,'result':value,'tool_search_calls':trace(*urls)}))
                return value,urls
            def assess(prompt,search):
                seen.append('assessment');return copy.deepcopy(analysis),set()
            def review(prompt,search):
                seen.append('review')
                draft=json.loads(prompt.split('Input: ')[-1])
                quality=draft['source_quality_audit']['sources']
                rows=[{'url':item['url'],
                       'assessment':'Synthetic test inspected the cited row and recorded its limitations.',
                       'disposition':'supported_as_qualified'} for item in quality]
                return {'approved':True,'issues':[],'source_reviews':rows},set()
            with patch.object(pipeline,'llm',fake),patch.dict(os.environ,{
                    'GITHUB_ACTIONS':'false','IRAN_OFFLINE_REVIEW_DIR':tmp},clear=True):
                result=pipeline.produce(history,researcher=fake,assessor=assess,
                    reviewer=review,metadata_reader=lambda u:{},now=lambda:opened)
            self.assertEqual(seen,['research','correction','assessment','review','review'])
            self.assertEqual(history,original)
            self.assertEqual(result['updates'][:-1],history['updates'])
            scored={f['event_id']:f for f in result['updates'][-1]['forecasts'] if f.get('scored')}
            for forecast in analysis['forecasts']:
                for key,value in forecast.items():
                    self.assertEqual(scored[forecast['event_id']][key],value)



if __name__=='__main__':unittest.main()

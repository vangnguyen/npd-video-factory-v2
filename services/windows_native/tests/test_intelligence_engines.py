from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.research import PublicWebResearchProvider, public_target, validate_findings
from services.windows_native.intelligence_models import ContentIdea, stamp
from services.windows_native.idea_engine import validate_candidates
from services.windows_native.idea_scoring import configuration, score


def receipt():
    return {'requested_url':'https://example.com/test','final_url':'https://example.com/test','status':200,'content_type':'text/html','raw_sha256':'a'*64,'raw_bytes':300,
            'html':'<html><title>Test fixture — never production research</title><meta property="article:published_time" content="2026-09-01T00:00:00Z"><script>Hidden fabricated data</script><p>A housing research fixture reports information about a sample housing market for unit tests only, with no real-world factual claim.</p></html>'}


class IntelligenceEngineTests(unittest.TestCase):
    def test_actual_provider_contract_retains_exact_excerpts_and_no_hidden_script(self):
        with tempfile.TemporaryDirectory() as root:
            provider=PublicWebResearchProvider(Path(root),fetch=lambda url:receipt())
            sources,findings,meta=provider.research('housing research',{'source_urls':['https://example.com/test'],'run_id':'a'*32})
            self.assertEqual(meta['paid_calls'],0)
            self.assertNotIn('Hidden fabricated',sources[0].text)
            self.assertIn(findings[0].claim,sources[0].text)
            self.assertEqual(findings[-1].kind,'UNCERTAIN')
            self.assertTrue((Path(root)/sources[0].id/'source.html').exists())
            findings[0].source_references[0].quote='Invented'
            with self.assertRaisesRegex(WorkflowError,'QUOTE'): validate_findings(sources,findings)

    def test_unknown_publication_is_not_retrieval_freshness(self):
        with tempfile.TemporaryDirectory() as root:
            raw=receipt(); raw['html']=raw['html'].replace('2026-09-01T00:00:00Z','unparseable')
            sources,findings,_=PublicWebResearchProvider(Path(root),fetch=lambda url:raw).research('housing',{'source_urls':['https://example.com/test'],'run_id':'a'*32})
            self.assertIsNone(sources[0].timestamp)
            self.assertFalse(sources[0].publication_date_known)

    def test_failure_never_falls_back_to_fabricated_findings(self):
        with tempfile.TemporaryDirectory() as root:
            def fail(url): raise WorkflowError('RESEARCH_HTTP_ERROR',http_status=403)
            with self.assertRaisesRegex(WorkflowError,'HTTP_ERROR'): PublicWebResearchProvider(Path(root),fetch=fail).research('housing',{'source_urls':['https://example.com/test'],'run_id':'a'*32})
            with self.assertRaisesRegex(WorkflowError,'SOURCE_URLS'): PublicWebResearchProvider(Path(root)).research('housing',{'source_urls':[]})

    def test_private_url_and_mixed_public_private_dns_are_refused(self):
        for url in ['http://example.com','https://user:secret@example.com','https://example.com:8443','https://example.com?api_key=secret']:
            with self.assertRaisesRegex(WorkflowError,'PUBLIC_HTTPS'): public_target(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443)),(2,1,6,'',('8.8.8.8',443))]):
            with self.assertRaisesRegex(WorkflowError,'PUBLIC_HTTPS'): public_target('https://example.com')

    def test_candidates_require_five_distinct_and_known_factual_lineage(self):
        candidate={'title':'Title','hook':'A hook with reasonable length','angle':'angle','target_audience':'audience','format':'Checklist','estimated_duration':30,'cta':'checklist','supporting_research':['f'],'evidence_references':['s'],'key_points':['point'],'rationale':'rationale'}
        findings=[{'id':'f','kind':'SOURCED_FACT','source_references':[{'source_id':'s','quote':'quote'}]}]; sources=[{'id':'s'}]
        candidates=[{**candidate,'title':str(i)} for i in range(5)]
        validate_candidates(candidates,findings,sources)
        for bad in [[candidate]*5,[{**c,'supporting_research':['invented']} for c in candidates],[{**c,'evidence_references':['other']} for c in candidates]]:
            with self.assertRaises(WorkflowError): validate_candidates(bad,findings,sources)

    def test_risk_is_penalty_and_weights_are_configuration(self):
        config=configuration(); profile=config['profiles'][0]
        idea=ContentIdea(run_id='r',opportunity_id='o',generation=1,title='Title',hook='A reasonable long hook here',angle='angle',target_audience=profile['target_audience'],format='Checklist',estimated_duration=30,cta='checklist',related_project=profile['related_project'],supporting_research=['f'],evidence_references=['s'],key_points=['point'],rationale='rationale',provenance={'origin':'test_fixture'}).model_dump(mode='json')
        findings=[{'id':'f','kind':'SOURCED_FACT','relevance':.8}]; sources=[{'id':'s','timestamp':None}]
        scores=score(idea,findings,sources,profile,config)
        self.assertEqual(scores.components['freshness'],0)
        self.assertEqual(scores.scoring_type,'HEURISTIC_SCORING')
        config['scoring']['weights']={k:0 for k in config['scoring']['weights']}; config['scoring']['weights']['risk']=1
        clean=score(idea,findings,sources,profile,config)
        risky=score({**idea,'hook':'cam kết lợi nhuận'},findings,sources,profile,config)
        self.assertLess(risky.final_score,clean.final_score)
        self.assertEqual(clean.final_score,100-clean.components['risk'])
        config['scoring']['weights']['risk']=0
        with self.assertRaisesRegex(WorkflowError,'WEIGHTS'): score(idea,findings,sources,profile,config)

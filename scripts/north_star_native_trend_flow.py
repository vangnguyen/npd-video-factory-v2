"""Owned HTTP trend/idea/distribution/learning fixture hook, no external API calls."""
import json,uuid
from pathlib import Path
from app.trend_providers import TrendProviderRegistry
from services.windows_native.tests.test_trend_radar import FixtureProvider
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.intelligence_store import IntelligenceStore
from services.windows_native.contracts import digest

def key():return uuid.uuid4().hex

def snapshot(root):
    store=IntelligenceStore(root)
    with store.transaction() as con:
        records=[store.get(v[0],con=con) for v in con.execute('SELECT id FROM records ORDER BY id')]
        return {'records':records,'versions':[dict(v) for v in con.execute('SELECT * FROM versions ORDER BY id,version')],
            'decisions':[dict(v) for v in con.execute('SELECT * FROM decisions ORDER BY id')],
            'operations':[dict(v) for v in con.execute('SELECT * FROM operations ORDER BY id')],
            'bridge_events':[dict(v) for v in con.execute('SELECT * FROM native_bridge_source_events ORDER BY event_id')]}

def prepare(server,send,out,write):
    provider=FixtureProvider(server.trends.timestamp());server.trends.providers=TrendProviderRegistry([provider])
    def fetch(_):
        value=receipt();value['html']=value['html'].replace('housing','AI educational video');return value
    server.intelligence.research_provider=PublicWebResearchProvider(server.config.data_root/'research-sources',fetch=fetch)
    server.intelligence.idea_provider=FixtureIdeas()
    collection=send('POST','/api/trends/collections',{'provider_key':provider.provider_key,'fixture_acknowledged':True,'request_key':key()})
    assert server.trends.process();collection=send('GET','/api/trends/records/'+collection['id']);assert collection['record']['payload']['status']=='succeeded' and provider.calls==1
    batch=send('POST','/api/trends/refresh',{'channel_profile_ref':'ai-education-reference@1','request_key':key()})
    radar=send('GET','/api/trends/radar?channel=ai-education-reference%401');assert len(radar['items'])==1
    assessment=radar['items'][0];handoff_body={'assessment_id':assessment['id'],'expected_sha256':assessment['sha256'],'acknowledged':True,'request_key':key()}
    handoff=send('POST','/api/trends/handoff',handoff_body);assert send('POST','/api/trends/handoff',handoff_body)==handoff
    bundle=send('GET','/api/intelligence/runs/'+handoff['payload']['research_run_id']);assert bundle['operations']==[]
    for action in ('research','ideas'):
        send('POST','/api/intelligence/runs/'+bundle['run']['id']+'/'+action,{'version':bundle['run']['version'],'request_key':key()})
        assert server.intelligence.run_one();bundle=send('GET','/api/intelligence/runs/'+bundle['run']['id']);assert bundle['operations'][0]['status']=='SUCCEEDED'
    idea=bundle['ideas'][0];send('POST','/api/intelligence/ideas/'+idea['id']+'/select',{'version':idea['version'],'opportunity_version':bundle['opportunity']['version'],'reviewer':'EXPLICIT FIXTURE; NOT OWNER'})
    bundle=send('GET','/api/intelligence/runs/'+bundle['run']['id']);brief=bundle['brief']
    send('POST','/api/intelligence/briefs/'+brief['id']+'/approve',{'version':brief['version'],'reviewer':'EXPLICIT FIXTURE; NOT OWNER','acknowledged':True})
    bundle=send('GET','/api/intelligence/runs/'+bundle['run']['id']);brief=bundle['brief']
    project_ref=send('POST','/api/intelligence/briefs/'+brief['id']+'/send',{'version':brief['version'],'production_quality':True,'narrated_workflow':True})
    project=send('GET','/api/projects/'+project_ref['project_id']);assert not project['jobs'] and project['approval'] is None and project['document']['niche']=='technology'
    write(out/'trend-evidence.json',collection);write(out/'trend-assessment.json',assessment);write(out/'trend-handoff.json',handoff)
    write(out/'idea-shortlist.json',bundle['ideas']);write(out/'selected-idea.json',next(v for v in bundle['ideas'] if v['status']=='SELECTED'))
    write(out/'research-evidence.json',{'sources':bundle['sources'],'findings':bundle['findings'],'run':bundle['run'],'actual_external_research':False})
    write(out/'approved-brief.json',brief)
    return project

def review_owned_images(server,send,project):
    # Test identity grants exact-byte exceptions for images authored by this
    # rehearsal. This does not establish legal or Owner production acceptance.
    base='/api/projects/'+project['id'];page=send('GET',base+'/rights-overrides')
    for item in page['items']:
        send('POST',base+'/rights-overrides/'+item['asset_id'],{'revision':project['revision'],'asset_sha256':item['asset_sha256'],
            'expected_rights_sha256':item['rights_sha256'],'action':'grant','reason':'Explicit signed fixture exception for program-authored geometric test images; no Owner/legal acceptance',
            'evidence_reference':'upload://'+item['asset_id'],'valid_days':1,'allow_publishing_review':True,'acknowledged':True,'request_key':key()})
        project=send('GET',base)
    return project

def distribution(server,send,out,write,project,job):
    base='/api/projects/'+project['id']
    send('POST','/api/jobs/'+job['id']+'/review',{'revision':job['revision'],'reviewer':'EXPLICIT SIGNED FINAL FIXTURE; NOT OWNER','acknowledged':True,'decision':'approve','note':'Mock distribution acceptance only'})
    publication=send('POST',base+'/publications',{'revision':job['revision'],'final_job_id':job['id'],'platform':'youtube','mode':'dry_run','metadata':{'title':'EXPLICIT TREND TO LEARNING FIXTURE','privacy':'private'},'request_key':key()})
    assert publication['status']=='blocked' and publication['snapshot']['validation']['platform']['status']=='passed'
    assert publication['snapshot']['validation']['attention']==['NATIVE_GENERATED_VOICE_PUBLICATION_PROVENANCE_REQUIRED']
    blocked=send('POST',base+'/publications/'+publication['publication_id']+'/approve',{'expected_fingerprint':publication['request_fingerprint'],'expected_artifact_sha256':publication['snapshot']['final_sha256'],'acknowledged':True},status=409)
    assert server.publications.process() is None
    sync=send('POST',base+'/analytics',{'publication_id':publication['publication_id'],'provider_mode':'official','request_key':key()})
    assert sync['status']=='not_configured' and server.analytics.process() is None
    from services.windows_native.analytics_features import capture
    features=capture(publication,server.store.get_job(job['id']),server.trends.timestamp().isoformat());trend=features['evidence']['trend_radar']
    assert features['trend_cluster_id']==trend['trend_cluster_id'] and features['niche']=='technology'
    learning=send('POST','/api/trends/learning',{'channel_profile_ref':'ai-education-reference@1','provider_mode':'fixture','fixture_acknowledged':True,'request_key':key()})
    assert len(learning['payload']['observations'])==0 and all(v['state']=='insufficient_data' for v in learning['payload']['recommendations'])
    send('POST','/api/trends/refresh',{'channel_profile_ref':'ai-education-reference@1','learning_snapshot_id':learning['id'],'request_key':key()})
    radar=send('GET','/api/trends/radar?channel=ai-education-reference%401');assert radar['items'][0]['payload']['ranking']['history_adjustment_points'] is None
    count=server.bridge.harvest();assert count>0;assert server.bridge.harvest()==0
    write(out/'mock-publication.json',publication);write(out/'blocked-publish-approval.json',blocked);write(out/'analytics-sync-not-configured.json',sync)
    write(out/'frozen-render-features.json',features);write(out/'learning-feedback.json',learning);write(out/'personalized-opportunity.json',radar)
    write(out/'bridge-harvest.json',{'harvested':count,'duplicate_harvested':0,'external_deliveries':0,'agent_hub_online_required':False})
    write(out/'trend-to-learning.json',{'mock_trend_provider':True,'mock_research_and_idea_provider':True,'authored_script_and_images':True,'mock_publication_and_analytics':True,
        'frozen_trend_family_preserved':True,'channel_profile_frozen':True,'latest_distinct_publication_count':0,'learning_state':'insufficient_data',
        'publication_blocked_on_generated_voice_provenance':True,'publication_completed':False,'analytics_snapshot_created':False,'winner_worker_run':False,'full_artifact_c_complete':False,
        'automatic_actions':False,'owner_approval_is_signed_fixture':True,'owner_acceptance':False,'rights_independently_verified':False,'real_external_provider_calls':0,'production_deployed':False})

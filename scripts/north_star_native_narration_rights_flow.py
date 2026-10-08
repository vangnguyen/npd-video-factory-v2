"""Signed legal/voice fixtures and mock distribution; never Owner/provider acceptance."""
import uuid
from services.windows_native.contracts import digest
def key():return uuid.uuid4().hex
def review(send,out,write,project):
    base='/api/projects/'+project['id'];page=send('GET',base+'/narration-rights');assert page['enabled'] and page['active_exception'] is None
    provenance=page['provenance'];assert provenance and not provenance['explicit_fixture'] and provenance['rights_status']=='unknown'
    body={'revision':project['revision'],'narration_job_id':provenance['narration_job_id'],'expected_provenance_sha256':page['provenance_sha256'],'action':'grant',
        'reason':'Explicit signed fixture legal exception bound to measured local voice; no actual Owner, speech or licensing acceptance',
        'evidence_reference':'document://explicit-narration-rights-fixture','valid_days':1,'allow_publishing_review':True,'acknowledged':True,'request_key':key()}
    grant=send('POST',base+'/narration-rights',body);again=send('POST',base+'/narration-rights',body)
    assert again['idempotent_replay'] and again['record']==grant['record']
    current=send('GET',base);assert current['revision']==project['revision']+1 and current['approval'] is None
    assert current['document']['canonical_timeline']==project['document']['canonical_timeline']
    after=send('GET',base+'/narration-rights');assert after['active_exception']==grant['record'] and after['provenance']==provenance
    assert not grant['record']['rights_independently_verified'] and not grant['record']['speech_quality_accepted'] and not grant['record']['publishing_authorized']
    write(out/'narration-rights-before.json',page);write(out/'narration-rights-exception.json',grant);write(out/'narration-rights-after.json',after)
    return current
def distribution(server,send,out,write,project,job):
    base='/api/projects/'+project['id'];send('POST','/api/jobs/'+job['id']+'/review',{'revision':job['revision'],'reviewer':'EXPLICIT SIGNED FINAL FIXTURE; NOT OWNER',
        'acknowledged':True,'decision':'approve','note':'Explicit dry-run only; no real legal or speech acceptance'})
    body={'revision':job['revision'],'final_job_id':job['id'],'platform':'youtube','mode':'dry_run','metadata':{'title':'EXPLICIT NARRATION RIGHTS AND TREND LEARNING FIXTURE','privacy':'private'},'request_key':key()}
    publication=send('POST',base+'/publications',body);assert publication['status']=='awaiting_publish_approval' and not publication['snapshot']['validation']['attention']
    assert publication['snapshot']['validation']['narration_rights']['status']=='explicit_owner_exception' and publication['approval'] is None and server.publications.process() is None
    publish_base=base+'/publications/'+publication['publication_id']
    approved=send('POST',publish_base+'/approve',{'expected_fingerprint':publication['request_fingerprint'],'expected_artifact_sha256':publication['snapshot']['final_sha256'],'acknowledged':True})
    assert approved['status']=='queued' and not approved['approval']['live_publication_authorized']
    completed=send('POST',publish_base+'/dry-run',{'expected_fingerprint':publication['request_fingerprint']})
    assert completed['status']=='dry_run_succeeded' and completed['receipt']['mock'] and completed['receipt']['remote_post_id'] is None and not completed['receipt']['external_action']
    assert send('POST',publish_base+'/dry-run',{'expected_fingerprint':publication['request_fingerprint']})==completed
    assert send('POST',base+'/publications',body)['receipt']==completed['receipt']
    official=send('POST',base+'/analytics',{'publication_id':publication['publication_id'],'provider_mode':'official','request_key':key()})
    assert official['status']=='not_configured' and server.analytics.process() is None
    analytics_body={'publication_id':publication['publication_id'],'provider_mode':'fixture','fixture_acknowledged':True,'fixture_profile':'normal','request_key':key()}
    sync=send('POST',base+'/analytics',analytics_body);processed=send('POST',base+'/analytics/'+sync['sync_id']+'/process',{'expected_fingerprint':sync['request_fingerprint']})
    assert processed['status']=='succeeded';detail=send('GET',base+'/analytics/'+sync['sync_id']);snapshot=detail['snapshot']
    assert snapshot['mock'] and not snapshot['evidence']['real_audience_observation'] and not snapshot['assessment']['automatic_action']
    assert snapshot['features']['niche']=='technology' and snapshot['features']['trend_cluster_id'] and snapshot['features']['evidence']['trend_radar']['assessment_sha256']
    assert send('POST',base+'/analytics',analytics_body)['snapshot_id']==snapshot['snapshot_id']
    learning_body={'channel_profile_ref':'ai-education-reference@1','provider_mode':'fixture','fixture_acknowledged':True,'request_key':key()}
    learning=send('POST','/api/trends/learning',learning_body);assert len(learning['payload']['observations'])==1
    assert all(v['state']=='insufficient_data' for v in learning['payload']['recommendations'])
    assert send('POST','/api/trends/learning',learning_body)==learning
    send('POST','/api/trends/refresh',{'channel_profile_ref':'ai-education-reference@1','learning_snapshot_id':learning['id'],'request_key':key()})
    radar=send('GET','/api/trends/radar?channel=ai-education-reference%401');assert radar['items'][0]['payload']['ranking']['history_adjustment_points'] is None
    count=server.bridge.harvest();assert count>0 and server.bridge.harvest()==0
    write(out/'publication-intent.json',publication);write(out/'publication-approval.json',approved);write(out/'mock-publication.json',completed)
    write(out/'analytics-sync-not-configured.json',official);write(out/'fixture-analytics-sync.json',detail);write(out/'fixture-analytics-snapshot.json',snapshot)
    write(out/'fixture-winner-assessment.json',snapshot['assessment']);write(out/'frozen-render-features.json',snapshot['features']);write(out/'learning-feedback.json',learning)
    write(out/'personalized-opportunity.json',radar);write(out/'bridge-harvest.json',{'harvested':count,'duplicate_harvested':0,'external_deliveries':0,'agent_hub_online_required':False})
    write(out/'trend-to-learning.json',{'mock_trend_provider':True,'mock_research_and_idea_provider':True,'authored_script_and_images':True,'mock_publication_and_analytics':True,
        'frozen_trend_family_preserved':True,'channel_profile_frozen':True,'latest_distinct_publication_count':1,'learning_state':'insufficient_data',
        'publication_completed':True,'publication_mode':'dry_run','analytics_snapshot_created':True,'winner_assessment_created':True,'winner_state':snapshot['assessment']['state'],
        'winner_basis':'explicit_fixture_absolute_reference_only','full_artifact_c_complete':False,'audience_observations_real':False,
        'automatic_actions':False,'owner_approval_is_signed_fixture':True,'owner_acceptance':False,'rights_independently_verified':False,'speech_quality_accepted':False,
        'real_external_provider_calls':0,'production_deployed':False})
    pending=send('POST',base+'/publications',{**body,'request_key':key()});assert pending['status']=='awaiting_publish_approval'
    page=send('GET',base+'/narration-rights');prior=page['active_exception'];assert prior
    revoke=send('POST',base+'/narration-rights',{'revision':page['revision'],'narration_job_id':prior['narration_job_id'],'expected_provenance_sha256':prior['provenance_sha256'],
        'action':'revoke','reason':'Explicit signed fixture revocation invalidates pending publishing review; no legal or Owner acceptance',
        'evidence_reference':'document://explicit-narration-revoke-fixture','valid_days':7,'allow_publishing_review':False,'acknowledged':True,
        'exception_id':prior['exception_id'],'expected_exception_sha256':prior['sha256'],'request_key':key()})
    assert revoke['approval_invalidated'] and send('GET',base+'/narration-rights')['active_exception'] is None
    blocked=send('POST',base+'/publications/'+pending['publication_id']+'/approve',{'expected_fingerprint':pending['request_fingerprint'],
        'expected_artifact_sha256':pending['snapshot']['final_sha256'],'acknowledged':True},status=409)
    assert server.publications.process() is None and send('GET',base+'/analytics/'+sync['sync_id'])['snapshot']==snapshot
    current=send('GET',base);duplicate=send('POST',base+'/duplicate',{'revision':current['revision']})
    assert 'prepared_narration' not in duplicate['document'] and 'narration_rights_exceptions' not in duplicate['document'] and duplicate['approval'] is None
    copy_page=send('GET','/api/projects/'+duplicate['id']+'/narration-rights');assert copy_page['history']==[] and copy_page['provenance'] is None
    write(out/'pending-publication-before-revoke.json',pending);write(out/'narration-rights-revocation.json',revoke);write(out/'blocked-publish-approval-after-revoke.json',blocked)
    write(out/'duplicate-without-narration-authority.json',duplicate)
def snapshot(store,con):
    # Exact retained database rows supplement the existing project/job/file and
    # intelligence snapshots. No mutation, dispatch, account inference or secrets.
    names=['native_narration_rights_requests','native_publications','native_publication_events','native_analytics_syncs','native_analytics_snapshots','native_analytics_events']
    return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in names}

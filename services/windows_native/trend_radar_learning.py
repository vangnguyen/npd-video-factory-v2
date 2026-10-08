"""Native frozen-channel history adapter using shared descriptive learning rules."""
from datetime import datetime
from collections import Counter
from app.learning_models import LearningObservation,aggregate,DIMENSIONS
from .contracts import WorkflowError,digest
from .channel_profiles import select
from .trend_radar_models import LearningRequest

def duration_bucket(value):
    if value is None:return None
    return 'under-15s' if value<15 else '15-30s' if value<30 else '30-60s' if value<60 else '60s-plus'

def create(radar,payload,*,actor):
    if not isinstance(payload,LearningRequest):payload=LearningRequest.model_validate(payload)
    selection=select(payload.channel_profile_ref)
    if payload.provider_mode=='fixture' and not payload.fixture_acknowledged:raise WorkflowError('TREND_FIXTURE_ACKNOWLEDGEMENT_REQUIRED',400)
    scope={'workspace_id':radar.workspace,'channel_profile_ref':payload.channel_profile_ref,'channel_profile_sha256':selection['profile_sha256'],
        'niche':selection['profile']['niche_profile']['niche'],'platform':payload.platform,'mock':payload.provider_mode=='fixture',
        'real_audience_observation':False,'provider_mode':payload.provider_mode,'winner_basis':'explicit_fixture_absolute_reference_only'}
    with radar.store.transaction() as con:
        identifier,request,prior=radar.replay(con,'learning',payload)
        if prior:return prior
    observations=[];excluded=Counter();scan_truncated=False;selected_truncated=False
    if payload.provider_mode=='fixture':
        # Freeze a consistent, bounded source DB read. Later syncs cannot overwrite it.
        with radar.analytics.store.transaction() as source:
            rows=source.execute('WITH ranked AS (SELECT *,ROW_NUMBER() OVER (PARTITION BY publication_id ORDER BY collected_at DESC,snapshot_id DESC) AS rank FROM native_analytics_snapshots WHERE workspace_id=?) SELECT * FROM ranked WHERE rank=1 ORDER BY collected_at DESC,snapshot_id DESC LIMIT 501',(radar.workspace,)).fetchall()
            scan_truncated=len(rows)>500
            basis_hash=None
            for row in rows[:500]:
                snapshot=radar.analytics.read_snapshot(row);features=snapshot['features'];evidence=features['evidence'];assessment=snapshot['assessment']
                if snapshot['platform']!=payload.platform or evidence.get('channel_profile_ref')!=payload.channel_profile_ref or evidence.get('channel_profile_sha256')!=selection['profile_sha256'] or features['niche']!=scope['niche']:
                    excluded['incompatible_frozen_channel_scope']+=1;continue
                publication=radar.analytics.publication(source,row['project_id'],row['publication_id'])
                job=radar.analytics.store.job(source.execute('SELECT * FROM jobs WHERE id=?',(publication['snapshot']['request']['final_job_id'],)).fetchone())
                if publication['status']!='dry_run_succeeded' or digest(job['snapshot'])!=publication['snapshot']['job_snapshot_sha256'] or publication['snapshot_sha256']!=snapshot['evidence']['publication_snapshot_sha256']:
                    raise WorkflowError('TREND_LEARNING_PUBLICATION_BINDING_CHANGED',409)
                if assessment.get('basis')!=scope['winner_basis'] or assessment['state']=='insufficient_data' or assessment.get('score') is None:
                    excluded['insufficient_or_incompatible_assessment']+=1;continue
                factors=assessment['factors']
                if not any(v['factor'] in ('retention','completion') and v.get('score') is not None for v in factors):
                    excluded['retention_required']+=1;continue
                basis=digest(sorted([{'factor':v['factor'],'weight':v['weight'],'available':v.get('score') is not None} for v in factors],key=lambda v:v['factor']))
                if basis_hash and basis!=basis_hash:excluded['incompatible_factor_basis']+=1;continue
                if len(observations)>=payload.policy.maximum_posts:selected_truncated=True;continue
                basis_hash=basis
                data={k:None for k in DIMENSIONS};data.update(trend_family=features['trend_cluster_id'],hook=features['hook_type'],
                    duration=duration_bucket(features['duration_seconds']),visual_strategy=features['visual_strategy'],
                    subtitle_style=features['subtitle_template'],voice_profile=features['voice_profile'])
                observations.append(LearningObservation(snapshot_id=snapshot['snapshot_id'],publication_id=snapshot['publication_id'],
                    assessment_id='native-absolute:'+snapshot['snapshot_id'],render_id=job['id'],timeline_version_id=publication['snapshot']['canonical_timeline_sha256'],
                    feature_context_sha256=evidence['feature_context_sha256'],remote_post_sha256=digest(['explicit-native-fixture-publication',snapshot['publication_id']]),
                    collected_at=datetime.fromisoformat(snapshot['collected_at']),score=assessment['score'],features=data,
                    winner_policy_sha256=digest(scope['winner_basis']),assessment_basis_sha256=basis))
    recommendations=[v.model_dump(mode='json') for v in aggregate(observations,payload.policy)]
    value={'request':request,'request_sha256':digest(request),'scope':scope,'status':'fixture_snapshot' if payload.provider_mode=='fixture' else 'not_configured',
        'observations':[v.model_dump(mode='json') for v in observations],'recommendations':recommendations,
        'candidate_rows_truncated':scan_truncated,'selected_posts_truncated':selected_truncated,'excluded_rows':dict(excluded),
        'recommendation_only':True,'autonomous_execution':False,'real_provider_tested':False,'provider_calls':0,'actor_ref':actor,
        'limitations':['Fixture observations are synthetic; they cannot rank real trend signals.',
            'Frozen channel annotations are not a verified official account or semantic classification.',
            'Latest compatible distinct publications in a bounded scan; incomplete channel history, no account totals.',
            'Shared descriptive median associations; no causal claim or predicted future performance.',
            'Publishing time and production cost remain unavailable; missing features stay null.',
            'Official Native analytics requires its authorized adapter and live publication acceptance.']}
    with radar.store.transaction() as con:
        _,_,prior=radar.replay(con,'learning',payload)
        if prior:return prior
        result=radar.put('learning',value,con,identifier)
        radar.store.decision(con,identifier,'human_requested_channel_learning_snapshot',{'actor_ref':actor,'observations':len(observations),'mock':scope['mock']})
        return result

"""Evidence-labelled Native clustering over shared Video Factory scoring contracts."""
from dataclasses import asdict
from datetime import datetime
import math
from types import SimpleNamespace
from app.models import NicheName
from app.trend_models import TrendClusterRefreshRequest
from app.trend_scoring import ClusterDraft, canonical_topic, normalized_text, jaccard, signal_tokens, lifecycle_for, score_cluster

def signal(value):
    data = value['payload']['signal']
    return SimpleNamespace(**{**data, 'signal_id':value['id'], 'observed_at':datetime.fromisoformat(data['observed_at']), 'hashtags_json':data['hashtags']})

def similarity(a,b,policy):
    left,right=signal(a),signal(b)
    gap=abs((left.observed_at-right.observed_at).total_seconds())/86400
    components={'keyword':jaccard(signal_tokens(left),signal_tokens(right)),
        'hashtag':jaccard(set(left.hashtags_json),set(right.hashtags_json)),
        'entity':jaccard({normalized_text(v) for v in left.entities},{normalized_text(v) for v in right.entities}), 'semantic':None}
    if (left.embedding is not None and right.embedding is not None and left.embedding_model==right.embedding_model and len(left.embedding)==len(right.embedding)):
        components['semantic']=max(0,min(1,sum(x*y for x,y in zip(left.embedding,right.embedding))/math.sqrt(sum(x*x for x in left.embedding)*sum(x*x for x in right.embedding))))
    available={'keyword':bool(signal_tokens(left) and signal_tokens(right)), 'hashtag':bool(left.hashtags_json and right.hashtags_json),
        'entity':bool(left.entities and right.entities),'semantic':components['semantic'] is not None}
    denominator=sum(getattr(policy,k+'_weight') for k in components if available[k])
    base=sum((components[k] or 0)*getattr(policy,k+'_weight') for k in components if available[k])/denominator if denominator else 0
    same=bool(normalized_text(left.topic) and normalized_text(left.topic)==normalized_text(right.topic))
    if same:base=1
    temporal=max(0,1-gap/policy.maximum_gap_days)
    value=0 if gap>policy.maximum_gap_days else min(1,base+(policy.temporal_bonus*temporal+policy.cross_platform_bonus*(left.source!=right.source) if base>=.15 else 0))
    return {'score':round(value,6),'components':components,'available':available,'same_topic':same,
        'gap_days':round(gap,6),'temporal_correlation_estimate':temporal,'cross_platform':left.source!=right.source,
        'semantic_model':left.embedding_model if available['semantic'] else None,'estimated':True}

def clusters(values,policy,as_of):
    groups=[];edges={}
    for value in sorted(values,key=lambda v:(v['payload']['signal']['observed_at'],v['id'])):
        best=None;best_value=0
        for index,group in enumerate(groups):
            comparisons=[(other,similarity(value,other,policy)) for other in group]
            other,evidence=max(comparisons,key=lambda pair:pair[1]['score'])
            if evidence['score']>=policy.similarity_threshold and evidence['score']>best_value:best=index;best_value=evidence['score'];edges[value['id']]={'matched_signal_id':other['id'],**evidence}
        if best is None:groups.append([value]);edges.pop(value['id'],None)
        else:groups[best].append(value)
    results=[]
    for group in groups:
        rows=[signal(v) for v in group];topic,key=canonical_topic(rows)
        draft=ClusterDraft(key,topic,f'{len(rows)} source observations; lifecycle and opportunity scores are estimates.',
            lifecycle_for(rows,as_of),min(v.observed_at for v in rows),max(v.observed_at for v in rows),[v.signal_id for v in rows],
            {v.signal_id:edges.get(v.signal_id,{}).get('score',1) for v in rows},sorted({v.source for v in rows}),
            sorted({v.keyword for v in rows if v.keyword}),sorted({tag for v in rows for tag in v.hashtags_json}))
        results.append((draft,group,{k:v for k,v in edges.items() if k in draft.signal_ids}))
    return results

def estimate(draft,values,request,selection):
    niche=selection['profile']['niche_profile']['niche']
    context=TrendClusterRefreshRequest(channel='short-video:'+selection['profile']['profile_ref'],niche=niche if niche in {v.value for v in NicheName} else 'custom',
        business_objective=request.business_objective,weights=request.weights)
    result=asdict(score_cluster(draft,[signal(v) for v in values],context))
    measured={name:sum(v['payload']['signal'].get(name) is not None for v in values) for name in
        ['views','likes','comments','shares','saves','engagement','creator_count','content_count','velocity','acceleration']}
    return {**result,'algorithm_version':'trend-opportunity-v1','estimated':True,'recommendation_only':True,'automatic_action':False,
        'measured_field_coverage':measured,'sample_count':len(values),
        'basis':{'velocity':'available_provider_metric_or_zero_score','acceleration':'available_provider_metric_or_zero_score',
            'cross_platform_spread':'observed_source_types','engagement_quality':'available_metrics_or_neutral_50_score',
            'saturation':'provider_counts_or_default_35_estimate','competition':'provider_creator_count_or_zero_score',
            'channel_fit':'configured_channel_and_observed_format','format_fit':'observed_format_ratio',
            'monetization_fit':'configured_niche_objective_estimate','rights_risk':'fixed_6_planning_placeholder_no_rights_approval',
            'policy_risk':'fixed_8_planning_placeholder_no_policy_approval'},
        'lifecycle_basis':'shared_velocity_acceleration_spread_saturation_age_heuristic',
        'lifecycle_history_measured':False,'real_performance_prediction':False,'missing_metrics_preserved':True}

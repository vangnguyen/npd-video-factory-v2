"""Frozen trend/channel references inside existing research and render lineage."""
from .contracts import WorkflowError,digest
from .channel_profiles import resolve
from .trend_radar_models import RadarRecord,SignalEvidence

def validate(value):
    try:
        if value['schema_version']!='native-trend-research-context-v1' or value['sha256']!=digest({k:v for k,v in value.items() if k!='sha256'}):raise ValueError()
        assessment=RadarRecord.model_validate(value['assessment']).model_dump(mode='json');p=assessment['payload']
        if assessment['record_type']!='assessment' or assessment['workspace_id']!=value['workspace_id'] or digest(assessment)!=value['assessment_sha256']:raise ValueError()
        if value['channel_selection']!=p['channel_selection'] or value['reference_only'] is not True or value['creator_media_download_allowed'] is not False or value['automatic_production'] is not False:raise ValueError()
        resolve({'channel_profile':value['channel_selection'],'niche':value['channel_selection']['profile']['niche_profile']['niche']})
        if p.get('learning_feedback') is not None:
            from .qualified_learning_feedback import validate_context
            feedback=validate_context(p['learning_feedback']);scope=feedback['scope'];selection=value['channel_selection']
            if (feedback['workspace_id']!=value['workspace_id'] or scope['channel_profile_ref']!=selection['profile']['profile_ref']
                or scope['channel_profile_sha256']!=selection['profile_sha256'] or scope['platform']!=p['platform']
                or feedback['mock'] and p['mock'] is not True
                or p['ranking']['learning_snapshot_id']!=feedback['projection_id']):raise ValueError()
        if {v['id'] for v in value['signals']}!=set(p['signal_ids']):raise ValueError()
        for raw in value['signals']:
            record=RadarRecord.model_validate(raw).model_dump(mode='json');signal=SignalEvidence.model_validate(record['payload']['signal']).model_dump(mode='json')
            if record['record_type']!='signal' or record['workspace_id']!=value['workspace_id'] or digest(signal)!=p['signal_hashes'][record['id']] or digest(signal)!=record['payload']['raw_signal_hash']:raise ValueError()
        return {'trend_cluster_id':p['cluster_id'],'assessment_id':assessment['id'],'assessment_sha256':value['assessment_sha256'],
            'trend_context_sha256':value['sha256'],'channel_profile_ref':p['channel_selection']['profile']['profile_ref'],
            'channel_profile_sha256':p['channel_selection']['profile_sha256'],'niche':p['channel_selection']['profile']['niche_profile']['niche'],
            'mock':p['mock'],'estimated':True,'recommendation_only':True}
    except (ValueError,TypeError,KeyError,WorkflowError):raise WorkflowError('TREND_RESEARCH_LINEAGE_INVALID',409) from None

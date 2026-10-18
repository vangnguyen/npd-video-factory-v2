"""Per-line input dependencies only. A plan is never measured audio or an execution receipt."""
import re,unicodedata
from pydantic import ValidationError
from .contracts import WorkflowError,digest,normalize
from .drama_casting import DramaConfiguration
from .north_star_quality import canonical_names,POLICY

SCHEMA='native-dialogue-delivery-plan.v1'

def build(configuration,library,*,provider_signatures=None):
    library.scope()
    try:config=DramaConfiguration.model_validate(configuration).model_dump(mode='json')
    except (ValidationError,TypeError):raise WorkflowError('DRAMA_REQUEST_INVALID',400) from None
    signatures={} if provider_signatures is None else provider_signatures
    if (not isinstance(signatures,dict) or any(not isinstance(k,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',k)
        or not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in signatures.items())):raise WorkflowError('DRAMA_PROVIDER_SIGNATURE_INVALID',400)
    characters={c['character_id']:c for c in config['characters']};casting={c['character_id']:c for c in config['casting']}
    voices={};lines=[];attention=[];excluded=[]
    pronunciation=digest({'id':POLICY['id'],'version':POLICY['version'],'proper_names':POLICY['proper_names']})
    for line in config['lines']:
        character=characters[line['character_id']]
        if not line['enabled'] or character['role']=='narrator' and not config['narrator_enabled']:
            excluded.append({'line_id':line['line_id'],'reason':'line_disabled' if not line['enabled'] else 'narrator_disabled'});continue
        cast=casting.get(line['character_id'])
        if cast is None:
            attention.append({'line_id':line['line_id'],'reason':'voice_selection_required'});continue
        reference=(cast['voice_id'],cast['voice_version'])
        if reference not in voices:voices[reference]=library.get(cast['voice_id'],version=cast['voice_version'])
        voice=voices[reference];definition=voice['definition']
        if voice['definition_sha256']!=cast['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
        reasons=[]
        if not voice['current']:reasons.append('voice_version_changed')
        if definition['rights_status'] not in ('owner_declared','source_licensed'):reasons.append('voice_rights_confirmation_required')
        if definition['source_type']=='licensed_reference' and not definition['cloning_consent']:reasons.append('reference_consent_required')
        profile=signatures.get(definition['provider'])
        if profile is None:reasons.append('provider_not_configured')
        if line['shot_id'] is None:reasons.append('shot_binding_required')
        reviewed_text=unicodedata.normalize('NFC',normalize(line['text']));tts_text=canonical_names(reviewed_text)
        if tts_text!=reviewed_text:reasons.append('proper_name_review_required')
        acoustic={k:definition[k] for k in ('provider','model','provider_voice_id','locale','source_type','reference_asset_id','reference_sha256')}
        synthesis=digest({'schema_version':SCHEMA,'workspace_id':library.workspace,'provider_configuration_sha256':profile,
            'voice':acoustic,'text':tts_text,'speed':line['speed'],'style':line['style'],'pronunciation_policy_sha256':pronunciation})
        entry={**line,'reviewed_text':reviewed_text,'tts_text':tts_text,'character_name':character['name'],'speaker_role':character['role'],
            'voice_id':voice['voice_id'],'voice_version':voice['version'],'voice_sha256':voice['definition_sha256'],
            'provider_configuration_sha256':profile,'synthesis_input_sha256':synthesis,'needs_attention':reasons,
            'measured_duration_seconds':None,'audio_asset_reference':None,'provider_job_id':None,'actual_cost':None}
        lines.append(entry);attention.extend({'line_id':line['line_id'],'reason':reason} for reason in reasons)
    if not lines:attention.append({'line_id':None,'reason':'no_active_cast_dialogue'})
    mix=digest([{'line_id':v['line_id'],'synthesis_input_sha256':v['synthesis_input_sha256'],'pause_after_seconds':v['pause_after_seconds']} for v in lines])
    captions=digest([{'line_id':v['line_id'],'speaker_id':v['character_id'],'speaker_name':v['character_name'],'shot_id':v['shot_id'],
        'text':v['reviewed_text'],'synthesis_input_sha256':v['synthesis_input_sha256'],'pause_after_seconds':v['pause_after_seconds']} for v in lines])
    body={'schema_version':SCHEMA,'workspace_id':library.workspace,'configuration_sha256':digest(config),'narrator_enabled':config['narrator_enabled'],
        'lines':lines,'excluded_lines':excluded,'needs_attention':attention,'audio_mix_input_sha256':mix,'subtitle_input_sha256':captions,
        'execution_ready':False,'execution_implemented_by_plan':False,'timing_basis':'pending_measured_per_line_audio','external_provider_calls':0}
    return {**body,'sha256':digest(body)}

def _verified(plan):
    try:
        if (not isinstance(plan,dict) or plan.get('schema_version')!=SCHEMA or plan.get('sha256')!=digest({k:v for k,v in plan.items() if k!='sha256'})
            or not isinstance(plan.get('lines'),list) or not isinstance(plan.get('workspace_id'),str) or plan.get('execution_ready') is not False):raise ValueError()
    except (ValueError,TypeError):raise WorkflowError('DRAMA_DELIVERY_PLAN_CHANGED') from None
    return plan

def affected(previous,current):
    current=_verified(current)
    if previous is not None:
        previous=_verified(previous)
        if previous['workspace_id']!=current['workspace_id']:raise WorkflowError('DRAMA_WORKSPACE_INVALID')
    before={v['line_id']:v for v in previous['lines']} if previous else {};after={v['line_id']:v for v in current['lines']}
    required=[key for key,v in after.items() if key not in before or v['synthesis_input_sha256']!=before[key]['synthesis_input_sha256']]
    reuse=[key for key in after if key not in required]
    return {'scope':'planned_dependencies_only','requires_synthesis_line_ids':required,'eligible_for_verified_cache_reuse_line_ids':reuse,
        'removed_line_ids':[key for key in before if key not in after],
        'audio_mix_invalidated':previous is None or previous['audio_mix_input_sha256']!=current['audio_mix_input_sha256'],
        'subtitle_input_invalidated':previous is None or previous['subtitle_input_sha256']!=current['subtitle_input_sha256'],
        'preview_invalidated':previous is None or previous['sha256']!=current['sha256'],'final_export_invalidated':previous is None or previous['sha256']!=current['sha256'],
        'visual_asset_regeneration_ids':[],'cache_bytes_verified':False,'cache_lookup_required_before_provider_dispatch':True,'provider_calls':0,'human_approval_granted':False}

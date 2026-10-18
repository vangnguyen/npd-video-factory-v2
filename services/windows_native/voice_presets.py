"""Install metadata from this runtime's hash-locked presets, never remote name lists."""
from .backup import guard
from .contracts import WorkflowError,digest,file_sha

def licensed_inventory(config):
    from .dialogue_vieneu import presets,PROVIDER
    locked,values=presets(config);rights=locked['rights']
    card=guard(config.runtime_root/'models/vieneu-v3-turbo/README.md',exists=True)
    license_file=guard(config.sdk_source/'LICENSE',exists=True)
    if file_sha(card)!=rights['model_card_sha256'] or file_sha(license_file)!=rights['sdk_license_sha256']:
        raise WorkflowError('VOICE_PRESET_LICENSE_EVIDENCE_CHANGED')
    evidence={'schema_version':'native-installed-preset-license.v1','model_card_sha256':rights['model_card_sha256'],
        'sdk_license_sha256':rights['sdk_license_sha256'],'preset_asset_sha256':rights['preset_asset_sha256'],
        'sdk_commit':locked['sdk_commit'],'model_revision':locked['model_revision']}
    source=f"https://huggingface.co/{rights['model_repository']}/blob/{locked['model_revision']}/README.md"
    permission='Pinned model card: license includes preset embeddings/reference codes; commercial generated audio permitted. Evidence '+digest(evidence)
    voices=[]
    for name,preset in values.items():
        definition={'display_name':name,'provider':PROVIDER,'model':locked['model'],'provider_voice_id':name,'locale':'vi-VN',
            'source_type':'provider_preset','rights_status':'source_licensed','license':rights['license_identifier'],
            'source_reference':source,'permission_reference':permission,'reference_asset_id':None,'reference_sha256':None,'cloning_consent':False}
        voices.append({'definition':definition,'metadata':{k:preset.get(k) for k in ('description','gender','region','style','featured','aliases')},
            'preset_payload_sha256':digest({k:preset[k] for k in ('speaker_emb','codes')}),'evidence':evidence})
    return sorted(voices,key=lambda v:(v['metadata']['featured'] or 999,v['definition']['display_name']))

def verify_definition(config,definition):
    expected=next((v for v in licensed_inventory(config) if v['definition']['provider_voice_id']==definition.get('provider_voice_id')),None)
    if expected is None or expected['definition']!=definition:raise WorkflowError('VOICE_PRESET_LICENSE_BINDING_CHANGED')
    return expected

def register_installed(library,config,*,actor_ref,authorization_check=lambda:None):
    """Explicit internal management operation; append immutable versions, do not recast films."""
    items=licensed_inventory(config);result=[]
    for item in items:
        authorization_check();definition=item['definition'];key='installed-preset:'+digest({'workspace':library.workspace,'definition':definition})
        result.append(library._write(None,{'request_key':key,'definition':definition},actor_ref,authorization_check,_source_evidence=item['evidence']))
    return {'registered':len(result),'items':result,'provider_calls':0,'human_voice_uat_complete':False,'existing_castings_changed':False}

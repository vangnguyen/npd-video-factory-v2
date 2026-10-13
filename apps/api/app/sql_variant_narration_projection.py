"""Audio-only semantic identity. Visual IDs/canvas cannot imply audio approval."""
import copy
import hashlib
import re
from .sql_variant_models import digest, canonical
from .sql_variant_repository import SqlVariantError
from .sql_tts_artifact_reuse import validate_evidence, prepared_audio_byte_limit, MAX_BYTES
from .production_logic import derive_subtitle_cues
from .production_models import VoiceConfig
from .timeline_models import TimelineSnapshot


def fail(code='SQL_VARIANT_NARRATION_SEMANTICS_CHANGED'):
    raise SqlVariantError(code)


def narration_projection(snapshot, cues, voice):
    snapshot=TimelineSnapshot.model_validate(snapshot)
    voice=VoiceConfig.model_validate(voice)
    if not voice.enabled or not cues:fail('SQL_VARIANT_NARRATION_SOURCE_REQUIRED')
    prepared_audio_byte_limit(snapshot.duration_seconds)
    plan=copy.deepcopy(snapshot.metadata.get('narration_plan'))
    if plan is not None:
        if not isinstance(plan,dict) or not isinstance(plan.get('units'),list):fail()
        for unit in plan['units']:
            text=unit.get('text')
            if not isinstance(text,str) or not 0<len(text)<=4096 \
                    or unit.get('text_sha256')!=hashlib.sha256(text.encode()).hexdigest():fail()
            unit.pop('unit_id',None)
        for scene in plan.get('scenes',[]):scene.pop('scene_id',None)
    values=[cue.model_dump(mode='json',exclude={'cue_id'}) for cue in cues]
    result={'schema_version':'sql-variant-narration-semantics.v1','duration_seconds':snapshot.duration_seconds,
        'sample_rate':48000,'voice':voice.model_dump(mode='json'),'cues':values,'plan':plan}
    if len(canonical(result))>8*1024*1024:fail('SQL_VARIANT_NARRATION_LIMIT')
    return result


def child_cues(snapshot):
    return derive_subtitle_cues(TimelineSnapshot.model_validate(snapshot))


def source_units(manifest, projection, profile_pins, normalization_pins):
    narration=copy.deepcopy(manifest.get('narration'))
    if not isinstance(narration,dict) or not isinstance(narration.get('timing'),list):fail()
    units=narration['timing']
    if not 0<len(units)<=300 or len(units)!=len(profile_pins) or len(units)!=len(normalization_pins):fail()
    plan=projection['plan']
    texts=[u['text'] for u in plan['units']] if plan else [c['text'] for c in projection['cues']]
    if len(texts)!=len(units):fail()
    for i,(unit,text) in enumerate(zip(units,texts,strict=True)):
        evidence=validate_evidence(unit.get('provider_evidence'))
        if (evidence.text_sha256!=hashlib.sha256(text.encode()).hexdigest()
                or evidence.profile_sha256!=profile_pins[i]
                or re.fullmatch(r'[a-f0-9]{64}',normalization_pins[i]) is None
                or evidence.usage.get('normalization_record_sha256')!=normalization_pins[i]
                or not re.fullmatch(r'(?:unit|voice)-[0-9]{3}-raw\.wav',unit.get('provider_audio_file',''))
                or not unit.get('provider_audio_asset_id') or not unit.get('provider_audio_asset_proof')
                or evidence.profile.locale!='vi-VN'):
            fail('SQL_VARIANT_NARRATION_PROVIDER_PROOF_CHANGED')
        # Provider synthesis parameters and subsequent PCM speed are distinct
        # controls. Full profile pins and exact source/child voice-config hashes
        # bind both; never invent absent speed fields on VieNeu/Realtime profiles.
        if projection['voice']['voice'] not in {'vi',evidence.profile.voice_id}:fail('SQL_VARIANT_NARRATION_VOICE_CHANGED')
        if not 0<unit.get('source_audio_duration_seconds',0)==evidence.decoded_duration_seconds:fail()
    return narration,units


def source_asset_limit(kind,duration):
    return MAX_BYTES if kind=='tts-provider-source' else prepared_audio_byte_limit(duration)

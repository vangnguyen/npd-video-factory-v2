"""Offline CPU inference feeds the existing immutable Native ASR/Auto Edit model."""
import asyncio,copy
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from app.local_asr_profile import validate_profile,digest as profile_digest
from app.local_transcription_provider import LocalCpuTranscriptionProvider
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import ProviderNotConfigured
from .contracts import WorkflowError,digest,file_sha
from .hardening import Artifacts,durable_json

def analyze_local(config,job,out,stage,profile,*,provider_factory=LocalCpuTranscriptionProvider):
    from .asr import pending_assets,visual_metadata,extract_audio,source_mapped_transcript
    from .media import media_path
    from .costs import CostLedger
    from .store import Store
    validate_profile(profile)
    out=Path(out);document=job['snapshot']['document'];records=[]
    for asset in pending_assets(document):
        source=media_path(config,asset['id'])
        if asset.get('rights_confirmed') is not True or not source.is_file() or file_sha(source)!=asset['sha256']:
            raise WorkflowError('ASR_SOURCE_MEDIA_CHANGED_OR_RIGHTS_MISSING')
        directory=out/'analysis'/asset['id'];directory.mkdir(parents=True,exist_ok=True)
        artifacts=Artifacts(directory,job);checkpoint=artifacts.load('analysis')
        if checkpoint:
            records.append(checkpoint['result']);continue
        stage('asr_local_media_analysis')
        record={'asset_id':asset['id'],'source_sha256':asset['sha256'],'media':visual_metadata(config,asset),
            'transcript':None,'provider_calls':0,'local_model_inferences':0}
        paths=[]
        if asset['kind'] in {'video','audio'} and asset.get('has_audio'):
            stage('asr_extract_audio');audio,metadata=extract_audio(config,asset,directory,artifacts)
            paths=[audio,directory/'checkpoint-audio.json']
            if (directory/'speech-clock.log').is_file():paths.append(directory/'speech-clock.log')
            if metadata.get('explicit_gap_padding') is not None:paths.append(directory/'decoded-speech.wav')
            cached=artifacts.load('local-transcript')
            if cached:
                result=cached['result']
                from app.local_transcription_provider import normalize
                transcript=normalize(result['raw'],profile,metadata['sha256'],metadata['duration_seconds'])
                value=asdict(transcript);value.pop('actual_cost_vnd',None)
                if digest(value)!=digest(result['transcript']):raise WorkflowError('LOCAL_ASR_RECEIPT_CHANGED')
            else:
                provider=(provider_factory(config.local_asr_manifest,profile['language'],model_key=profile['model_key'])
                    if profile.get('model_key') else provider_factory(config.local_asr_manifest,profile['language']))
                if provider.profile!=profile:raise WorkflowError('LOCAL_ASR_PROFILE_CHANGED')
                ledger=CostLedger(Store(config.data_root))
                operation=ledger.begin(project_id=job['project_id'],job_id=job['id'],provider='faster-whisper',
                    model=profile['model'].split('/')[-1]+':'+profile['model_revision'][:12],operation='local-asr-'+asset['id'],request_sha256=profile_digest({
                        'job':job['id'],'source':asset['sha256'],'pcm':metadata['sha256'],'profile':profile}),
                    estimated_cost=0,paid=False,external_call=False)
                stage('asr_local_cpu_inference')
                try:
                    transcript=asyncio.run(provider.transcribe(audio,metadata=MediaMetadata(media_kind='audio',
                        detected_content_type='audio/wav',duration_seconds=metadata['duration_seconds'],
                        audio_channels=1,audio_sample_rate=16000),checksum_sha256=metadata['sha256']))
                    value=asdict(transcript);value.pop('actual_cost_vnd',None)
                    raw=copy.deepcopy(provider.raw_result)
                    if digest(raw)!=value['provenance']['raw_response_sha256']:raise ValueError('LOCAL_ASR_RECEIPT_CHANGED')
                    durable_json(directory/'local-transcript.json',{'raw':raw,'transcript':value})
                    artifacts.commit('local-transcript',[directory/'local-transcript.json'],{'raw':raw,'transcript':value})
                    ledger.settle(operation,status='response_received',response_sha256=digest(raw))
                except Exception as exc:
                    if ledger.pending(operation):ledger.settle(operation,status='rejected',error_code='LOCAL_ASR_EXECUTION_FAILED')
                    code='LOCAL_ASR_NOT_CONFIGURED' if isinstance(exc,ProviderNotConfigured) else 'LOCAL_ASR_EXECUTION_FAILED'
                    raise WorkflowError(code,503 if isinstance(exc,ProviderNotConfigured) else 409) from None
            paths.extend([directory/'local-transcript.json',directory/'checkpoint-local-transcript.json'])
            original=copy.deepcopy(value)
            try:value,pcm=source_mapped_transcript(value,metadata,float(record['media']['duration_seconds']))
            except (ValueError,WorkflowError):raise WorkflowError('LOCAL_ASR_SOURCE_CLOCK_REVIEW_REQUIRED') from None
            if pcm is not None:record['provider_pcm_transcript']=original
            record.update(transcript=value,audio=metadata,local_model_inferences=1)
            if asset['kind']=='audio':
                from .auto_edit_analysis import normalize_transcript,asset_reference
                identifier='ana_'+digest(['native-local-audio-transcript-v1',asset['id'],asset['sha256'],
                    value['provenance']['raw_response_sha256']])[:24]
                normalized=normalize_transcript(value,analysis_id=identifier,asset_id=asset_reference(asset),
                    duration=record['media']['duration_seconds'],created_at=datetime.now(timezone.utc))
                record['normalized_transcript']=normalized.model_dump(mode='json')
        record['analysis_sha256']=digest(record)
        durable_json(directory/'analysis.json',record)
        artifacts.commit('analysis',paths+[directory/'analysis.json'],record);records.append(record)
    result={'media_analysis':records,'source':'measured_media_and_provider_transcript','provider_calls':0,
        'local_model_inferences':sum(r.get('local_model_inferences',0) for r in records),
        'human_review_required':True,'automatic_paid_replay':False}
    durable_json(out/'analysis-result.json',result)
    paths=[p for p in (out/'analysis').rglob('*') if p.is_file() and p.suffix in {'.json','.wav'} and '.part.' not in p.name]
    Artifacts(out,job).commit('asr',paths+[out/'analysis-result.json'],result)
    return result

"""Byte-verified same-project TTS reuse. Original evidence is never retargeted.

Only explicitly fingerprinted adapters opt in. Pending/unknown/corrupt entries
never become cache misses and never cause automatic provider replay.
"""
import asyncio
import copy
from datetime import timedelta, timezone
import hashlib
import math
import re
import uuid
import wave
from pathlib import Path
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from .content_service import canonical_bytes
from .db import utc_now
from .local_asr_runtime import plain
from .object_storage import sha256_file, filesystem_path, validate_object_key
from .platform_models import AssetRegister
from .providers import VoiceResult
from .tts_evidence import TTSArtifactEvidence
from .sql_tts_artifact_reuse_db import TTSArtifactReuseORM
from .production_db import ProductionRenderJobORM
from .frozen_storage_read import frozen_asset_read, completed_read

SCHEMA = 'sql-raw-tts-reuse.v1'
MAX_BYTES = 20_000_000
PREPARED_AUDIO_MAX_DURATION_SECONDS = 600  # Existing timeline-render manifest contract.
PREPARED_AUDIO_HEADER_MAX_BYTES = 64 * 1024
PREPARED_AUDIO_SAMPLE_RATE = 48000


class TTSReuseRejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def asset_proof(asset):
    """Public storage custody frozen into the reviewed manifest."""
    return {'asset_id':asset.asset_id,'workspace_id':asset.workspace_id,'project_id':asset.project_id,
        'asset_class':asset.asset_class,'project_version_id':asset.project_version_id,
        'object_key':asset.object_key,'storage_provider':asset.storage_provider,'kind':asset.kind,
        'content_type':asset.content_type,'size_bytes':asset.size_bytes,'checksum_sha256':asset.checksum_sha256,
        'asset_version':asset.version,'provenance_sha256':digest(asset.provenance)}


def validate_evidence(value):
    try:
        return TTSArtifactEvidence.model_validate(value)
    except (ValueError,TypeError):
        raise TTSReuseRejected('TTS_REUSE_PROVIDER_EVIDENCE_INVALID') from None


def pcm(path, evidence):
    try:
        path = plain(path)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise TTSReuseRejected('TTS_REUSE_PCM_LIMIT')
        if sha256_file(path) != evidence.audio_sha256:
            raise TTSReuseRejected('TTS_REUSE_PCM_CHANGED')
        with wave.open(str(filesystem_path(path)), 'rb') as audio:
            count = audio.getnframes()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 48000) \
                    or count <= 0 or abs(count/48000-evidence.decoded_duration_seconds) > 1/48000 \
                    or len(audio.readframes(count)) != count*2:
                raise TTSReuseRejected('TTS_REUSE_PCM_INVALID')
        if sha256_file(path)!=evidence.audio_sha256:
            raise TTSReuseRejected('TTS_REUSE_PCM_CHANGED')
    except TTSReuseRejected:
        raise
    except (OSError,ValueError,wave.Error,EOFError):
        raise TTSReuseRejected('TTS_REUSE_PCM_UNAVAILABLE') from None


def deadline(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


class TTSArtifactReuseRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def claim(self, binding, render_id, *, require_ready=False):
        fingerprint = digest(binding);identity = 'ttr_'+fingerprint
        for _ in range(2):
            try:
                async with self.session_factory() as session, session.begin():
                    await session.execute(update(TTSArtifactReuseORM).where(TTSArtifactReuseORM.reuse_id==identity)
                        .values(updated_at=TTSArtifactReuseORM.updated_at))
                    row = await session.get(TTSArtifactReuseORM,identity,with_for_update=True,populate_existing=True)
                    if row is None:
                        if require_ready:
                            return {'reuse_id':identity,'state':'missing'}
                        claim = uuid.uuid4().hex;now = utc_now()
                        session.add(TTSArtifactReuseORM(reuse_id=identity,workspace_id=binding['workspace_id'],
                            project_id=binding['project_id'],content_version_id=binding['content_version_id'],
                            fingerprint=fingerprint,binding_json=binding,state='pending',claim_id=claim,
                            lease_until=now+timedelta(seconds=720),source_render_id=render_id))
                        await session.flush()
                        return {'reuse_id':identity,'state':'claimed','claim_id':claim}
                    if row.binding_json != binding or row.fingerprint != fingerprint \
                            or (row.workspace_id,row.project_id,row.content_version_id) != (
                                binding['workspace_id'],binding['project_id'],binding['content_version_id']):
                        raise TTSReuseRejected('TTS_REUSE_BINDING_CHANGED')
                    if row.state == 'ready':
                        if row.result_json is None or digest(row.result_json)!=row.result_sha256:
                            raise TTSReuseRejected('TTS_REUSE_EVIDENCE_CHANGED')
                        return {'reuse_id':identity,'state':'ready','result':copy.deepcopy(row.result_json),
                            'result_sha256':row.result_sha256,'source_render_id':row.source_render_id}
                    source=await session.get(ProductionRenderJobORM,row.source_render_id)
                    if row.state == 'pending' and (source is None or source.status!='running'
                            or source.cancellation_requested or deadline(row.lease_until) is None
                            or deadline(row.lease_until)<=utc_now()):
                        row.state='unknown';row.error_code='TTS_REUSE_EXPIRED_UNKNOWN';row.updated_at=utc_now()
                    return {'reuse_id':identity,'state':row.state}
            except IntegrityError:
                continue
        raise TTSReuseRejected('TTS_REUSE_CLAIM_CONFLICT')

    async def complete(self, identity, claim, result):
        async with self.session_factory() as session, session.begin():
            row = await session.get(TTSArtifactReuseORM,identity,with_for_update=True)
            if row is None or row.state!='pending' or row.claim_id!=claim \
                    or deadline(row.lease_until) is None or deadline(row.lease_until)<=utc_now():
                raise TTSReuseRejected('TTS_REUSE_CLAIM_EXPIRED_OR_CHANGED')
            source=await session.get(ProductionRenderJobORM,row.source_render_id,with_for_update=True)
            if source is None or source.status!='running' or source.cancellation_requested or source.invalidated_at is not None:
                raise TTSReuseRejected('TTS_REUSE_SOURCE_RENDER_NOT_CURRENT')
            changed=await session.execute(update(TTSArtifactReuseORM).where(TTSArtifactReuseORM.reuse_id==identity,
                TTSArtifactReuseORM.state=='pending',TTSArtifactReuseORM.claim_id==claim).values(state='ready',
                result_json=result,result_sha256=digest(result),claim_id=None,lease_until=None,updated_at=utc_now()))
            if changed.rowcount!=1:
                raise TTSReuseRejected('TTS_REUSE_CLAIM_EXPIRED_OR_CHANGED')

    async def unknown(self, identity, claim):
        async with self.session_factory() as session, session.begin():
            await session.execute(update(TTSArtifactReuseORM).where(TTSArtifactReuseORM.reuse_id==identity,
                TTSArtifactReuseORM.state=='pending',TTSArtifactReuseORM.claim_id==claim).values(
                state='unknown',error_code='TTS_REUSE_UNIT_OUTCOME_UNKNOWN',updated_at=utc_now()))


class ReusingTTSProvider:
    def __init__(self, provider, *, repository, platform, assets, storage, render, content, voice_config, guard, target_binding, review_pins=None):
        self.provider,self.repository,self.platform,self.assets,self.storage = provider,repository,platform,assets,storage
        self.render,self.content,self.voice_config,self.guard = render,content,voice_config,guard
        self.model,self.voice = provider.model,provider.voice
        self._adapter = copy.deepcopy(provider.artifact_reuse_binding)
        self._target = copy.deepcopy(target_binding)
        self._pins=copy.deepcopy(review_pins);self._unit=0
        self._scope = {'schema_version':SCHEMA,'workspace_id':render.workspace_id,'project_id':render.project_id,
            'content_version_id':content.project_version_id,'content_sha256':digest(content.snapshot),
            'content_provenance_sha256':digest(content.provenance),'adapter':self._adapter,
            'voice_config_sha256':digest(voice_config.model_dump(mode='json'))}

    async def current(self):
        await self.guard()
        latest=await self.platform.get_version(self.content.project_version_id)
        if latest is None or latest.project_id!=self.render.project_id or latest.workspace_id!=self.render.workspace_id \
                or digest(latest.snapshot)!=self._scope['content_sha256'] \
                or digest(latest.provenance)!=self._scope['content_provenance_sha256']:
            raise TTSReuseRejected('TTS_REUSE_CONTENT_CHANGED')
        # Metadata reads are awaited: a cancel/current-target writer during
        # that read must be observed before admitting any read or result.
        await self.guard()
        if self.provider.artifact_reuse_binding != self._adapter:
            raise TTSReuseRejected('TTS_REUSE_RUNTIME_CHANGED')
        if digest(self.voice_config.model_dump(mode='json'))!=self._scope['voice_config_sha256'] \
                or (self.model,self.voice)!=(self.provider.model,self.provider.voice):
            raise TTSReuseRejected('TTS_REUSE_VOICE_CONFIG_CHANGED')

    async def synthesize(self, *, text, language, output_path):
        await self.current()
        if language!='vi' or not isinstance(text,str) or not text.strip() or len(text)>4096:
            raise TTSReuseRejected('TTS_REUSE_INPUT_INVALID')
        binding={**self._scope,'language':language,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        pin=None
        if self.render.render_kind=='final':
            if self._pins is None or self._unit>=len(self._pins['units']):
                raise TTSReuseRejected('TTS_REUSE_REVIEW_UNIT_REQUIRED')
            pin=self._pins['units'][self._unit]
            if digest(binding)!=pin['input_fingerprint']:
                raise TTSReuseRejected('TTS_REUSE_APPROVED_INPUT_CHANGED_REVIEW_REQUIRED')
        self._unit+=1
        requested=Path(output_path)
        if not requested.is_absolute() or not re.fullmatch(r'(?:unit|voice)-[0-9]{3}-raw\.wav',requested.name):
            raise TTSReuseRejected('TTS_REUSE_OUTPUT_PATH_INVALID')
        try:
            target=plain(requested.parent)/requested.name
        except (OSError,ValueError):
            raise TTSReuseRejected('TTS_REUSE_OUTPUT_PATH_INVALID') from None
        if target.is_symlink() or target.exists():
            raise TTSReuseRejected('TTS_REUSE_OUTPUT_CONFLICT')
        entry=await self.repository.claim(binding,self.render.render_id,require_ready=pin is not None)
        if entry['state']=='ready':
            result=entry['result']
            if result.get('schema_version')!=SCHEMA or result.get('input_fingerprint')!=digest(binding) \
                    or result.get('source_render_id')!=entry['source_render_id']:
                raise TTSReuseRejected('TTS_REUSE_EVIDENCE_CHANGED')
            evidence=validate_evidence(result['original_evidence'])
            if pin is not None and (evidence.audio_sha256!=pin['audio_sha256']
                    or result['original_evidence_sha256']!=pin['original_evidence_sha256']):
                raise TTSReuseRejected('TTS_REUSE_APPROVED_AUDIO_CHANGED_REVIEW_REQUIRED')
            if evidence.text_sha256!=binding['text_sha256'] or evidence.profile_sha256!=self._adapter['profile_sha256'] \
                    or result['original_evidence_sha256']!=digest(result['original_evidence']) \
                    or evidence.usage.get('server_source_sha256')!=self._adapter['server_source_sha256'] \
                    or result['normalization_record_sha256']!=evidence.usage.get('normalization_record_sha256'):
                raise TTSReuseRejected('TTS_REUSE_EVIDENCE_CHANGED')
            asset=await self.assets.get_asset(result['asset_id'])
            if asset is None or (asset.workspace_id,asset.project_id,asset.storage_provider)!=(
                    self.render.workspace_id,self.render.project_id,self.storage.name) \
                    or asset.asset_class!='generated' or asset.project_version_id!=self.content.project_version_id \
                    or asset.kind!='tts-reuse-source' or asset.content_type!='audio/wav' \
                    or asset.checksum_sha256!=evidence.audio_sha256 or asset.size_bytes!=result['size_bytes'] \
                    or asset.object_key!=result['object_key'] or asset_proof(asset)!=result.get('asset_proof'):
                raise TTSReuseRejected('TTS_REUSE_ASSET_CHANGED')
            try:
                proof=frozen_asset_read(asset,workspace_id=self.render.workspace_id,
                    project_id=self.render.project_id,storage=self.storage,maximum=MAX_BYTES)
                await proof.download(self.storage,target)
                await completed_read(asyncio.to_thread(pcm,target,evidence))
            except TTSReuseRejected:
                raise
            except Exception:
                raise TTSReuseRejected('TTS_REUSE_SOURCE_UNAVAILABLE') from None
            await self.current()
            latest_asset=await self.assets.get_asset(asset.asset_id)
            if latest_asset is None or asset_proof(latest_asset)!=result['asset_proof']:
                raise TTSReuseRejected('TTS_REUSE_ASSET_CHANGED')
            await self.current()
            receipt={'schema_version':SCHEMA,'reuse_id':entry['reuse_id'],'input_fingerprint':digest(binding),
                'source_render_id':entry['source_render_id'],'source_asset_id':asset.asset_id,
                'source_result_sha256':entry['result_sha256'],'original_evidence_sha256':result['original_evidence_sha256'],
                'audio_sha256':evidence.audio_sha256,'normalization_record_sha256':result['normalization_record_sha256'],
                'workspace_id':self.render.workspace_id,'project_id':self.render.project_id,
                'content_version_id':self.content.project_version_id,'target_render_id':self.render.render_id,
                'target_timeline_version_id':self.render.timeline_version_id,'target_timeline_version':self.render.timeline_version,
                'target_subtitle_version_id':self.render.subtitle_version_id,'target_audio_version_id':self.render.audio_version_id,
                'target_canonical_binding_sha256':digest(self._target),
                'provider_calls':0,'credential_reads':0,'new_inferences':0,'additional_provider_billed_cost_vnd':0,
                'operating_cost_vnd':None,'fresh_provider_measurement':False,'approval_transferred':False,
                'rights_authority_transferred':False,'owner_uat_accepted':False,'publishing_enabled':False,
                'transport_mode':self._adapter['transport_mode']}
            if pin is not None:
                receipt['approved_review_render_id']=self._pins['review_render_id']
                receipt['approved_review_raw_audio_preserved']=True
            return VoiceResult(path=target,duration_seconds=evidence.decoded_duration_seconds,
                provider=result['provider'],voice=result['voice'],evidence=evidence,reuse=receipt)
        if entry['state']!='claimed':
            raise TTSReuseRejected('TTS_REUSE_PENDING' if entry['state']=='pending' else 'TTS_REUSE_UNKNOWN_MANUAL_REVIEW')
        try:
            await self.current()
            original=await self.provider.synthesize(text=text,language=language,output_path=target)
            await self.current()
            evidence=original.evidence
            if evidence is None or original.path.absolute()!=target or evidence.text_sha256!=binding['text_sha256'] \
                    or evidence.profile_sha256!=self._adapter['profile_sha256'] \
                    or evidence.usage.get('server_source_sha256')!=self._adapter['server_source_sha256'] \
                    or not re.fullmatch(r'[a-f0-9]{64}',evidence.usage.get('normalization_record_sha256','')):
                raise TTSReuseRejected('TTS_REUSE_PROVIDER_EVIDENCE_REQUIRED')
            await completed_read(asyncio.to_thread(pcm,target,evidence))
            key=validate_object_key(f"workspaces/{self.render.workspace_id}/projects/{self.render.project_id}/tts-reuse/{entry['reuse_id']}.wav")
            try:
                stored=await self.storage.put_file(object_key=key,path=target,content_type='audio/wav')
            except asyncio.CancelledError:
                raise
            except Exception:
                raise TTSReuseRejected('TTS_REUSE_STORAGE_IO_FAILED') from None
            await self.current()
            if stored.checksum_sha256!=evidence.audio_sha256 or stored.size_bytes!=target.stat().st_size:
                raise TTSReuseRejected('TTS_REUSE_STORED_PCM_CHANGED')
            asset=await self.platform.register_asset(self.render.project_id,AssetRegister(
                project_version_id=self.content.project_version_id,asset_class='generated',kind='tts-reuse-source',
                filename=entry['reuse_id']+'.wav',object_key=stored.object_key,content_type='audio/wav',
                size_bytes=stored.size_bytes,checksum_sha256=stored.checksum_sha256,storage_provider=stored.storage_provider,
                provenance={'schema_version':SCHEMA,'source_render_id':self.render.render_id,
                    'input_fingerprint':digest(binding),'original_evidence_sha256':digest(evidence.model_dump(mode='json')),
                    'human_accepted':False,'rights_status':'unknown','transport_mode':self._adapter['transport_mode']}))
            result={'schema_version':SCHEMA,'input_fingerprint':digest(binding),'source_render_id':self.render.render_id,
                'asset_id':asset.asset_id,'object_key':asset.object_key,'size_bytes':asset.size_bytes,
                'asset_proof':asset_proof(asset),
                'provider':original.provider,'voice':original.voice,'original_evidence':evidence.model_dump(mode='json'),
                'original_evidence_sha256':digest(evidence.model_dump(mode='json')),
                'normalization_record_sha256':evidence.usage['normalization_record_sha256']}
            await self.current()
            await self.repository.complete(entry['reuse_id'],entry['claim_id'],result)
            await self.current()
            return original.model_copy(update={'cache_origin':{'schema_version':SCHEMA,'reuse_id':entry['reuse_id'],
                'input_fingerprint':digest(binding),'transport_mode':self._adapter['transport_mode'],
                'source_render_id':self.render.render_id,'original_evidence_sha256':result['original_evidence_sha256'],
                'fresh_provider_response':True,'human_accepted':False}})
        except OSError:
            await self.repository.unknown(entry['reuse_id'],entry['claim_id'])
            raise TTSReuseRejected('TTS_REUSE_STORAGE_IO_FAILED') from None
        except BaseException:
            await self.repository.unknown(entry['reuse_id'],entry['claim_id'])
            raise


def canonical_audio_binding(render, snapshot, subtitles, config):
    return {'schema_version':'sql-approved-audio-binding.v1',
        'identity':[render.workspace_id,render.project_id,render.timeline_version_id,
            render.subtitle_version_id,render.audio_version_id],
        'timeline_sha256':digest(snapshot),
        'subtitle_sha256':digest({'cues':[cue.model_dump(mode='json') for cue in subtitles.cues],
            'style':subtitles.style.model_dump(mode='json')}),
        'audio_config_sha256':digest(config.model_dump(mode='json'))}


def prepared_audio_byte_limit(duration):
    """Stereo PCM16 capacity plus bounded WAV metadata, not a duration shrink."""
    if type(duration) not in (int,float) or not math.isfinite(duration) \
            or not 0 < duration <= PREPARED_AUDIO_MAX_DURATION_SECONDS:
        raise TTSReuseRejected('TTS_REUSE_PREPARED_AUDIO_DURATION_INVALID')
    # Keep the existing one-sample clock tolerance, including fractional frames.
    return (math.ceil(duration*PREPARED_AUDIO_SAMPLE_RATE)+1)*2*2+PREPARED_AUDIO_HEADER_MAX_BYTES


def prepared_pcm(path, duration):
    """Actual prepared audio length/sample count; no listening/QC inference."""
    try:
        maximum=prepared_audio_byte_limit(duration)
        path=plain(path)
        size=path.stat().st_size
        if not 0<size<=maximum:
            raise TTSReuseRejected('TTS_REUSE_PREPARED_AUDIO_LIMIT')
        with wave.open(str(filesystem_path(path)),'rb') as audio:
            rate=audio.getframerate();channels=audio.getnchannels();count=audio.getnframes()
            if rate!=PREPARED_AUDIO_SAMPLE_RATE or channels not in {1,2} or audio.getsampwidth()!=2 \
                    or abs(count/rate-duration)>1/rate:
                raise TTSReuseRejected('TTS_REUSE_PREPARED_AUDIO_CLOCK_INVALID')
            if not 0<size-count*channels*2<=PREPARED_AUDIO_HEADER_MAX_BYTES:
                raise TTSReuseRejected('TTS_REUSE_PREPARED_AUDIO_HEADER_LIMIT')
            remaining=count
            while remaining:
                amount=min(remaining,48000)
                if len(audio.readframes(amount))!=amount*channels*2:
                    raise TTSReuseRejected('TTS_REUSE_PREPARED_AUDIO_TRUNCATED')
                remaining-=amount
    except TTSReuseRejected:
        raise
    except (OSError,ValueError,wave.Error):
        raise TTSReuseRejected('TTS_REUSE_PREPARED_AUDIO_UNAVAILABLE') from None


async def prepared_final_audio(*, repository, assets, storage, render, snapshot, subtitles, config, workdir):
    duration=snapshot.get('duration_seconds')
    prepared_maximum=prepared_audio_byte_limit(duration)
    source=await repository.approved_audio_reuse_source(render.render_id)
    target=canonical_audio_binding(render,snapshot,subtitles,config)
    manifest=source['manifest'];narration=copy.deepcopy(manifest.get('narration',{}));mix=copy.deepcopy(manifest.get('mix',{}))
    original_binding=narration.get('canonical_audio_binding')
    # JSON stores tuples as lists. Canonical hashing compares their values.
    if original_binding is None or digest(original_binding)!=digest(target) \
            or not isinstance(narration.get('timing'),list) or not manifest.get('supporting_asset_ids'):
        raise TTSReuseRejected('TTS_REUSE_PREPARED_REVIEW_PROOF_REQUIRED')
    target['review_manifest_sha256']=source['manifest_sha256']
    async def current():
        await repository.assert_audio_reuse_current(render.render_id,target)
    await current()
    try:
        workdir=plain(workdir)
    except (OSError,ValueError):
        raise TTSReuseRejected('TTS_REUSE_OUTPUT_PATH_INVALID') from None
    copies=[]
    async def download(asset_id, name, kind, expected_sha=None, maximum=prepared_maximum, frozen_proof=None):
        asset=await assets.get_asset(asset_id) if asset_id else None
        if asset is None or (asset.workspace_id,asset.project_id,asset.storage_provider)!=(
                render.workspace_id,render.project_id,storage.name) or asset.asset_class!='render' \
                or asset.kind!=kind or asset.content_type!='audio/wav' \
                or not 0<asset.size_bytes<=maximum or expected_sha is not None and asset.checksum_sha256!=expected_sha:
            raise TTSReuseRejected('TTS_REUSE_APPROVED_ASSET_REQUIRED')
        if kind in {'narration-track','audio-mix'} \
                and asset_proof(asset)!=manifest.get('supporting_audio_proofs',{}).get(kind):
            raise TTSReuseRejected('TTS_REUSE_APPROVED_AUDIO_PROOF_CHANGED_REVIEW_REQUIRED')
        if frozen_proof is not None and asset_proof(asset)!=frozen_proof:
            raise TTSReuseRejected('TTS_REUSE_APPROVED_RAW_PROOF_CHANGED_REVIEW_REQUIRED')
        path=Path(workdir)/name
        if path.is_symlink() or path.exists():
            raise TTSReuseRejected('TTS_REUSE_OUTPUT_CONFLICT')
        try:
            proof=frozen_asset_read(asset,workspace_id=render.workspace_id,project_id=render.project_id,
                storage=storage,maximum=maximum)
            await proof.download(storage,path)
            plain(path)
            if path.stat().st_size!=asset.size_bytes or await completed_read(asyncio.to_thread(sha256_file,path))!=asset.checksum_sha256:
                raise TTSReuseRejected('TTS_REUSE_APPROVED_ASSET_CHANGED')
        except TTSReuseRejected:
            raise
        except Exception:
            raise TTSReuseRejected('TTS_REUSE_APPROVED_ASSET_UNAVAILABLE') from None
        await current()
        latest=await assets.get_asset(asset.asset_id)
        try:
            if latest is None or asset_proof(latest)!=asset_proof(asset) \
                    or await completed_read(asyncio.to_thread(sha256_file,path))!=asset.checksum_sha256:
                raise TTSReuseRejected('TTS_REUSE_APPROVED_ASSET_CHANGED')
        except OSError:
            raise TTSReuseRejected('TTS_REUSE_APPROVED_ASSET_UNAVAILABLE') from None
        latest=await assets.get_asset(asset.asset_id)
        if latest is None or asset_proof(latest)!=asset_proof(asset):
            raise TTSReuseRejected('TTS_REUSE_APPROVED_ASSET_CHANGED')
        await current()
        copies.append({'kind':kind,'asset_id':asset.asset_id,'sha256':asset.checksum_sha256,'bytes':asset.size_bytes})
        return path
    supporting=manifest['supporting_asset_ids']
    voice_path=await download(supporting.get('narration-track'),'narration.wav','narration-track')
    mix_path=await download(supporting.get('audio-mix'),'audio-mix.wav','audio-mix')
    for path in (voice_path,mix_path):
        await completed_read(asyncio.to_thread(prepared_pcm,path,duration))
    pins=await repository.approved_tts_reuse_units(render.render_id)
    if pins is not None and len(pins['units'])!=len(narration['timing']):
        raise TTSReuseRejected('TTS_REUSE_REVIEW_UNIT_COUNT_CHANGED')
    for index,unit in enumerate(narration['timing']):
        if unit.get('provider_evidence') is not None:
            evidence=validate_evidence(unit['provider_evidence'])
            name=unit.get('provider_audio_file','')
            if not re.fullmatch(r'(?:unit|voice)-[0-9]{3}-raw\.wav',name):
                raise TTSReuseRejected('TTS_REUSE_REVIEW_RAW_REFERENCE_INVALID')
            raw=await download(unit.get('provider_audio_asset_id'),name,'tts-provider-source',
                expected_sha=evidence.audio_sha256,maximum=MAX_BYTES,frozen_proof=unit.get('provider_audio_asset_proof'))
            if not unit.get('provider_audio_asset_proof'):
                raise TTSReuseRejected('TTS_REUSE_APPROVED_RAW_PROOF_REQUIRED')
            await completed_read(asyncio.to_thread(pcm,raw,evidence))
            if pins is not None and (pins['units'][index]['audio_sha256']!=evidence.audio_sha256
                    or pins['units'][index]['original_evidence_sha256']!=digest(unit['provider_evidence'])):
                raise TTSReuseRejected('TTS_REUSE_APPROVED_RAW_AUDIO_CHANGED')
        # These are historical units, including previous latency/cost/request IDs.
        unit['prepared_audio_reused']=True
    await current()
    receipt={'schema_version':'sql-approved-prepared-audio-reuse.v1','source_review_render_id':source['review_render_id'],
        'source_review_manifest_sha256':source['manifest_sha256'],'target_render_id':render.render_id,
        'target_canonical_binding_sha256':digest(target),'workspace_id':render.workspace_id,'project_id':render.project_id,
        'approved_audio_preserved':True,'copied_assets':copies,'provider_calls':0,'credential_reads':0,
        'new_inferences':0,'additional_provider_billed_cost_vnd':0,'operating_cost_vnd':None,
        'fresh_provider_measurement':False,'approval_transferred_to_assets':False,'rights_authority_transferred':False,
        'human_quality_accepted':False,'owner_uat_accepted':False,'publishing_enabled':False}
    narration['prepared_audio_reuse']=receipt
    return narration,mix

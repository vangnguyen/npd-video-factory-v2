"""Provider-neutral CPU transcript adapter with no paid/remote fallback."""
import asyncio,json,math,os,wave
from decimal import Decimal
from pathlib import Path
from .auto_edit_providers import ProviderTranscript,ProviderSegment,ProviderWord,ProviderNotConfigured
from .local_asr_profile import profile,digest,canonical
from .local_asr_runtime import runtime,plain,file_sha

SCRIPT=Path(__file__).resolve().parents[3]/'services/local_asr/run.py'

def normalize(value,selected,checksum,duration):
    if (not isinstance(value,dict) or value.get('version')!='local-asr-result.v1'
        or value.get('profile_sha256')!=digest(selected) or value.get('source_sha256')!=checksum
        or value.get('model_revision')!=selected['model_revision'] or value.get('library_version')!='1.2.1'
        or value.get('device')!='cpu' or value.get('compute_type')!='int8'
        or any(type(value.get(key)) is not int for key in ('external_calls','paid_calls','model_inferences'))
        or value.get('external_calls')!=0 or value.get('paid_calls')!=0 or value.get('model_inferences')!=1
        or type(value.get('vad_filter')) is not bool or value.get('vad_filter')!=selected['vad_filter']):
        raise ValueError('LOCAL_ASR_RESULT_BINDING_INVALID')
    language=value.get('language')
    if language not in ('vi','en') or selected['language']!='auto' and language!=selected['language']:
        raise ValueError('LOCAL_ASR_LANGUAGE_MISMATCH')
    actual=value.get('duration_seconds')
    if type(actual) not in (int,float) or not math.isfinite(actual) or abs(actual-duration)>1/16000:
        raise ValueError('LOCAL_ASR_DURATION_MISMATCH')
    probability=value.get('language_confidence')
    if selected['language']!='auto' and probability is not None:
        raise ValueError('LOCAL_ASR_FORCED_LANGUAGE_IS_NOT_DETECTION')
    if probability is not None and (type(probability) not in (int,float) or not math.isfinite(probability) or not 0<=probability<=1):
        raise ValueError('LOCAL_ASR_CONFIDENCE_INVALID')
    if selected['language']=='auto' and probability is None:raise ValueError('LOCAL_ASR_CONFIDENCE_INVALID')
    if selected['vad_filter']:
        kept=value.get('duration_after_vad_seconds')
        if (type(kept) not in (int,float) or not math.isfinite(kept) or not 0<kept<=duration+1/16000
            or value.get('timestamp_coordinate_system')!='original_input_pcm_seconds'):
            raise ValueError('LOCAL_ASR_VAD_SOURCE_CLOCK_INVALID')
    segments=[];previous=0.;count=0
    if not isinstance(value.get('segments'),list) or not 1<=len(value['segments'])<=2000:
        raise ValueError('LOCAL_ASR_NO_SPEECH_OR_RESULT_LIMIT')
    for raw in value['segments']:
        words=tuple(ProviderWord(**w) for w in raw['words']);count+=len(words)
        segment=ProviderSegment(**{**raw,'words':words})
        if not segment.text.strip() or count>10000 or not words or segment.confidence is not None or segment.speaker is not None:
            raise ValueError('LOCAL_ASR_SEGMENT_INVALID')
        numbers=[segment.start_seconds,segment.end_seconds,*(n for w in words for n in (w.start_seconds,w.end_seconds))]
        if any(type(n) not in (int,float) or not math.isfinite(n) for n in numbers):raise ValueError('LOCAL_ASR_TIMING_INVALID')
        if segment.start_seconds<previous-1e-6 or segment.end_seconds>duration+1/16000 or segment.end_seconds<=segment.start_seconds:
            raise ValueError('LOCAL_ASR_TIMING_INVALID')
        word_end=segment.start_seconds
        for word in words:
            if (not word.text or word.start_seconds<word_end-1e-6 or word.end_seconds>segment.end_seconds+1/16000
                or type(word.confidence) not in (int,float) or not math.isfinite(word.confidence) or not 0<=word.confidence<=1):
                raise ValueError('LOCAL_ASR_WORD_INVALID')
            word_end=word.end_seconds
        previous=segment.end_seconds;segments.append(segment)
    return ProviderTranscript(language=language,confidence=None,segments=tuple(segments),actual_cost_vnd=None,
        provenance={'provider':'faster-whisper','model':selected['model'],'model_revision':selected['model_revision'],
            'profile_sha256':digest(selected),'raw_response_sha256':digest(value),'source_checksum':checksum,
            'requested_language':selected['language'],'language_detection_requested':selected['language']=='auto',
            'language_detection_performed':selected['language']=='auto','language_confidence':probability,
            'word_alignment_source':'model_estimate','word_timing_rewritten':False,'original_evidence':True,
            'recognition_review_required':True,'low_confidence_word_count':sum(w.confidence<.5 for s in segments for w in s.words),
            'local_inference':True,'external_call':False,'paid_call':False,'model_inferences':1,'diarization_supported':False,
            **({'vad_filter':True,'duration_after_vad_seconds':value['duration_after_vad_seconds'],
                'timestamp_coordinate_system':value['timestamp_coordinate_system'],'vad_time_mapping':'faster-whisper-estimated-to-original-pcm'}
                if selected['vad_filter'] else {})})

class LocalCpuTranscriptionProvider:
    key='local-faster-whisper';model='Systran/faster-whisper-base';external_call=False;paid=False
    credential_alias=None;estimated_cost_vnd=Decimal('0')
    def __init__(self,manifest,language='auto',model_key='base'):
        self.manifest=manifest;self.profile=profile(language,model_key);self.raw_result=None
        self.model_key=model_key;self.model=self.profile['model']

    async def transcribe(self,path,*,metadata,checksum_sha256,execution_trace=None):
        try:config=await asyncio.to_thread(runtime,self.manifest,model_key=self.model_key)
        except (OSError,ValueError,TypeError,KeyError):raise ProviderNotConfigured('LOCAL_ASR_NOT_CONFIGURED_OR_CHANGED') from None
        source=plain(path)
        if file_sha(source)!=checksum_sha256:raise ValueError('LOCAL_ASR_AUDIO_CHANGED')
        with wave.open(str(source),'rb') as audio:
            if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=16000:
                raise ValueError('LOCAL_ASR_PCM_REQUIRED')
            duration=audio.getnframes()/16000.
        if metadata.duration_seconds is None or abs(metadata.duration_seconds-duration)>1/16000:
            raise ValueError('LOCAL_ASR_DURATION_MISMATCH')
        env={k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP') if k in os.environ}
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONUTF8='1')
        request={'audio':str(source),'audio_sha256':checksum_sha256,'model_root':config['model_root'],
            'profile':self.profile,'cpu_threads':config['cpu_threads']}
        child=await asyncio.create_subprocess_exec(config['python'],'-I',str(SCRIPT),stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
        try:output,_=await asyncio.wait_for(child.communicate(canonical(request)),config['timeout_seconds'])
        except (TimeoutError,asyncio.CancelledError):
            if child.returncode is None:child.kill()
            await child.communicate();raise
        if child.returncode or len(output)>4*1024*1024:raise ValueError('LOCAL_ASR_EXECUTION_FAILED')
        if await asyncio.to_thread(runtime,self.manifest,model_key=self.model_key)!=config:raise ValueError('LOCAL_ASR_RUNTIME_CHANGED')
        if file_sha(source)!=checksum_sha256:raise ValueError('LOCAL_ASR_AUDIO_CHANGED')
        self.raw_result=json.loads(output)
        return normalize(self.raw_result,self.profile,checksum_sha256,duration)

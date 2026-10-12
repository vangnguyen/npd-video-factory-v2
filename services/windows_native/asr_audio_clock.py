"""Explicit derived-WAV gap padding; decoded PCM and source media stay intact."""
import re,wave
from .contracts import WorkflowError,digest,file_sha
from app.decoded_audio_clock import audio_clock_segments


def padding_plan(clock):
    if clock.get('schema_version')!='decoded-mono-audio-clock-v2' or clock.get('contiguous') is not False or clock.get('sample_rate')!=16000:
        raise WorkflowError('ASR_AUDIO_GAP_CLOCK_INVALID')
    segments=audio_clock_segments(clock)
    if segments!=clock.get('segments') or len(segments)<2 or len(segments)>10000:
        raise WorkflowError('ASR_AUDIO_GAP_CLOCK_INVALID')
    origin=segments[0]['source_start_sample'];cursor=0;decoded_cursor=0;plan=[];gaps=[]
    if clock.get('source_start_seconds')!=origin/16000 or clock.get('source_end_seconds')!=(clock['frames'][-1]['pts']+clock['frames'][-1]['nb_samples'])/16000 or clock.get('time_base_numerator')!=1 or clock.get('time_base_denominator')!=16000 or any(clock.get(k) is not False for k in ('implicit_gap_fill_performed','implicit_overlap_removal_performed')):
        raise WorkflowError('ASR_AUDIO_GAP_CLOCK_INVALID')
    for segment in segments:
        start=segment['source_start_sample']-origin;count=segment['pcm_end_sample']-segment['pcm_start_sample']
        if type(start) is not int or type(count) is not int or start<cursor or count<=0 or segment['pcm_start_sample']!=decoded_cursor:
            raise WorkflowError('ASR_AUDIO_GAP_CLOCK_INVALID')
        if start>cursor:gaps.append({'pcm_start_sample':cursor,'pcm_end_sample':start})
        plan.append({**segment,'normalized_pcm_start_sample':start,'normalized_pcm_end_sample':start+count})
        cursor=start+count;decoded_cursor+=count
    if decoded_cursor!=clock['pcm_samples'] or cursor>16000*600 or abs(cursor+origin-clock['frames'][-1]['pts']-clock['frames'][-1]['nb_samples'])>1:
        raise WorkflowError('ASR_AUDIO_GAP_CLOCK_INVALID')
    expected_gaps=[{'source_start_sample':g['pcm_start_sample']+origin,'source_end_sample':g['pcm_end_sample']+origin,
                    'decoded_pcm_boundary_sample':plan[i+1]['pcm_start_sample']} for i,g in enumerate(gaps)]
    if expected_gaps!=clock.get('gaps'):raise WorkflowError('ASR_AUDIO_GAP_CLOCK_INVALID')
    return {'source_origin_sample':origin,'sample_rate':16000,'decoded_pcm_samples':decoded_cursor,'normalized_pcm_samples':cursor,
            'inserted_silence_samples':sum(g['pcm_end_sample']-g['pcm_start_sample'] for g in gaps),'segments':plan,'gaps':gaps}


def pad_wav(decoded,output,clock):
    plan=padding_plan(clock)
    with wave.open(str(decoded),'rb') as raw, wave.open(str(output),'wb') as padded:
        if raw.getparams()[:4]!=(1,2,16000,plan['decoded_pcm_samples']):raise WorkflowError('ASR_AUDIO_GAP_PCM_INVALID')
        padded.setnchannels(1);padded.setsampwidth(2);padded.setframerate(16000);cursor=0
        for segment in plan['segments']:
            missing=segment['normalized_pcm_start_sample']-cursor
            while missing:
                count=min(missing,32768);padded.writeframesraw(b'\0'*(count*2));missing-=count
            remaining=segment['pcm_end_sample']-segment['pcm_start_sample']
            while remaining:
                count=min(remaining,32768);data=raw.readframes(count)
                if len(data)!=count*2:raise WorkflowError('ASR_AUDIO_GAP_PCM_INVALID')
                padded.writeframesraw(data);remaining-=count
            cursor=segment['normalized_pcm_end_sample']
        if raw.readframes(1):raise WorkflowError('ASR_AUDIO_GAP_PCM_INVALID')
    return {'schema_version':'native-asr-explicit-gap-padding-v1','plan':plan,'decoded_audio_clock_sha256':digest(clock),
            'decoded_wav_sha256':file_sha(decoded),'normalized_wav_sha256':file_sha(output),
            'source_media_mutated':False,'time_scale_changed':False,'overlap_removal_performed':False}


def validate_padding(metadata):
    clock=metadata['decoded_source_clock'];receipt=metadata.get('explicit_gap_padding')
    plan=padding_plan(clock)
    if not isinstance(receipt,dict) or receipt.get('schema_version')!='native-asr-explicit-gap-padding-v1' or receipt.get('plan')!=plan or receipt.get('decoded_audio_clock_sha256')!=digest(clock) or not all(re.fullmatch('[0-9a-f]{64}',str(receipt.get(k,''))) for k in ('normalized_wav_sha256','decoded_wav_sha256')) or receipt.get('normalized_wav_sha256')!=metadata.get('sha256') or receipt.get('decoded_wav_sha256')!=metadata.get('decoded_pcm_wav',{}).get('sha256') or any(receipt.get(k) is not False for k in ('source_media_mutated','time_scale_changed','overlap_removal_performed')) or metadata['duration_seconds']!=plan['normalized_pcm_samples']/16000:
        raise WorkflowError('ASR_AUDIO_GAP_PADDING_CHANGED')
    return plan

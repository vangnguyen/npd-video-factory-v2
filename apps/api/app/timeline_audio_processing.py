"""Opt-in canonical audio processing; legacy timeline mixing is unchanged.

Normalization precedes clip gain, so editorial gain is not silently cancelled.
Ducking uses actual original-audio energy, not fabricated speech detection.
"""
from dataclasses import dataclass
from typing import Any
from pydantic import Field
from .models import StrictModel
from .timeline_audio import TimelineAudioGraph,build_timeline_audio_graph


class AudioProcessing(StrictModel):
    normalize_original_audio:bool=Field(default=False,strict=True)
    normalize_music:bool=Field(default=False,strict=True)
    duck_music:bool=Field(default=False,strict=True)
    original_target_lufs:float=Field(default=-16,ge=-24,le=-12)
    music_target_lufs:float=Field(default=-24,ge=-35,le=-16)
    duck_threshold:float=Field(default=.02,ge=.001,le=.2)
    duck_ratio:float=Field(default=8,ge=2,le=20)
    duck_attack_ms:float=Field(default=20,ge=1,le=500)
    duck_release_ms:float=Field(default=250,ge=20,le=2000)


@dataclass(frozen=True)
class ProcessedAudioGraph(TimelineAudioGraph):
    processing:dict[str,Any]


def build_processed_audio_graph(snapshot,assets,*,first_input_index,processing=None):
    base=build_timeline_audio_graph(snapshot,assets,first_input_index=first_input_index)
    config=AudioProcessing.model_validate(processing or {})
    receipt={'schema':'canonical-audio-processing-v1','configuration':config.model_dump(mode='json'),
        'normalization_clip_ids':[],'normalization_skipped_short_clip_ids':[],
        'normalization_original_audio_clip_ids':[],'normalization_music_clip_ids':[],
        'normalization_mode':'ffmpeg_loudnorm_single_pass_before_editorial_gain',
        'measured_integrated_loudness':None,'music_ducking':False,
        'sidechain_source':'canonical_original_audio_energy','speech_detection_performed':False,
        'limiter_peak_db':-1 if base.clips else None}
    if not base.clips or not any((config.normalize_original_audio,config.normalize_music,config.duck_music)):
        return ProcessedAudioGraph(base.inputs,base.filters,base.clips,base.muted_clip_ids,receipt)
    tracks={track.track_id:track for track in snapshot.tracks};filters=list(base.filters[:-1])
    groups={'original':[],'music':[],'other':[]}
    for index,clip in enumerate(base.clips):
        kind=tracks[clip['track_id']].kind
        role='original' if kind in {'original_audio','voice'} else 'music' if kind=='music' else 'other'
        groups[role].append(f'[audio{index}]')
        normalize=config.normalize_original_audio if role=='original' else config.normalize_music if role=='music' else False
        if normalize and clip['duration']<.4:
            receipt['normalization_skipped_short_clip_ids'].append(clip['clip_id'])
        elif normalize:
            target=config.original_target_lufs if role=='original' else config.music_target_lufs
            # All inserted parameters are finite typed numbers, never client
            # filter strings. Apply normalization before saved volume/fades.
            marker=f"volume={clip['volume']:.9f}"
            filters[index]=filters[index].replace(marker,
                f'loudnorm=I={target:.6f}:LRA=11:TP=-1,aresample=48000,'+marker,1)
            receipt['normalization_clip_ids'].append(clip['clip_id'])
            receipt['normalization_original_audio_clip_ids' if role=='original' else 'normalization_music_clip_ids'].append(clip['clip_id'])
    labels={}
    for role,clips in groups.items():
        if not clips:continue
        name='stem_'+role;labels[role]=f'[{name}]'
        filters.append(''.join(clips)+f'amix=inputs={len(clips)}:duration=longest:dropout_transition=0:normalize=0,'
            f'apad,atrim=duration={snapshot.duration_seconds:.9f}[{name}]')
    if config.duck_music and 'original' in labels and 'music' in labels:
        filters.append(labels['original']+'asplit=2[original_out][sidechain]')
        filters.append(labels['music']+f'[sidechain]sidechaincompress=threshold={config.duck_threshold:.9f}:'
            f'ratio={config.duck_ratio:.6f}:attack={config.duck_attack_ms:.6f}:'
            f'release={config.duck_release_ms:.6f}:makeup=1[ducked_music]')
        labels.update(original='[original_out]',music='[ducked_music]');receipt['music_ducking']=True
    filters.append(''.join(labels.values())+f'amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,'
        'alimiter=limit=0.891250938:level=0:latency=1,apad,'
        f'atrim=duration={snapshot.duration_seconds:.9f},asetpts=PTS-STARTPTS[outa]')
    return ProcessedAudioGraph(base.inputs,filters,base.clips,base.muted_clip_ids,receipt)

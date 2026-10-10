"""Opt-in processing contracts and measured local PCM, never speech/provider claims."""
import array
from datetime import datetime,timezone
import hashlib
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave
import pytest
from app.platform_models import AssetRead
from app.timeline_models import TimelineClip,TimelineTrack,TimelineSnapshot
from app.timeline_audio import build_timeline_audio_graph
from app.timeline_audio_processing import AudioProcessing,build_processed_audio_graph


def fixture(tmp_path,*,original=True,volume=1):
    assets={};tracks=[];timestamp=datetime.now(timezone.utc)
    for role,frequency,gain in [('original_audio',880,volume),('music',220,.25)]:
        if role=='original_audio' and not original:continue
        path=tmp_path/f'{role}.wav'
        values=array.array('h',(round((.3 if role=='original_audio' else .08)*32767*math.sin(2*math.pi*frequency*n/48000))
            if role=='music' or 48000<=n<96000 else 0 for n in range(144000)))
        if sys.byteorder!='little':values.byteswap()
        with wave.open(str(path),'wb') as target:
            target.setparams((1,2,48000,0,'NONE','not compressed'));target.writeframes(values.tobytes())
        identifier='ast_'+role
        assets[identifier]=(AssetRead(asset_id=identifier,workspace_id='wrk_fixture',project_id='prj_fixture',
            project_version_id=None,job_id=None,asset_class='source',kind='audio',filename=path.name,
            object_key=path.name,content_type='audio/wav',size_bytes=path.stat().st_size,
            checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),storage_provider='local',version=1,
            provenance={'fixture':True},created_at=timestamp,updated_at=timestamp),path)
        tracks.append(TimelineTrack(track_id='trk_'+role,type='audio',kind=role,label=role,order=len(tracks),
            clips=[TimelineClip(clip_id='clip_'+role,kind=role,label=role,asset_id=identifier,
                source_start=0,source_end=3,timeline_start=0,duration=3,volume=gain)]))
    return TimelineSnapshot(duration_seconds=3,tracks=tracks),assets


def encode(tmp_path,snapshot,assets,processing,filename):
    if not shutil.which('ffmpeg'):pytest.skip('Real local FFmpeg unavailable')
    graph=build_processed_audio_graph(snapshot,assets,first_input_index=0,processing=processing)
    filters=tmp_path/(filename+'.filters');filters.write_text(';'.join(graph.filters),encoding='utf-8')
    path=tmp_path/(filename+'.wav')
    command=['ffmpeg','-v','error','-nostdin','-n',*graph.inputs,'-/filter_complex',str(filters),
        '-map','[outa]','-ar','48000','-ac','2','-c:a','pcm_s16le',str(path)]
    result=subprocess.run(command,capture_output=True,timeout=30)
    if result.returncode and b"Unrecognized option '/filter_complex'" in result.stderr:
        command[command.index('-/filter_complex')]='-filter_complex_script'
        result=subprocess.run(command,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr[-500:]
    with wave.open(str(path),'rb') as output:
        assert (output.getframerate(),output.getnchannels(),output.getnframes())==(48000,2,144000)
        values=array.array('h');values.frombytes(output.readframes(output.getnframes()))
    if sys.byteorder!='little':values.byteswap()
    return [value/32768 for value in values[::2]],graph


def amplitude(values,frequency,start,end):
    section=values[round(start*48000):round(end*48000)]
    return 2*abs(sum(value*complex(math.cos(2*math.pi*frequency*n/48000),
        math.sin(2*math.pi*frequency*n/48000)) for n,value in enumerate(section)))/len(section)


def test_processing_defaults_preserve_exact_legacy_graph(tmp_path):
    snapshot,assets=fixture(tmp_path)
    old=build_timeline_audio_graph(snapshot,assets,first_input_index=2)
    new=build_processed_audio_graph(snapshot,assets,first_input_index=2)
    assert (old.inputs,old.filters,old.clips,old.muted_clip_ids)==(new.inputs,new.filters,new.clips,new.muted_clip_ids)
    assert new.processing['normalization_clip_ids']==[] and not new.processing['music_ducking']

@pytest.mark.parametrize('processing',[{}, {'duck_music':True}, {'normalize_original_audio':True,'normalize_music':True,'duck_music':True}])
def test_independent_stem_outputs_keep_production_graph_and_actual_mixed_pcm_unchanged(tmp_path,processing):
    if not shutil.which('ffmpeg'):pytest.skip('Real local FFmpeg unavailable')
    snapshot,assets=fixture(tmp_path);before={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,(_,path) in assets.items()}
    _,old=encode(tmp_path,snapshot,assets,processing,'original-mix')
    graph=build_processed_audio_graph(snapshot,assets,first_input_index=0,processing=processing,stem_outputs=True)
    assert old.inputs==graph.inputs and old.filters==graph.filters
    mixed=tmp_path/'original-mix.wav';mix_hash=hashlib.sha256(mixed.read_bytes()).hexdigest()
    with wave.open(str(mixed),'rb') as a:original_pcm=a.readframes(a.getnframes())
    for role,label in graph.stems.items():
        filters=tmp_path/(role+'.filters');filters.write_text(';'.join(graph.stem_graphs[role]),encoding='utf-8')
        command=['ffmpeg','-v','error','-nostdin','-n','-filter_complex_threads','1',*graph.inputs,'-/filter_complex',str(filters),
            '-map',label,'-ar','48000','-ac','2','-f','f32le',str(tmp_path/(role+'.f32le'))]
        result=subprocess.run(command,capture_output=True,timeout=30)
        if result.returncode and b"Unrecognized option '/filter_complex'" in result.stderr:
            command[command.index('-/filter_complex')]='-filter_complex_script';result=subprocess.run(command,capture_output=True,timeout=30)
        assert result.returncode==0,result.stderr[-500:]
    assert hashlib.sha256(mixed.read_bytes()).hexdigest()==mix_hash
    with wave.open(str(mixed),'rb') as a:assert a.readframes(a.getnframes())==original_pcm
    for role in ('reference','music'):assert (tmp_path/(role+'.f32le')).stat().st_size==144000*8
    if processing.get('duck_music'):
        values=array.array('f');values.frombytes((tmp_path/'music.f32le').read_bytes())
        if sys.byteorder!='little':values.byteswap()
        channel=values[::2]
        rms=lambda start,end:math.sqrt(sum(v*v for v in channel[start:end])/(end-start))
        assert rms(60000,84000)<rms(12000,36000)
    assert old.processing==graph.processing
    assert {key:hashlib.sha256(path.read_bytes()).hexdigest() for key,(_,path) in assets.items()}==before


@pytest.mark.parametrize('body',[{'duck_ratio':math.inf},{'duck_music':1},{'filter':'arbitrary'},
    {'original_target_lufs':math.nan},{'music_target_lufs':-1}])
def test_processing_rejects_unsafe_or_untyped_configuration(body):
    with pytest.raises(ValueError):AudioProcessing.model_validate(body)


def test_short_windows_and_absent_original_audio_do_not_fabricate_normalization_or_ducking(tmp_path):
    snapshot,assets=fixture(tmp_path,original=False)
    clip=snapshot.tracks[0].clips[0];clip.source_end=.3;clip.duration=.3
    graph=build_processed_audio_graph(snapshot,assets,first_input_index=0,processing={'normalize_music':True,'duck_music':True})
    assert not graph.processing['normalization_clip_ids'] and not graph.processing['music_ducking']
    assert graph.processing['normalization_skipped_short_clip_ids']==[clip.clip_id]


def test_real_ducking_reduces_only_music_during_actual_original_audio_energy(tmp_path):
    snapshot,assets=fixture(tmp_path)
    plain,_=encode(tmp_path,snapshot,assets,{},'plain')
    ducked,graph=encode(tmp_path,snapshot,assets,{'duck_music':True},'ducked')
    quiet=amplitude(ducked,220,.3,.7);active=amplitude(ducked,220,1.2,1.6)
    assert quiet>.005 and active<quiet*.6
    assert quiet==pytest.approx(amplitude(plain,220,.3,.7),rel=.02)
    assert amplitude(ducked,880,1.2,1.6)==pytest.approx(amplitude(plain,880,1.2,1.6),rel=.02)
    assert max(abs(value) for value in ducked)<=.892
    assert graph.processing['music_ducking'] and not graph.processing['speech_detection_performed']


def test_real_normalization_retains_editorial_gain_and_exact_pcm_duration(tmp_path):
    snapshot,assets=fixture(tmp_path);snapshot.tracks[1].muted=True
    normal,graph=encode(tmp_path,snapshot,assets,{'normalize_original_audio':True},'normal')
    snapshot.tracks[0].clips[0].volume=.5
    quiet,_=encode(tmp_path,snapshot,assets,{'normalize_original_audio':True},'half')
    assert amplitude(normal,880,1.2,1.6)>.1
    assert amplitude(quiet,880,1.2,1.6)==pytest.approx(amplitude(normal,880,1.2,1.6)*.5,rel=.02)
    assert graph.processing['normalization_clip_ids']==['clip_original_audio']

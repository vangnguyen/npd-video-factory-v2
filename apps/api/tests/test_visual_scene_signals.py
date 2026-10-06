"""Synthetic pixels/tone, real bounded FFmpeg decoding; no semantic Vision claim."""
import asyncio
import shutil
import subprocess
from pathlib import Path
import pytest
from app.visual_signals import WIDTH,HEIGHT,frame_signals,measure_visual_signals
from app.auto_edit_providers import FFmpegMediaSignalProvider,MediaSignals
from app.auto_edit_models import MediaMetadata
from app.auto_edit_logic import build_scenes,build_highlights


def test_actual_pixel_metrics_do_not_invent_previous_frames_or_semantic_subjects():
    dark=bytes(WIDTH*HEIGHT);first=frame_signals(dark,None);second=frame_signals(dark,dark)
    assert first['temporal_difference'] is None and first['identical_to_previous'] is None
    assert first['black_frame'] and first['mean_luma']==0
    assert second['temporal_difference']==0 and second['identical_to_previous'] is True
    white=frame_signals(bytes([255])*(WIDTH*HEIGHT),dark)
    assert white['temporal_difference']==1 and white['overexposure_candidate']
    signals=MediaSignals((),(),{},visual={'frames':[{'timestamp_seconds':0,**first},{'timestamp_seconds':.5,**second}]})
    scenes=build_scenes(duration=1,signals=signals,transcript=None)
    assert scenes[0]['subjects']==[] and not scenes[0]['evidence']['subjects_available']
    assert scenes[0]['evidence']['local_metrics']['motion_score']==0
    assert scenes[0]['quality_score']==0


def test_missing_motion_energy_quality_remain_null_in_explained_highlight_factors():
    scenes=build_scenes(duration=2,signals=MediaSignals((),(),{}),transcript=None)
    result=build_highlights(scenes=scenes,top_k=3)[0]
    evidence=result['evidence']
    assert evidence['factors']['motion'] is None and evidence['factors']['audio_energy'] is None
    assert evidence['factors']['quality'] is None and not evidence['vision_used']
    assert 'motion' in evidence['missing_factors']
    assert sum(evidence['contributions'].values())==pytest.approx(result['highlight_score'],abs=1e-5)
    assert 'scene motion' not in result['reason']


@pytest.mark.asyncio
async def test_local_decoder_finds_real_cut_and_bounds_measurement_without_audio(tmp_path):
    executable=shutil.which('ffmpeg')
    if not executable:pytest.skip('local FFmpeg unavailable')
    source=tmp_path/'synthetic.mp4'
    subprocess.run([executable,'-v','error','-nostdin','-f','lavfi','-i','color=black:s=320x240:r=30:d=2',
        '-f','lavfi','-i','testsrc2=s=320x240:r=30:d=2','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
        '-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
    metadata=MediaMetadata(media_kind='video',detected_content_type='video/mp4',duration_seconds=4,width=320,height=240,video_codec='h264')
    result=await FFmpegMediaSignalProvider().analyze(source,metadata=metadata,silence_threshold_db=-35,minimum_silence_duration=.3)
    assert result.waveform is None and result.visual['measured'] and not result.visual['semantic_vision']
    assert 1<=len(result.visual['frames'])<=360
    assert result.visual['frames'][0]['black_frame'] and not result.visual['frames'][-1]['black_frame']
    assert any(abs(time-2)<.1 and .35<score<=1 for time,score in result.shot_boundaries)
    scenes=build_scenes(duration=4,signals=result,transcript=None)
    assert len(scenes)>=2 and scenes[0]['quality_score']<scenes[-1]['quality_score']
    limited=await measure_visual_signals(source,executable=executable,duration_seconds=4,maximum_frames=3)
    assert len(limited['frames'])<=3 and limited['sampling_fps']==.75


@pytest.mark.asyncio
async def test_failed_local_stage_cancels_siblings_before_source_cleanup():
    cancelled=asyncio.Event()
    async def slow():
        try:await asyncio.sleep(10)
        finally:cancelled.set()
    async def fail():raise ValueError('fixture failure')
    with pytest.raises(ValueError):await FFmpegMediaSignalProvider._gather(slow(),fail())
    assert cancelled.is_set()

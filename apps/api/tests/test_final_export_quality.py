"""Measured tail failures cannot hide behind a low whole-file silence ratio."""
import asyncio
import math
import shutil
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app import production_qc as module


@pytest.mark.asyncio
@pytest.mark.parametrize('events,tail,total', [
    ('silence_start: 9\nsilence_end: 12 | silence_duration: 3', 3, 3),
    ('silence_start: 9', 3, 3),
    ('silence_start: 1\nsilence_end: 2\nsilence_start: 9\nsilence_end: 12', 3, 4),
    ('silence_start: 1\nsilence_end: 2', 0, 1),
    ('', 0, 0),
    ('silence_start: 0\nsilence_end: 12.01', 12, 12),
])
async def test_tail_measurement_including_unclosed_interval(monkeypatch, tmp_path, events, tail, total):
    monkeypatch.setattr(module, '_run', AsyncMock(return_value=('', events)))
    value = await module.FullProductionQC()._silence(tmp_path/'output.mp4', 12)
    assert value['trailing_silence_seconds'] == tail
    assert value['silence_seconds'] == total


@pytest.mark.asyncio
@pytest.mark.parametrize('tail,passes', [(0, True), (2, True), (2.001, False), (3, False), (None, False), (math.nan, False)])
async def test_full_qc_default_gate_is_two_seconds_and_requires_measurement(monkeypatch, tmp_path, tail, passes):
    path = tmp_path/'contract-only-not-playable.mp4'; path.write_bytes(b'x'*10001)
    qc = module.FullProductionQC()
    values = {
        '_probe': {'streams': [
            {'codec_type':'video','codec_name':'h264','width':1080,'height':1920,'avg_frame_rate':'30/1','duration':'12'},
            {'codec_type':'audio','codec_name':'aac','sample_rate':'48000','duration':'12'}], 'format':{'duration':'12'}},
        '_black': {'black_frame_ratio':0}, '_freeze': {'freeze_frame_seconds':0,'freeze_intervals':[]},
        '_volume': {'audio_mean_db':-20,'audio_peak_db':-6,'audio_clipping':False},
        '_silence': {'silence_ratio':.25,'trailing_silence_seconds':tail},
        '_vision_samples': {'dark_visual_sample_ratio':0}, '_decode': {'broken_frames':0}}
    for method,value in values.items(): monkeypatch.setattr(qc,method,AsyncMock(return_value=value))
    args = dict(expected_duration=12,expected_width=1080,expected_height=1920,expected_fps=30,
        subtitle_qc={'status':'passed'},timeline_qc={'status':'passed'})
    if passes:
        assert (await qc.inspect(path,**args))['status']=='passed'
    else:
        with pytest.raises(module.ProductionQCError, match='trailing audio silence'):
            await qc.inspect(path,**args)


@pytest.mark.parametrize('threshold', [True, -1, 11, math.nan, math.inf])
def test_threshold_cannot_silently_disable_gate(threshold):
    with pytest.raises(ValueError): module.FullProductionQC(max_trailing_silence_seconds=threshold)


@pytest.mark.asyncio
async def test_actual_encoded_aac_three_second_tail_fails_full_qc(tmp_path):
    executable = shutil.which('ffmpeg')
    if executable is None:
        from services.windows_native.pipeline import Config
        executable = str(Config().ffmpeg_bin/'ffmpeg.exe')
    if not Path(executable).is_file(): pytest.skip('FFmpeg unavailable')
    probe = str(Path(executable).with_name('ffprobe.exe' if executable.endswith('.exe') else 'ffprobe'))
    path = tmp_path/'actual-moving-test-pattern-and-tone.mp4'
    process = await asyncio.create_subprocess_exec(executable,'-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=30',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=9','-af','apad=whole_dur=12',
        '-t','12','-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p','-c:a','aac',str(path))
    assert await process.wait()==0
    with pytest.raises(module.ProductionQCError,match='trailing audio silence') as error:
        await module.FullProductionQC(ffmpeg_path=executable,ffprobe_path=probe).inspect(path,
            expected_duration=12,expected_width=320,expected_height=240,expected_fps=30,
            subtitle_qc={'status':'passed'},timeline_qc={'status':'passed'})
    report=error.value.report
    assert 2.9 < report['trailing_silence_seconds'] < 3.1
    assert report['silence_ratio'] < .3
    assert report['failures']==['trailing audio silence exceeds the configured threshold']

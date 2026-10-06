"""Explicit silent timelines keep visual QC; aborted tools are killed and reaped."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app import production_qc as module


@pytest.mark.asyncio
async def test_silent_volume_is_json_null_without_nonfinite_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(module, '_run', AsyncMock(return_value=(
        '', 'mean_volume: -inf dB\nmax_volume: -inf dB')))
    value=await module.FullProductionQC()._volume(tmp_path/'silent.mp4')
    assert value=={'audio_mean_db':None,'audio_peak_db':None,'audio_clipping':False}
    json.dumps(value, allow_nan=False)


@pytest.mark.asyncio
async def test_only_explicit_silent_plan_can_pass_audio_and_still_requires_visual_qc(monkeypatch, tmp_path):
    path=tmp_path/'contract-only-not-playable.mp4';path.write_bytes(b'x'*10001)
    qc=module.FullProductionQC()
    measurements={
        '_probe':{'streams':[
            {'codec_type':'video','codec_name':'h264','width':1080,'height':1920,'avg_frame_rate':'30/1','duration':'3'},
            {'codec_type':'audio','codec_name':'aac','sample_rate':'48000','duration':'3'}], 'format':{'duration':'3'}},
        '_black':{'black_frame_ratio':0},
        '_freeze':{'freeze_frame_seconds':0,'freeze_intervals':[]},
        '_volume':{'audio_mean_db':None,'audio_peak_db':None,'audio_clipping':False},
        '_silence':{'silence_ratio':1},
        '_vision_samples':{'dark_visual_sample_ratio':0},
        '_decode':{'broken_frames':0}}
    for method,value in measurements.items():monkeypatch.setattr(qc,method,AsyncMock(return_value=value))
    args=dict(expected_duration=3,expected_width=1080,expected_height=1920,expected_fps=30,
        subtitle_qc={'status':'passed'},timeline_qc={'status':'passed'})
    with pytest.raises(module.ProductionQCError,match='effectively silent'):
        await qc.inspect(path,**args)
    args['timeline_qc']['intentional_audio_silence']=True
    report=await qc.inspect(path,**args)
    assert report['status']=='passed' and report['intentional_audio_silence'] is True
    json.dumps(report,allow_nan=False)
    monkeypatch.setattr(qc,'_black',AsyncMock(return_value={'black_frame_ratio':1}))
    with pytest.raises(module.ProductionQCError,match='black-frame'):
        await qc.inspect(path,**args)


@pytest.mark.asyncio
async def test_cancellation_kills_and_drains_owned_qc_child(monkeypatch):
    class Process:
        returncode=None
        killed=False
        drained=False
        def __init__(self):self.entered=asyncio.Event();self.done=asyncio.Event()
        async def communicate(self):
            self.entered.set();await self.done.wait();self.drained=True
            return b'',b''
        def kill(self):self.killed=True;self.returncode=-9;self.done.set()
    process=Process()
    monkeypatch.setattr(module.asyncio,'create_subprocess_exec',AsyncMock(return_value=process))
    task=asyncio.create_task(module._run(['explicit-mock-qc-tool'],'fixture'))
    await asyncio.wait_for(process.entered.wait(),2);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert process.killed and process.drained and process.returncode==-9

import test from 'node:test';
import assert from 'node:assert/strict';
import {waveformPath} from '../waveform.mjs';
const bins=[{start_seconds:0,end_seconds:1,peak:0},{start_seconds:1,end_seconds:2,peak:.5},{start_seconds:2,end_seconds:3,peak:1}];
const clip={source_start:0,source_end:3,duration:3,metadata:{source_audio_waveform:{measured:true,method:'ffmpeg-mono-pcm-peak-rms-v1',bins}}};
test('Waveform is measured, source-relative and follows edits without invented amplitudes',()=>{
  assert.equal(waveformPath(clip),'M16.667 50.000V50.000 M50.000 28.000V72.000 M83.333 6.000V94.000');
  assert.equal(waveformPath({...clip,source_start:1,source_end:2,speed:2,duration:.5,timeline_start:30}),'M50.000 28.000V72.000');
  assert.equal(waveformPath({...clip,metadata:{}}),null);
  assert.equal(waveformPath({...clip,metadata:{source_audio_waveform:{measured:false,bins}}}),null);
});

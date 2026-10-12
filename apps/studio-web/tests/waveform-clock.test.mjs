import test from 'node:test';
import assert from 'node:assert/strict';
import {waveformPath} from '../waveform.mjs';
test('v2 measured waveform retains source offset and legacy v1 still renders',()=>{
  const clip={duration:2,source_start:0,metadata:{source_audio_waveform:{measured:true,method:'ffmpeg-mono-pcm-peak-rms-v2',
    bins:[{start_seconds:.5,end_seconds:.6,peak:.5}]}}};
  assert.match(waveformPath(clip),/^M27\.500 /);
  clip.source_start=.5;assert.match(waveformPath(clip),/^M2\.500 /);
  clip.metadata.source_audio_waveform.method='ffmpeg-mono-pcm-peak-rms-v1';assert.ok(waveformPath(clip));
  clip.metadata.source_audio_waveform.method='unmeasured';assert.equal(waveformPath(clip),null);
});

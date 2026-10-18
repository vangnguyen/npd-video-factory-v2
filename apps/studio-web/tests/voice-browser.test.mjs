import test from 'node:test';import assert from 'node:assert/strict';
import {usableVoice,voiceDescription,auditionUrl} from '../voice-browser.mjs';
test('Voice labels use installed metadata only, and unknown rights are never ready',()=>{
  assert.equal(voiceDescription({display_name:'Tên bất kỳ'}),'Chưa phân loại chất giọng');
  assert.equal(voiceDescription({metadata:{description:'Nữ · Bắc · Phong cách tự nhiên'}}),'Nữ · Bắc · Phong cách tự nhiên');
  assert.equal(usableVoice({definition:{rights_status:'source_licensed'}}),true);assert.equal(usableVoice({definition:{rights_status:'unknown'}}),false);
});
test('Audition audio must be a scoped local result, never mock or remote audio',()=>{
  assert.equal(auditionUrl('/api/voice-auditions/nsample_'+'a'.repeat(32)+'/audio'),'/api/voice-auditions/nsample_'+'a'.repeat(32)+'/audio');
  for(const url of ['data:audio/wav;base64,AAAA','https://example.com/sample.wav','/api/voice-auditions/../../file','/api/voice-auditions/nsample_bad/audio'])assert.equal(auditionUrl(url),null);
});

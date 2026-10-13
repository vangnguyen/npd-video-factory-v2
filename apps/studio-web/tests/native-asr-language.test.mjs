import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {asrLanguageChoices,asrLanguageSelection,asrLanguageHint} from '../native-asr-language.mjs';

test('legacy and capability-absent calls preserve old identity while explicit choices bind new requests',()=>{
  assert.deepEqual(asrLanguageSelection('legacy',true),{request:undefined,keySuffix:''});
  assert.deepEqual(asrLanguageSelection('en',false),{request:undefined,keySuffix:''});
  for(const language of ['vi','en','auto'])assert.deepEqual(asrLanguageSelection(language,true),{request:{language},keySuffix:`-studio-${language}-v1`});
  assert.throws(()=>asrLanguageSelection('fr',true));assert.throws(()=>asrLanguageSelection({language:'en'},true));
});
test('UI names actual external speech operation and preserves saved transcript scope',()=>{
  assert.equal(asrLanguageChoices.length,11);assert.ok(Object.isFrozen(asrLanguageChoices));
  for(const value of ['legacy','vi','en','auto'])assert.match(asrLanguageHint(value),/AssemblyAI.*có thể phát sinh phí/);
  assert.match(asrLanguageHint('auto'),/phát hiện ngôn ngữ/);assert.match(asrLanguageHint('en'),/tiếng Anh/);
  assert.match(asrLanguageHint('vi'),/kết quả đã lưu được giữ nguyên/);
});
test('local CPU choices require configured capability and never select a remote fallback',()=>{
  for(const language of ['vi','en','auto']){
    assert.throws(()=>asrLanguageSelection('local-'+language,true,false));
    assert.deepEqual(asrLanguageSelection('local-'+language,true,true),{
      request:{language,provider:'local-whisper'},keySuffix:`-local-${language}-v1`});
    assert.match(asrLanguageHint('local-'+language),/không được gửi.*không có phí API/);
  }
});
test('small CPU choices have explicit model identity, separate capability and bounded cost guidance',()=>{
  for(const language of ['vi','en','auto']){
    assert.throws(()=>asrLanguageSelection('local-small-'+language,true,true,false));
    assert.deepEqual(asrLanguageSelection('local-small-'+language,true,false,true),{
      request:{language,provider:'local-whisper',model_key:'small'},keySuffix:`-local-small-${language}-v2`});
    assert.match(asrLanguageHint('local-small-'+language),/nhiều bộ nhớ và thời gian/);
    assert.notEqual(asrLanguageSelection('local-'+language,true,true).keySuffix,
      asrLanguageSelection('local-small-'+language,true,true,true).keySuffix);
  }
});
test('Vietnamese specialized choice is separate, configured explicitly and never claims verified timing',()=>{
  assert.throws(()=>asrLanguageSelection('local-pho-vi',true,true,true,false));
  assert.deepEqual(asrLanguageSelection('local-pho-vi',true,false,false,true),{
    request:{language:'vi',provider:'local-whisper',model_key:'phowhisper-small'},keySuffix:'-local-phowhisper-vi-v2'});
  assert.match(asrLanguageHint('local-pho-vi'),/ước lượng.*Kiểm tra transcript/);
});
test('shipped handler includes language in stored retry identity and does not create a separate ASR timeline',async()=>{
  const source=await readFile(new URL('../native.mjs',import.meta.url),'utf8');
  assert.match(source,/kind==='asr'\?asrLanguageSelection/);assert.match(source,/kind\}\$\{selection.keySuffix\}/);
  assert.match(source,/asr_request:selection.request/);
  const html=await readFile(new URL('../native.html',import.meta.url),'utf8');
  assert.match(html,/id="asr-language-label" hidden/);for(const c of asrLanguageChoices)assert.ok(html.includes(`value="${c.value}"`));
});

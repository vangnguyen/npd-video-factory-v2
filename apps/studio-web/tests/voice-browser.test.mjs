import test from 'node:test';import assert from 'node:assert/strict';
import {usableVoice,voiceDescription,auditionUrl,initializeVoiceBrowser} from '../voice-browser.mjs';
test('Voice labels use installed metadata only, and unknown rights are never ready',()=>{
  assert.equal(voiceDescription({display_name:'Tên bất kỳ'}),'Chưa phân loại chất giọng');
  assert.equal(voiceDescription({metadata:{description:'Nữ · Bắc · Phong cách tự nhiên'}}),'Nữ · Bắc · Phong cách tự nhiên');
  assert.equal(usableVoice({definition:{rights_status:'source_licensed'}}),true);assert.equal(usableVoice({definition:{rights_status:'unknown'}}),false);
});
test('Audition audio must be a scoped local result, never mock or remote audio',()=>{
  assert.equal(auditionUrl('/api/voice-auditions/nsample_'+'a'.repeat(32)+'/audio'),'/api/voice-auditions/nsample_'+'a'.repeat(32)+'/audio');
  for(const url of ['data:audio/wav;base64,AAAA','https://example.com/sample.wav','/api/voice-auditions/../../file','/api/voice-auditions/nsample_bad/audio'])assert.equal(auditionUrl(url),null);
});
// Playback is a DOM contract fixture. No actual audio is generated or used as provider evidence.
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.listeners={};this.textContent='';this.paused=true;this.src='';}
  append(n){this.children.push(n);}replaceChildren(){this.children=[];}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,fn){this.listeners[k]=fn;}
  pause(){this.paused=true;}play(){this.paused=false;this.listeners.play?.();return Promise.resolve();}
  all(){return this.children.flatMap(v=>[v,...v.all()]);}querySelectorAll(selector){return this.all().filter(v=>selector==='audio[data-voice-audition]'?v.tagName==='audio'&&'data-voice-audition' in v.attrs:v.tagName===selector);}
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function voiceFixture(){const dom=new Element('document');dom.createElement=tag=>new Element(tag);const root=new Element('section');dom.append(root);const voices=['a','b'].map((key,i)=>({voice_id:'nvoice_'+key.repeat(32),version:1,definition:{display_name:'Explicit DOM fixture '+i,provider_voice_id:'fixture-'+i,rights_status:'source_licensed',locale:'vi-VN'}}));return {dom,root,voices,catalog:{voices:voices.map(v=>({provider_voice_id:v.definition.provider_voice_id,installed:true,metadata:{description:'Explicit metadata fixture'}}))}};}
test('opening voice cards only reads and an explicit queued sample is not submitted twice',async t=>{
  const f=voiceFixture(),calls=[];let items=[];
  const api=async(path,options)=>{calls.push({path,options});if(options){const request=JSON.parse(options.body),sample={sample_id:'nsample_'+'c'.repeat(32),voice_id:request.voice_id,voice_version:1,kind:'sample',state:'queued',human_listening_accepted:false};items=[sample];return sample;}return {items,inference_dispatched:false};};
  const controller=initializeVoiceBrowser({...f,api});t.after(()=>controller.dispose());await tick();assert.equal(calls.filter(v=>v.options).length,0);
  const sample=f.root.querySelectorAll('button').find(v=>v.textContent==='Nghe mẫu');await sample.listeners.click();await sample.listeners.click();assert.equal(calls.filter(v=>v.options).length,1);assert.equal(JSON.parse(calls.find(v=>v.options).options.body).voice_id,f.voices[0].voice_id);assert.equal(sample.disabled,true);
});
test('only one cached audition plays and choosing a role does not record listening acceptance',async t=>{
  const f=voiceFixture(),chosen=[],calls=[],items=f.voices.map((v,i)=>({sample_id:'nsample_'+String(i+1).repeat(32),voice_id:v.voice_id,voice_version:1,kind:'sample',state:'ready',audio_url:'/api/voice-auditions/nsample_'+String(i+1).repeat(32)+'/audio',human_listening_accepted:false}));
  const controller=initializeVoiceBrowser({...f,api:async(...args)=>{calls.push(args);return {items,inference_dispatched:false};},getCharacter:()=>({name:'An',character_id:'fixture-role'}),onSelect:(voice,c)=>chosen.push([voice.voice_id,c.name])});t.after(()=>controller.dispose());await tick();
  const buttons=f.root.querySelectorAll('button').filter(v=>v.textContent==='Nghe mẫu'),audios=f.root.querySelectorAll('audio');await buttons[0].listeners.click();assert.equal(audios[0].paused,false);await buttons[1].listeners.click();assert.equal(audios[0].paused,true);assert.equal(audios[1].paused,false);
  f.root.querySelectorAll('button').find(v=>v.textContent==='Chọn cho An').listeners.click();assert.deepEqual(chosen,[[f.voices[0].voice_id,'An']]);assert.ok(items.every(v=>v.human_listening_accepted===false));assert.equal(calls.filter(v=>v[1]).length,0);
});
test('card order follows the installed catalog order so real featured presets are easy to find',async t=>{
  const f=voiceFixture();f.voices.reverse();const controller=initializeVoiceBrowser({...f,api:async()=>({items:[],inference_dispatched:false})});t.after(()=>controller.dispose());await tick();assert.equal(f.root.querySelectorAll('h3')[0].textContent,'Explicit DOM fixture 0');
});

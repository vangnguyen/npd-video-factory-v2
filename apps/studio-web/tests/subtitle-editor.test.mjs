import test from 'node:test';
import assert from 'node:assert/strict';
import {subtitleCueEdit,compatibleSubtitleTemplates,subtitleSaveStyle} from '../subtitle-editor.mjs';

test('Style edits retain exact measured alignment; text/time edits remove stale timestamps',()=>{
  const original={cue_id:'sub_one',text:'Cần Giờ',start_seconds:.123456,end_seconds:1.987654,
    words:[{text:'Cần',start_seconds:.123456,end_seconds:.5},{text:'Giờ',start_seconds:.6,end_seconds:1.987654}]};
  const values={cue_id:original.cue_id,text:original.text,start_seconds:original.start_seconds,end_seconds:original.end_seconds};
  const same=subtitleCueEdit(original,values);assert.deepEqual(same.words,original.words);
  same.words[0].text='changed copy';assert.equal(original.words[0].text,'Cần');
  assert.deepEqual(subtitleCueEdit(original,{...values,text:'Cần Giờ mới'}).words,[]);
  assert.deepEqual(subtitleCueEdit(original,{...values,start_seconds:.12}).words,[]);
  assert.deepEqual(subtitleCueEdit(original,{...values,text:original.text.normalize('NFD')}).words,original.words);
});

test('Templates disclose timing requirements and legacy style saves omit extensions',()=>{
  const catalog={templates:[{template_ref:'timed@v1',requires_word_timestamps:true},
    {template_ref:'sentence@v1',requires_word_timestamps:false}]};
  assert.deepEqual(compatibleSubtitleTemplates(catalog,[{words:[]}]).map(t=>t.disabled),[true,false]);
  assert.deepEqual(subtitleSaveStyle({animation:'none'},null,{font_size:48}),{animation:'none',font_size:48});
  const template={style:{template_ref:'karaoke-gold@v1',animation:'karaoke',font_size:48}};
  assert.equal(subtitleSaveStyle({animation:'none'},template,{font_size:52}).template_ref,'karaoke-gold@v1');
});

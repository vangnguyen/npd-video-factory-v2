import test from 'node:test';
import assert from 'node:assert/strict';
import {batchEntry,calendarGroups,visibleItems,escapeHtml} from '../production.mjs';
import {canApprovePreflight,initialResearchRun} from '../intelligence.mjs';

test('A human opening new content from a profile starts fresh while explicit run links remain authoritative',()=>{
  assert.equal(initialResearchRun(new URLSearchParams('profile=infrastructure-news'),'old-run'),null);
  assert.equal(initialResearchRun(new URLSearchParams('run=explicit-run&profile=infrastructure-news'),'old-run'),'explicit-run');
  assert.equal(initialResearchRun(new URLSearchParams(''),'old-run'),'old-run');
});

test('Phase10 brief approval needs exact current preflight and reasoned duplicate acknowledgment',()=>{
  const brief={id:'b',version:2},check={brief_id:'b',brief_version:2,human_override_required:true};
  assert.equal(canApprovePreflight(null,brief,true,'checked'),false);
  assert.equal(canApprovePreflight({...check,brief_version:1},brief,true,'checked'),false);
  assert.equal(canApprovePreflight(check,brief,false,'checked'),false);
  assert.equal(canApprovePreflight(check,brief,true,'   '),false);
  assert.equal(canApprovePreflight(check,brief,true,'Different target audience'),true);
  assert.equal(canApprovePreflight({...check,human_override_required:false},brief,false,''),true);
});

test('Explicit batch selections carry immutable content binding and local planning version',()=>{
  const first={id:'one',binding_sha256:'first-binding',planning:{version:7}},second={id:'two',binding_sha256:'second-binding',planning:{version:1}};
  assert.deepEqual([first,second].map(batchEntry),[{id:'one',planning_version:7,binding_sha256:'first-binding'},{id:'two',planning_version:1,binding_sha256:'second-binding'}]);
  assert.equal(escapeHtml('<img src=x onerror="alert(1)">').includes('<img'),false);
});

test('Planning calendar keeps undated work visible and never changes underlying content',()=>{
  const rows=[{id:'one',archived:false,profile_name:'Profile',planning:{planned_date:'2026-10-20',campaign:'Autumn',format:'9:16'}},
    {id:'two',archived:false,profile_name:'Profile',planning:{planned_date:null,campaign:'',format:'16:9'}},
    {id:'three',archived:false,profile_name:'Profile',planning:{planned_date:'2026-11-02',campaign:'Winter',format:'9:16'}}];
  const before=JSON.stringify(rows),groups=calendarGroups(rows,'date','2026-10');
  assert.deepEqual(new Set(groups.flatMap(([,items])=>items.map(r=>r.id))),new Set(['one','two']));
  assert.equal(JSON.stringify(rows),before);
});

test('Staff filters can retain archived projects explicitly without hiding current review stages',()=>{
  const base={title:'Tin hạ tầng',profile_name:'Infrastructure News',related_project:null,profile_id:'infrastructure-news',stage:'SCRIPT_REVIEW',planning:{campaign:'October'}};
  const rows=[{...base,id:'one',archived:false},{...base,id:'two',archived:true}];
  assert.deepEqual(visibleItems(rows,{search:'hạ tầng',stage:'SCRIPT_REVIEW'}).map(r=>r.id),['one']);
  assert.deepEqual(visibleItems(rows,{archived:true,profile:'infrastructure-news'}).map(r=>r.id),['one','two']);
});

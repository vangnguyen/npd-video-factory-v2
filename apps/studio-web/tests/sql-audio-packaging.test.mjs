import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,stat} from 'node:fs/promises';

test('SQL Studio deployment copies all direct ES modules and permits verified local audio playback',async()=>{
  const root=new URL('../',import.meta.url);
  const [script,docker,nginx]=await Promise.all(['studio.js','Dockerfile','nginx.conf'].map(p=>readFile(new URL(p,root),'utf8')));
  const modules=[...script.matchAll(/from\s+["']\/([^"'?]+\.mjs)(?:\?[^"']*)?["']/g)].map(m=>m[1]);
  assert.ok(modules.includes('uploaded-audio-review.mjs'));
  assert.match(docker,/^COPY \*\.mjs \/usr\/share\/nginx\/html\//m);
  for(const name of modules)assert.ok((await stat(new URL(name,root))).isFile(),name);
  assert.match(nginx,/media-src 'self' blob:/);
  assert.match(nginx,/location ~ \\.mjs\$/);
  assert.match(nginx,/default_type application\/javascript/);
});

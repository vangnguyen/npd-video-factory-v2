import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {digestNativeFile,FILE_HASH_CHUNK_BYTES} from '../native-file-sha256.mjs';
const expected=bytes=>createHash('sha256').update(bytes).digest('hex');
function file(bytes,{onRead=()=>{},short=false}={}){
  return {size:bytes.byteLength,arrayBuffer:()=>{throw Error('Whole-file allocation forbidden');},slice:(a,b)=>{
    assert.ok(b-a<=FILE_HASH_CHUNK_BYTES);return {arrayBuffer:async()=>{onRead(a,b);return bytes.slice(a,short?b-1:b).buffer;}};
  }};
}
test('SHA-256 known vectors and independent Node/WebCrypto outputs match',async()=>{
  for(const[text,sha]of[['','e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
    ['abc','ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
    ['a'.repeat(1000000),'cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0']]){
    const bytes=new TextEncoder().encode(text);assert.equal(await digestNativeFile(file(bytes)),sha);assert.equal(expected(bytes),sha);
    assert.equal(Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex'),sha);
  }
});
test('padding/block/chunk boundaries and non-text bytes match independent SHA-256',async()=>{
  for(const size of[1,7,55,56,57,63,64,65,119,120,127,128,129,511,512,513,FILE_HASH_CHUNK_BYTES-1,FILE_HASH_CHUNK_BYTES,FILE_HASH_CHUNK_BYTES+1,2*FILE_HASH_CHUNK_BYTES+123]){
    const bytes=Uint8Array.from({length:size},(_,i)=>(i*17+(i>>>9))&255);assert.equal(await digestNativeFile(file(bytes)),expected(bytes),String(size));
  }
});
test('large input reads at most one bounded slice and reports complete ordered progress',async()=>{
  const bytes=new Uint8Array(3*FILE_HASH_CHUNK_BYTES+19).fill(203),reads=[],progress=[];
  assert.equal(await digestNativeFile(file(bytes,{onRead:(a,b)=>reads.push([a,b])}),{onProgress:(done,total)=>progress.push([done,total])}),expected(bytes));
  assert.deepEqual(reads,[[0,FILE_HASH_CHUNK_BYTES],[FILE_HASH_CHUNK_BYTES,2*FILE_HASH_CHUNK_BYTES],[2*FILE_HASH_CHUNK_BYTES,3*FILE_HASH_CHUNK_BYTES],[3*FILE_HASH_CHUNK_BYTES,bytes.length]]);
  assert.equal(progress.at(-1)[0],bytes.length);assert.ok(progress.every(([done,total])=>total===bytes.length&&done<=total));
});
test('pause or changed scope abandons the digest before another read',async()=>{
  const bytes=new Uint8Array(2*FILE_HASH_CHUNK_BYTES+9);let current=true,reads=0;
  assert.equal(await digestNativeFile(file(bytes,{onRead:()=>reads++}),{isCurrent:()=>current,onProgress:()=>{current=false;}}),null);assert.equal(reads,1);
  assert.equal(await digestNativeFile(file(bytes,{onRead:()=>reads++}),{isCurrent:()=>false}),null);assert.equal(reads,1);
});
test('bad size, short slice, unreadable source and a changing byte count fail closed',async()=>{
  for(const size of[-1,NaN,1.5,251*FILE_HASH_CHUNK_BYTES])await assert.rejects(digestNativeFile({size,slice:()=>{throw Error('No read');}}));
  const bytes=new Uint8Array(10);await assert.rejects(digestNativeFile(file(bytes,{short:true})),/không đọc đủ/);
  await assert.rejects(digestNativeFile({size:1,slice:()=>({arrayBuffer:async()=>{throw Error('Source not readable');}})}),/not readable/);
  const changing=file(bytes);changing.slice=()=>({arrayBuffer:async()=>{changing.size=11;return bytes.buffer;}});await assert.rejects(digestNativeFile(changing),/File đã thay đổi/);
});

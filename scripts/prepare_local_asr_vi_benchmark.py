"""Three fixed-order official FLEURS speech samples; bounded stream, no full archive."""
import argparse,csv,hashlib,io,json,tarfile,urllib.request
from pathlib import Path,PurePosixPath

REVISION='70bb2e84b976b7e960aa89f1c648e09c59f894dd'
BASE='https://huggingface.co/datasets/google/fleurs/resolve/'+REVISION+'/'
TSV='data/vi_vn/test.tsv';TSV_GIT_SHA='5e6d9d0bb2252181c78080eb80d5c0af09b5c42f'
ARCHIVE='data/vi_vn/audio/test.tar.gz'
ARCHIVE_SHA='b359261216ef14b8eea159abce794e270c2a0be903218cf1e1e8f7c7c1565b5c'

class LimitedStream:
    def __init__(self,stream,limit):self.stream=stream;self.limit=limit;self.bytes_read=0;self.sha=hashlib.sha256()
    def read(self,size=-1):
        if size<0:raise ValueError('BOUNDED_READ_REQUIRED')
        if self.bytes_read+size>self.limit:raise ValueError('BENCHMARK_STREAM_LIMIT')
        value=self.stream.read(size);self.bytes_read+=len(value);self.sha.update(value);return value

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
 out=Path(args.output).resolve();assert not out.exists();out.mkdir()
 with urllib.request.urlopen(BASE+TSV,timeout=30) as response:raw=response.read(1024*1024+1)
 assert len(raw)==613728
 assert hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==TSV_GIT_SHA
 rows=list(csv.reader(io.StringIO(raw.decode('utf-8')),delimiter='\t',quoting=csv.QUOTE_NONE))
 assert all(len(row)==7 for row in rows)
 by_name={row[1]:row for row in rows}
 samples=[]
 with urllib.request.urlopen(BASE+ARCHIVE,timeout=60) as response:
  stream=LimitedStream(response,8*1024*1024)
  with tarfile.open(fileobj=stream,mode='r|gz') as archive:
   for member in archive:
    if not member.isfile() or not member.name.endswith('.wav'):continue
    parts=PurePosixPath(member.name)
    assert not parts.is_absolute() and '..' not in parts.parts and 0<member.size<=4*1024*1024
    name=parts.name;assert name in by_name
    row=by_name[name];audio=archive.extractfile(member).read(member.size+1)
    assert len(audio)==member.size and audio[:4]==b'RIFF' and audio[8:12]==b'WAVE'
    filename=f'{len(samples):02d}.wav';(out/filename).write_bytes(audio)
    samples.append({'index':len(samples),'archive_member':member.name,'dataset_id':int(row[0]),
      'dataset_filename':name,'reference':row[3],'raw_reference':row[2],'num_samples':int(row[5]),
      'gender':row[6],'language_code':'vi_vn','filename':filename,'sha256':hashlib.sha256(audio).hexdigest(),
      'bytes':len(audio),'license':'CC-BY-4.0','attribution':'Google FLEURS dataset, Conneau et al., 2022',
      'source_reference':BASE+ARCHIVE+'#'+member.name,'original_audio_unchanged':True})
    if len(samples)==3:break
  assert len(samples)==3
  downloaded=stream.bytes_read;prefix_sha=stream.sha.hexdigest()
 receipt={'schema_version':'local-asr-vi-benchmark.v1','dataset':'google/fleurs','dataset_revision':REVISION,
  'dataset_source':'https://huggingface.co/datasets/google/fleurs','license':'CC-BY-4.0',
  'attribution':'Google FLEURS dataset, Conneau et al., FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech, 2022',
  'selection':'first_three_regular_wav_archive_members_in_order','selection_is_result_independent':True,
  'tsv_git_blob_verified':True,'tsv_git_blob_sha1':TSV_GIT_SHA,'tsv_sha256':hashlib.sha256(raw).hexdigest(),
  'archive_lfs_sha256':ARCHIVE_SHA,'archive_complete_hash_verified':False,'archive_stored':False,
  'archive_prefix_bytes_read':downloaded,'archive_prefix_sha256':prefix_sha,'samples':samples,
  'benchmark_only':True,'Owner_UAT':False,'full_Mode_B_accepted':False}
 (out/'manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'samples':3,'archive_bytes_read':downloaded,'archive_stored':False,'original_wav_bytes':sum(x['bytes'] for x in samples)}))

if __name__=='__main__':main()

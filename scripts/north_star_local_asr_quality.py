"""Same three licensed speech samples, two approved models, no reference prompts."""
import argparse,asyncio,json,subprocess,sys,time,wave
from pathlib import Path
from dataclasses import asdict
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'apps/api'),str(REPO)]
from app.local_asr_runtime import file_sha
from app.local_transcription_provider import LocalCpuTranscriptionProvider
from app.asr_reference_quality import assessment,aggregate
from app.auto_edit_models import MediaMetadata
from services.windows_native.pipeline import Config

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--benchmark',required=True)
 parser.add_argument('--runtime-manifest',required=True)
 parser.add_argument('--models',nargs='+',choices=['base','small'],default=['base','small'])
 args=parser.parse_args()
 out=Path(args.output).resolve();assert not out.exists();out.mkdir()
 benchmark=Path(args.benchmark).resolve();source=json.loads((benchmark/'manifest.json').read_bytes())
 assert source['selection_is_result_independent'] and source['license']=='CC-BY-4.0' and len(source['samples'])==3
 cases=[];by_model={key:[] for key in args.models}
 for item in source['samples']:
  original=benchmark/item['filename'];assert file_sha(original)==item['sha256']
  pcm=out/(str(item['index'])+'-pcm.wav')
  subprocess.run([str(Config().ffmpeg_bin/'ffmpeg.exe'),'-v','error','-i',str(original),'-ar','16000','-ac','1',
    '-c:a','pcm_s16le',str(pcm)],check=True,timeout=20)
  with wave.open(str(pcm),'rb') as audio:
   frames=audio.getnframes();assert frames==item['num_samples'];duration=frames/16000.
  for key in by_model:
   provider=LocalCpuTranscriptionProvider(Path(args.runtime_manifest).resolve(),'vi',model_key=key)
   assert provider.profile['initial_prompt'] is None
   started=time.monotonic()
   value=await provider.transcribe(pcm,metadata=MediaMetadata(media_kind='audio',detected_content_type='audio/wav',
      duration_seconds=duration,audio_channels=1,audio_sample_rate=16000),checksum_sha256=file_sha(pcm))
   transcript=asdict(value);hypothesis=' '.join(s.text for s in value.segments)
   quality=assessment(item['reference'],hypothesis);by_model[key].append(quality)
   case={'sample_index':item['index'],'source_audio_sha256':item['sha256'],'model_key':key,
      'profile':provider.profile,'elapsed_seconds':time.monotonic()-started,'reference':item['reference'],
      'hypothesis':hypothesis,'assessment':quality,'raw_provider':provider.raw_result,'transcript':transcript,
      'reference_supplied_to_inference':False,'external_calls':0,'paid_calls':0}
   write(out/(str(item['index'])+'-'+key+'.json'),case);cases.append(case)
  assert file_sha(original)==item['sha256']
 scores={key:aggregate(values) for key,values in by_model.items()}
 report={'schema_version':'local-asr-reference-comparison.v1','benchmark_manifest_sha256':file_sha(benchmark/'manifest.json'),
   'dataset_source':source['dataset_source'],'dataset_revision':source['dataset_revision'],'license':source['license'],
   'attribution':source['attribution'],'samples':3,'actual_cpu_inferences':len(cases),'scores':scores,
   'small_lower_error_on_this_sample':scores['small']['token_edit_distance']<scores['base']['token_edit_distance'] if {'base','small'}<=set(scores) else None,
   'references_sent_to_model':False,'input_audio_unchanged':True,'forced_language_vi':True,
   'model_timestamps_not_reference_aligned':True,'proper_names_quality_accepted':False,'VI_quality_accepted':False,
   'genuine_user_footage_accepted':False,'Owner_UAT':False,'external_calls':0,'paid_calls':0,'full_Mode_A_B_accepted':False}
 write(out/'evidence.json',report)
 print(json.dumps({'samples':3,'actual_cpu_inferences':len(cases),'scores':scores,'small_lower_error':report['small_lower_error_on_this_sample']}))

if __name__=='__main__':asyncio.run(main())

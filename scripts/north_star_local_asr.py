"""Actual local CPU ASR/Native analysis evidence; no paid API or Owner acceptance."""
import argparse,copy,json,subprocess,sys,tempfile,time,uuid
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'apps/api'),str(REPO)]
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.media import ingest_media
from services.windows_native.server import Runner
from services.windows_native import auto_edit_analysis
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--runtime-manifest',required=True)
 p.add_argument('--vietnamese-wav',required=True);p.add_argument('--english-audio',required=True)
 args=p.parse_args();out=Path(args.output).resolve();assert not out.exists();out.mkdir()
 inputs=[('vi',Path(args.vietnamese_wav).resolve()),('en',Path(args.english_audio).resolve()),('auto',Path(args.english_audio).resolve())]
 before={str(source):file_sha(source) for language,source in inputs}
 with tempfile.TemporaryDirectory(prefix='vf-local-asr-real-') as temporary:
  root=Path(temporary)/'state';config=Config(data_root=root,local_asr_manifest=Path(args.runtime_manifest).resolve())
  store=Store(root);results=[]
  for language,source in inputs:
   folder=out/language;folder.mkdir();video=folder/'source.mp4'
   subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-f','lavfi','-i','color=c=navy:s=320x180:r=25',
    '-i',str(source),'-shortest','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-ar','48000',str(video)],check=True,timeout=30)
   project=store.create('Local CPU ASR '+language,'','media')
   asset=ingest_media(config,video,'video/mp4','local-asr-speech-'+language+'.mp4',rights_confirmed=True,illustration=False)
   assert asset['rights_status']=='unknown'
   project=store.append_media(project['id'],project['revision'],asset)
   job=store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex,
     asr_request={'language':language,'provider':'local-whisper'})
   started=time.monotonic();Runner(store,Pipeline(config)).run_one();saved=store.get_job(job['id'])
   write(folder/'asr-job.json',saved);assert saved['status']=='succeeded',saved.get('error')
   project=store.get(project['id']);original=copy.deepcopy(project['document']['media_analysis'])
   transcript=original[0]['transcript'];assert transcript['provenance']['local_inference'] and not transcript['provenance']['paid_call']
   assert saved['result']['provider_calls']==0 and saved['result']['local_model_inferences']==1
   analysis_job=store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex)
   Runner(store,Pipeline(config)).run_one();analysis_saved=store.get_job(analysis_job['id'])
   write(folder/'analysis-job.json',analysis_saved);assert analysis_saved['status']=='succeeded',analysis_saved.get('error')
   current=auto_edit_analysis.view(store,project['id']);analysis=current['analyses'][0]['analysis']
   assert analysis['transcript']['language']==('en' if language=='auto' else language)
   edit=auto_edit_analysis.edit_transcript(store,project['id'],current['revision'],analysis['analysis_id'],{
     'expected_version':analysis['transcript']['version'],
     'segments':[{'segment_id':s['segment_id'],'text':s['text']+' [CI review]'} for s in analysis['transcript']['segments']]})
   changed=edit['analyses'][0]['analysis']['transcript'];assert changed['version']==analysis['transcript']['version']+1
   assert store.get(project['id'])['document']['media_analysis']==original
   assert store.get(project['id'])['approval'] is None
   write(folder/'original-transcript.json',transcript);write(folder/'analysis.json',analysis)
   write(folder/'edited-transcript.json',changed);write(folder/'project.json',store.get(project['id']))
   raw_file=root/'jobs'/job['id']/'analysis'/asset['id']/'local-transcript.json'
   write(folder/'local-provider-receipt.json',json.loads(raw_file.read_bytes()))
   results.append({'language_request':language,'language_result':transcript['language'],'project_id':project['id'],
     'asr_job_id':job['id'],'analysis_job_id':analysis_job['id'],'actual_cpu_inference_seconds':time.monotonic()-started,
     'words':sum(len(s['words']) for s in transcript['segments']),'model_estimated_timing':True,
     'low_confidence_words':transcript['provenance']['low_confidence_word_count'],'human_review_required':True,
     'source_sha256':asset['sha256'],'original_transcript_unchanged':True,'versioned_ci_edit':True,
     'source_is_existing_local_TTS':language=='vi','source_is_public_software_benchmark':language!='vi',
     'visual_is_generated_fixture':True,'rights_status':'unknown','external_calls':0,'paid_calls':0})
  backup=out/'local-asr-state.zip';receipt=create_backup(config,backup);write(out/'backup.json',receipt)
  projects={item['project_id']:digest(store.get(item['project_id'])) for item in results}
  expected=out/'expected-projects.json';write(expected,projects)
  child_code='''import json,sys,tempfile
from pathlib import Path
from services.windows_native.backup import restore_backup
from services.windows_native.store import Store
from services.windows_native.contracts import digest
with tempfile.TemporaryDirectory(prefix="vf-local-asr-cold-") as tmp:
 root=Path(tmp)/"restore";restore_backup(Path(sys.argv[1]),root,expected_sha256=sys.argv[2]);store=Store(root)
 expected=json.loads(Path(sys.argv[3]).read_bytes());actual={p:digest(store.get(p)) for p in expected};assert actual==expected
 print(json.dumps({"projects":len(actual),"exact_fresh_process_restore":True,"provider_calls":0}))
'''
  child=subprocess.run([sys.executable,'-X','utf8','-c',child_code,str(backup),file_sha(backup),str(expected)],
    capture_output=True,text=True,timeout=60)
  if child.returncode:raise RuntimeError(child.stderr[-1600:])
  restore=json.loads(child.stdout.strip().splitlines()[-1]);write(out/'fresh-process-restore.json',restore)
 assert all(file_sha(Path(name))==sha for name,sha in before.items())
 report={'schema_version':'north-star-local-cpu-asr-real-v1','cases':results,'input_hashes':before,
  'original_inputs_unchanged':True,'actual_local_cpu_inferences':3,'external_calls':0,'paid_calls':0,
  'separate_process_restore':restore,'owned_temporary_roots_cleaned':True,'model_weights_in_backup':False,
  'VI_quality_accepted':False,'genuine_user_uploaded_footage_accepted':False,'Owner_UAT':False,
  'full_Mode_A_B_accepted':False,'production_deployed':False}
 write(out/'evidence.json',report);print(json.dumps({'cases':3,'local_inferences':3,'external_calls':0,
  'words':[item['words'] for item in results],'exact_restore':True,'VI_quality_accepted':False,'full_Mode_A_B_accepted':False}))

if __name__=='__main__':main()

"""Real local synthetic PCM; saved transcript and reviews remain fixtures."""
import copy,json,os,subprocess,sys,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch
from services.windows_native import source_render,source_audio_cache as cache
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.source_variants import SourceVariants,Create
from services.windows_native.tests import test_source_preview as fixture
from app.timeline_models import TimelineSnapshot
from app.timeline_audio_processing import build_processed_audio_graph
from services.windows_native.source_preview import resolve_assets

class SourceAudioCacheTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    real_source=fixture.NativeSourcePreviewTests.real_source
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis

    def prepare(self,project,name,event=None):
        directory=self.root/name;directory.mkdir()
        source_render.prepare_project(self.config,project,directory,'explicit-cache-'+name,event)
        return json.loads((directory/'audio-analysis.json').read_bytes()),directory/'media/mix.wav'

    def family(self):
        service=SourceVariants(self.store)
        value,_=service.create(self.project['id'],Create(revision=self.project['revision'],expected_version=self.project['shot_timeline']['version'],
            profile_refs=['youtube-landscape@1','tiktok-short@1'],request_key='explicit-cache-family-fixture-key'),actor='fixture-editor')
        return [self.store.get(item['project_id']) for item in value['result']['variants']]

    def test_real_pcm_family_and_master_reuse_keep_current_clip_ids_and_private_job_paths(self):
        source=self.real_source();before=self.store.get(self.project['id']);sha=file_sha(source)
        first,mix=self.prepare(self.project,'master');children=self.family()
        receipts=[self.prepare(child,'child-'+str(i)) for i,child in enumerate(children)]
        self.assertEqual(first['intermediate_cache']['status'],'built')
        for child,(value,path) in zip(children,receipts):
            self.assertEqual(value['intermediate_cache']['status'],'hit');self.assertEqual(file_sha(path),file_sha(mix))
            self.assertEqual(value['intermediate_cache']['key'],first['intermediate_cache']['key'])
            active={clip['clip_id'] for track in child['document']['canonical_timeline']['snapshot']['tracks'] if track['type']=='audio' for clip in track['clips'] if not clip['disabled']}
            self.assertEqual({clip['clip_id'] for clip in value['clips']},active)
            manifest=json.loads((path.parents[1]/'timeline-render.json').read_bytes())
            self.assertEqual(Path(manifest['audio']['mix_uri']),path);self.assertEqual(json.loads((path.parents[1]/'timeline.json').read_bytes()),child['document']['canonical_timeline'])
            self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(file_sha(source),sha)

    def test_real_audio_gain_change_misses_but_visual_only_edit_hits(self):
        self.real_source();first,_=self.prepare(self.project,'first');visual=copy.deepcopy(self.project)
        snap=visual['document']['canonical_timeline']['snapshot'];snap['width']=1080;snap['height']=1080;snap['aspect_ratio']='1:1'
        visual['document']['canonical_timeline']['sha256']=digest(snap)
        second,_=self.prepare(visual,'visual');self.assertEqual(second['intermediate_cache']['key'],first['intermediate_cache']['key']);self.assertEqual(second['intermediate_cache']['status'],'hit')
        changed=copy.deepcopy(self.project);track=next(track for track in changed['document']['canonical_timeline']['snapshot']['tracks'] if track['type']=='audio');track['clips'][0]['volume']=.2
        changed['document']['canonical_timeline']['sha256']=digest(changed['document']['canonical_timeline']['snapshot'])
        third,mix=self.prepare(changed,'changed');self.assertEqual(third['intermediate_cache']['status'],'built');self.assertNotEqual(third['intermediate_cache']['pcm']['sha256'],first['intermediate_cache']['pcm']['sha256'])

    def test_concurrent_requests_build_once_and_restart_reuses_verified_receipt(self):
        self.real_source();children=self.family();original=source_render.command_run;calls=[]
        def counted(command,*args,**kwargs):calls.append(command);return original(command,*args,**kwargs)
        with patch.object(source_render,'command_run',side_effect=counted),ThreadPoolExecutor(max_workers=2) as pool:
            values=list(pool.map(lambda item:self.prepare(item[1],'parallel-'+str(item[0])),enumerate(children)))
        self.assertEqual(len(calls),1);self.assertEqual(sorted(value['intermediate_cache']['status'] for value,_ in values),['built','hit'])
        with patch.object(source_render,'command_run',side_effect=AssertionError('Verified hit must not encode')):
            value,_=self.prepare(self.store.get(children[0]['id']),'restarted')
        self.assertEqual(value['intermediate_cache']['status'],'hit');self.assertEqual(cache._locks,{})

    def test_unregistered_copy_and_other_root_cannot_share_family_scope(self):
        self.real_source();children=self.family();family=cache.scope(self.root,children[0]);duplicate=self.store.duplicate(children[0]['id'],children[0]['revision'])
        self.assertNotEqual(cache.scope(self.root,duplicate),family)
        forged=copy.deepcopy(self.project);forged['document']['canonical_timeline']['snapshot']['metadata']['source_variant']=children[0]['document']['canonical_timeline']['snapshot']['metadata']['source_variant']
        with self.assertRaisesRegex(WorkflowError,'FAMILY_INVALID'):cache.scope(self.root,forged)
        first,_=self.prepare(children[0],'family');second,_=self.prepare(duplicate,'duplicate');self.assertEqual(second['intermediate_cache']['status'],'built');self.assertNotEqual(first['intermediate_cache']['key'],second['intermediate_cache']['key'])
        other=self.root/'other-workspace';other.mkdir();self.assertNotEqual(cache.scope(other,self.project)['data_root_sha256'],family['data_root_sha256'])
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':'wsp_other_fixture'}))
        with self.assertRaisesRegex(WorkflowError,'FAMILY_INVALID'):cache.scope(self.root,children[0])

    def test_corrupt_cache_and_receipt_fail_closed_without_overwriting_evidence(self):
        self.real_source();first,_=self.prepare(self.project,'first');entry=self.root/'cache'/cache.ALGORITHM/first['intermediate_cache']['key']/'ready'
        receipt=json.loads((entry/'receipt.json').read_bytes());receipt['pcm']['sha256']='a'*64;receipt['receipt_sha256']=digest({key:value for key,value in receipt.items() if key!='receipt_sha256'})
        (entry/'receipt.json').write_text(json.dumps(receipt));preserved=file_sha(entry/'receipt.json')
        with patch.object(source_render,'command_run',side_effect=AssertionError('Corruption never rebuilds accepted entry')),self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.prepare(self.project,'bad-receipt')
        self.assertEqual(file_sha(entry/'receipt.json'),preserved)
        (entry/'mix.wav').write_bytes(b'EXPLICIT ISOLATED PCM CORRUPTION')
        with self.assertRaisesRegex(WorkflowError,'PCM_INVALID'):self.prepare(self.project,'bad-pcm')

    def test_linked_cache_path_and_changed_current_source_reject_even_when_cached(self):
        source=self.real_source();first,_=self.prepare(self.project,'first');entry=self.root/'cache'/cache.ALGORITHM/first['intermediate_cache']['key']/'ready';linked=self.root/'explicit-hardlink.wav'
        os.link(entry/'mix.wav',linked)
        with self.assertRaisesRegex(WorkflowError,'LINKED_PATH_REJECTED'):self.prepare(self.project,'linked')
        linked.unlink();source.write_bytes(b'EXPLICIT ISOLATED SOURCE CORRUPTION')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED'):self.prepare(self.project,'source-changed')

    def test_cancellation_and_failed_build_never_commit_or_copy_a_ready_mix(self):
        self.real_source();event=threading.Event();event.set()
        with self.assertRaisesRegex(WorkflowError,'PREVIEW_CANCELLED'):self.prepare(self.project,'cancelled',event)
        with patch.object(source_render,'command_run',side_effect=WorkflowError('EXPLICIT_BUILD_FAILURE')),self.assertRaisesRegex(WorkflowError,'BUILD_FAILURE'):self.prepare(self.project,'failed')
        self.assertFalse(list((self.root/'cache').rglob('ready')));self.assertFalse((self.root/'failed/media/mix.wav').exists())
        value,_=self.prepare(self.project,'retried');self.assertEqual(value['intermediate_cache']['status'],'built')

    def test_fingerprint_includes_full_filter_source_duration_and_ffmpeg_identity(self):
        self.real_source();snapshot,assets=resolve_assets(self.config,self.project);audio=build_processed_audio_graph(snapshot,assets,first_input_index=0);binding=cache.scope(self.root,self.project)
        def key(graph=audio,duration=snapshot.duration_seconds,executable=self.config.ffmpeg_bin/'ffmpeg.exe'):
            return digest(cache.fingerprint(binding,graph,assets,duration,executable))
        original=key();modified=copy.deepcopy(audio);modified.filters.append('[outa]volume=0.5[changed]');self.assertNotEqual(key(modified),original)
        self.assertNotEqual(key(duration=snapshot.duration_seconds+.01),original)
        binary=self.root/'explicit-identity-fixture.exe';binary.write_bytes(b'EXPLICIT NONEXECUTABLE TOOL IDENTITY');self.assertNotEqual(key(executable=binary),original)
        asset=next(iter(assets.values()))[0];asset.checksum_sha256='b'*64;self.assertNotEqual(key(),original)

    def test_capacity_bypasses_without_eviction_or_shared_approval(self):
        self.real_source()
        with patch.object(cache,'MAX_ENTRIES',0):value,mix=self.prepare(self.project,'bounded')
        self.assertEqual(value['intermediate_cache']['status'],'bypass_capacity');self.assertTrue(mix.is_file());self.assertFalse(list((self.root/'cache').rglob('ready')))
        self.assertIsNone(self.store.get(self.project['id'])['approval'])

    def test_two_processes_share_one_atomic_commit(self):
        code='''import json,sys,time,wave
from pathlib import Path
from services.windows_native.source_audio_cache import materialize
root=Path(sys.argv[1]);target=root/('process-'+sys.argv[2]+'.wav')
def build(path):
    with (root/'explicit-build-count.log').open('a') as file:file.write('build\\n')
    time.sleep(.2)
    with wave.open(str(path),'wb') as output:
        output.setnchannels(2);output.setsampwidth(2);output.setframerate(48000);output.writeframes(b'\\x01\\x00'*2*4800)
value=materialize(root,{'duration_seconds':.1,'scope':{'explicit_process_fixture':True}},target,build)
print(json.dumps(value))
'''
        children=[subprocess.Popen([sys.executable,'-c',code,str(self.root),str(index)],cwd=Path(__file__).resolve().parents[3],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0) for index in range(2)]
        try:
            values=[]
            for child in children:
                out,error=child.communicate(timeout=30);self.assertEqual(child.returncode,0,error.decode());values.append(json.loads(out))
            self.assertEqual(sorted(value['status'] for value in values),['built','hit']);self.assertEqual((self.root/'explicit-build-count.log').read_text(),'build\n')
            self.assertEqual(file_sha(self.root/'process-0.wav'),file_sha(self.root/'process-1.wav'))
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.wait(timeout=5)

if __name__=='__main__':unittest.main()

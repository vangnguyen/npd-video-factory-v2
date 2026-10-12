"""Uploaded SFX retain canonical provenance in both modes; no providers or UAT."""
import copy,json,shutil,subprocess,unittest,uuid,wave
from pathlib import Path
from types import SimpleNamespace
from services.windows_native.tests import test_source_media_tracks as source,test_narrated_media_tracks as narrated,test_source_media_tracks_http as signed
from services.windows_native import source_media_tracks as media,auto_edit_timeline as timeline,narrated_timeline_editor as editor
from services.windows_native.source_media_track_origins import validate_timeline,verify_physical
from services.windows_native.source_assets import used_timeline_asset_ids
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.shot_adapter import validate_document

def signed_controller(case,asset):
    case.start_server()
    try:
        p=case.store.get(case.project['id']);context=case.owned/'owned-sfx-controller-context.json'
        context.write_text(json.dumps({'fixture_human':True,'origin':'http://127.0.0.1:'+str(case.server.server_port),
            'workspace_id':case.workspace,'project':{'id':p['id'],'revision':p['revision']},'cookie':case.cookie,'csrf':case.csrf,
            'sfx_asset_id':asset['id'],'sfx_asset_sha256':asset['sha256']}),encoding='utf-8')
        repo=Path(__file__).resolve().parents[3]
        result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_media_sfx_http_ui.mjs'),str(context)],capture_output=True,timeout=60)
        case.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        proof=json.loads(result.stdout);case.assertEqual(len(proof['requests']),2);case.assertEqual(proof['saved']['mutation']['asset_id'],asset['id'])
        case.assertFalse(proof['browser_rendered']);case.assertFalse(proof['owner_UAT']);case.assertEqual(proof['provider_calls'],0)
        current=case.store.get(p['id']);validate_document(current['document']);verify_physical(case.root,current['document'])
        return proof
    finally:case.stop_server()

class SourceSFXTests(unittest.TestCase):
    setUp=source.prepare
    def tearDown(self):self.temp.cleanup()
    binding=source.SourceMediaTracksTests.binding
    audio_body=source.SourceMediaTracksTests.audio_body
    start_server=signed.SourceMediaTracksHTTPTests.start_server
    stop_server=signed.SourceMediaTracksHTTPTests.stop_server
    def test_SFX_import_replay_edit_and_mute_keep_source_rights_and_original_tracks(self):
        before=self.store.get(self.project['id']);original=file_sha(self.root/'assets'/self.music['id'])
        body=self.audio_body(self.music,role='sfx',source_start=.1,source_end=.6,timeline_start=.5,volume=.2,fade_in_seconds=.05,fade_out_seconds=.05)
        receipt=media.add_audio(self.store,self.project['id'],body,actor_ref='owned-fixture-editor',config=self.config)
        current=self.store.get(self.project['id']);s=current['document']['canonical_timeline'];track=next(t for t in s['snapshot']['tracks'] if t['track_id']==receipt['track_id'])
        self.assertEqual(track['kind'],'sfx');self.assertEqual(track['clips'][0]['kind'],'sfx');self.assertTrue(track['clips'][0]['metadata']['source_audio_waveform']['measured'])
        self.assertEqual(s['snapshot']['tracks'][:-1],before['document']['canonical_timeline']['snapshot']['tracks'])
        self.assertTrue(media.add_audio(self.store,current['id'],body,actor_ref='owned-fixture-editor',config=self.config)['replayed'])
        self.assertEqual(self.store.get(current['id']),current);self.assertEqual(verify_physical(self.root,current['document'])[self.music['id']],original)
        self.assertIn(self.music['id'],used_timeline_asset_ids(s['snapshot']))
        from app.publishing_logic import validate_rights
        self.assertEqual(validate_rights([SimpleNamespace(asset_id=self.music['id'],provenance={'rights_status':'unknown','license':None})]).status,'failed')
        edited=timeline.edit(self.store,current['id'],current['revision'],{'expected_version':s['version'],'operations':[
            {'type':'move','clip_id':receipt['clip_ids'][0],'timeline_start':1},
            {'type':'set_track_state','track_id':receipt['track_id'],'muted':True}]})
        validate_timeline(edited['document']);self.assertNotIn(self.music['id'],verify_physical(self.root,edited['document']))
        restored=timeline.restore(self.store,current['id'],edited['revision'],{'expected_version':edited['document']['canonical_timeline']['version'],'restore_revision':current['revision']})
        self.assertEqual(restored['document']['canonical_timeline']['sha256'],s['sha256']);self.assertIsNone(restored['approval']);self.assertEqual(file_sha(self.root/'assets'/self.music['id']),original)
    def test_SFX_repetition_captions_stale_SHA_and_wrong_track_do_not_mutate(self):
        body=self.audio_body(self.music,role='sfx',source_end=.5);before=self.store.get(self.project['id'])
        for extra in [{'repeat_until':2},{'crossfade_seconds':.1},{'timeline_sha256':'a'*64},
            {'captions':{'transcript_id':'trn_'+'a'*24,'analysis_sha256':'a'*64,'subtitle_template_ref':'sentence-clean@v1'}}]:
            with self.assertRaises(WorkflowError):media.add_audio(self.store,self.project['id'],{**body,**extra},actor_ref='owned-fixture-editor',config=self.config)
            self.assertEqual(self.store.get(self.project['id']),before)
        voice=media.add_audio(self.store,self.project['id'],self.audio_body(),actor_ref='owned-fixture-editor',config=self.config)
        before=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'TRACK_NOT_FOUND'):
            media.add_audio(self.store,self.project['id'],self.audio_body(self.music,role='sfx',source_end=.5,track_id=voice['track_id']),actor_ref='owned-fixture-editor',config=self.config)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_import_role_cannot_be_reclassified_without_immutable_source_decision(self):
        receipt=media.add_audio(self.store,self.project['id'],self.audio_body(self.music,role='sfx',source_end=.5),actor_ref='owned-fixture-editor',config=self.config)
        document=self.store.get(self.project['id'])['document']
        for target in ['track','clip']:
            changed=copy.deepcopy(document);track=next(t for t in changed['canonical_timeline']['snapshot']['tracks'] if t['track_id']==receipt['track_id'])
            if target=='track':track['kind']='music'
            else:track['clips'][0]['kind']='voice'
            with self.assertRaisesRegex(WorkflowError,'IMPORT_AUDIO_INVALID'):validate_timeline(changed)
    def test_actual_signed_Studio_imports_SFX_without_provider_or_browser_claim(self):
        self.assertEqual(signed_controller(self,self.music)['saved']['timeline_mode'],'source')

class NarratedSFXTests(unittest.TestCase):
    setUp=narrated.prepare
    def tearDown(self):self.temp.cleanup()
    start=narrated.NarratedMediaTracksTests.start
    finish=narrated.NarratedMediaTracksTests.finish
    body=narrated.NarratedMediaTracksTests.body
    binding=source.SourceMediaTracksTests.binding
    audio_body=source.SourceMediaTracksTests.audio_body
    start_server=signed.SourceMediaTracksHTTPTests.start_server
    stop_server=signed.SourceMediaTracksHTTPTests.stop_server
    def test_SFX_retains_measured_narration_preparation_and_canonical_edit_history(self):
        before=self.store.get(self.project['id']);voice_sha=file_sha(self.voice_out/'voice.wav')
        receipt=media.add_audio(self.store,self.project['id'],self.audio_body(self.music_asset,role='sfx',source_start=.1,source_end=.6,timeline_start=.5,volume=.2),actor_ref='owned-fixture-editor',config=self.config)
        current=self.store.get(self.project['id']);validate_document(current['document'])
        self.assertEqual(current['document']['prepared_narration'],before['document']['prepared_narration']);self.assertEqual(file_sha(self.voice_out/'voice.wav'),voice_sha)
        page=editor.view(self.store,current['id'],self.workspace)
        split=editor.edit(self.store,current['id'],{'revision':page['revision'],'expected_version':page['timeline_version'],'timeline_sha256':page['timeline_sha256'],
            'operations':[{'type':'split','clip_id':receipt['clip_ids'][0],'at_seconds':.75}]},self.workspace)
        pieces=next(t['clips'] for t in split['snapshot']['tracks'] if t['track_id']==receipt['track_id'])
        self.assertEqual(len(pieces),2);self.assertEqual(pieces[0]['source_end'],pieces[1]['source_start'])
        self.assertTrue(all(c['metadata']['native_media_import_id']==receipt['import_id'] for c in pieces))
        validate_document(self.store.get(current['id'])['document']);self.assertEqual(file_sha(self.voice_out/'voice.wav'),voice_sha)
    def test_actual_signed_Studio_imports_SFX_into_measured_Mode_A(self):
        self.assertEqual(signed_controller(self,self.music_asset)['saved']['timeline_mode'],'narrated')
    def test_actual_mixed_SFX_sample_clock_survives_voice_music_ducking(self):
        import numpy as np
        tone=self.owned/'owned-3000hz-SFX.wav'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i',
            'sine=frequency=3000:duration=1','-ar','48000','-ac','1','-c:a','pcm_s16le',str(tone)],check=True,capture_output=True,timeout=20)
        asset=source.upload(self,tone.read_bytes(),'audio','audio/wav')
        media.add_audio(self.store,self.project['id'],self.audio_body(self.music_asset,role='music',volume=.12,repeat_until=3.3,crossfade_seconds=.2),actor_ref='owned-fixture-editor',config=self.config)
        media.add_audio(self.store,self.project['id'],self.audio_body(asset,role='sfx',source_start=.1,source_end=.6,timeline_start=.9,volume=.3,fade_in_seconds=.05,fade_out_seconds=.05),actor_ref='owned-fixture-editor',config=self.config)
        directory=self.owned/'owned-SFX-mix';directory.mkdir();shutil.copyfile(self.voice_out/'voice.wav',directory/'placed-voice.wav')
        from services.windows_native.narrated_media_mix import prepare
        receipt=prepare(self.config,self.store.get(self.project['id'])['document'],directory,'placed-voice.wav',1)
        self.assertTrue(receipt['processing']['music_ducking'])
        with wave.open(str(directory/'narrated-mix.wav'),'rb') as wav:
            rate=wav.getframerate();samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').reshape(-1,wav.getnchannels()).mean(axis=1)/32768
        def band(start,end):
            x=samples[round(start*rate):round(end*rate)];window=np.hanning(len(x));spectrum=np.fft.rfft(x*window);freq=np.fft.rfftfreq(len(x),1/rate)
            return float(np.sqrt(2*np.sum(np.abs(spectrum[(freq>=2930)&(freq<=3070)])**2)/(len(x)*np.sum(window**2))))
        inside=band(1.05,1.25);outside=max(band(.2,.6),band(1.65,2.1))
        self.assertGreater(inside,.005);self.assertGreater(inside,outside*10+.0001)

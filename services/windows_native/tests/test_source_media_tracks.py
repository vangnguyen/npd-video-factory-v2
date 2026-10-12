"""Actual uploads/decoders/timeline/audio with explicit saved speech fixtures."""
import copy,json,subprocess,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from services.windows_native import source_media_tracks as media,auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError,file_sha,digest
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.multipart_ingestion import NativeMultipartIngestion
from services.windows_native.tests import test_auto_edit_analysis as analysis_fixture,test_asr as asr_fixture
from services.windows_native.source_assets import used_timeline_asset_ids
from app.production_logic import derive_subtitle_cues
from app.timeline_models import TimelineSnapshot
from app.subtitle_templates import load_templates

def prepare(case):
    case.temp=tempfile.TemporaryDirectory();case.owned=Path(case.temp.name);case.root=case.owned/'state'
    case.config=Config(data_root=case.root);case.store=Store(case.root);case.workspace='wsp_source_media_tracks_fixture'
    case.project=case.store.create('Owned video/audio/cue integration fixture','','media')
    case.uploads=NativeMultipartIngestion(case.store,case.config,workspace_id=case.workspace)
    video=case.owned/'owned-source.mp4';voice=case.owned/'owned-tone-not-speech.wav'
    subprocess.run([str(case.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3',
        '-f','lavfi','-i','sine=frequency=880:duration=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-t','3',str(video)],check=True,capture_output=True,timeout=30)
    subprocess.run([str(case.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','sine=frequency=440:duration=2',
        '-ar','16000','-ac','1','-c:a','pcm_s16le',str(voice)],check=True,capture_output=True,timeout=20)
    case.video=upload(case,video.read_bytes(),'video','video/mp4');case.voice=upload(case,voice.read_bytes(),'audio','audio/wav')
    case.music=upload(case,voice.read_bytes(),'music','audio/wav')
    case.subtitle=upload(case,'1\n00:00:00,100 --> 00:00:01,000\nVinhomes Cần Giờ\n\n2\n00:00:01,300 --> 00:00:02,200\nVang Nguyễn giới thiệu\n'.encode(),'subtitle','application/x-subrip')
    with case.store.transaction() as con:
        doc=copy.deepcopy(case.store.project(con.execute('SELECT * FROM projects WHERE id=?',(case.project['id'],)).fetchone())['document'])
        doc['media_analysis']=[analysis_fixture.saved_asr(case.video)]
        con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),case.project['id']))
        case.store.version(con,case.project['id'])
    case.project=case.store.get(case.project['id'])
    job=case.store.enqueue(case.project['id'],case.project['revision'],'auto_edit_analysis',uuid.uuid4().hex)
    Runner(case.store,Pipeline(case.config)).run_one();completed=case.store.get_job(job['id']);case.assertEqual(completed['status'],'succeeded',completed.get('error'))
    case.project=case.store.get(case.project['id']);analysis=case.project['document']['auto_edit_analyses'][0]['analysis']
    timeline.create(case.store,case.project['id'],case.project['revision'],{'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id']})
    case.sentence=next(v['template_ref'] for v in load_templates() if not v['requires_word_timestamps'])
    case.karaoke=next(v['template_ref'] for v in load_templates() if v['style']['animation']=='karaoke')

def upload(case,raw,kind,mime):
    current=case.store.get(case.project['id']);row=case.uploads.create(current['id'],{'revision':current['revision'],'kind':kind,'content_type':mime,
        'filename':'Owned bytes with untrusted extension.bin','total_bytes':len(raw),'rights_confirmed':True,'request_key':uuid.uuid4().hex},actor='fixture-editor')[0]
    from hashlib import sha256
    for start in range(0,len(raw),1024*1024):
        chunk=raw[start:start+1024*1024];row=case.uploads.chunk(current['id'],row['upload_id'],start,sha256(chunk).hexdigest(),chunk)[0]
    return case.uploads.complete(current['id'],row['upload_id'],{'revision':current['revision'],'expected_parts_sha256':row['parts_sha256']})[0]['result']['asset']

class SourceMediaTracksTests(unittest.TestCase):
    def setUp(self):prepare(self)
    def tearDown(self):self.temp.cleanup()
    def page(self,**kwargs):return media.catalog(self.store,self.project['id'],self.workspace,**kwargs)
    def binding(self,asset):
        p=self.store.get(self.project['id']);s=p['document']['canonical_timeline']
        return {'revision':p['revision'],'expected_version':s['version'],'timeline_sha256':s['sha256'],
            'asset_id':asset['id'],'asset_sha256':asset['sha256'],'request_key':uuid.uuid4().hex}
    def audio_body(self,asset=None,**extras):
        return {**self.binding(asset or self.voice),'role':'voice','source_start':0,'source_end':2,'timeline_start':0,**extras}
    def subtitle_body(self,**extras):
        p=self.page();track=next(t['track_id'] for t in p['tracks'] if t['kind']=='subtitles')
        return {**self.binding(self.subtitle),'replace_track_id':track,'subtitle_template_ref':self.sentence,**extras}
    def captions_body(self,text='Chữ Việt đã sửa trên timeline',**extras):
        p=self.page();return {'revision':p['revision'],'expected_version':p['timeline_version'],'timeline_sha256':p['timeline_sha256'],
            'subtitle_template_ref':self.sentence,'edits':[{'clip_id':p['captions'][0]['clip_id'],'text':text,'timeline_start':.2,'duration':.7}],**extras}
    def test_actual_audio_waveform_single_source_and_idempotent_replay_preserve_originals(self):
        before=self.store.get(self.project['id']);hashes={a['id']:file_sha(self.root/'assets'/a['id']) for a in before['document']['assets']}
        body=self.audio_body(timeline_start=.5,volume=.8,fade_in_seconds=.1,fade_out_seconds=.2);first=media.add_audio(self.store,self.project['id'],body,actor_ref='fixture-editor')
        after=self.store.get(self.project['id']);self.assertEqual(after['revision'],before['revision']+1);self.assertIsNone(after['approval'])
        state=after['document']['canonical_timeline'];self.assertEqual(state['version'],before['document']['canonical_timeline']['version']+1)
        track=next(t for t in state['snapshot']['tracks'] if t['track_id']==first['track_id']);clip=track['clips'][0]
        self.assertEqual((clip['source_start'],clip['source_end'],clip['timeline_start'],clip['duration']),(0,2,.5,2))
        wave=clip['metadata']['source_audio_waveform'];self.assertTrue(wave['measured']);self.assertEqual(wave['method'],'ffmpeg-mono-pcm-peak-rms-v2');self.assertTrue(wave['decoded_pts_verified']);self.assertGreater(max(b['peak'] for b in wave['bins']),.05)
        replay=media.add_audio(self.store,self.project['id'],body,actor_ref='fixture-editor');self.assertTrue(replay['replayed']);self.assertEqual(replay['clip_ids'],first['clip_ids']);self.assertEqual(self.store.get(self.project['id']),after)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):media.add_audio(self.store,self.project['id'],{**body,'volume':.7},actor_ref='fixture-editor')
        self.assertEqual({a['id']:file_sha(self.root/'assets'/a['id']) for a in before['document']['assets']},hashes)
    def test_music_loop_fades_canonical_edit_and_locked_track_reject_replace(self):
        body=self.audio_body(self.music,role='music',volume=.12,repeat_until=3,crossfade_seconds=.2,fade_in_seconds=.1,fade_out_seconds=.1)
        result=media.add_audio(self.store,self.project['id'],body,actor_ref='fixture-editor');p=self.store.get(self.project['id']);track=next(t for t in p['document']['canonical_timeline']['snapshot']['tracks'] if t['track_id']==result['track_id'])
        self.assertEqual(len(track['clips']),2);self.assertEqual(track['clips'][1]['timeline_start'],1.8);self.assertEqual(track['clips'][1]['source_end'],1.2)
        p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['document']['canonical_timeline']['version'],'operations':[{'type':'set_track_state','track_id':result['track_id'],'locked':True}]})
        before=self.store.get(p['id'])
        with self.assertRaisesRegex(WorkflowError,'TRACK_LOCKED'):media.add_audio(self.store,p['id'],self.audio_body(self.music,role='music',track_id=result['track_id'],replace_existing=True),actor_ref='fixture-editor')
        self.assertEqual(self.store.get(p['id']),before)
    def test_SRT_import_edits_original_bytes_provenance_and_undo(self):
        before=self.store.get(self.project['id']);original=file_sha(self.root/'originals'/self.subtitle['original_id'])
        result=media.add_subtitles(self.store,self.project['id'],self.subtitle_body(),actor_ref='fixture-editor');p=self.page()
        self.assertEqual(result['caption_count'],2);self.assertEqual(p['captions'][0]['text'],'Vinhomes Cần Giờ');self.assertFalse(p['captions'][0]['has_word_timing'])
        raw_before=copy.deepcopy(self.store.get(self.project['id'])['document']['media_analysis']);edit=media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='fixture-editor');self.assertTrue(edit['changed'])
        self.assertEqual(self.page()['captions'][0]['text'],'Chữ Việt đã sửa trên timeline');self.assertFalse(self.page()['captions'][0]['has_word_timing'])
        current=self.store.get(self.project['id']);self.assertEqual(current['document']['media_analysis'],raw_before);self.assertEqual(file_sha(self.root/'originals'/self.subtitle['original_id']),original)
        restored=timeline.restore(self.store,current['id'],current['revision'],{'expected_version':current['document']['canonical_timeline']['version'],'restore_revision':before['revision']})
        self.assertEqual([t['clips'] for t in restored['document']['canonical_timeline']['snapshot']['tracks']],[t['clips'] for t in before['document']['canonical_timeline']['snapshot']['tracks']]);self.assertIsNone(restored['approval'])
    def test_caption_unknown_rights_cannot_be_omitted_from_publication(self):
        media.add_subtitles(self.store,self.project['id'],self.subtitle_body(),actor_ref='fixture-editor');doc=self.store.get(self.project['id'])['document']
        self.assertIn(self.subtitle['id'],used_timeline_asset_ids(doc['canonical_timeline']['snapshot']))
        from app.publishing_logic import validate_rights
        rows=[SimpleNamespace(asset_id=a['id'],provenance={k:a.get(k) for k in ['rights_status','license']}) for a in doc['assets'] if a['id'] in used_timeline_asset_ids(doc['canonical_timeline']['snapshot'])]
        report=validate_rights(rows);self.assertEqual(report.status,'failed');self.assertIn(self.subtitle['id'],json.dumps(report.model_dump(mode='json')))
    def test_source_time_mapping_and_explicit_out_of_bounds_trim(self):
        p=self.store.get(self.project['id']);p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['document']['canonical_timeline']['version'],'operations':[{'type':'trim','clip_id':next(t['clips'][0]['clip_id'] for t in p['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='source'),'source_start':1,'source_end':3}]})
        # Generic trim retains a gap; mapping follows the saved source clip, not duration guesses.
        result=media.add_subtitles(self.store,p['id'],self.subtitle_body(timebase='source'),actor_ref='fixture-editor');self.assertEqual(result['caption_count'],1);self.assertEqual(result['dropped_intervals'],1)
        p=self.page();self.assertAlmostEqual(p['captions'][0]['timeline_start'],.3,places=5)
        body=self.subtitle_body(offset_seconds=-.5)
        with self.assertRaisesRegex(WorkflowError,'OUT_OF_BOUNDS'):media.add_subtitles(self.store,p['project_id'],body,actor_ref='fixture-editor')
        result=media.add_subtitles(self.store,p['project_id'],{**body,'trim_to_timeline':True},actor_ref='fixture-editor');self.assertEqual(result['clipped_intervals'],1);self.assertEqual(self.page()['captions'][0]['timeline_start'],0)
    def test_stale_sha_invalid_bounds_and_unknown_fields_never_mutate(self):
        before=self.store.get(self.project['id']);base=self.audio_body()
        for change in [{'asset_sha256':'a'*64},{'timeline_sha256':'a'*64},{'source_end':2.5},{'timeline_start':2},
            {'volume':True},{'source_start':'0'},{'provider':'unapproved'},{'role':'owner'},{'repeat_until':3}]:
            with self.assertRaises(WorkflowError):media.add_audio(self.store,self.project['id'],{**base,**change},actor_ref='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before)
        with self.assertRaisesRegex(WorkflowError,'WORD_ALIGNMENT_UNAVAILABLE'):media.add_subtitles(self.store,self.project['id'],self.subtitle_body(subtitle_template_ref=self.karaoke),actor_ref='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_changed_subtitle_bytes_and_metadata_block_preview_and_edits(self):
        media.add_subtitles(self.store,self.project['id'],self.subtitle_body(),actor_ref='fixture-editor');before=self.store.get(self.project['id'])
        from services.windows_native.source_preview import resolve_assets
        (self.root/'assets'/self.subtitle['id']).write_bytes(b'Changed owned test bytes')
        with self.assertRaises(WorkflowError):resolve_assets(self.config,before)
        with self.assertRaises(WorkflowError):media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_duplicate_and_public_backup_restore_keep_provenance_without_replay_authority(self):
        audio=media.add_audio(self.store,self.project['id'],self.audio_body(),actor_ref='fixture-editor');media.add_subtitles(self.store,self.project['id'],self.subtitle_body(),actor_ref='fixture-editor')
        p=self.store.get(self.project['id']);child=self.store.duplicate(p['id'],p['revision']);self.assertIsNone(child['approval']);self.assertEqual(child['document']['canonical_timeline']['version'],1)
        from services.windows_native.source_preview import resolve_assets
        resolve_assets(self.config,child)
        inherited=child['document']['source_media_track_imports'];self.assertTrue(all(r['request_key_sha256'] is None for r in inherited));self.assertNotIn(audio['import_id'],{r['import_id'] for r in inherited})
        from services.windows_native.backup import create_backup,restore_backup
        receipt=create_backup(self.config,self.owned/'backup.zip');destination=self.owned/'restore';restore_backup(receipt['backup_path'],destination,expected_sha256=receipt['sha256'])
        self.assertEqual(media.catalog(Store(destination),child['id'],self.workspace),media.catalog(self.store,child['id'],self.workspace))
    def test_source_change_while_measuring_fails_second_CAS_without_database_lock(self):
        from app.audio_waveform import measure_waveform
        async def concurrent(*args,**kwargs):
            wave=await measure_waveform(*args,**kwargs)
            with self.store.transaction() as con:con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],))
            return wave
        with patch('app.audio_waveform.measure_waveform',side_effect=concurrent):
            with self.assertRaises(WorkflowError):media.add_audio(self.store,self.project['id'],self.audio_body(),actor_ref='fixture-editor')
        self.assertEqual(self.page()['imports'],[])

    def test_audio_ASR_words_bind_to_caption_clock_and_edited_text_cannot_keep_karaoke(self):
        from services.windows_native import asr,audio_transcripts
        original=asr.analyze;asr_fixture.FixtureTransport.calls=[];asr_fixture.FixtureTransport.invalid_timing=False
        with patch.object(asr.connection,'status',return_value={'connected':True}),patch.object(asr.connection,'load_credential',return_value=asr_fixture.KEY),\
             patch.object(asr,'analyze',side_effect=lambda c,j,o,s:original(c,j,o,s,transport_factory=asr_fixture.FixtureTransport)):
            p=self.store.get(self.project['id']);job=self.store.enqueue(p['id'],p['revision'],'asr',uuid.uuid4().hex);Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job['id'])['status'],'succeeded');row=audio_transcripts.view(self.store,self.project['id'],self.workspace)['items'][0]
        caption_track=next(t['track_id'] for t in self.page()['tracks'] if t['kind']=='subtitles')
        body=self.audio_body(timeline_start=.5,captions={'transcript_id':row['current']['transcript_id'],'analysis_sha256':row['analysis_sha256'],
            'replace_track_id':caption_track,'subtitle_template_ref':self.karaoke})
        result=media.add_audio(self.store,self.project['id'],body,actor_ref='fixture-editor');self.assertEqual(result['caption_count'],1)
        p=self.store.get(self.project['id']);cues=derive_subtitle_cues(TimelineSnapshot.model_validate(p['document']['canonical_timeline']['snapshot']))
        self.assertEqual(cues[0].text,'Xin chào.');self.assertEqual(cues[0].words[0].start_seconds,.5);self.assertEqual(cues[0].words[1].start_seconds,.71)
        before=self.store.get(self.project['id']);bad=self.captions_body(subtitle_template_ref=self.karaoke)
        with self.assertRaisesRegex(WorkflowError,'WORD_ALIGNMENT_UNAVAILABLE'):media.edit_captions(self.store,self.project['id'],bad,actor_ref='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before)
        media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='fixture-editor');self.assertFalse(self.page()['captions'][0]['has_word_timing'])
        with self.assertRaisesRegex(WorkflowError,'SPOKEN_WORD_CUT'):media.add_audio(self.store,self.project['id'],self.audio_body(source_start=.1),actor_ref='fixture-editor')

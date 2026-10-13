"""Manual Native review uses real owned media/SQLite and explicit ASR/human fixtures."""
import copy,json,math,unittest,uuid,subprocess
from unittest.mock import patch
from app.transcript_word_review import WordReview,revised
from app.auto_edit_models import TranscriptRead
from services.windows_native import auto_edit_analysis as analysis,auto_edit_timeline as timeline,transcript_word_review as words
from services.windows_native.transcript_word_routes import view
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.tests import test_auto_edit_analysis as fixture
from services.windows_native.tests import test_audio_transcripts as audio_fixture

def request(transcript,version=None):
    segment=transcript['segments'][0]
    return {'expected_version':transcript['version'],'expected_transcript_id':transcript['transcript_id'],
        'expected_timeline_version':version,'acknowledged':True,'segments':[{'segment_id':segment['segment_id'],
            'start_seconds':segment['start_seconds'],'end_seconds':segment['end_seconds'],
            'words':[{k:word[k] for k in ('word_id','text','start_seconds','end_seconds')} for word in segment['words']]}],
        'note':'Explicit CI manual review; no Owner UAT'}

class NativeWordReviewTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeAutoEditTests.setUp(self)
        path=self.root/'assets'/self.asset['id'];path.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-f','lavfi','-i','color=c=navy:s=320x240:r=30:d=3',
            '-f','lavfi','-i','sine=frequency=440:duration=3','-shortest','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,timeout=20)
        from services.windows_native.contracts import file_sha
        self.asset.update(sha256=file_sha(path),bytes=path.stat().st_size)
        from services.windows_native.media import project_assets
        with self.store.transaction() as con:
            document=self.project['document']
            document['assets']=[{**a,**self.asset} if a['id']==self.asset['id'] else a for a in project_assets(document)]
            document['media_analysis']=[fixture.saved_asr(self.asset)]
            con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(document),self.project['id']))
        self.project=self.store.get(self.project['id'])
    tearDown=fixture.NativeAutoEditTests.tearDown
    save_analysis=fixture.NativeAutoEditTests.save_analysis
    def prepare(self,canonical=False):
        original=self.save_analysis();item=original['analyses'][0]
        if canonical:
            self.project=timeline.create(self.store,self.project['id'],original['revision'],{
                'analysis_id':item['analysis']['analysis_id'],'transcript_id':item['analysis']['transcript']['transcript_id']})
        return view(self.store,self.project['id'],'wsp_word_review_fixture')
    def save(self,bundle,payload=None,**kwargs):
        item=bundle['items'][0]
        return words.save(self.store,self.project['id'],bundle['revision'],item['identity'],payload or request(item['current'],bundle['timeline_version']),
            actor_ref='fixture-editor',asset_sha256=item['asset_sha256'],analysis_sha256=item['analysis_sha256'],**kwargs)
    def test_manual_word_text_time_version_and_raw_evidence_are_preserved(self):
        bundle=self.prepare();item=bundle['items'][0];before=copy.deepcopy(self.store.get(self.project['id'])['document'])
        body=request(item['current']);body['segments'][0]['words'][0]['text']='Vang Nguyễn'
        body['segments'][0]['words'][0]['end_seconds']=.59
        result=self.save(bundle,body);value=result['analyses'][0]['analysis']['transcript']
        self.assertEqual(value['version'],2);self.assertFalse(value['is_original_evidence']);self.assertEqual(value['segments'][0]['text'],'Vang Nguyễn chào.')
        self.assertTrue(all(w['confidence'] is None for w in value['segments'][0]['words']))
        self.assertEqual(value['segments'][1]['words'][0]['confidence'],.8)
        self.assertEqual(value['provenance']['actor_ref'],'fixture-editor');self.assertFalse(value['provenance']['timing_independently_measured'])
        current=self.store.get(self.project['id']);self.assertEqual(current['document']['media_analysis'],before['media_analysis'])
        self.assertEqual(current['document']['auto_edit_analyses'],before['auto_edit_analyses']);self.assertIsNone(current['approval'])
        self.assertEqual(analysis.view(self.store,self.project['id']),result)
    def test_add_remove_words_are_explicit_and_confidence_is_not_invented(self):
        bundle=self.prepare();body=request(bundle['items'][0]['current'])
        source=body['segments'][0]['words'];source[0]['text']='Xin';source[0]['end_seconds']=.4
        source[1:]=[{'word_id':None,'text':'chào','start_seconds':.4,'end_seconds':.8},
            {'word_id':None,'text':'bạn.','start_seconds':.8,'end_seconds':1.2}]
        value=self.save(bundle,body)['analyses'][0]['analysis']['transcript']
        self.assertEqual([w['text'] for w in value['segments'][0]['words']],['Xin','chào','bạn.'])
        self.assertTrue(all(w['confidence'] is None for w in value['segments'][0]['words']))
    def test_canonical_captions_follow_review_and_other_tracks_do_not_change(self):
        bundle=self.prepare(True);project=self.store.get(self.project['id']);state=project['document']['canonical_timeline']
        original_clip=next(t for t in state['snapshot']['tracks'] if t['kind']=='source')['clips'][0]
        reused=copy.deepcopy(original_clip);reused['clip_id']='clip_'+uuid.uuid4().hex[:24]
        next(t for t in state['snapshot']['tracks'] if t['kind']=='broll')['clips']=[reused]
        state['sha256']=digest(state['snapshot'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(project['document']),self.project['id']))
        before=copy.deepcopy(state)
        body=request(bundle['items'][0]['current'],bundle['timeline_version']);segment=body['segments'][0]
        segment['start_seconds']=.1;segment['end_seconds']=1.3
        segment['words'][0].update(text='Xin',start_seconds=.1,end_seconds=.5)
        segment['words'][1].update(text='chào bạn.',start_seconds=.5,end_seconds=1.3)
        self.save(bundle,body);after=self.store.get(self.project['id'])['document']['canonical_timeline']
        self.assertEqual(after['version'],before['version']+1)
        self.assertEqual([t for t in before['snapshot']['tracks'] if t['kind']!='subtitles'],
            [t for t in after['snapshot']['tracks'] if t['kind']!='subtitles'])
        captions=[c for t in after['snapshot']['tracks'] if t['kind']=='subtitles' for c in t['clips']]
        changed=next(c for c in captions if c['metadata'].get('human_word_timing_review'))
        self.assertEqual(len([c for c in captions if c['metadata'].get('human_word_timing_review')]),1)
        self.assertEqual(changed['source_start'],.1);self.assertEqual(changed['source_end'],1.3)
        self.assertEqual(changed['metadata']['measured_source_words'][1]['start_seconds'],.5)
        self.assertEqual(changed['metadata']['timing_source'],'human_supplied_source_word_intervals')
    def test_locked_caption_track_rolls_back_history_approval_and_canonical(self):
        bundle=self.prepare(True)
        project=self.store.get(self.project['id']);state=project['document']['canonical_timeline']
        for track in state['snapshot']['tracks']:
            if track['kind']=='subtitles':track['locked']=True
        state['sha256']=digest(state['snapshot'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(project['document']),self.project['id']))
        before=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'LOCKED'):self.save(bundle)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_word_spanning_a_retained_source_cut_is_refused_without_history_write(self):
        bundle=self.prepare(True);project=self.store.get(self.project['id']);state=project['document']['canonical_timeline']
        source=next(t for t in state['snapshot']['tracks'] if t['kind']=='source')
        first=source['clips'][0];first['source_end']=1.3;first['duration']=1.3-first['source_start']
        state['sha256']=digest(state['snapshot']);timeline.validate_document(project['document'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(project['document']),self.project['id']))
        before=self.store.get(self.project['id']);body=request(bundle['items'][0]['current'],bundle['timeline_version'])
        body['segments'][0]['end_seconds']=1.4;body['segments'][0]['words'][-1]['end_seconds']=1.4
        with self.assertRaisesRegex(WorkflowError,'EXISTING_SOURCE_CUT'):self.save(bundle,body)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_explicit_caption_layout_is_preserved_during_word_review(self):
        bundle=self.prepare(True);project=self.store.get(self.project['id']);state=project['document']['canonical_timeline']
        caption=next(t for t in state['snapshot']['tracks'] if t['kind']=='subtitles')
        state['snapshot']['metadata']['source_caption_edited_tracks']=[caption['track_id']]
        for clip in caption['clips']:clip['metadata']['human_caption_edit']=True
        state['sha256']=digest(state['snapshot']);before=copy.deepcopy(caption)
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(project['document']),self.project['id']))
        self.save(bundle)
        after=self.store.get(self.project['id'])['document']['canonical_timeline']['snapshot']
        self.assertEqual(next(t for t in after['tracks'] if t['kind']=='subtitles'),before)
        self.assertTrue(after['metadata']['transcript_revision']['review_required'])
    def test_unrounded_explicit_source_boundary_keeps_first_word_in_karaoke(self):
        bundle=self.prepare(True);body=request(bundle['items'][0]['current'],bundle['timeline_version'])
        start=.199999999999999;body['segments'][0]['start_seconds']=start
        body['segments'][0]['words'][0]['start_seconds']=start
        self.save(bundle,body)
        from app.timeline_models import TimelineSnapshot
        from app.production_models import SubtitleStyle
        from app.production_logic import derive_subtitle_cues
        snapshot=TimelineSnapshot.model_validate(self.store.get(self.project['id'])['document']['canonical_timeline']['snapshot'])
        cues=derive_subtitle_cues(snapshot,style=SubtitleStyle(animation='karaoke'))
        self.assertEqual([w.text for cue in cues for w in cue.words],['Xin','chào.','Cơ','hội','mới.'])
        from services.windows_native.source_linked_edit import edit
        project=self.store.get(self.project['id']);state=project['document']['canonical_timeline']
        clip=next(t for t in state['snapshot']['tracks'] if t['kind']=='source')['clips'][0]
        edited=edit(self.store,project['id'],project['revision'],{'expected_version':state['version'],
            'operation':{'type':'set_clip_properties','clip_id':clip['clip_id'],'speed':2}})
        snapshot=TimelineSnapshot.model_validate(edited['document']['canonical_timeline']['snapshot'])
        captions=[c for t in snapshot.tracks if t.kind=='subtitles' for c in t.clips]
        self.assertTrue(all(c.metadata.get('human_word_timing_review') and c.metadata['timing_independently_measured'] is False for c in captions))
        self.assertEqual([w.text for cue in derive_subtitle_cues(snapshot,style=SubtitleStyle(animation='karaoke')) for w in cue.words],
            ['Xin','chào.','Cơ','hội','mới.'])
    def test_stale_foreign_nonfinite_overlap_and_missing_ack_fail_without_writes(self):
        bundle=self.prepare();original=request(bundle['items'][0]['current']);before=self.store.get(self.project['id'])
        invalid=[]
        for field,value in [('expected_version',99),('expected_transcript_id','trn_'+'f'*24),('acknowledged',False)]:
            body=copy.deepcopy(original);body[field]=value;invalid.append(body)
        for field,value in [('start_seconds',math.nan),('end_seconds',.1),('start_seconds',True),('text',' ')]:
            body=copy.deepcopy(original);body['segments'][0]['words'][0][field]=value;invalid.append(body)
        body=copy.deepcopy(original);body['segments'][0]['words'][1]['start_seconds']=.5;invalid.append(body)
        body=copy.deepcopy(original);body['segments'][0]['words'][0]['word_id']='wrd_'+'f'*24;invalid.append(body)
        for body in invalid:
            with self.assertRaises(WorkflowError):self.save(bundle,body)
            self.assertEqual(self.store.get(self.project['id']),before)
    def test_observed_missing_audio_gap_is_refused_and_history_tamper_is_detected(self):
        bundle=self.prepare();before=self.store.get(self.project['id'])
        with patch.object(words,'gaps',return_value=[(.3,.4)]):
            with self.assertRaisesRegex(WorkflowError,'AUDIO_GAP'):self.save(bundle)
        self.assertEqual(self.store.get(self.project['id']),before)
        self.save(bundle)
        project=self.store.get(self.project['id']);document=project['document']
        with self.store.transaction() as con:
            document['auto_edit_transcripts'][0]['segments'][0]['words'][0]['text']='rehashed? no'
            con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(document),self.project['id']))
        with self.assertRaisesRegex(WorkflowError,'HISTORY_CHANGED'):analysis.view(self.store,self.project['id'])
    def test_original_and_current_views_survive_new_store_without_provider_calls(self):
        bundle=self.prepare();self.save(bundle)
        from services.windows_native.store import Store
        self.assertEqual(view(self.store,self.project['id'],'wsp_word_review_fixture'),view(Store(self.root),self.project['id'],'wsp_word_review_fixture'))

class AudioWordReviewTests(unittest.TestCase):
    setUp=audio_fixture.AudioTranscriptTests.setUp
    tearDown=audio_fixture.AudioTranscriptTests.tearDown
    upload=audio_fixture.AudioTranscriptTests.upload
    run_job=audio_fixture.AudioTranscriptTests.run_job
    collected=audio_fixture.AudioTranscriptTests.collected
    def test_audio_word_review_uses_same_original_and_hashed_version_history(self):
        bundle=self.collected();item=bundle['items'][0];before=copy.deepcopy(self.project['document']['media_analysis'])
        body=request(item['current']);body['segments'][0]['words'][0]['text']='Cần'
        value=words.save(self.store,self.project['id'],bundle['revision'],item['asset_id'],body,actor_ref='fixture-editor',
            asset_sha256=item['asset_sha256'],analysis_sha256=item['analysis_sha256'],audio=True,workspace_id='wsp_audio_transcript_fixture')
        self.assertEqual(value['items'][0]['current']['version'],2);self.assertEqual(value['items'][0]['original'],item['original'])
        self.assertEqual(self.store.get(self.project['id'])['document']['media_analysis'],before)
        self.assertEqual(value['items'][0]['current']['segments'][0]['words'][0]['text'],'Cần')

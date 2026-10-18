"""Actual measured tone PCM/canonical caption windows, never speech or Owner acceptance."""
import copy,json,shutil,unittest
from services.windows_native.tests import test_dialogue_runtime as fixture
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.branding import resolve
from services.windows_native.shot_render_timing import retime_voice
from services.windows_native.narrated_media_captions import render
from services.windows_native import dialogue_qc

class DialogueQCTests(unittest.TestCase):
    cast=fixture.DialogueRuntimeTests.cast
    save_cast=fixture.DialogueRuntimeTests.save_cast
    compile=fixture.DialogueRuntimeTests.compile
    approved_job=fixture.DialogueRuntimeTests.approved_job
    prepare=fixture.DialogueRuntimeTests.prepare
    apply=fixture.DialogueRuntimeTests.apply
    def setUp(self):
        fixture.DialogueRuntimeTests.setUp(self);job,result,self.source=self.prepare();self.project=self.apply(job,result);self.counter=0
    tearDown=fixture.DialogueRuntimeTests.tearDown
    def document(self):return copy.deepcopy(self.store.get(self.project['id'])['document'])
    def captions(self,document):return next(t['clips'] for t in document['canonical_timeline']['snapshot']['tracks'] if t['kind']=='subtitles')
    def bind(self,document):
        # Explicit corruption fixtures remain otherwise valid canonical human
        # caption overrides. Ordinary user moves below use the real editor.
        snapshot=document['canonical_timeline']['snapshot'];tracks=[t for t in snapshot['tracks'] if t['kind']=='subtitles']
        snapshot['metadata']['narrated_caption_edited_tracks']=[t['track_id'] for t in tracks]
        for track in tracks:
            for clip in track['clips']:clip['metadata']['human_caption_edit']=True
        document['canonical_timeline']['sha256']=digest(snapshot);return document
    def output(self,document):
        self.counter+=1;out=self.root/('caption-qc-'+str(self.counter));out.mkdir()
        for name in ('voice.wav','voice.json'):shutil.copyfile(self.source/name,out/name)
        meta=json.loads((out/'voice.json').read_bytes());brand,template=resolve(document);retime_voice(document,meta,out,brand,template)
        return out
    def inspect(self,document):
        out=self.output(document);captions=render(document,out,1080,1920,[70,90,1010,1740]);return out,captions

    def test_positive_two_speaker_measurement_is_pinned_and_does_not_claim_word_alignment(self):
        document=self.document();out,captions=self.inspect(document);proof=json.loads((out/'dialogue-qc.json').read_bytes())
        self.assertEqual(proof['status'],'passed');self.assertEqual(len(proof['cue_windows']),2);self.assertFalse(proof['speech_semantics_verified']);self.assertFalse(proof['human_voice_uat_complete'])
        self.assertFalse(proof['word_alignment_claimed']);manifest={'captions':captions,'dialogue_qc_sha256':file_sha(out/'dialogue-qc.json')}
        self.assertEqual(dialogue_qc.verify(document,out,manifest),proof)

    def test_caption_moved_into_other_actor_window_fails_before_ass_or_mp4(self):
        from services.windows_native.narrated_timeline_editor import edit
        project=self.store.get(self.project['id']);state=project['document']['canonical_timeline'];a,b=self.captions(project['document'])
        edit(self.store,project['id'],{'revision':project['revision'],'expected_version':state['version'],'timeline_sha256':state['sha256'],
            'operations':[{'type':'disable','clip_id':b['clip_id'],'disabled':True},{'type':'move','clip_id':a['clip_id'],'timeline_start':b['timeline_start']}]},self.library.workspace)
        document=self.document();out=self.output(document)
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):render(document,out,1080,1920,[70,90,1010,1740])
        proof=json.loads((out/'dialogue-qc.json').read_bytes());self.assertEqual(proof['status'],'failed_qc');self.assertIn('subtitle_outside_measured_speaker_window',proof['reasons'])
        self.assertFalse((out/'subtitles.ass').exists());self.assertFalse((out/'final.mp4').exists())

    def test_wrong_speaker_identity_cannot_relabel_another_actor_line(self):
        document=self.document();a,b=self.captions(document);a['metadata']['speaker_id']=b['metadata']['speaker_id'];a['metadata']['speaker_name']=b['metadata']['speaker_name']
        self.bind(document);out=self.output(document)
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):render(document,out,1080,1920,[70,90,1010,1740])
        self.assertIn('subtitle_speaker_or_line_binding_changed',json.loads((out/'dialogue-qc.json').read_bytes())['reasons'])

    def test_muted_approved_dialogue_cannot_pass_as_audio_included(self):
        document=self.document();next(t for t in document['canonical_timeline']['snapshot']['tracks'] if t['kind']=='voice')['muted']=True;self.bind(document);out=self.output(document)
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):render(document,out,1080,1920,[70,90,1010,1740])
        self.assertIn('approved_dialogue_voice_missing_or_unbound_voice_overlap',json.loads((out/'dialogue-qc.json').read_bytes())['reasons'])

    def test_explicit_export_audio_off_keeps_valid_speaker_caption_timing(self):
        from services.windows_native.narrated_timeline_editor import configure
        project=self.store.get(self.project['id']);state=project['document']['canonical_timeline']
        configure(self.store,project['id'],{'revision':project['revision'],'expected_version':state['version'],'timeline_sha256':state['sha256'],'audio_included':False},self.library.workspace)
        document=self.document();next(t for t in document['canonical_timeline']['snapshot']['tracks'] if t['kind']=='voice')['muted']=True;self.bind(document)
        out,_=self.inspect(document);self.assertEqual(json.loads((out/'dialogue-qc.json').read_bytes())['status'],'passed')

    def test_changed_qc_report_or_placed_voice_metadata_never_self_heals(self):
        document=self.document();out,captions=self.inspect(document);manifest={'captions':captions,'dialogue_qc_sha256':file_sha(out/'dialogue-qc.json')}
        proof=json.loads((out/'dialogue-qc.json').read_bytes());proof['cue_windows'][0]['start_seconds']=0;(out/'dialogue-qc.json').write_text(json.dumps(proof),encoding='utf-8');changed=file_sha(out/'dialogue-qc.json')
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):dialogue_qc.verify(document,out,manifest)
        self.assertEqual(file_sha(out/'dialogue-qc.json'),changed)
        fresh,captions=self.inspect(document);manifest={'captions':captions,'dialogue_qc_sha256':file_sha(fresh/'dialogue-qc.json')}
        meta=json.loads((fresh/'render-voice.json').read_bytes());meta['units'][0]['activity_end_seconds']-=.4;(fresh/'render-voice.json').write_text(json.dumps(meta),encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):dialogue_qc.verify(document,fresh,manifest)

    def test_missing_measured_source_or_speaker_metadata_fails_closed(self):
        document=self.document();out=self.output(document);(out/'render-voice.json').unlink()
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):render(document,out,1080,1920,[70,90,1010,1740])
        document=self.document();self.captions(document)[0]['metadata'].pop('speaker_id');self.bind(document);out=self.output(document)
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_QC_FAILED'):render(document,out,1080,1920,[70,90,1010,1740])

    def test_dialogue_quality_error_becomes_failed_qc_with_actionable_user_guidance(self):
        job=self.approved_job();self.store.finish(job,error={'code':dialogue_qc.CODE});result=self.store.get_job(job['id'])
        self.assertEqual(result['status'],'failed_qc');self.assertIn('phụ đề',result['failure']['action']);self.assertFalse(result['failure']['automatic_paid_replay'])
        from services.windows_native.hardening import failure
        self.assertIn('bản render mới',failure('EXPORT_DIALOGUE_QC_REVIEW_REQUIRED')['action'])

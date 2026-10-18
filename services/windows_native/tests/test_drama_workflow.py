"""Drama authoring is explicit, canonical and provider-free; never Owner UAT."""
import copy,tempfile,unittest
from pathlib import Path
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError
from services.windows_native.production_workflows import parse_script,save_script,drama_selection
from services.windows_native.shot_adapter import shots,validate_document

SCRIPT='CẢNH 1: Chiếc ô\n(An đặt chiếc ô lên bàn.)\nAn: Mình tìm thấy chiếc ô của bạn rồi.\nBình: Cảm ơn, mình đã tìm nó cả buổi.'

class DramaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store(Path(self.temp.name))
        self.project=self.store.create('Chiếc ô','',input_kind='script',workflow_kind='drama')
    def save(self,text=SCRIPT,confirm=False,key='drama-script-test-0001',**kwargs):
        return save_script(self.store,self.project['id'],dict(revision=self.project['revision'],request_key=key,text=text,confirm_characters=confirm,**kwargs),actor_ref='explicit-test-fixture')
    def test_empty_creation_has_real_profile_no_narrator_cta_logo_or_placeholder_speech(self):
        doc=self.project['document'];self.assertEqual(doc['production_workflow']['kind'],'drama');self.assertEqual(doc['prompt'],'')
        self.assertEqual(doc['brand_template']['template']['purpose'],'drama');self.assertEqual(doc['brand_template']['template']['aspect_ratio'],'9:16')
        self.assertEqual(doc['brand_template']['brand']['primary_cta'],'');self.assertIsNone(doc['brand_template']['brand']['logo'])
        self.assertNotIn('drama_casting',doc);self.assertIsNone(doc['proposal']);self.assertEqual(self.project['jobs'],[])
    def test_old_standard_project_is_not_migrated_and_four_drama_canvases_are_explicit(self):
        old=self.store.create('Old film','Nội dung cũ.');before=copy.deepcopy(old)
        for ratio,size in [('9:16',(1080,1920)),('16:9',(1920,1080)),('1:1',(1080,1080)),('4:5',(1080,1350))]:
            value=drama_selection(ratio)['template'];self.assertEqual((value['width'],value['height']),size)
        self.assertEqual(self.store.get(old['id']),before);self.assertNotIn('production_workflow',old['document'])
    def test_parser_never_reads_actions_or_assumes_ambiguous_speaker(self):
        value=parse_script(SCRIPT+'\nMột câu chưa rõ ai nói.',self.project['id'])
        self.assertEqual(len(value['characters']),2);self.assertEqual(len(value['needs_speaker']),1)
        self.assertNotIn('đặt chiếc ô',' '.join(v['text'] for v in value['lines']));self.assertFalse(value['narrator_enabled'])
    def test_incomplete_draft_saves_and_reopens_without_media_or_voice(self):
        result=self.save();current=Store(self.store.root).get(self.project['id'])
        self.assertEqual(current['revision'],2);self.assertFalse(result['characters_confirmed'])
        self.assertNotIn('canonical_timeline',current['document']);self.assertEqual(current['document']['drama_script']['raw_text'],SCRIPT)
        self.assertIsNone(current['approval']);self.assertEqual(current['jobs'],[])
    def test_confirmation_creates_same_canonical_timeline_and_two_uncast_characters_without_assets(self):
        self.save(confirm=True);project=self.store.get(self.project['id']);doc=project['document'];validate_document(doc)
        self.assertEqual(len(shots(doc)),1);self.assertEqual(len(doc['drama_casting']['configuration']['characters']),2)
        self.assertEqual(doc['drama_casting']['configuration']['casting'],[]);self.assertFalse(doc['drama_casting']['configuration']['narrator_enabled'])
        self.assertEqual(len(doc['drama_casting']['configuration']['lines']),2);self.assertNotIn('đặt chiếc ô',doc['proposal']['narration'])
        self.assertEqual(doc['assets'],[]);self.assertIsNone(project['approval'])
    def test_unknown_speaker_confirmation_and_narrator_only_script_fail_without_mutation(self):
        for text,code in [('Ai đang nói câu này?','SPEAKER_SELECTION_REQUIRED'),('Người kể: Ngày xưa có một chiếc ô.','ACTIVE_DIALOGUE_REQUIRED')]:
            with self.subTest(text=text),self.assertRaisesRegex(WorkflowError,code):self.save(text,confirm=True)
        self.assertEqual(self.store.get(self.project['id'])['revision'],1)
    def test_exact_lost_response_replay_does_not_rewind_later_draft(self):
        first=self.save();self.project=self.store.get(self.project['id']);self.save(SCRIPT+'\nAn: Mai gặp lại nhé.',key='drama-script-test-0002')
        value=save_script(self.store,self.project['id'],dict(revision=1,request_key='drama-script-test-0001',text=SCRIPT,confirm_characters=False),actor_ref='explicit-test-fixture')
        self.assertTrue(value['idempotent_replay']);self.assertEqual(value['revision'],first['revision']);self.assertEqual(self.store.get(self.project['id'])['revision'],3)
    def test_idea_draft_does_not_invent_speakers_or_spoken_actions(self):
        self.save('Hai người bạn tìm lại chiếc ô.',input_mode='idea');doc=self.store.get(self.project['id'])['document']
        self.assertEqual(doc['input_kind'],'idea');self.assertEqual(doc['drama_script']['parsed']['characters'],[]);self.assertNotIn('canonical_timeline',doc)
    def test_new_unconfirmed_draft_blocks_old_compiled_dialogue_inputs(self):
        from services.windows_native.dialogue_binding import inputs
        self.save(confirm=True);self.project=self.store.get(self.project['id']);self.save(SCRIPT+'\nAn: Mình về trước nhé.',key='changed-drama-draft-0001')
        with self.assertRaisesRegex(WorkflowError,'CHARACTER_CONFIRMATION_REQUIRED'):inputs(self.store.get(self.project['id'])['document'])
    def test_script_replay_retains_m1_receipt_from_before_optional_idea_mode(self):
        from services.windows_native.production_workflows import ScriptSave
        from services.windows_native.contracts import digest
        self.save();body=ScriptSave.model_validate(dict(revision=1,request_key='drama-script-test-0001',text=SCRIPT)).model_dump()
        with self.store.transaction() as con:con.execute('UPDATE native_drama_script_writes SET fingerprint=?',(digest({k:v for k,v in body.items() if k!='input_mode'}),))
        replay=save_script(self.store,self.project['id'],body,actor_ref='explicit-test-fixture');self.assertTrue(replay['idempotent_replay']);self.assertEqual(self.store.get(self.project['id'])['revision'],2)

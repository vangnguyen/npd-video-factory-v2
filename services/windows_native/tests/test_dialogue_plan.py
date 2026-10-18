"""Dependency planning with explicit voice metadata fixtures, never generated audio."""
import copy,json,tempfile,unittest
from pathlib import Path
from services.windows_native.store import Store
from services.windows_native.voice_library import NativeVoiceLibrary
from services.windows_native.dialogue_plan import build,affected
from services.windows_native.contracts import WorkflowError
from services.windows_native.tests.test_voice_library import definition

CHAR_A='chr_'+'a'*32;CHAR_B='chr_'+'b'*32;CHAR_N='chr_'+'c'*32
LINE_A='line_'+'d'*32;LINE_B='line_'+'e'*32;LINE_N='line_'+'f'*32

class DialoguePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.library=NativeVoiceLibrary(Store(self.base/'state'))
        self.voices=[self.library.create({'request_key':'explicit-dialogue-voice-key-'+str(i),'definition':definition(provider_voice_id='fixture-'+str(i),
            rights_status='owner_declared',license='Explicit fixture only',source_reference='fixture://preset',permission_reference='Fixture declaration, not real rights')},actor_ref='EXPLICIT FIXTURE') for i in (1,2,3)]
    def tearDown(self):self.temp.cleanup()
    def cast(self,char,voice):return {'character_id':char,'voice_id':voice['voice_id'],'voice_version':voice['version'],'voice_sha256':voice['definition_sha256']}
    def config(self):return {'characters':[{'character_id':CHAR_A,'name':'An'},{'character_id':CHAR_B,'name':'Bình'}],
        'casting':[self.cast(CHAR_A,self.voices[0]),self.cast(CHAR_B,self.voices[1])],
        'lines':[{'line_id':LINE_A,'character_id':CHAR_A,'shot_id':'shot_'+'1'*32,'text':'Vang Nguyễn giới thiệu.'},
            {'line_id':LINE_B,'character_id':CHAR_B,'shot_id':'shot_'+'1'*32,'text':'Vinhomes Saigon Park.'}]}
    def plan(self,config=None,signature='1'*64):return build(config or self.config(),self.library,provider_signatures={'explicit-fixture':signature})

    def test_character_voice_change_only_changes_that_characters_synthesis_inputs(self):
        old=self.plan();config=self.config();config['casting'][0]=self.cast(CHAR_A,self.voices[2]);new=self.plan(config);change=affected(old,new)
        self.assertEqual(change['requires_synthesis_line_ids'],[LINE_A]);self.assertEqual(change['eligible_for_verified_cache_reuse_line_ids'],[LINE_B])
        self.assertTrue(change['audio_mix_invalidated']);self.assertTrue(change['subtitle_input_invalidated']);self.assertTrue(change['final_export_invalidated'])
        self.assertEqual(change['visual_asset_regeneration_ids'],[]);self.assertEqual(change['provider_calls'],0);self.assertFalse(change['cache_bytes_verified'])
        self.assertEqual(new['lines'][1]['synthesis_input_sha256'],old['lines'][1]['synthesis_input_sha256'])

    def test_text_edit_changes_only_its_line_and_keeps_measured_values_unknown(self):
        old=self.plan();config=self.config();config['lines'][0]['text']='Vinhomes Green Paradise Cần Giờ.';new=self.plan(config)
        self.assertEqual(affected(old,new)['requires_synthesis_line_ids'],[LINE_A])
        for line in new['lines']:
            self.assertIsNone(line['measured_duration_seconds']);self.assertIsNone(line['audio_asset_reference']);self.assertIsNone(line['actual_cost'])
        self.assertFalse(new['execution_ready']);self.assertEqual(new['timing_basis'],'pending_measured_per_line_audio')

    def test_pause_and_reorder_rebuild_mix_and_subtitles_without_resynthesizing_speech(self):
        old=self.plan();config=self.config();config['lines'][0]['pause_after_seconds']=.7;pause=self.plan(config)
        change=affected(old,pause);self.assertEqual(change['requires_synthesis_line_ids'],[]);self.assertTrue(change['audio_mix_invalidated']);self.assertTrue(change['subtitle_input_invalidated'])
        config=self.config();config['lines'].reverse();order=affected(old,self.plan(config))
        self.assertEqual(order['requires_synthesis_line_ids'],[]);self.assertTrue(order['audio_mix_invalidated'])

    def test_character_display_name_only_changes_speaker_caption_input(self):
        old=self.plan();config=self.config();config['characters'][0]['name']='Tên nhân vật đã sửa';change=affected(old,self.plan(config))
        self.assertEqual(change['requires_synthesis_line_ids'],[]);self.assertFalse(change['audio_mix_invalidated']);self.assertTrue(change['subtitle_input_invalidated'])

    def test_optional_narrator_is_excluded_by_default_and_added_only_with_explicit_selection(self):
        config=self.config();config['characters'].append({'character_id':CHAR_N,'name':'Dẫn chuyện','role':'narrator'})
        config['lines'].append({'line_id':LINE_N,'character_id':CHAR_N,'shot_id':'shot_'+'1'*32,'text':'Lời dẫn tùy chọn.'})
        old=self.plan(config);self.assertEqual(len(old['lines']),2);self.assertEqual(old['excluded_lines'],[{'line_id':LINE_N,'reason':'narrator_disabled'}])
        config['narrator_enabled']=True;draft=self.plan(config);self.assertIn({'line_id':LINE_N,'reason':'voice_selection_required'},draft['needs_attention'])
        config['casting'].append(self.cast(CHAR_N,self.voices[2]));new=self.plan(config)
        self.assertEqual(affected(old,new)['requires_synthesis_line_ids'],[LINE_N]);self.assertEqual(new['lines'][-1]['speaker_role'],'narrator')

    def test_same_voice_and_text_can_reuse_fingerprint_across_projects_within_workspace(self):
        first=self.plan();config=self.config();config['lines'][0]['line_id']=LINE_N;second=self.plan(config)
        self.assertEqual(first['lines'][0]['synthesis_input_sha256'],second['lines'][0]['synthesis_input_sha256'])
        self.assertTrue(affected(first,second)['cache_lookup_required_before_provider_dispatch'])
        other_root=self.base/'other';other_store=Store(other_root);(other_root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':'wsp_other'}))
        other=NativeVoiceLibrary(other_store,workspace_id='wsp_other');new_config=copy.deepcopy(self.config())
        for i,cast in enumerate(new_config['casting']):
            voice=other.create({'request_key':'explicit-other-workspace-'+str(i),'definition':self.voices[i]['definition']},actor_ref='fixture');cast.update(voice_id=voice['voice_id'],voice_sha256=voice['definition_sha256'])
        foreign=build(new_config,other,provider_signatures={'explicit-fixture':'1'*64})
        self.assertNotEqual(first['lines'][0]['synthesis_input_sha256'],foreign['lines'][0]['synthesis_input_sha256'])
        with self.assertRaisesRegex(WorkflowError,'WORKSPACE_INVALID'):affected(first,foreign)

    def test_provider_revision_invalidates_both_voices_and_missing_provider_never_becomes_ready(self):
        old=self.plan();new=self.plan(signature='2'*64);self.assertEqual(affected(old,new)['requires_synthesis_line_ids'],[LINE_A,LINE_B])
        unconfigured=build(self.config(),self.library);self.assertFalse(unconfigured['execution_ready'])
        self.assertTrue(all('provider_not_configured' in line['needs_attention'] for line in unconfigured['lines']))

    def test_proper_name_changes_need_visible_review_and_nfc_is_preserved(self):
        config=self.config();config['lines'][0]['text']='Vang Nguyen ở Green Paradise Cần Giờ.';plan=self.plan(config)
        line=plan['lines'][0];self.assertEqual(line['tts_text'],'Vang Nguyễn ở Vinhomes Green Paradise Cần Giờ.')
        self.assertIn('proper_name_review_required',line['needs_attention']);self.assertNotEqual(line['reviewed_text'],line['tts_text'])

    def test_changed_plan_or_invalid_provider_signature_is_rejected(self):
        plan=self.plan();changed=copy.deepcopy(plan);changed['lines'][0]['text']='changed without recomputing plan'
        with self.assertRaisesRegex(WorkflowError,'PLAN_CHANGED'):affected(plan,changed)
        for signatures in ([],{'explicit-fixture':'raw-credential-is-not-a-signature'},{'https://not-a-provider':'1'*64}):
            with self.subTest(signatures=signatures),self.assertRaisesRegex(WorkflowError,'SIGNATURE_INVALID'):build(self.config(),self.library,provider_signatures=signatures)

if __name__=='__main__':unittest.main()

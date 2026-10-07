"""Configured niches share the same Native engine; no external/account acceptance."""
import copy,json
from pathlib import Path
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native import channel_profiles as channels,auto_edit_timeline as timeline,source_render
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.tests import test_source_preview as fixture

class ChannelProfileTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source

    def create_profile(self,reference='ai-education-reference@1'):
        self.project=self.store.create('Explicit configured channel fixture','','media',channel_profile=channels.select(reference))
        self.project=self.store.append_media(self.project['id'],self.project['revision'],self.asset)
        return self.real_source()

    def test_catalog_has_two_typed_niches_with_explicit_disabled_distribution_and_analytics(self):
        value=channels.catalog();self.assertEqual({item['niche_profile']['niche'] for item in value['profiles']},{'technology','real_estate'})
        for item in value['selections']:
            self.assertFalse(item['profile']['publishing_profile']['enabled']);self.assertFalse(item['profile']['analytics_profile']['enabled'])
            self.assertEqual(item['profile']['analytics_profile']['provider_status'],'NOT_CONFIGURED');self.assertEqual(item['external_dispatches'],0)
        for changes in [{'publish_enabled':True},{'publishing_profile':{**value['profiles'][0]['publishing_profile'],'enabled':True}},
            {'analytics_profile':{**value['profiles'][0]['analytics_profile'],'enabled':True}},{'voice_profile_sha256':'a'*64}]:
            with self.subTest(fields=list(changes)),self.assertRaises(ValidationError):channels.ChannelProfile.model_validate({**value['profiles'][0],**changes})

    def test_frozen_technology_profile_binds_source_defaults_and_real_audio_metadata_without_mutation(self):
        original=self.store.get(self.project['id']);source=self.create_profile();before=self.store.get(self.project['id']);sha=file_sha(source)
        selection=before['document']['channel_profile'];state=timeline.validate_document(before['document'])
        self.assertEqual(before['document']['niche'],'technology');self.assertEqual(before['document']['brand_template']['brand']['id'],'vf-ai-education')
        self.assertEqual(state['snapshot']['metadata']['channel_selection_sha256'],selection['selection_sha256'])
        self.assertEqual(state['snapshot']['metadata']['subtitle_template_ref'],'sentence-clean@v1');self.assertEqual(state['snapshot']['metadata']['source_preview_mode'],'final_effects')
        self.assertIsNone(before['approval']);self.assertEqual([job['kind'] for job in before['jobs']],['auto_edit_analysis'])
        directory=self.root/'real-profile-prepare';directory.mkdir();source_render.prepare_project(self.config,before,directory,'explicit-profile-preparation')
        manifest=json.loads((directory/'timeline-render.json').read_bytes());self.assertEqual(manifest['metadata']['niche'],'technology');self.assertEqual(manifest['brand']['name'],selection['brand_template']['brand']['name'])
        self.assertEqual(self.store.get(before['id']),before);self.assertEqual(self.store.get(original['id']),original);self.assertEqual(file_sha(source),sha)

    def test_reopening_and_later_catalog_removal_never_changes_frozen_profile(self):
        self.create_profile();before=self.store.get(self.project['id']);chosen=before['document']['channel_profile']
        with patch.object(channels,'CATALOG',self.root/'explicit-missing-future-catalog.json'):
            self.assertEqual(channels.resolve(self.store.get(self.project['id'])['document']),chosen)
            self.assertEqual(timeline.validate_document(before['document']),before['document']['canonical_timeline'])
        self.assertEqual(self.store.get(before['id']),before)

    def test_snapshot_and_rehashed_wrong_niche_style_or_timeline_binding_fail_closed(self):
        self.create_profile();document=self.project['document']
        for mutate in [lambda value:value['channel_profile']['profile'].update(name='CHANGED'),
            lambda value:value.update(niche='custom'),lambda value:value['channel_profile'].pop('catalog_sha256')]:
            copied=copy.deepcopy(document);mutate(copied)
            with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_CHANGED'):channels.resolve(copied)
        copied=copy.deepcopy(document);snapshot=copied['canonical_timeline']['snapshot'];snapshot['metadata']['channel_selection_sha256']='a'*64;copied['canonical_timeline']['sha256']=digest(snapshot)
        with self.assertRaisesRegex(WorkflowError,'TIMELINE_BINDING_CHANGED'):timeline.validate_document(copied)

    def test_generic_new_niche_requires_only_catalog_configuration_and_no_core_mapping(self):
        document=json.loads(channels.CATALOG.read_text(encoding='utf-8'));profile=copy.deepcopy(document['profiles'][0]);profile['profile_ref']='knowledge-reference@1'
        profile['niche_profile'].update(profile_ref='knowledge-education@1',niche='knowledge',name='Knowledge example');document['profiles'].append(profile)
        custom=self.root/'explicit-additive-profile-config.json';custom.write_text(json.dumps(document),encoding='utf-8')
        with patch.object(channels,'CATALOG',custom):selection=channels.select('knowledge-reference@1')
        project=self.store.create('Knowledge configuration fixture','','media',channel_profile=selection)
        self.assertEqual(project['document']['niche'],'knowledge');self.assertEqual(channels.resolve(project['document']),selection);self.assertEqual(project['jobs'],[])

    def test_conflicting_content_profile_unknown_reference_and_bad_catalog_never_create_projects(self):
        before=self.store.list()
        with self.assertRaisesRegex(WorkflowError,'CONTENT_PROFILE_CONFLICT'):
            self.store.create('Conflict fixture','','media',channel_profile=channels.select('ai-education-reference@1'),content_profile={'id':'vietnam-property','name':'Explicit conflict'})
        for reference in [None,True,'unknown@1','../../escape@1']:
            with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):channels.select(reference)
        bad=self.root/'explicit-invalid-catalog.json';bad.write_text('{"schema_version":"invalid"}')
        with patch.object(channels,'CATALOG',bad),self.assertRaisesRegex(WorkflowError,'CATALOG_INVALID'):channels.catalog()
        self.assertEqual(self.store.list(),before)

    def test_unselected_legacy_source_keeps_its_current_defaults(self):
        self.real_source();metadata=self.project['document']['canonical_timeline']['snapshot']['metadata']
        self.assertNotIn('channel_profile',self.project['document']);self.assertNotIn('channel_selection_sha256',metadata)
        self.assertNotIn('subtitle_template_ref',metadata);self.assertIsNone(channels.resolve(self.project['document']))

if __name__=='__main__':unittest.main()

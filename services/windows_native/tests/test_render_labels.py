"""Configuration-based text without rewriting legacy frozen brand snapshots."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services.windows_native import render_labels as labels,channel_profiles,branding
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.store import Store

class RenderLabelTests(unittest.TestCase):
    def document(self,brand='vf-ai-education'):
        return {'brand_template':{'brand':{'id':brand}},'render_labels':labels.freeze(brand)}
    def test_legacy_document_is_exact_and_readable_without_any_label_configuration(self):
        old={'brand_template':branding.choose('vf-ai-education','ai-education-30'),'legacy_snapshot':'unchanged'};before=copy.deepcopy(old)
        with patch.object(labels,'CATALOG',Path('missing-owned-label-config.json')):
            self.assertEqual(labels.resolve(old),'Phối cảnh minh họa')
        self.assertEqual(old,before)
    def test_new_technology_property_and_unlisted_niche_labels_are_configuration_driven(self):
        self.assertEqual(labels.resolve(self.document()),'Minh họa kỹ thuật')
        self.assertEqual(labels.resolve(self.document('vf-reference')),'Phối cảnh minh họa')
        self.assertEqual(labels.resolve(self.document('knowledge-course')),'Minh họa')
        self.assertEqual(branding.choose('vf-ai-education','ai-education-30')['template']['purpose'],'education')
    def test_saved_label_survives_config_change_and_removal_without_live_lookup(self):
        document=self.document();before=copy.deepcopy(document)
        with tempfile.TemporaryDirectory() as name:
            file=Path(name)/'labels.json';data=json.loads(labels.CATALOG.read_bytes());data['brand_overrides'][-1].update(profile_ref='technology-illustration@2',illustration_label='Dữ liệu minh họa');file.write_text(json.dumps(data),encoding='utf-8')
            with patch.object(labels,'CATALOG',file):
                self.assertEqual(labels.resolve(document),'Minh họa kỹ thuật')
                self.assertEqual(labels.resolve(self.document()),'Dữ liệu minh họa')
            with patch.object(labels,'CATALOG',Path(name)/'missing.json'):self.assertEqual(labels.resolve(document),'Minh họa kỹ thuật')
        self.assertEqual(document,before)
    def test_brand_mismatch_digest_extra_field_and_control_characters_reject(self):
        before=self.document()
        for mutate in [lambda d:d['brand_template']['brand'].update(id='vf-reference'),
                       lambda d:d['render_labels']['labels'].update(illustration_label='Changed'),
                       lambda d:d['render_labels'].update(snapshot_sha256='0'*64),
                       lambda d:d['render_labels'].update(extra='forged')]:
            changed=copy.deepcopy(before);mutate(changed)
            with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_CHANGED'):labels.resolve(changed)
        for text in ['', ' white space ', 'line\nbreak', 'nul\x00', 'x'*41]:
            changed=copy.deepcopy(before);changed['render_labels']['labels']['illustration_label']=text
            changed['render_labels']['labels_sha256']=digest(changed['render_labels']['labels'])
            changed['render_labels']['snapshot_sha256']=digest({k:v for k,v in changed['render_labels'].items() if k!='snapshot_sha256'})
            with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_CHANGED'):labels.resolve(changed)
    def test_creation_freezes_and_explicit_brand_edit_rebinds_without_jobs_or_approval(self):
        with tempfile.TemporaryDirectory() as name:
            store=Store(Path(name));project=store.create('Technology label fixture','Owned manual fixture',channel_profile=channel_profiles.select('ai-education-reference@1'))
            initial=copy.deepcopy(project['document']['render_labels']);self.assertEqual(labels.resolve(project['document']),'Minh họa kỹ thuật')
            changed=store.set_brand(project['id'],project['revision'],'vf-reference','property-30')
            self.assertEqual(labels.resolve(changed['document']),'Phối cảnh minh họa');self.assertIsNone(changed['approval']);self.assertEqual(changed['jobs'],[])
            with store.transaction() as con:
                historical=json.loads(con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=1',(project['id'],)).fetchone()[0])
            self.assertEqual(historical['render_labels'],initial)
    def test_invalid_config_cannot_partially_create_a_channel_project(self):
        with tempfile.TemporaryDirectory() as name:
            store=Store(Path(name));profile=channel_profiles.select('ai-education-reference@1');before=store.list()
            with patch.object(labels,'CATALOG',Path(name)/'missing.json'),self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):
                store.create('Must not persist','Owned fixture',channel_profile=profile)
            self.assertEqual(store.list(),before)

if __name__=='__main__':unittest.main()

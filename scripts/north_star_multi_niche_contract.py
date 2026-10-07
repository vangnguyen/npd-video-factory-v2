"""Retain configuration-only non-property planning proof, with explicit mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run(data_root, output_root):
    for path in (data_root, output_root):
        if path.exists() or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in [path, *path.parents]):
            raise ValueError('FRESH_UNLINKED_ROOT_REQUIRED')
    data_root.mkdir(parents=True, exist_ok=False); output_root.mkdir(parents=True, exist_ok=False)
    from services.windows_native.tests.test_multi_niche import build_tech_project
    from services.windows_native import branding
    from services.windows_native.contracts import digest
    from services.windows_native.production_intelligence import ProductionIntelligence
    from services.windows_native.store import Store
    exports = {}
    def export(name, value):
        path = output_root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        exports[name] = {'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size}
    baseline = '75d0391d364e84e3584f060aaf4c8a822578b67d'
    core = ['intelligence_service.py', 'idea_engine.py', 'idea_scoring.py', 'research.py',
        'production_intelligence.py', 'store.py', 'pipeline.py', 'editor.py', 'branding.py', 'media.py', 'contracts.py']
    source_hashes, blob_hashes, lineending_differences = {}, {}, []
    for name in core:
        relative = 'services/windows_native/' + name
        old = subprocess.check_output(['git', 'show', baseline + ':' + relative], cwd=ROOT)
        current_bytes = (ROOT / relative).read_bytes()
        assert old.replace(b'\r\n', b'\n') == current_bytes.replace(b'\r\n', b'\n'), relative
        blob_hashes[relative] = hashlib.sha256(old).hexdigest()
        if old != current_bytes: lineending_differences.append(relative)
        source_hashes[relative] = sha(ROOT / relative)
    preservation = {}
    for name, list_key, identity in [('intelligence.json', 'profiles', 'id'), ('production-intelligence.json', 'profiles', 'profile_id')]:
        relative = 'services/windows_native/profiles/' + name
        previous = json.loads(subprocess.check_output(['git', 'show', baseline + ':' + relative], cwd=ROOT))
        current = json.loads((ROOT / relative).read_bytes())
        old_profiles = {p[identity]: p for p in previous[list_key]}
        new_profiles = {p[identity]: p for p in current[list_key]}
        assert all(new_profiles[k] == v for k, v in old_profiles.items())
        assert all(current[k] == previous[k] for k in previous if k != list_key)
        preservation[name] = {'original_profiles_retained_exactly': list(old_profiles),
            'additional_profiles': sorted(set(new_profiles) - set(old_profiles)), 'other_configuration_unchanged': True}
    relative = 'services/windows_native/profiles/catalog.json'
    previous = json.loads(subprocess.check_output(['git', 'show', baseline + ':' + relative], cwd=ROOT))
    current = json.loads((ROOT / relative).read_bytes())
    assert current['defaults'] == previous['defaults'] and current['durations'] == previous['durations']
    for key in ['brands', 'template_families']:
        now = {p['id']: p for p in current[key]}
        assert all(now[p['id']] == p for p in previous[key])
    preservation['catalog.json'] = {'original_brands_families_defaults_and_durations_unchanged': True,
        'new_brand': 'vf-ai-education', 'new_family': 'ai-education'}
    config, store, intelligence, project, bundle, preserved = build_tech_project(data_root)
    shot_view = store.shot_view(project['id'])
    # A first reviewable editor operation persists the legacy projection into
    # the existing canonical timeline; it does not dispatch voice or media.
    project = store.mutate_shots(project['id'], project['revision'], {'type': 'reorder',
        'shot_ids': [s['shot_id'] for s in shot_view['shot_timeline']['shots']]})
    profiles = ProductionIntelligence(config, store, intelligence).profiles()
    assert len(profiles['profiles']) == 6 and len(profiles['brand_templates']['templates']) == 30
    assert Store(data_root).get(project['id'])['document'] == project['document']
    assert Store(data_root).get(preserved['id']) == preserved
    assert project['approval'] is None and project['jobs'] == [] and all(s['source_type'] == 'test_fixture' for s in bundle['sources'])
    export('profiles.json', profiles)
    export('research-evidence.json', {'sources': bundle['sources'], 'findings': bundle['findings'], 'run': bundle['run']})
    export('idea-shortlist.json', bundle['ideas'])
    export('selected-idea.json', next(i for i in bundle['ideas'] if i['id'] == bundle['brief']['idea_id']))
    export('brief.json', bundle['brief'])
    export('project.json', project)
    export('storyboard-plan.json', project['document']['edit_plan'])
    export('canonical-timeline.json', project['document']['canonical_timeline'])
    export('brand-template.json', project['document']['brand_template'])
    export('asset-provenance.json', project['document']['assets'])
    export('preservation.json', preservation)
    export('contract-receipt.json', {'schema': 'north-star-multi-niche-contract-v1', 'baseline_head': baseline,
        'core_source_unchanged': True, 'core_source_sha256': source_hashes, 'baseline_git_blob_sha256': blob_hashes,
        'core_comparison_basis': 'exact bytes after CRLF-to-LF normalization; raw runtime/blob hashes retained separately',
        'raw_source_lineending_difference_paths': lineending_differences,
        'executed_source_sha256': {p: sha(ROOT / p) for p in ['scripts/north_star_multi_niche_contract.py',
            'services/windows_native/tests/test_multi_niche.py', 'services/windows_native/profiles/intelligence.json',
            'services/windows_native/profiles/production-intelligence.json', 'services/windows_native/profiles/catalog.json']},
        'profile': 'ai-education', 'brand': 'vf-ai-education', 'template': 'ai-education-30',
        'research_and_ideas': 'explicit fixtures; not real provider/trend observations',
        'brief_review': 'explicit mock gate exercise; not Owner UAT', 'script': 'explicit technology fixture; not AI generation',
        'actual_provider_calls': 0, 'source_publication_dates_unknown': True, 'full_render_executed': False,
        'duration_policy': branding.FIT_NARRATION_POLICY,
        'duration_policy_calculation_only': {'hypothetical_voice_seconds': 5,
            'calculated_total_seconds': branding.measured_duration(project['document'], 5), 'actual_voice_generated': False},
        'project_and_final_human_approval_still_required': True, 'script_media_and_narration_are_not_certified': True,
        'canonical_timeline_sha256': digest(project['document']['canonical_timeline']), 'restart_exact': True,
        'preserved_other_project_unchanged': True, 'real_provider_tested': False, 'production_deployed': False,
        'exports': exports})
    print(json.dumps({'status': 'CONFIGURATION_ONLY_MULTI_NICHE_CONTRACT_PASS', 'exports': len(exports),
        'core_source_unchanged': True, 'full_render_executed': False, 'owner_uat_accepted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.data_root, args.output_root)

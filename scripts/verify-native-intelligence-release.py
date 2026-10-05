"""Read-only release/restart evidence. Does not dispatch providers or approve content."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import importlib.metadata as metadata
import json
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical, digest, file_sha
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config, verify_runtime
from services.windows_native.store import Store


def tables(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        result = {}
        for row in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
            values = [dict(r) for r in con.execute('SELECT * FROM "' + row['name'] + '" ORDER BY rowid')]
            result[row['name']] = {"ddl": row['sql'], "rows": len(values), "rows_sha256": digest(values)}
        return result, con.execute("PRAGMA user_version").fetchone()[0]


def main():
    args = argparse.ArgumentParser()
    args.add_argument("output", type=Path)
    target = args.parse_args().output
    if target.exists():
        raise SystemExit("Evidence target already exists; preserve the earlier capture")
    repo = Path(__file__).resolve().parents[1]
    evidence = repo / "evidence/post-mvp-roadmap/phase-9"
    baseline = json.loads((evidence / "release-baseline.json").read_bytes())
    manifest = json.loads((evidence / "idea-brief-review-manifest.json").read_bytes())
    config = Config()
    native, native_version = tables(config.data_root / "workflow.sqlite3")
    intelligence, intelligence_version = tables(config.data_root / "intelligence.sqlite3")
    with sqlite3.connect(f"file:{config.data_root / 'workflow.sqlite3'}?mode=ro", uri=True) as con:
        active_native = con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]
    with sqlite3.connect(f"file:{config.data_root / 'intelligence.sqlite3'}?mode=ro", uri=True) as con:
        active_intelligence = con.execute("SELECT count(*) FROM operations WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]
        decisions = [r[0] for r in con.execute("SELECT action FROM decisions")]
    assert not active_native and not active_intelligence, "Active jobs: defer restart"
    assert native == baseline['tables'], "Accepted production rows/schema changed: inspect before restart"
    accepted_evidence = {name: file_sha(repo / 'evidence/post-mvp-roadmap/phase-8' / name)
                         for name in baseline['accepted_evidence']}
    assert accepted_evidence == baseline['accepted_evidence'], "Accepted evidence changed"
    accepted_videos = {str(v['number']): file_sha(Path(v['path'])) for v in baseline['final_videos']}
    assert all(accepted_videos[str(v['number'])] == v['sha256'] for v in baseline['final_videos'])
    dependencies = sorted([{'name': d.metadata['Name'], 'version': d.version}
                           for d in metadata.distributions()], key=lambda d: d['name'].lower())
    assert dependencies == baseline['dependencies'], "Runtime dependency versions changed"
    service = IntelligenceService(config, Store(config.data_root))
    cases = []
    for case in manifest['cases']:
        run = service.store.get(case['run_id'], 'ResearchRun')
        sources = [service.store.get(i, 'ResearchSource') for i in run['source_ids']]
        findings = [service.store.get(i, 'ResearchFinding') for i in run['finding_ids']]
        service.verify_sources(sources, findings)
        ideas = [service.store.get(i, 'ContentIdea') for i in run['idea_ids']]
        assert len(ideas) == 5
        opportunity = service.store.get(run['opportunity_id'], 'Opportunity')
        cases.append({'number': case['number'], 'run_id': run['id'], 'source_integrity': 'PASS',
                      'ideas': len(ideas), 'selected_idea_id': opportunity['selected_idea_id'],
                      'brief_id': opportunity['brief_id'], 'production_project_id': opportunity['production_project_id']})
    git = lambda *values: subprocess.check_output([str(config.git), *values], cwd=repo, text=True).strip()
    result = {'captured_at': datetime.now(timezone.utc).isoformat(), 'implementation_head_sha': git('rev-parse', 'HEAD'),
              'baseline_sha': baseline['head_sha'], 'branch': git('branch', '--show-current'),
              'active_native_jobs': active_native, 'active_intelligence_operations': active_intelligence,
              'production_tables': native, 'intelligence_tables': intelligence,
              'schema_versions': {'native_sqlite_user_version': native_version, 'intelligence_sqlite_user_version': intelligence_version},
              'existing_production_tables_and_rows_unchanged': True, 'accepted_evidence_unchanged': True,
              'accepted_ten_video_bytes_unchanged': True, 'runtime_dependency_versions_unchanged': True,
              'runtime': verify_runtime(config, full=True), 'cases': cases,
              'review_bundle_sha256': file_sha(evidence/'idea-brief-review-bundle.md'),
              'review_manifest_sha256': file_sha(evidence/'idea-brief-review-manifest.json'),
              'human_selection_decisions': sum(a == 'human_selected_idea' for a in decisions),
              'human_brief_approval_decisions': sum(a == 'human_approved_brief' for a in decisions),
              'provider_calls_created_by_this_check': 0, 'human_approvals_created_by_this_check': 0}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical(result))
    print(json.dumps({'evidence': str(target), 'cases': len(cases), 'source_integrity': 'PASS',
                      'accepted_release_unchanged': True, 'active_jobs': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()

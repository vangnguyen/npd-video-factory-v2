"""Read-only release capture; accepted Phase 8 evidence is never rewritten."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib.metadata as metadata
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from services.windows_native.contracts import canonical, digest, file_sha
from services.windows_native.pipeline import Config, verify_runtime

repo = Path(__file__).resolve().parents[1]
config = Config()
evidence = repo / "evidence/post-mvp-roadmap/phase-9"
evidence.mkdir(parents=True, exist_ok=True)
target = evidence / "release-baseline.json"
if target.exists():
    raise SystemExit("Baseline already exists; do not replace a release capture")
git = lambda *args: subprocess.check_output([str(config.git), *args], cwd=repo, text=True).strip()
head = git("rev-parse", "HEAD")
if git("diff", "--name-only", "9c3e9e9dfa61fe29f76380f6811f4db1b0a26257", "--", "services/windows_native", "apps/studio-web"):
    raise SystemExit("Accepted application code changed")
phase8 = repo / "evidence/post-mvp-roadmap/phase-8"
certificate = json.loads((phase8 / "release-certification.json").read_bytes())
assert certificate["INTERNAL_PRODUCTION_READY"] == "YES" and all(certificate["checks"].values())
con = sqlite3.connect(f"file:{config.data_root / 'workflow.sqlite3'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
tables = {}
for row in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
    rows = [dict(r) for r in con.execute('SELECT * FROM "' + row['name'] + '" ORDER BY rowid')]
    tables[row['name']] = {"ddl": row['sql'], "rows": len(rows), "rows_sha256": digest(rows)}
videos = []
for item in certificate['acceptance_matrix']:
    job = dict(con.execute("SELECT * FROM jobs WHERE id=?", (item['job_id'],)).fetchone())
    review = dict(con.execute("SELECT * FROM render_reviews WHERE job_id=? ORDER BY id DESC LIMIT 1", (item['job_id'],)).fetchone())
    path = config.data_root / "jobs" / item['job_id'] / "final.mp4"
    assert job['status'] == 'succeeded' and review['decision'] == 'approve'
    assert file_sha(path) == item['actual_mp4_sha256'] == review['artifact_sha256']
    videos.append({"number": item['number'], "project_id": item['project_id'], "job_id": item['job_id'],
                   "path": str(path), "sha256": file_sha(path), "human_review": review})
backup = Path(r"C:\NPD-Video-Factory\post-mvp-validation") / ("owner-phase9-release-freeze-" + head[:12] + ".sqlite3")
if backup.exists():
    raise SystemExit("Freeze backup already exists")
with sqlite3.connect(backup) as dest:
    con.backup(dest)
con.close()
result = {"captured_at": datetime.now(timezone.utc).isoformat(), "branch": git("branch", "--show-current"),
          "head_sha": head, "accepted_application_sha": "9c3e9e9dfa61fe29f76380f6811f4db1b0a26257",
          "INTERNAL_PRODUCTION_READY": "YES", "scope": certificate['scope'], "tables": tables,
          "schema_versions": {"sqlite": "seven additive native tables; DDL captured", "project_input": "project-input-v1",
                              "editor": "native-editor-v1", "brand_template": "native-brand-template-v1",
                              "canonical_timeline": "1.1", "checkpoint": 1, "voice_profile": 1},
          "runtime": verify_runtime(config, full=True), "python": sys.version,
          "dependencies": sorted([{"name": d.metadata['Name'], "version": d.version} for d in metadata.distributions()], key=lambda d: d['name'].lower()),
          "native_test_log": {"result": "103/103 PASS", "sha256": file_sha(repo/'evidence/post-mvp-roadmap/phase-7/native-tests-fixed.log')},
          "studio_test_log": {"result": "27/27 PASS", "sha256": file_sha(repo/'evidence/post-mvp-roadmap/phase-7/studio-tests.log')},
          "accepted_evidence": {p.name: file_sha(p) for p in sorted(phase8.iterdir()) if p.is_file()},
          "final_videos": videos, "backup": {"path": str(backup), "sha256": file_sha(backup)},
          "automatic_provider_calls": 0, "existing_evidence_modified": False}
target.write_bytes(canonical(result))
print(json.dumps({"baseline": head, "accepted_videos": len(videos), "integrity": "ok", "runtime": result['runtime']}, ensure_ascii=False))

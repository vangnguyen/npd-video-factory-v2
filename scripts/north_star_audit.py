"""Render an evidence-indexed North Star audit; never infer readiness from existence."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'IMPLEMENTED_REAL', 'IMPLEMENTED_MOCK_ONLY', 'PARTIAL', 'INTERFACE_ONLY', 'MISSING', 'NOT_VERIFIED', 'BLOCKED_EXTERNAL'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    rows = json.loads((ROOT/'docs/north-star/capabilities.json').read_text(encoding='utf-8'))
    assert [r['id'] for r in rows] == list(range(1, 65))
    inventory = {}
    for row in rows:
        assert row['status'] in ALLOWED
        for field in ('source', 'behavior', 'gap', 'severity', 'dependency', 'wave', 'acceptance'):
            assert field in row and row[field] is not None, (row['id'], field)
        for source in row['source']:
            path = ROOT/source
            assert path.is_file(), (row['id'], source)
            inventory[source] = hashlib.sha256(path.read_bytes()).hexdigest()
    sections = re.findall(r'^# (\d+)\. (.+)$', (ROOT/'docs/CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md').read_text(encoding='utf-8'), re.M)
    assert [int(n) for n, _ in sections] == list(range(90))
    crosswalk = json.loads((ROOT/'docs/north-star/master-crosswalk.json').read_text(encoding='utf-8'))
    assert set(crosswalk) == {n for n, _ in sections}
    for ids in crosswalk.values():
        assert ids and all(1 <= i <= 64 for i in ids)
    text = ['# North Star capability matrix', '',
        'Authority: `CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md`, sections 0–89, plus VF-NORTH-STAR-COMPLETION-PROGRAM-01.', '',
        'Audit baseline: `2ced7bc81f9402368fb22c9e7aca242e740531af`. This matrix describes inspected source and its remaining behavior. IMPLEMENTED_REAL means executable non-fixture behavior exists; it does not certify real-provider acceptance or production deployment. Historical acceptance is preserved separately. Source hashes are in `docs/north-star/source-inventory.json`.', '',
        'The Native Studio and PostgreSQL Studio are separate implementations. Their existing analysis, media, publishing and analytics paths are not automatically available in the accepted Native workflow. This integration gap is P0. No phase report alone proves a requirement.', '',
        '## Capability audit', '',
        '| ID / requirement | Classification | Current source / behavior | Missing behavior | Severity / dependency / wave | Acceptance |',
        '| --- | --- | --- | --- | --- | --- |']
    for r in rows:
        sources = ', '.join(f'[{s}](../{s})' for s in r['source'])
        text.append(f"| {r['id']}. {r['name']} | {r['status']} | {sources}. {r['behavior']} | {r['gap']} | {r['severity']}; {r['dependency']}; Wave {r['wave']} | {r['acceptance']} |")
    text += ['', '## Complete Master Spec crosswalk', '',
        'Every numbered section has an explicit audit destination; governance and extraction requirements remain applicable. Historical migration evidence does not authorize deleting legacy code, merging main or deploying production.', '',
        '| Section | Audited capabilities |', '| --- | --- |']
    text += [f"| {n}. {title} | {', '.join(str(i) for i in crosswalk[n])} |" for n, title in sections]
    text += ['', '## Current acceptance state', '',
        '- SOURCE_PRESERVED = YES: pushed completion branch, verified full-history bundle, raw Git archive including unreachable objects, and 15 hash-verified accepted video backups.',
        '- Phase 8/9 certified states are historical YES; current source regression must continue passing.',
        '- PHASE10_READY = NO; OWNER_UAT_REQUIRED = YES. Repaired candidate videos are not self-accepted.',
        '- IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO for this completion program.',
        '- No external publication, paid provider call, production mutation or protected-main merge was performed.', '',
        '## Verification limits', '',
        'See `NORTH_STAR_BASELINE_2026.md` and `NORTH_STAR_WAVE_REPORTS.md` for exact commands, runtime failures, passing suites and evidence. The isolated Ubuntu baseline at 834d6db passed 1,896 tests with 5 skips, including the three POSIX modules unavailable on Windows; later changes require their own checks. Docker is not available on this host. Future changes must update both the machine-readable rows and this matrix. A NOT_CONFIGURED capability does not waive adapter implementation or mock contract acceptance.', '']
    (ROOT/'docs/NORTH_STAR_CAPABILITY_MATRIX.md').write_text('\n'.join(text), encoding='utf-8')
    (ROOT/'docs/north-star/source-inventory.json').write_text(json.dumps({'head': git('rev-parse','HEAD'), 'audited_at':datetime.now(timezone.utc).isoformat(), 'sha256':inventory}, indent=2), encoding='utf-8')
    print(json.dumps({'requirements':len(rows),'master_sections':len(sections),'source_files':len(inventory),'classification':dict(Counter(r['status'] for r in rows))}))


if __name__ == '__main__':
    main()

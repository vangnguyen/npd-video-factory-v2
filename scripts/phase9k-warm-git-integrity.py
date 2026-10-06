"""Verify portable warm voice evidence against committed Git blob bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import file_sha, write_json
from services.windows_native.pipeline import Config, REPO

PREFIX = 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03'
OUT = REPO / PREFIX
config = Config()
head = subprocess.check_output([str(config.git), 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
files = subprocess.check_output([str(config.git), 'ls-files', '-z', '--', PREFIX], cwd=REPO).decode().split('\0')
process = subprocess.Popen([str(config.git), 'cat-file', '--batch'], cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
entries = []
try:
    for name in filter(None, files):
        if name.endswith('/git-byte-integrity.json'):
            continue  # Receipt binds the evidence commit, not itself.
        process.stdin.write((head + ':' + name + '\n').encode())
        process.stdin.flush()
        header = process.stdout.readline().decode().strip().split()
        assert len(header) == 3 and header[1] == 'blob', name
        size = int(header[2]); raw = process.stdout.read(size)
        assert len(raw) == size and process.stdout.read(1) == b'\n'
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == file_sha(REPO / name), 'Git/working bytes differ: ' + name
        entries.append({'path': name, 'bytes': size, 'sha256': actual})
finally:
    process.stdin.close()
    process.wait(timeout=10)
assert process.returncode == 0
tracked = {entry['path'] for entry in entries}
media = [p for p in OUT.rglob('*') if p.is_file() and p.suffix.lower() in {'.wav', '.mp4'}]
assert all(p.relative_to(REPO).as_posix() in tracked for p in media), 'Required audio/video was ignored by Git'
owner = json.loads((OUT / 'owner-B-approval.json').read_bytes())
for name, sha256 in owner['frozen_prior_evidence'].items():
    assert file_sha(REPO / name) == sha256, 'Historical evidence changed: ' + name
result = {'evidence_commit_sha': head, 'tracked_byte_exact_files': len(entries),
          'tracked_byte_exact_bytes': sum(e['bytes'] for e in entries),
          'all_actual_WAV_and_MP4_files_tracked': len(media),
          'frozen_prior_evidence_unchanged': len(owner['frozen_prior_evidence']),
          'files': entries, 'human_final_video_approvals': 0, 'CONTENT_INTELLIGENCE_READY': 'NO'}
target = OUT / 'git-byte-integrity.json'
assert not target.exists(), 'Preserve earlier committed-byte receipt'
write_json(target, result)
print(json.dumps({k: v for k, v in result.items() if k != 'files'}))

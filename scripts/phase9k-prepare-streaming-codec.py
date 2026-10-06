"""Download two official files at the already pinned codec revision for trials.

The accepted runtime directory is left byte-exact. This separate trial directory
uses copies of the locked full decoder and shared weights, plus the SDK-supported
streaming decoder and its metadata from the same immutable upstream revision.
"""
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import file_sha, write_json
from services.windows_native.pipeline import Config, profile, verify_runtime


def main():
    from huggingface_hub import hf_hub_download
    verify_runtime(Config())
    root = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
    target = root / 'codec-streaming'
    target.mkdir(exist_ok=False)
    locked = profile()['rights']
    files = []
    for name in ('moss_audio_tokenizer_decode_full.onnx', 'moss_audio_tokenizer_decode_shared.data'):
        original = Path('C:/NPD-Video-Factory/runtime/models/moss-codec') / name
        shutil.copyfile(original, target / name)
        assert file_sha(original) == file_sha(target / name)
        files.append({'name': name, 'source': 'COPY_OF_ACCEPTED_LOCKED_RUNTIME', 'sha256': file_sha(original)})
    for name in ('codec_browser_onnx_meta.json', 'moss_audio_tokenizer_decode_step.onnx'):
        cached = Path(hf_hub_download(repo_id=locked['codec_repository'], filename=name,
                      revision=locked['codec_revision'], token=False))
        shutil.copyfile(cached, target / name)
        files.append({'name': name, 'source': 'OFFICIAL_UPSTREAM_AT_PINNED_REVISION',
                      'repository': locked['codec_repository'], 'revision': locked['codec_revision'],
                      'sha256': file_sha(target / name), 'bytes': (target / name).stat().st_size})
    meta = json.loads((target / 'codec_browser_onnx_meta.json').read_bytes())
    assert meta.get('streaming_decode'), 'OFFICIAL_STREAMING_METADATA_REQUIRED'
    verify_runtime(Config())
    write_json(root / 'streaming-codec-artifacts.json', {'classification': 'ISOLATED_EXPERIMENTAL_CODEC_DIRECTORY',
               'directory': str(target), 'accepted_runtime_changed': False,
               'repository': locked['codec_repository'], 'revision': locked['codec_revision'], 'files': files,
               'human_audio_quality_pass': False})
    print(json.dumps({'official_streaming_files_downloaded': 2, 'same_pinned_revision': locked['codec_revision'],
                      'accepted_runtime_unchanged': True}), flush=True)


if __name__ == '__main__': main()

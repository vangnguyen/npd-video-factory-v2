"""Compare real cached acoustic codes with full and official stateful decoding."""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import file_sha, write_json
from services.windows_native.pipeline import profile


def main():
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    root = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
    class CheckEngine(OnnxV3LiteEngine):
        def _load_denoiser(self): return None
    engine = CheckEngine(checkpoint_path='C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo',
                         onnx_dir='C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo/onnx_update',
                         codec_dir=str(root / 'codec-streaming'), threads=4)
    assert engine.sess_codec_step is not None and engine._codec_stream_spec
    records = []
    for case in (4, 1):
        source = root / f'case-{case:02}/generated-codes.npz'
        arrays = np.load(source, allow_pickle=False)
        for name in arrays.files:
            codes = arrays[name]
            full = engine._decode_codes(codes)
            state = engine._stream_new_state()
            parts = [engine._stream_decode(codes[i:i + 25], state) for i in range(0, len(codes), 25)]
            streamed = np.concatenate(parts)
            assert full.shape == streamed.shape and np.isfinite(streamed).all()
            difference = streamed.astype(np.float64) - full.astype(np.float64)
            maximum = float(np.abs(difference).max())
            rms = float(np.sqrt(np.mean(difference ** 2)))
            passed = maximum < 1e-4 and rms < 1e-5
            records.append({'case': case, 'call': name, 'frames': len(codes), 'sample_count': len(full),
                            'source_codes_file_sha256': file_sha(source), 'max_abs_difference': maximum,
                            'rms_difference': rms, 'same_duration': True, 'numerical_comparison_pass': passed})
    result = {'classification': 'REAL_LOCAL_DECODER_NUMERICAL_INTEGRATION_TEST',
              'official_repository': profile()['rights']['codec_repository'],
              'official_revision': profile()['rights']['codec_revision'], 'calls_compared': len(records),
              'tolerance': {'max_abs_difference_less_than': 1e-4, 'rms_difference_less_than': 1e-5},
              'all_pass': all(r['numerical_comparison_pass'] for r in records), 'calls': records,
              'human_audio_naturalness_pass': False, 'accepted_runtime_changed': False}
    write_json(root / 'stream-decoder-comparison.json', result)
    print(json.dumps({k: result[k] for k in ('calls_compared', 'all_pass', 'human_audio_naturalness_pass', 'accepted_runtime_changed')}), flush=True)
    assert result['all_pass'], 'STREAM_CODEC_NUMERICAL_COMPARISON_FAILED'


if __name__ == '__main__': main()

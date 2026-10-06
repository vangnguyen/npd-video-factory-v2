"""Use the already connected AssemblyAI adapter for real trial word timings.

One durable upload/transcript per trial; known responses can be observed without
replaying an uncertain paid operation. No content or Native project is changed.
"""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import Config, REPO
sys.path.insert(0, str(REPO / 'apps/api'))
from services.windows_native import assemblyai_connection as connection
from services.windows_native.asr import DurableTransport
from services.windows_native.contracts import WorkflowError, digest, file_sha, write_json
from app.assemblyai_asr_profile import ASSEMBLYAI_CREDENTIAL_ALIAS, assemblyai_asr_profile, assemblyai_profile_sha256
from app.assemblyai_transcription_provider import AssemblyAITranscriptionProvider
from app.auto_edit_models import MediaMetadata

ROOT = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')


def main(case):
    config = Config()
    assert connection.status(config)['connected'], 'Existing AssemblyAI connection required; never create credentials here'
    parent = ROOT / f'warm-sentence-case-{case:02}'
    folders = sorted(parent.glob('scene-*'))
    assert folders
    for folder in folders:
        source = folder / 'with-context.wav'
        assert source.is_file() and json.loads((folder / 'results.json').read_bytes())['observed_eos']
        with wave.open(str(source), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
            rate, channels = wav.getframerate(), wav.getnchannels()
        profile = assemblyai_asr_profile()
        binding = digest({'voice_sha256': file_sha(source), 'trial_sha256': file_sha(folder / 'trial.json'),
                          'profile_sha256': assemblyai_profile_sha256()})
        transport = DurableTransport(folder / 'provider', binding, lambda stage: print(
            json.dumps({'case': case, 'scene': folder.name, 'stage': stage}), flush=True))
        provider = AssemblyAITranscriptionProvider(model=profile.model, credential_alias=ASSEMBLYAI_CREDENTIAL_ALIAS,
                   credential_resolver=lambda _: connection.load_credential(config), profile=profile,
                   transport=transport, poll_interval_seconds=3)
        async def execute():
            return await asyncio.wait_for(provider.transcribe(source, metadata=MediaMetadata(media_kind='audio',
                detected_content_type='audio/wav', duration_seconds=duration, audio_channels=channels,
                audio_sample_rate=rate), checksum_sha256=file_sha(source)), timeout=180)
        try:
            transcript = asyncio.run(execute())
        except (ValueError, WorkflowError, TimeoutError) as error:
            code = error.code if isinstance(error, WorkflowError) else str(error)
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{1,119}', code): code = 'ASR_TRIAL_TIMING_FAILED'
            write_json(folder / 'timing-failure.json', {'classification': 'ACTUAL_PROVIDER_FAILURE', 'code': code,
                       'automatic_paid_replay': False, 'fixture_provider': False, 'human_audio_quality_pass': False})
            print(json.dumps({'case': case, 'scene': folder.name, 'failure': code}), flush=True)
            continue
        value = asdict(transcript); value.pop('actual_cost_vnd', None)
        raw = transport.load('provider-completed')
        assert raw and digest(raw) == value['provenance']['raw_response_sha256']
        write_json(folder / 'transcript.json', {'classification': 'REAL_EXISTING_PROVIDER_WORD_TIMINGS_FOR_EXPERIMENT',
                   'trial_sha256': file_sha(folder / 'trial.json'), 'voice_sha256': file_sha(source),
                   'transcript': value, 'provider_is_fixture': False, 'new_provider_added': False,
                   'model_fallback': False, 'automatic_paid_replay': False,
                   'speech_word_timestamps_are_not_human_audio_quality_acceptance': True})
        print(json.dumps({'case': case, 'scene': folder.name, 'status': 'actual_transcript_received',
                          'text': raw['text'], 'word_count': len(raw['words'])}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('case', type=int, choices=(1, 2, 4))
    main(parser.parse_args().case)

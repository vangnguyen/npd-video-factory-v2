"""Bound local-video result evidence to this source and frozen invocation."""
import copy
import json
import re
from .local_video_transcription_provider import LocalVideoEvidenceRejected
from .uploaded_audio_repository import digest


def frozen_video_binding(provider):
    value = getattr(provider, 'immutable_binding', None)
    if value is None:return None
    if (provider.key != 'local-faster-whisper' or provider.external_call is not False or provider.paid is not False
        or not isinstance(value, dict) or value.get('schema_version') != 'sql-local-video-runtime.v1'
        or value.get('input_media_kind') != 'video' or not callable(getattr(provider, 'verify', None))
        or digest({k:v for k,v in value.items() if k != 'sha256'}) != value.get('sha256')):
        raise ValueError('AUTO_EDIT_LOCAL_VIDEO_BINDING_INVALID')
    return copy.deepcopy(value)


def validated_evidence(value, binding, snapshot):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if not isinstance(value, dict) or len(encoded) > 32*1024*1024:return None
        valid = (value['schema_version'] == 'sql-local-video-evidence.v1'
            and value['immutable_binding'] == binding
            and value['source_sha256'] == snapshot['source_sha256']
            and type(value['source_size_bytes']) is int and value['source_size_bytes'] == snapshot['source_size_bytes']
            and isinstance(value['model_result'], dict) and digest(value['model_result']) == value['model_result_sha256']
            and isinstance(value['decoded_audio_clock'], dict) and digest(value['decoded_audio_clock']) == value['decoded_audio_clock_sha256']
            and re.fullmatch('[a-f0-9]{64}', value['pcm_sha256']) is not None
            and type(value['provider_result_normalized']) is bool and type(value['source_projection_validated']) is bool
            and value['source_checksum_verified_before_inference'] is True
            and (value['source_checksum_verified_after_result'] is None or value['source_checksum_verified_after_result'] is True)
            and type(value['provider_billed_cost_vnd']) is int and value['provider_billed_cost_vnd'] == 0
            and value['operating_electricity_hardware_cost_vnd'] is None
            and value['human_accepted'] is False and value['publishing_enabled'] is False)
        return copy.deepcopy(value) if valid else None
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError):
        return None


def rejected_evidence(error, binding, snapshot):
    if not isinstance(error, LocalVideoEvidenceRejected) or binding is None or snapshot is None:return None
    if digest(error.evidence) != error.evidence_sha256:return None
    value = validated_evidence(error.evidence, binding, snapshot)
    return value if value is not None and value.get('rejection_code') == error.code else None

"""Opt-in speech context policies; the accepted sentence policy stays the default."""
import json
from pathlib import Path

from .contracts import WorkflowError, digest


def registered_policy(identifier):
    policies = json.loads(Path(__file__).with_name('voice-quality-policies.json').read_bytes())
    if not isinstance(identifier, str) or identifier not in policies:
        raise WorkflowError('UNKNOWN_VOICE_QUALITY_POLICY', 400)
    return policies[identifier]


def policy_reference(identifier):
    value = registered_policy(identifier)
    return {'id': identifier, 'version': value['version'], 'sha256': digest(value)}


def resolve_policy(document):
    if 'voice_quality' not in document:
        return None
    reference = document['voice_quality']
    if not isinstance(reference, dict):
        raise WorkflowError('VOICE_QUALITY_POLICY_REFERENCE_INVALID', 400)
    value = registered_policy(reference.get('id'))
    if reference != policy_reference(value['id']):
        raise WorkflowError('VOICE_QUALITY_POLICY_CHANGED', 409)
    return value

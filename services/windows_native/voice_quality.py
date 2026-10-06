"""Opt-in speech context policies; the accepted sentence policy stays the default."""
import json
from pathlib import Path

from .contracts import WorkflowError, digest


def catalog():
    """Expose existing policy references without changing any accepted recipe."""
    policies = json.loads(Path(__file__).with_name('voice-quality-policies.json').read_bytes())
    labels = {'scene': 'Thùy Dung · theo cảnh', 'warm_scene': 'Thùy Dung · Giọng B (ngữ cảnh)'}
    choices = []
    for identifier, value in policies.items():
        if (not isinstance(value, dict) or value.get('id') != identifier
                or type(value.get('version')) is not int or value['version'] < 1
                or value.get('unit_grouping') not in labels):
            raise WorkflowError('VOICE_QUALITY_REGISTRY_INVALID', 503)
        # A registry display label is optional; grouping supplies the safe default
        # for the already frozen registry. Its bytes and reference hash stay intact.
        label = value.get('label', labels[value['unit_grouping']])
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 180:
            raise WorkflowError('VOICE_QUALITY_REGISTRY_INVALID', 503)
        choices.append({'id': identifier, 'version': value['version'], 'sha256': digest(value), 'label': label.strip()})
    return {'choices': choices, 'default': {'id': None, 'label': 'Thùy Dung · MVP đã nghiệm thu (theo câu)'},
            'human_listening_required': True, 'selection_requires_explicit_action': True}


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

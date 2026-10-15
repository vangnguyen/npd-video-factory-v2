"""Dedicated VF intent witnesses. HMAC only proves exact prior authorization.

It never proves that a request did or did not execute. Secret provisioning,
current human/source validation and SQL settlement belong to separate layers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

PURPOSE = 'video-factory:broll-prepare-intent:v1'
CLAIMS_VERSION = 'vf-broll-prepare-witness-claims.v1'
KEYRING_VERSION = 'vf-broll-request-witness-keys.v1'
DOMAIN = b'NPD-Video-Factory/Broll-Prepare-Intent-Witness/v1\n'
MAX_CLAIMS_BYTES = 262144
MAX_TTL = 30 * 86400
KEY_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class WitnessError(RuntimeError):
    def __init__(self, code='BROLL_WITNESS_INVALID', status=409):
        self.code, self.status = code, status
        super().__init__(code)


class WitnessEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, hide_input_in_errors=True)
    schema_version: Literal['vf-broll-request-witness.v1']
    key_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    claims_json: str = Field(min_length=1, max_length=MAX_CLAIMS_BYTES)
    signature: str = Field(pattern=r'^[a-f0-9]{64}$')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def parse_unique(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError('nonfinite')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def _integer(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


@dataclass(frozen=True)
class WitnessKey:
    key_id: str
    secret: bytes = field(repr=False)
    not_before: int
    sign_until: int
    verify_until: int
    state: Literal['active', 'verify_only', 'revoked']

    def __post_init__(self):
        if (not isinstance(self.key_id, str) or not KEY_ID.fullmatch(self.key_id)
                or type(self.secret) is not bytes or len(self.secret) != 32
                or not all(_integer(v) for v in (self.not_before, self.sign_until, self.verify_until))
                or not self.not_before < self.sign_until <= self.verify_until
                or self.state not in {'active', 'verify_only', 'revoked'}):
            raise WitnessError('BROLL_WITNESS_KEYRING_INVALID', 503)


@dataclass(frozen=True)
class WitnessKeyring:
    active_key_id: str
    keys: Mapping[str, WitnessKey] = field(repr=False)

    def __post_init__(self):
        values = dict(self.keys)
        if (not 1 <= len(values) <= 8 or self.active_key_id not in values
                or any(not isinstance(v, WitnessKey) or k != v.key_id for k, v in values.items())
                or values[self.active_key_id].state != 'active'
                or sum(v.state == 'active' for v in values.values()) != 1):
            raise WitnessError('BROLL_WITNESS_KEYRING_INVALID', 503)
        object.__setattr__(self, 'keys', MappingProxyType(values))

    @classmethod
    def from_json(cls, raw):
        try:
            if not isinstance(raw, str) or not 1 <= len(raw.encode()) <= 16384:
                raise ValueError()
            value = parse_unique(raw)
            if (type(value) is not dict or set(value) != {'schema_version', 'purpose', 'active_key_id', 'keys'}
                    or value['schema_version'] != KEYRING_VERSION or value['purpose'] != PURPOSE
                    or not isinstance(value['active_key_id'], str) or type(value['keys']) is not list
                    or not 1 <= len(value['keys']) <= 8):
                raise ValueError()
            keys = {}
            for item in value['keys']:
                if (type(item) is not dict or set(item) != {'key_id', 'secret_b64', 'not_before', 'sign_until', 'verify_until', 'state'}
                        or not isinstance(item['secret_b64'], str) or len(item['secret_b64']) > 128):
                    raise ValueError()
                key = WitnessKey(**{k: v for k, v in item.items() if k != 'secret_b64'},
                    secret=base64.b64decode(item['secret_b64'], validate=True))
                if key.key_id in keys:
                    raise ValueError()
                keys[key.key_id] = key
            return cls(value['active_key_id'], keys)
        except Exception:
            raise WitnessError('BROLL_WITNESS_KEYRING_INVALID', 503) from None

    @staticmethod
    def _message(identifier, literal):
        return DOMAIN + identifier.encode('ascii') + b'\n' + literal.encode('utf-8')

    @staticmethod
    def _claims(value):
        if (type(value) is not dict or value.get('schema_version') != CLAIMS_VERSION
                or value.get('purpose') != PURPOSE
                or not _integer(value.get('issued_at')) or not _integer(value.get('expires_at'))
                or not 300 <= value['expires_at'] - value['issued_at'] <= MAX_TTL):
            raise WitnessError()
        return value

    def sign(self, claims, *, now):
        value = self._claims(claims)
        key = self.keys[self.active_key_id]
        if (not _integer(now) or value['issued_at'] != now or key.state != 'active'
                or not key.not_before <= now < key.sign_until or value['expires_at'] > key.verify_until):
            raise WitnessError('BROLL_WITNESS_SIGNING_KEY_UNAVAILABLE', 503)
        try:
            literal = canonical(value)
            if len(literal.encode()) > MAX_CLAIMS_BYTES:
                raise ValueError()
            signature = hmac.new(key.secret, self._message(key.key_id, literal), hashlib.sha256).hexdigest()
            return WitnessEnvelope(schema_version='vf-broll-request-witness.v1', key_id=key.key_id,
                claims_json=literal, signature=signature)
        except Exception:
            raise WitnessError('BROLL_WITNESS_CLAIMS_INVALID') from None

    def verify(self, envelope, *, now):
        try:
            value = envelope if isinstance(envelope, WitnessEnvelope) else WitnessEnvelope.model_validate(envelope)
            if not _integer(now) or len(value.claims_json.encode()) > MAX_CLAIMS_BYTES:
                raise ValueError()
            key = self.keys.get(value.key_id)
            if key is None or key.state == 'revoked' or not key.not_before <= now < key.verify_until:
                raise ValueError()
            expected = hmac.new(key.secret, self._message(value.key_id, value.claims_json), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, value.signature):
                raise ValueError()
            claims = self._claims(parse_unique(value.claims_json))
            if (not key.not_before <= claims['issued_at'] < key.sign_until
                    or claims['issued_at'] > now or not now < claims['expires_at'] <= key.verify_until):
                raise ValueError()
            return claims
        except Exception:
            raise WitnessError() from None

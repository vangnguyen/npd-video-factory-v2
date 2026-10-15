"""Dedicated environment-injected VF keyring, never a provider/Hub credential.

No implicit generation, filesystem discovery or decryption. SecretStr follows
the existing API Settings contract; deployments supply stable private material.
"""
from typing import Protocol

from .broll_request_witness import WitnessError, WitnessKeyring


class WitnessSecretProvider(Protocol):
    def load(self) -> WitnessKeyring: ...


def load_witness_keyring(provider):
    try:
        value = provider.load()
        if not isinstance(value, WitnessKeyring):
            raise ValueError()
        return value
    except WitnessError:
        raise
    except Exception:
        raise WitnessError('BROLL_WITNESS_KEYRING_UNAVAILABLE', 503) from None


class SettingsWitnessSecretProvider:
    def __init__(self, settings):
        self._settings = settings

    def load(self):
        if self._settings.broll_request_witness_enabled is not True:
            raise WitnessError('BROLL_WITNESS_NOT_CONFIGURED', 503)
        try:
            secret = self._settings.broll_request_witness_keyring_json.get_secret_value()
            if not secret:
                raise WitnessError('BROLL_WITNESS_NOT_CONFIGURED', 503)
            return WitnessKeyring.from_json(secret)
        except WitnessError:
            raise
        except Exception:
            raise WitnessError('BROLL_WITNESS_KEYRING_UNAVAILABLE', 503) from None

    def __repr__(self):
        return 'SettingsWitnessSecretProvider(dedicated=True)'

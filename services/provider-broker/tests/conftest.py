import logging
import socket
from pathlib import Path

import pytest

from npd_provider_broker.config import Config


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Broker tests must never open a network connection")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.delenv("NPD_VF_CONTENT_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_PROXY_CERT", raising=False)
    states = [(logger, logger.disabled, logger.level) for logger in logging.root.manager.loggerDict.values()
              if isinstance(logger, logging.Logger)]
    yield
    for logger, disabled, level in states:
        logger.disabled, logger.level = disabled, level


@pytest.fixture
def config(tmp_path):
    return Config(source_head="a"*40, api_key_file=tmp_path/"key", token_file=tmp_path/"token",
                  claims_dir=tmp_path/"claims")


@pytest.fixture
def vps_module():
    import importlib.util
    path = Path(__file__).resolve().parents[1]/"scripts/vps.py"
    spec = importlib.util.spec_from_file_location("broker_vps_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

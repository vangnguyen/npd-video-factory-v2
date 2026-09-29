from datetime import datetime, timezone
import json
from pathlib import Path
import socket

import pytest
from pydantic import ValidationError

from app import provider_secret_resolver as resolver
from app.runtime_activation import RuntimeActivationBinding
from test_runtime_activation import binding_data


NOW = datetime(2026, 9, 30, 13, 15, tzinfo=timezone.utc)
SECRET = b"synthetic-non-provider-qualification-value"


def request_data(**changes):
    value = {
        "version": 1,
        "credential_alias": resolver.CANONICAL_ALIAS,
        "operation_id": "op-01",
        "authority_receipt_sha256": "a" * 64,
        "final_bundle_sha256": "b" * 64,
        "execution_scope_sha256": "e" * 64,
        "execution_plane_promotion_sha256": "d" * 64,
        "o2_activation_receipt_sha256": "f" * 64,
    }
    value.update(changes)
    return value


def policy(tmp_path, **changes):
    value = {
        **request_data(),
        "mode": "ONE_SHOT_PROVIDER_SECRET_RESOLUTION",
        "systemd_credential_id": resolver.SYSTEMD_CREDENTIAL_ID,
        "socket_path": str(resolver.CANONICAL_SOCKET),
        "expected_peer_uid": 999,
        "expected_peer_gid": 989,
        "runtime_activation_binding": "/etc/npd-video-factory/runtime-activation.json",
        "runtime_activation_binding_sha256": "1" * 64,
        "spent_marker_directory": str(tmp_path),
        "valid_from_utc": datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc),
        "expires_at_utc": datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc),
        "max_resolutions": 1,
        "authority_granted": False,
    }
    value.pop("version")
    value = {"version": 1, **value}
    value.update(changes)
    return resolver.ResolverPolicy.model_validate(value)


def serve(tmp_path, monkeypatch, request=None, peer=(123, 999, 989)):
    server, client = socket.socketpair()
    activation = RuntimeActivationBinding.model_validate(binding_data())
    monkeypatch.setattr(resolver, "_peer_credentials", lambda connection: peer)
    monkeypatch.setattr(resolver, "_verify_root_artifact", lambda *args: None)
    monkeypatch.setattr(resolver, "load_runtime_activation_binding", lambda *args: activation)
    document = request or resolver.ResolverRequest.model_validate(request_data())
    client.sendall(document.model_dump_json().encode() + b"\n")
    code = resolver.serve_connection(
        server,
        policy=policy(tmp_path),
        credential_loader=lambda: SECRET,
        now=lambda: NOW,
    )
    length = int.from_bytes(client.recv(4), "big")
    response = client.recv(length)
    server.close()
    client.close()
    return code, response


def test_synthetic_handoff_accepts_exact_peer_and_context_once(tmp_path, monkeypatch):
    code, response = serve(tmp_path, monkeypatch)
    assert code == "RESOLVER_HANDOFF_COMPLETE"
    assert response == SECRET
    assert list(tmp_path.glob("*.spent"))


def test_second_read_is_rejected_by_durable_marker(tmp_path, monkeypatch):
    serve(tmp_path, monkeypatch)
    with pytest.raises(resolver.ResolverBlocked, match="RESOLVER_ALREADY_USED"):
        serve(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    "peer,request_value,code",
    [
        ((123, 1000, 989), None, "RESOLVER_PEER_REJECTED"),
        ((123, 999, 989), request_data(credential_alias="secret://wrong/value"), "RESOLVER_REQUEST_MALFORMED"),
        ((123, 999, 989), request_data(operation_id="wrong"), "RESOLVER_CONTEXT_MISMATCH"),
        ((123, 999, 989), request_data(authority_receipt_sha256="f" * 64), "RESOLVER_CONTEXT_MISMATCH"),
        ((123, 999, 989), request_data(o2_activation_receipt_sha256="9" * 64), "RESOLVER_CONTEXT_MISMATCH"),
    ],
)
def test_peer_alias_and_context_mismatches_fail_closed(tmp_path, monkeypatch, peer, request_value, code):
    server, client = socket.socketpair()
    activation = RuntimeActivationBinding.model_validate(binding_data())
    monkeypatch.setattr(resolver, "_peer_credentials", lambda connection: peer)
    monkeypatch.setattr(resolver, "_verify_root_artifact", lambda *args: None)
    monkeypatch.setattr(resolver, "load_runtime_activation_binding", lambda *args: activation)
    raw = json.dumps(request_value or request_data(), separators=(",", ":")).encode() + b"\n"
    client.sendall(raw)
    with pytest.raises(resolver.ResolverBlocked, match=code):
        resolver.serve_connection(
            server, policy=policy(tmp_path), credential_loader=lambda: SECRET,
            now=lambda: NOW,
        )
    server.close()
    client.close()


def test_malformed_extra_fields_and_oversize_are_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValidationError):
        resolver.ResolverRequest.model_validate({**request_data(), "path": "/etc/shadow"})
    server, client = socket.socketpair()
    monkeypatch.setattr(resolver, "_peer_credentials", lambda connection: (123, 999, 989))
    monkeypatch.setattr(resolver, "_verify_root_artifact", lambda *args: None)
    client.sendall(b"{" + b"x" * resolver.MAX_REQUEST_BYTES + b"\n")
    with pytest.raises(resolver.ResolverBlocked, match="RESOLVER_REQUEST_MALFORMED"):
        resolver.serve_connection(
            server, policy=policy(tmp_path), credential_loader=lambda: SECRET,
            now=lambda: NOW,
        )
    server.close()
    client.close()


def test_secret_is_not_in_policy_request_or_spent_evidence(tmp_path, monkeypatch, capsys):
    serve(tmp_path, monkeypatch)
    material = policy(tmp_path).model_dump_json() + json.dumps(request_data())
    material += "".join(path.read_text() for path in tmp_path.glob("*.spent"))
    material += capsys.readouterr().out + capsys.readouterr().err
    assert SECRET.decode() not in material


def test_resolver_unavailable_fails_closed_before_handoff(tmp_path):
    client = resolver.SecretResolverClient(
        policy(tmp_path), resolver.ResolverRequest.model_validate(request_data())
    )
    with pytest.raises(resolver.ResolverBlocked, match="RESOLVER_UNAVAILABLE"):
        client.resolve(resolver.CANONICAL_ALIAS)
    assert client.reads == 0


def test_socket_symlink_substitution_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.write_text("not a socket")
    link = tmp_path / "resolver.sock"
    link.symlink_to(target)
    monkeypatch.setattr(resolver, "CANONICAL_SOCKET", link)
    with pytest.raises(resolver.ResolverBlocked, match="RESOLVER_SOCKET_PATH_INVALID"):
        resolver._verify_socket(link, 989)


def test_activation_artifact_symlink_substitution_is_rejected(tmp_path):
    target = tmp_path / "activation-target.json"
    target.write_text("{}")
    link = tmp_path / "activation.json"
    link.symlink_to(target)
    with pytest.raises(resolver.ResolverBlocked, match="RESOLVER_ACTIVATION_CUSTODY_INVALID"):
        resolver._verify_root_artifact(link, "RESOLVER_ACTIVATION_CUSTODY_INVALID")


def test_lost_response_after_request_never_claims_zero_reads(tmp_path, monkeypatch):
    class FakeSocket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def settimeout(self, value):
            pass
        def connect(self, value):
            pass
        def sendall(self, value):
            self.sent = value

    fake = FakeSocket()
    monkeypatch.setattr(resolver, "_verify_socket", lambda *a: None)
    monkeypatch.setattr(resolver.socket, "socket", lambda *a: fake)
    monkeypatch.setattr(resolver, "_peer_credentials", lambda *a: (1, 0, 0))
    monkeypatch.setattr(
        resolver, "_recv_exact",
        lambda *a: (_ for _ in ()).throw(resolver.ResolverBlocked("RESOLVER_RESPONSE_TRUNCATED")),
    )
    client = resolver.SecretResolverClient(
        policy(tmp_path), resolver.ResolverRequest.model_validate(request_data())
    )
    with pytest.raises(resolver.ResolverBlocked, match="RESOLVER_RESPONSE_TRUNCATED"):
        client.resolve(resolver.CANONICAL_ALIAS)
    assert client.reads is None

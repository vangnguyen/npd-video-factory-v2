import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from npd_provider_broker import main, security

HEAD="a"*40
DECISION="VF-MVP1-VPS-PROVIDER-BROKER-BOOTSTRAP-21"


@pytest.mark.parametrize("mode,uid,gid,valid",[(0o100600,0,0,True),(0o100644,0,0,False),
    (0o100600,1000,0,False),(0o100600,0,1000,False),(0o120600,0,0,False),(0o040600,0,0,False)])
def test_secret_requires_regular_root_owned_0600(monkeypatch,mode,uid,gid,valid):
    path=SimpleNamespace(lstat=lambda:SimpleNamespace(st_mode=mode,st_uid=uid,st_gid=gid,st_size=5))
    assert security.probe_file(path)==dict(exists=True,non_empty=True,permissions_valid=valid)


def test_missing_secret_and_readiness_never_open_file(config,monkeypatch):
    monkeypatch.setattr(os,"open",lambda *a,**k:pytest.fail("readiness must not open secrets"))
    state=main.readiness(config)
    assert state["code"]=="BROKER_SECRET_NOT_INSTALLED"
    assert state["openai_secret_present"] is False and state["broker_token_present"] is False


def test_custody_rechecked_on_open(config,monkeypatch):
    # Synthetic file: simulate correct pre-open metadata, wrong opened custody.
    config.api_key_file.write_text("offline-only")
    monkeypatch.setattr(security,"probe_file",lambda p:dict(exists=True,non_empty=True,permissions_valid=True))
    actual=os.fstat
    def changed(fd):
        info=actual(fd)
        return SimpleNamespace(st_dev=info.st_dev,st_ino=info.st_ino,st_mode=stat.S_IFREG|0o644,
                               st_uid=0,st_gid=0,st_size=info.st_size)
    monkeypatch.setattr(os,"fstat",changed)
    with pytest.raises(security.SecurityError,match="BROKER_SECRET_PERMISSIONS_INVALID"):
        security.read_secret(config.api_key_file)


@pytest.mark.parametrize("change",[{"bind_host":"0.0.0.0"},{"bind_port":18085},{"source_head":"not-a-sha"},
                                     {"timeout_seconds":0},{"max_body_bytes":100000}])
def test_configuration_fail_closed(config,change):
    assert config.valid() and not replace(config,**change).valid()


def test_compose_is_isolated_and_loopback_only():
    root=Path(__file__).resolve().parents[1]
    compose=(root/"docker-compose.provider-broker.yml").read_text()
    docker=(root/"Dockerfile").read_text()
    assert "network_mode: host" in compose and "ports:" not in compose
    assert '"127.0.0.1"' in docker and '"18084"' in docker
    assert "read_only: true" in compose and "cap_drop: [ALL]" in compose and "no-new-privileges:true" in compose
    assert compose.count("read_only: true")==3
    assert "OPENAI_API_KEY" not in compose and "NPD_VF_CONTENT_API_KEY" not in compose
    assert "create_host_path: false" in compose


def test_service_has_no_content_ledger_dependency():
    root=Path(__file__).resolve().parents[1]
    source="\n".join(p.read_text() for p in (root/"app").glob("*.py"))
    for name in ("provider_safety", "sqlite3", "sqlalchemy", "npd-vf-content-budget-epoch", "resolve_for_context"):
        assert name not in source
    assert "BROKER_CONTENT_EXECUTION_DISABLED" in source


@pytest.mark.parametrize("action",["preflight","deploy","live-canaries","install-secrets"])
def test_cloud_cannot_be_broker_runtime(vps_module,monkeypatch,action,tmp_path,capsys):
    monkeypatch.setenv("NPD_VF_CONTENT_API_KEY","synthetic-presence-only")
    args=[action,"--source-head",HEAD,"--owner-authorized","--owner-decision-id",DECISION,"--output-dir",str(tmp_path/"out")]
    assert vps_module.main(args)==2
    assert "BROKER_VPS_RUNTIME_REQUIRED" in capsys.readouterr().out
    assert not (tmp_path/"out").exists()


def test_secret_install_needs_owner_and_never_overwrites(vps_module,monkeypatch,tmp_path,capsys):
    assert vps_module.main(["install-secrets"])==2
    assert "BROKER_OWNER_SECRET_INSTALL_REQUIRED" in capsys.readouterr().out
    monkeypatch.setattr(vps_module,"vps_only",lambda:None)
    monkeypatch.setattr(vps_module,"SECRET_ROOT",tmp_path)
    monkeypatch.setattr(os,"chown",lambda *a:None)
    monkeypatch.setattr(Path,"stat",lambda p,**k:SimpleNamespace(st_uid=0,st_mode=stat.S_IFDIR|0o700))
    monkeypatch.setattr(Path,"exists",lambda p:True)
    monkeypatch.setattr(vps_module.getpass,"getpass",lambda *a:pytest.fail("must not prompt on existing secret"))
    with pytest.raises(vps_module.Blocked,match="NO_OVERWRITE"):
        vps_module.install_secrets()


def test_live_command_requires_explicit_authority(vps_module,capsys):
    assert vps_module.main(["live-canaries","--source-head",HEAD])==2
    assert "BROKER_OWNER_CANARY_APPROVAL_REQUIRED" in capsys.readouterr().out


@pytest.fixture
def live_fixture(vps_module,monkeypatch):
    monkeypatch.setattr(vps_module,"vps_only",lambda:None)
    monkeypatch.setattr(vps_module,"verified_bundle",lambda head:None)
    monkeypatch.setattr(vps_module,"container_identity",lambda head:{"health":"healthy"})
    monkeypatch.setattr(vps_module,"health_ready",lambda:{"version":"0.1.0"})
    return vps_module


@pytest.mark.parametrize("status",[401,403,429,500])
def test_controller_stops_after_failed_model(live_fixture,monkeypatch,tmp_path,status):
    calls=[]
    def request(method,path,**kwargs):
        calls.append(path)
        return 502,{"code":"BROKER_OPENAI_KEY_INVALID","provider_http_status":status,"provider_call_count":1}
    monkeypatch.setattr(live_fixture,"local_request",request)
    result=live_fixture.live_canaries(HEAD,DECISION,tmp_path/"out")
    assert calls==["/internal/canary/openai-model"] and result["provider_call_count"]==1
    assert result["retries"]==0


@pytest.mark.parametrize("responses_status",[200,400,401,403,429,500])
def test_controller_issues_at_most_two_calls(live_fixture,monkeypatch,tmp_path,responses_status):
    calls=[]
    def request(method,path,**kwargs):
        calls.append(path)
        if path.endswith("openai-model"):
            return 200,{"code":"BROKER_MODEL_AUTH_PASS","provider_http_status":200,"provider_call_count":1}
        return (200 if responses_status==200 else 502),{
            "code":"BROKER_RESPONSES_CANARY_PASS" if responses_status==200 else "BROKER_OPENAI_PROVIDER_FAILURE",
            "provider_http_status":responses_status,"provider_call_count":1}
    monkeypatch.setattr(live_fixture,"local_request",request)
    result=live_fixture.live_canaries(HEAD,DECISION,tmp_path/"out")
    assert calls==["/internal/canary/openai-model","/internal/canary/openai-responses"]
    assert result["provider_call_count"]==2 and result["Content_ledger_writes"]==0 and result["Content_operations"]==0
    with pytest.raises(FileExistsError): live_fixture.live_canaries(HEAD,DECISION,tmp_path/"out")
    assert len(calls)==2


def test_ambiguous_broker_dispatch_is_not_claimed_zero(live_fixture,monkeypatch,tmp_path):
    calls=[]
    def request(*a,**k):
        calls.append(1);raise TimeoutError("must-not-echo")
    monkeypatch.setattr(live_fixture,"local_request",request)
    result=live_fixture.live_canaries(HEAD,DECISION,tmp_path/"out")
    assert calls==[1] and result["provider_call_count"] is None
    assert result["broker_canary_dispatch_attempts"]==1 and result["retries"]==0
    assert "must-not-echo" not in json.dumps(result)


def test_not_ready_prevents_canary(live_fixture,monkeypatch,tmp_path):
    def blocked(): raise live_fixture.Blocked("BROKER_READINESS_BLOCKED")
    monkeypatch.setattr(live_fixture,"health_ready",blocked)
    monkeypatch.setattr(live_fixture,"local_request",lambda *a,**k:pytest.fail("no provider-capable request"))
    with pytest.raises(live_fixture.Blocked,match="READINESS"):
        live_fixture.live_canaries(HEAD,DECISION,tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_wrong_owner_decision_is_blocked(live_fixture,tmp_path):
    with pytest.raises(live_fixture.Blocked,match="OWNER_DECISION_MISMATCH"):
        live_fixture.live_canaries(HEAD,"OTHER",tmp_path/"out")


def test_bundle_rejects_modified_source(vps_module,monkeypatch,tmp_path):
    import hashlib
    paths=["Dockerfile","pyproject.toml","app/main.py","scripts/vps.py","docker-compose.provider-broker.yml"]
    for name in paths:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("offline-source")
    data={"source_head":HEAD,"file_sha256":{name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in paths}}
    (tmp_path/"SOURCE_MANIFEST.json").write_text(json.dumps(data))
    monkeypatch.setattr(vps_module,"ROOT",tmp_path)
    vps_module.verified_bundle(HEAD)
    (tmp_path/"app/main.py").write_text("modified")
    with pytest.raises(vps_module.Blocked,match="CHECKSUM"):
        vps_module.verified_bundle(HEAD)


@pytest.mark.parametrize("failure,code",[("missing","BROKER_SECRET_NOT_INSTALLED"),
    ("permissions","BROKER_SECRET_PERMISSIONS_INVALID"),("docker","BROKER_CONTAINER_RUNTIME_UNAVAILABLE"),
    ("port","BROKER_PORT_CONFLICT"),(None,"BROKER_PREFLIGHT_PASS")])
def test_preflight_failure_matrix_without_secret_reads(vps_module,monkeypatch,failure,code):
    monkeypatch.setattr(vps_module,"vps_only",lambda:None)
    monkeypatch.setattr(vps_module,"verified_bundle",lambda head:None)
    monkeypatch.setattr(vps_module.custody,"probe_file",lambda p:{"exists":failure!="missing","non_empty":True,
                                                               "permissions_valid":failure!="permissions"})
    monkeypatch.setattr(vps_module.custody,"read_secret",lambda p:pytest.fail("preflight must not read secrets"))
    def command(args,**kwargs):
        assert args[:2] in (["docker","info"],["docker","compose"])
        if failure=="docker": raise OSError()
        return b"available"
    monkeypatch.setattr(vps_module.subprocess,"check_output",command)
    class Port:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def bind(self,address):
            assert address==("127.0.0.1",18084)
            if failure=="port": raise OSError()
    monkeypatch.setattr(vps_module.socket,"socket",Port)
    if failure:
        with pytest.raises(vps_module.Blocked,match=code): vps_module.preflight(HEAD)
    else:
        assert vps_module.preflight(HEAD)["code"]==code


def test_claim_directory_requires_root_custody(tmp_path):
    path=tmp_path/"unsafe-claims";path.mkdir(mode=0o755)
    with pytest.raises(security.SecurityError,match="BROKER_CLAIM_CUSTODY_INVALID"):
        main.secure_directory(path)


def test_public_bundle_export_is_deterministic_and_excludes_untracked(tmp_path,monkeypatch):
    import importlib.util
    import subprocess
    import sys
    import tarfile
    exporter=Path(__file__).resolve().parents[1]/"scripts/export-bundle.py"
    spec=importlib.util.spec_from_file_location("broker_export_test",exporter)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    repo=tmp_path/"repo";service=repo/"services/provider-broker"
    (service/"scripts").mkdir(parents=True)
    (service/"app").mkdir()
    (service/"app/main.py").write_text("public-source")
    subprocess.check_call(["git","init","-q",str(repo)])
    subprocess.check_call(["git","add","services"],cwd=repo)
    subprocess.check_call(["git","-c","user.name=Offline Test","-c","user.email=offline@example.invalid",
                           "commit","-q","-m","Public fixture"],cwd=repo)
    (service/"excluded-runtime.fixture").write_text("untracked-fixture")
    module.__file__=str(service/"scripts/export-bundle.py")
    for name in ("bundle-one","bundle-two"):
        monkeypatch.setattr(sys,"argv",["export","--output-dir",str(tmp_path/name)])
        module.main()
    first=(tmp_path/"bundle-one/provider-broker-source.tar.gz").read_bytes()
    assert first==(tmp_path/"bundle-two/provider-broker-source.tar.gz").read_bytes()
    with tarfile.open(tmp_path/"bundle-one/provider-broker-source.tar.gz") as archive:
        assert archive.getnames()==["SOURCE_MANIFEST.json","app/main.py"]

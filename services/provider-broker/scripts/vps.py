#!/usr/bin/env python3
"""VPS-only bootstrap. Default preflight never invokes OpenAI or installs secrets."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import http.client
import importlib.util
import json
import os
import re
import secrets
import socket
import subprocess
import sys
from pathlib import Path

# Portable bundles remain byte-identical; do not generate unchecked bytecode.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SECRET_ROOT = Path("/etc/npd-video-factory/provider-broker")
STATE_ROOT = Path("/var/lib/npd-provider-broker")
COMPOSE = ROOT/"docker-compose.provider-broker.yml"
SPEC = importlib.util.spec_from_file_location("broker_secret_custody", ROOT/"app/security.py")
custody = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(custody)


class Blocked(RuntimeError):
    pass


def vps_only():
    if "NPD_VF_CONTENT_API_KEY" in os.environ or "CODEX_PROXY_CERT" in os.environ:
        raise Blocked("BROKER_VPS_RUNTIME_REQUIRED")
    if os.geteuid() != 0:
        raise Blocked("BROKER_ROOT_SECRET_CUSTODY_REQUIRED")


def verified_bundle(source_head):
    if not re.fullmatch(r"[a-f0-9]{40}",source_head):
        raise Blocked("BROKER_SOURCE_IDENTITY_INVALID")
    manifest = ROOT/"SOURCE_MANIFEST.json"
    if manifest.is_file():
        data=json.loads(manifest.read_text())
        if data.get("source_head") != source_head:
            raise Blocked("BROKER_SOURCE_IDENTITY_INVALID")
        declared=set(data["file_sha256"])
        actual={str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.name!="SOURCE_MANIFEST.json"}
        if declared!=actual or not {"Dockerfile","pyproject.toml","app/main.py","scripts/vps.py","docker-compose.provider-broker.yml"}<=declared:
            raise Blocked("BROKER_BUNDLE_CHECKSUM_INVALID")
        for name,pin in data["file_sha256"].items():
            path=ROOT/name
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file():
                raise Blocked("BROKER_BUNDLE_CHECKSUM_INVALID")
            if hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
                raise Blocked("BROKER_BUNDLE_CHECKSUM_INVALID")  # PUBLIC source files only.
    else:
        repo=ROOT.parents[1]
        try:
            head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True,stderr=subprocess.DEVNULL).strip()
            subprocess.check_call(["git","diff","--quiet","HEAD","--"],cwd=repo,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception:
            raise Blocked("BROKER_SOURCE_IDENTITY_INVALID") from None
        if head!=source_head:
            raise Blocked("BROKER_SOURCE_IDENTITY_INVALID")


def compose(source_head,*arguments):
    environment=dict(os.environ)
    environment["BROKER_SOURCE_HEAD"]=source_head
    return subprocess.check_output(["docker","compose","-p","npd-provider-broker","-f",str(COMPOSE),*arguments],
        cwd=ROOT,env=environment,text=True,stderr=subprocess.DEVNULL)


def preflight(source_head):
    vps_only();verified_bundle(source_head)
    flags={name:custody.probe_file(SECRET_ROOT/name) for name in ("openai_api_key","broker_token")}
    if any(not value["exists"] or not value["non_empty"] for value in flags.values()):
        raise Blocked("BROKER_SECRET_NOT_INSTALLED")
    if any(not value["permissions_valid"] for value in flags.values()):
        raise Blocked("BROKER_SECRET_PERMISSIONS_INVALID")
    try:
        subprocess.check_output(["docker","info","--format","{{.ServerVersion}}"],stderr=subprocess.DEVNULL)
        subprocess.check_output(["docker","compose","version"],stderr=subprocess.DEVNULL)
    except Exception:
        raise Blocked("BROKER_CONTAINER_RUNTIME_UNAVAILABLE") from None
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",18084))
    except OSError:
        raise Blocked("BROKER_PORT_CONFLICT") from None
    return {"code":"BROKER_PREFLIGHT_PASS","bind_address":"127.0.0.1:18084",
        "openai_secret_present":True,"broker_token_present":True,"provider_call_count":0}


def install_secrets():
    vps_only()
    SECRET_ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    if SECRET_ROOT.is_symlink() or SECRET_ROOT.stat().st_uid!=0:
        raise Blocked("BROKER_SECRET_PERMISSIONS_INVALID")
    os.chown(SECRET_ROOT,0,0);os.chmod(SECRET_ROOT,0o700)
    key_path,token_path=SECRET_ROOT/"openai_api_key",SECRET_ROOT/"broker_token"
    if key_path.exists() or key_path.is_symlink() or token_path.exists() or token_path.is_symlink():
        raise Blocked("BROKER_SECRET_ALREADY_INSTALLED_NO_OVERWRITE")
    # Owner enters the credential on the VPS terminal only; no echo, argv/env,
    # logging, hashing, Platform key creation or Codex Cloud key transport.
    value=getpass.getpass("Owner OpenAI credential on VPS (hidden): ")
    if not value:
        raise Blocked("BROKER_SECRET_NOT_INSTALLED")
    for path,text in ((key_path,value),(token_path,secrets.token_urlsafe(48))):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.fchown(fd,0,0);os.fchmod(fd,0o600)
        with os.fdopen(fd,"w") as handle:
            handle.write(text);handle.flush();os.fsync(handle.fileno())
    return {"code":"BROKER_SECRETS_INSTALLED","openai_secret_present":True,"broker_token_present":True}


def local_request(method,path,*,body=None,authenticated=False):
    if path not in ("/healthz","/readyz","/internal/canary/openai-model","/internal/canary/openai-responses"):
        raise Blocked("BROKER_FIXED_ENDPOINT_REQUIRED")
    headers={"Content-Type":"application/json"}
    if authenticated:
        headers["Authorization"]="Bearer "+custody.read_secret(SECRET_ROOT/"broker_token")
    client=http.client.HTTPConnection("127.0.0.1",18084,timeout=35)
    try:
        client.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
        response=client.getresponse()
        raw=response.read(8193)
        if len(raw)>8192:
            raise Blocked("BROKER_LOCAL_RESPONSE_INVALID")
        parsed=json.loads(raw)
        if not isinstance(parsed,dict):
            raise Blocked("BROKER_LOCAL_RESPONSE_INVALID")
        return response.status,parsed
    finally:
        client.close()


def container_identity(source_head):
    container=compose(source_head,"ps","-q","provider-broker").strip()
    if not re.fullmatch(r"[a-f0-9]{12,64}",container):
        raise Blocked("BROKER_CONTAINER_NOT_RUNNING")
    fmt='{"id":"{{.Id}}","image":"{{.Image}}","revision":"{{index .Config.Labels "org.opencontainers.image.revision"}}","running":{{.State.Running}},"health":"{{if .State.Health}}{{.State.Health.Status}}{{else}}unavailable{{end}}"}'
    result=json.loads(subprocess.check_output(["docker","inspect","--format",fmt,container],text=True,stderr=subprocess.DEVNULL))
    if result["revision"]!=source_head or not result["running"]:
        raise Blocked("BROKER_CONTAINER_SOURCE_MISMATCH")
    return result


def health_ready():
    health_status,health=local_request("GET","/healthz")
    ready_status,ready=local_request("GET","/readyz")
    if health_status!=200 or health.get("status")!="ok" or health.get("service")!="npd-provider-broker":
        raise Blocked("BROKER_HEALTH_BLOCKED")
    if ready_status!=200 or ready.get("status")!="ready":
        raise Blocked("BROKER_READINESS_BLOCKED")
    return {"health":"PASS","ready":"PASS","version":health.get("version"),
        "openai_secret_present":ready.get("openai_secret_present") is True,
        "broker_token_present":ready.get("broker_token_present") is True}


def deploy(source_head):
    preflight(source_head)
    STATE_ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    if STATE_ROOT.is_symlink() or STATE_ROOT.stat().st_uid!=0:
        raise Blocked("BROKER_CLAIM_CUSTODY_INVALID")
    os.chown(STATE_ROOT,0,0);os.chmod(STATE_ROOT,0o700)
    compose(source_head,"build","provider-broker")
    compose(source_head,"up","-d","--no-deps","--wait","--wait-timeout","60","provider-broker")
    return {"code":"BROKER_DEPLOYED_NO_PROVIDER_REQUESTS","source_head":source_head,
        "container":container_identity(source_head),**health_ready(),"provider_call_count":0}


def live_canaries(source_head,decision,output_dir):
    vps_only();verified_bundle(source_head)
    if decision!="VF-MVP1-VPS-PROVIDER-BROKER-BOOTSTRAP-21":
        raise Blocked("BROKER_OWNER_DECISION_MISMATCH")
    identity=container_identity(source_head)
    state=health_ready()
    if identity["health"]!="healthy":
        raise Blocked("BROKER_HEALTH_BLOCKED")
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=False)
    result={"source_head":source_head,"service_version":state["version"],"container":identity,
        "health":"PASS","ready":"PASS","bind_address":"127.0.0.1:18084","retries":0,
        "Content_operations":0,"Content_ledger_writes":0,"provider_call_count":0,"broker_canary_dispatch_attempts":0}
    # Public client marker; the server also atomically consumes each decision endpoint.
    (output_dir/"CANARY_PAIR_CONSUMED.json").write_text(json.dumps({"owner_decision_id":decision,"source_head":source_head}))
    try:
        result["broker_canary_dispatch_attempts"]+=1
        _,model=local_request("POST","/internal/canary/openai-model",body={"owner_decision_id":decision},authenticated=True)
        result["model_canary"]=model
        result["provider_call_count"]+=model.get("provider_call_count",0)
        result["verdict"]=model.get("code","BROKER_DEPLOYMENT_BLOCKED")
        if model.get("code")=="BROKER_MODEL_AUTH_PASS" and model.get("provider_http_status")==200:
            result["broker_canary_dispatch_attempts"]+=1
            _,responses=local_request("POST","/internal/canary/openai-responses",body={"owner_decision_id":decision},authenticated=True)
            result["responses_canary"]=responses
            result["provider_call_count"]+=responses.get("provider_call_count",0)
            result["verdict"]=responses.get("code","BROKER_DEPLOYMENT_BLOCKED")
            if responses.get("code")=="BROKER_RESPONSES_CANARY_PASS" and responses.get("provider_http_status")==200:
                result["verdict"]="VPS_PROVIDER_BROKER_COMPATIBILITY_PASS / CONTENT_INTEGRATION_READY"
    except Exception:
        result["verdict"]="BROKER_DEPLOYMENT_BLOCKED"
        result["classification"]="CANARY_TRANSPORT_UNCERTAIN_NO_RETRY"
        result["provider_call_count"]=None  # Do not assert zero after an ambiguous broker dispatch.
    (output_dir/"EVIDENCE.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",nargs="?",default="preflight",choices=["preflight","install-secrets","deploy","live-canaries"])
    parser.add_argument("--source-head")
    parser.add_argument("--owner-authorized",action="store_true")
    parser.add_argument("--owner-decision-id")
    parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.action=="install-secrets":
            if not args.owner_authorized: raise Blocked("BROKER_OWNER_SECRET_INSTALL_REQUIRED")
            result=install_secrets()
        elif not args.source_head:
            raise Blocked("BROKER_SOURCE_IDENTITY_REQUIRED")
        elif args.action=="live-canaries":
            if not args.owner_authorized or not args.owner_decision_id or not args.output_dir:
                raise Blocked("BROKER_OWNER_CANARY_APPROVAL_REQUIRED")
            result=live_canaries(args.source_head,args.owner_decision_id,args.output_dir)
        elif args.action=="deploy":
            result=deploy(args.source_head)
        else:
            result=preflight(args.source_head)
    except Blocked as exc:
        print(json.dumps({"code":str(exc),"automatic_retry":False}));return 2
    except Exception:
        print(json.dumps({"code":"BROKER_DEPLOYMENT_BLOCKED","automatic_retry":False}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__": raise SystemExit(main())

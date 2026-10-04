#!/usr/bin/env python3
"""Offline container smoke: synthetic secrets, internal network, diagnostics only."""
import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-head",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    environment=dict(os.environ)
    for name in ("DOCKER_HOST","DOCKER_CONTEXT","DOCKER_TLS_VERIFY","DOCKER_CERT_PATH"):
        environment.pop(name,None)
    prefix=["docker","--host","unix:///var/run/docker.sock"]
    def docker(*arguments):
        return subprocess.check_output([*prefix,*arguments],env=environment,text=True,stderr=subprocess.DEVNULL).strip()
    identity=uuid.uuid4().hex
    name="npd-broker-offline-"+identity
    network="npd-broker-isolated-"+identity
    image="npd-provider-broker-offline:"+args.source_head
    build=["build","--build-arg","BROKER_SOURCE_HEAD="+args.source_head,"-t",image]
    if environment.get("CODEX_PROXY_CERT"):
        build.extend(["--secret","id=build_ca,src="+environment["CODEX_PROXY_CERT"]])  # Public build CA only.
    docker(*build,str(root))
    with tempfile.TemporaryDirectory(prefix="broker-offline-") as folder:
        fixture=Path(folder)
        for filename in ("openai_api_key","broker_token"):
            path=fixture/filename;path.write_text("synthetic-offline-fixture");path.chmod(0o600)
            if os.geteuid()==0: os.chown(path,0,0)
        if os.geteuid()!=0:
            fixture.chmod(0o755)
            # Isolated fixture-only helper; no sudo, network or actual credentials.
            docker("run","--rm","--network","none","--read-only","--cap-drop","ALL","--cap-add","CHOWN",
                "--security-opt","no-new-privileges:true","--mount",f"type=bind,source={fixture},target=/fixture",
                "--entrypoint","python",image,"-c",
                "import os; [os.chown('/fixture/'+name,0,0) for name in ('openai_api_key','broker_token')]")
        docker("network","create","--internal",network)
        try:
            container=docker("run","-d","--name",name,"--network",network,"--read-only","--cap-drop","ALL",
                "--security-opt","no-new-privileges:true","--tmpfs","/tmp:rw,noexec,nosuid,size=16m",
                "--mount",f"type=bind,source={fixture/'openai_api_key'},target=/run/secrets/openai_api_key,readonly",
                "--mount",f"type=bind,source={fixture/'broker_token'},target=/run/secrets/broker_token,readonly",image)
            # Executed inside its isolated container: loopback diagnostics only.
            check='''import json,time,urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(40):
    try:
        health=json.load(opener.open("http://127.0.0.1:18084/healthz",timeout=2))
        ready=json.load(opener.open("http://127.0.0.1:18084/readyz",timeout=2))
        break
    except OSError:
        time.sleep(.25)
else:
    raise SystemExit("BROKER_DIAGNOSTICS_FAILED")
assert health["status"]=="ok" and ready["status"]=="ready"
print(json.dumps({"health":health,"ready":ready}))'''
            checks=json.loads(docker("exec",name,"python","-c",check))
            revision=docker("inspect","--format",'{{index .Config.Labels "org.opencontainers.image.revision"}}',name)
            assert revision==args.source_head
            evidence={"source_head":args.source_head,"container_id":container,"image_id":docker("inspect","--format","{{.Image}}",name),
                      **checks,"network":"isolated_internal","secrets":"SYNTHETIC_OFFLINE_FIXTURES",
                      "provider_call_count":0,"Content_ledger_writes":0}
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
            print("BROKER_OFFLINE_CONTAINER_SMOKE_PASS provider_call_count=0")
        finally:
            subprocess.run([*prefix,"rm","-f",name],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            docker("network","rm",network)


if __name__=="__main__": main()

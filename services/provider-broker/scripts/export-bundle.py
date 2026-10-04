#!/usr/bin/env python3
"""Export only committed public broker source to a create-only directory outside Git."""
import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[3]
    destination=args.output_dir.resolve()
    if destination.is_relative_to(repo):
        parser.error("Bundle must be outside Git")
    subprocess.check_call(["git","diff","--quiet","HEAD","--"],cwd=repo)
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    prefix="services/provider-broker/"
    names=subprocess.check_output(["git","ls-tree","-r","--name-only",head,"--",prefix],cwd=repo,text=True).splitlines()
    files={name.removeprefix(prefix):subprocess.check_output(["git","show",head+":"+name],cwd=repo) for name in names}
    if not files: parser.error("Committed broker source required")
    manifest={"schema":"npd-provider-broker-source-bundle-v1","source_head":head,
              "file_sha256":{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}}
    files["SOURCE_MANIFEST.json"]=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
    destination.mkdir(parents=True,exist_ok=False)
    target=destination/"provider-broker-source.tar.gz"
    with target.open("xb") as raw, gzip.GzipFile(filename="",mode="wb",fileobj=raw,mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode="w") as archive:
            for name,data in sorted(files.items()):
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
                archive.addfile(info,io.BytesIO(data))
    (destination/"SOURCE_MANIFEST.json").write_bytes(files["SOURCE_MANIFEST.json"])
    checksum=hashlib.sha256(target.read_bytes()).hexdigest()
    (destination/"SHA256SUMS").write_text(checksum+"  "+target.name+"\n")
    print(json.dumps({"source_head":head,"bundle_sha256":checksum,"bundle_path":str(target)},sort_keys=True))


if __name__=="__main__": main()

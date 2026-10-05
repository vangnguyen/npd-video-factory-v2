"""Explicit isolated browser acceptance harness; no paid dispatch/new voice inference.

Only exact accepted speech with an INTEGRATION FIXTURE reviewer may reuse saved
real voice. Production server/pipeline has no fixture fallback or option.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import WorkflowError, file_sha, normalize, write_json
from services.windows_native.hardening import Artifacts, durable_json
from services.windows_native.pipeline import Config, Pipeline, verify_runtime
from services.windows_native.server import LocalServer, Runner
from services.windows_native.windows_job import contain_process_tree, lock_data_root


class ExplicitFixturePipeline(Pipeline):
    def run(self,job,stage):
        doc=job["snapshot"]["document"]
        if job["kind"]=="content" and doc.get("input_kind")!="script":
            raise WorkflowError("FIXTURE_NO_CONTENT_PROVIDER_DISPATCH")
        if job["kind"]=="asr": raise WorkflowError("FIXTURE_NO_ASR_PROVIDER_DISPATCH")
        if job["kind"]=="render":
            source=Path(r"C:\NPD-Video-Factory\outputs\MVP1")
            expected=json.loads((source/"content-proposal.json").read_bytes())
            if normalize(doc["proposal"]["narration"])!=normalize(expected["narration"]) or not job["snapshot"]["approval"]["reviewer"].startswith("INTEGRATION FIXTURE"):
                raise WorkflowError("FIXTURE_EXACT_ACCEPTED_NARRATION_AND_TEST_REVIEWER_REQUIRED")
            receipt=json.loads((source/"owner-final-video-approval.json").read_bytes())
            assert file_sha(source/"voice.wav")==receipt["voice_sha256"]
            out=self.config.data_root/"jobs"/job["id"]; out.mkdir(parents=True,exist_ok=True); art=Artifacts(out,job)
            if not art.load("tts"):
                voice=art.publish(source/"voice.wav","voice.wav")
                original_meta=Path(r"C:\NPD-Video-Factory\phase2-validation\single-media-regression\voice.json")
                value=json.loads(original_meta.read_bytes()); cursor=0
                for scene in doc["proposal"]["visual_brief"]:
                    texts=[]
                    while cursor<len(value["units"]) and normalize(" ".join(texts))!=normalize(scene["narration_excerpt"]):
                        unit=value["units"][cursor]; texts.append(unit["text"]); unit["scene"]=scene["scene"]; cursor+=1
                    if normalize(" ".join(texts))!=normalize(scene["narration_excerpt"]):
                        raise WorkflowError("FIXTURE_SCENE_SPLIT_MUST_MATCH_EXISTING_MEASURED_SENTENCES")
                if cursor!=len(value["units"]): raise WorkflowError("FIXTURE_INCOMPLETE_SCENE_COVERAGE")
                value["explicit_fixture_lineage"]={"source_metadata_sha256":file_sha(original_meta),"audio_and_sentence_times_unchanged":True,"scene_assignment_projected_to_same_ordered_sentences":True}
                write_json(out/"fixture-voice-scene-projection.json",value)
                meta=art.publish(out/"fixture-voice-scene-projection.json","voice.json")
                art.commit("tts",[voice,meta],{"explicit_fixture":True,"reused_existing_real_accepted_WAV":True,"new_inference":False})
                stage("fixture_reuses_existing_accepted_audio_no_new_tts")
        return super().run(job,stage)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--data-root",type=Path,required=True); parser.add_argument("--port",type=int,default=8031)
    args=parser.parse_args(); root=args.data_root.resolve()
    if root.parent!=Path(r"C:\NPD-Video-Factory\post-mvp-validation") or not root.name.startswith("phase6-dashboard-"):
        raise ValueError("ISOLATED_NAMED_FIXTURE_ROOT_REQUIRED")
    config=Config(data_root=root); verify_runtime(config,full=True); contain_process_tree(); root.mkdir(exist_ok=True)
    with lock_data_root(root), LocalServer(args.port,config,start_worker=False) as server:
        runner=Runner(server.store,ExplicitFixturePipeline(config))
        def drain():
            while not runner.stop.is_set():
                if not runner.run_one(): runner.stop.wait(.1)
        thread=threading.Thread(target=drain,daemon=True); thread.start()
        durable_json(root/"fixture-mode.json",{"explicit_fixture":True,"provider_dispatch":False,"new_tts_inference":False,"human_acceptance":False})
        print(f"Explicit fixture dashboard http://127.0.0.1:{server.server_port}",flush=True)
        try: server.serve_forever()
        finally: runner.stop.set(); thread.join(timeout=3)


if __name__=="__main__": main()

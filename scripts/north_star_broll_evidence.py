"""Read an isolated UI fixture, export evidence and encode its canonical visuals.

Requires a fresh output directory. No accepted media, live data, provider calls,
human approval or final-render certification are changed or inferred.
"""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.db import create_engine,create_session_factory
from app.auto_edit_repository import AutoEditRepository
from app.repositories import PlatformRepository
from app.timeline_repository import TimelineRepository
from app.timeline_service import FFmpegProxyRenderer
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.object_storage import LocalObjectStorageProvider,sha256_file


async def run(fixture: Path,output: Path):
    session=json.loads((fixture/'fixture-session.json').read_text(encoding='utf-8'))
    if session.get('fixture_asr') is not True or session.get('real_provider_acceptance') is not False:
        raise ValueError('only explicitly labeled isolated fixtures are supported')
    project_id=session['project_id']
    output.mkdir(parents=True,exist_ok=False)
    engine=create_engine(f'sqlite+aiosqlite:///{(fixture/"auto-edit.db").as_posix()}')
    try:
        sessions=create_session_factory(engine)
        timelines=TimelineRepository(sessions)
        timeline=await timelines.get_timeline(project_id)
        if timeline is None:raise ValueError('fixture has no canonical timeline')
        assets=await PlatformRepository(sessions).list_assets(project_id)
        auto=AutoEditRepository(sessions)
        analysis=await auto.get_analysis(timeline.source_analysis_id,
            transcript_id=(timeline.snapshot.metadata.get('transcript_revision')or{}).get('transcript_id'))
        plans=await MediaIntelligenceRepository(sessions).list_plans(project_id)
        (output/'timeline.json').write_text(timeline.model_dump_json(indent=2),encoding='utf-8')
        (output/'analysis.json').write_text(analysis.model_dump_json(indent=2),encoding='utf-8')
        (output/'media-plans.json').write_text(json.dumps([plan.model_dump(mode='json') for plan in plans],ensure_ascii=False,indent=2),encoding='utf-8')
        versions=await timelines.list_versions(project_id)
        original=next((version.snapshot for version in versions if version.version==1),None)
        if original is None:raise ValueError('original timeline evidence is missing')
        unchanged_tracks=all(next((track for track in timeline.snapshot.tracks if track.track_id==before.track_id),None)==before
            for before in original.tracks if before.kind!='broll')
        if not unchanged_tracks or original.duration_seconds!=timeline.snapshot.duration_seconds:
            raise ValueError('this evidence run requires preserved primary/audio/caption tracks and duration')
        (output/'timeline-history.json').write_text(json.dumps([version.model_dump(mode='json')for version in versions],ensure_ascii=False,indent=2),encoding='utf-8')
        storage=LocalObjectStorageProvider(fixture/'objects')
        bound={}
        checks=[]
        for asset in assets:
            path=output/'inputs'/asset.filename
            await storage.download_file(object_key=asset.object_key,destination=path)
            digest=sha256_file(path)
            if digest!=asset.checksum_sha256:raise ValueError('fixture source bytes differ from registered asset')
            bound[asset.asset_id]=(asset,path)
            checks.append({'asset_id':asset.asset_id,'filename':asset.filename,'sha256':digest,
                'rights_status':asset.provenance.get('rights_status','unknown'),'provenance':asset.provenance})
        started=time.monotonic()
        async def cancelled():return time.monotonic()-started>120
        rendered=await FFmpegProxyRenderer().render(snapshot=timeline.snapshot,assets=bound,
            output_path=output/'preview.mp4',width=540,height=960,is_cancelled=cancelled)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(rendered.path)],text=True))
        pixel=list(subprocess.check_output(['ffmpeg','-v','error','-nostdin','-ss','0.5','-i',str(rendered.path),
            '-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1']))
        frame_path=output/'broll-frame.png'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-ss','0.5','-i',str(rendered.path),'-frames:v','1',str(frame_path)],check=True,timeout=30)
        costs=await PlatformRepository(sessions).list_cost_records(project_id)
        (output/'cost.json').write_text(json.dumps([cost.model_dump(mode='json')for cost in costs],ensure_ascii=False,indent=2),encoding='utf-8')
        evidence={'fixture_asr':True,'local_real_media_encoding':True,'real_provider_tested':False,'human_approval_claimed':False,
            'provider_dispatches':0,'production_deployed':False,'timeline_version':timeline.current_version,
            'non_broll_tracks_preserved':unchanged_tracks,'timeline_duration_preserved':True,
            'inputs':checks,'render':rendered.manifest,'preview_sha256':sha256_file(rendered.path),'probe':probe,
            'decoded_mean_pixel_rgb_at_half_second':pixel,'frame_sha256':sha256_file(frame_path),
            'original_media_mutated':False,'output_directory':str(output)}
        (output/'broll-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'timeline_version':timeline.current_version,'playable':rendered.manifest['playable'],
            'audio_included':rendered.manifest['audio_included'],'rgb':pixel,'evidence':str(output/'broll-evidence.json')}))
    finally:await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    asyncio.run(run(args.fixture,args.output))

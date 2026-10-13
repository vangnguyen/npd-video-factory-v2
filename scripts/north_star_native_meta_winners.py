"""Export an actual Native Meta counter cohort/route history with explicit mocks."""
import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.tests.test_meta_winners import MetaWinnerFixture
from services.windows_native import official_winner_routes,official_learning_routes
from services.windows_native.official_learning import NativeOfficialLearning
from services.windows_native.official_learning_models import Create as LearningCreate
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.trend_radar import NativeTrendRadar
from services.windows_native.qualified_learning_feedback import NativeQualifiedLearningFeedback,Create as FeedbackCreate
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.pipeline import Config
from services.windows_native.backup import create_backup
from services.windows_native.hardening import durable_json

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();assert not out.exists() and ROOT not in out.parents;out.mkdir(parents=True);captured={}
 for platform in ('instagram_reels','facebook'):
  f=MetaWinnerFixture(platform);root=f.c.folder
  try:
   for i in range(1,9):f.peer(i,positive=i>=6);row,request=f.assessment()
   project=row['project_id'];folder=out/platform;folder.mkdir();learning=NativeOfficialLearning(f.winners)
   learn_request=LearningCreate(assessment_id=row['assessment_id'],expected_assessment_sha256=row['snapshot_sha256'],
    acknowledged_recommendation_only=True,acknowledged_protocol_mock=True,request_key='explicit-meta-counter-learning-export')
   learned=learning.create(project,learn_request,principal=f.c.principal)[0]
   handler=SimpleNamespace(server=SimpleNamespace(official_winners=f.winners,official_learning=learning),path='/api/connections/official-winners')
   runtime=official_winner_routes.get(handler,handler.path)
   handler.path='/api/projects/'+project+'/official-winners/source/'+f.anchor['sync_id'];source=official_winner_routes.get(handler,handler.path)
   handler.path='/api/connections/official-learning';learning_runtime=official_learning_routes.get(handler,handler.path)
   handler.path='/api/projects/'+project+'/official-learning/source/'+row['assessment_id'];learning_source=official_learning_routes.get(handler,handler.path)
   intelligence=IntelligenceService(Config(data_root=f.c.root),f.c.store,idea_provider=FixtureIdeas())
   radar=NativeTrendRadar(intelligence,NativeAnalytics(f.c.store,f.c.publications),workspace=f.c.workspace,clock=lambda:f.c.clock[0])
   feedback=NativeQualifiedLearningFeedback(learning,radar)
   projected=feedback.create(FeedbackCreate(project_id=project,learning_id=learned['learning_id'],expected_learning_sha256=learned['snapshot_sha256'],
    channel_profile_ref='ai-education-reference@1',platform=platform,acknowledged_recommendation_only=True,
    acknowledged_protocol_mock=True,request_key='explicit-meta-counter-projection-export'),principal=f.c.principal)[0]
   value={'workspace_id':f.c.workspace,'project':f.c.store.get(project),'analytics':f.anchor,'source':source,'runtime':runtime,
    'assessment':row,'page':f.winners.page(project,publication=row['publication_id']),
    'request':request.model_dump(mode='json'),'learning':learned,'learning_runtime':learning_runtime,'learning_source':learning_source,
    'learning_request':learn_request.model_dump(mode='json'),'learning_page':learning.page(project,publication=row['publication_id']),
    'projection':projected,'nonplayable_media_fixture':True,'Owner_UAT':False,'real_provider_calls':0,
    'paid_calls':0,'production_deployed':False,'actual_HTTP_browser_verified':False}
   durable_json(folder/'public-fixture.json',value);durable_json(folder/'cost.json',f.case.analytics.costs.summary(project))
   config=Config(data_root=f.c.root,runtime_root=root/'runtime',secret_file=root/'private/missing.env',
    assemblyai_secret_file=root/'private/absent.dpapi',ffmpeg_bin=root/'absent-ffmpeg')
   durable_json(folder/'backup.json',create_backup(config,folder/'owned-state.zip'));captured[platform]=value
  finally:f.close()
  assert not root.exists()
 durable_json(out/'captured-controller-fixtures.json',captured)
 durable_json(out/'evidence.json',{'platforms':{k:{'state':v['assessment']['assessment']['state'],
  'peers':v['assessment']['peer_count'],'source_basis':v['assessment']['assessment']['basis'],'learning_state':v['learning']['status'],
  'learning_observations':v['learning']['observation_count'],'projection_consumers':list(v['projection']['payload']['consumers'])} for k,v in captured.items()},
  'owned_roots_cleaned':True,'actual_Native_domain_and_route_DTOs':True,'protocol_mock':True,'real_provider_calls':0,'paid_calls':0,
  'Owner_UAT':False,'full_Mode_A_B_accepted':False,'real_publishing':False,'production_deployed':False})
 print(json.dumps({'platforms':2,'owned_roots_cleaned':True,'real_provider_calls':0,'Owner_UAT':False}))

if __name__=='__main__':main()

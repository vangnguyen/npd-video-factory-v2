"""Export actual Native domain/controller DTOs using explicit protocol fixtures.

No HTTP/browser/Owner/audience/production acceptance is inferred. Existing
publication fixtures use mock transports only; all roots are owned lifecycle
data and are cleaned after immutable export.
"""
import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace
from datetime import timedelta

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.tests.test_meta_analytics import NativeMetaAnalyticsTests
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh
from services.windows_native import official_analytics_routes
from services.windows_native.contracts import digest,file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.backup import create_backup
from services.windows_native.pipeline import Config
from app.publishing_credentials import target_digest


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 out=args.output.resolve();assert not out.exists() and out!=ROOT and ROOT not in out.parents;out.mkdir(parents=True)
 results=[]
 for platform in ('instagram_reels','facebook'):
  case=NativeMetaAnalyticsTests('test_scoped_meta_collection_keeps_null_timing_costs_and_protocol_mock_labels')
  case.PLATFORM=platform;case.setUp()
  try:
   helper=SimpleNamespace(server=SimpleNamespace(official_analytics=case.analytics))
   path=f'/api/projects/{case.project["id"]}/official-analytics/source/{case.completed["publication_id"]}'
   helper.path=path;source=official_analytics_routes.get(helper,path)
   source['target_binding_sha256']=target_digest(case.target)
   manual_created=case.collect();manual_done=case.analytics.process();assert manual_done['status']=='succeeded',manual_done['failure_code']
   refresh=NativeOfficialAnalyticsRefresh(case.analytics,enabled=True)
   plan_created=refresh.create(case.project['id'],case.refresh_request(),principal=case.c.principal)[0]
   for ordinal in (1,2):
    if ordinal==2:case.c.clock[0]+=timedelta(seconds=60);case.views=250
    refresh.tick();value=case.analytics.process();assert value['status']=='succeeded',value['failure_code'];refresh.tick()
   plan_done=refresh.get(case.project['id'],plan_created['plan_id']);assert plan_done['status']=='completed'
   folder=out/platform;folder.mkdir()
   public={'schema_version':'native-meta-analytics-contract-fixture-v1','workspace_id':case.c.workspace,
    'project':{'id':case.project['id'],'revision':case.project['revision'],'archived':False},
    'publication':case.publisher.service.get(case.project['id'],case.completed['publication_id']),
    'runtime':case.analytics.states(),'refresh_runtime':refresh.states(),
    'source':source,'manual_created':manual_created,'manual_done':manual_done,
    'plan_created':plan_created,'plan_done':plan_done,
    'real_provider_acceptance':False,'owner_uat':False,'actual_HTTP_tested':False,'actual_browser_tested':False}
   durable_json(folder/'public-fixture.json',public)
   durable_json(folder/'project.json',case.store.get(case.project['id']))
   durable_json(folder/'cost.json',case.analytics.costs.summary(case.project['id']))
   backup=create_backup(Config(data_root=case.c.root,secret_file=case.c.folder/'private'/'absent.env',
       assemblyai_secret_file=case.c.folder/'private'/'absent.dpapi'),folder/'owned-state.zip')
   durable_json(folder/'backup.json',backup)
   results.append({'platform':platform,'manual_snapshot':manual_done['result_snapshot_id'],
    'refresh_runs':plan_done['run_count'],'provider_requests':len(case.calls),'mock':True,
    'source_root':str(case.c.root),'owned_parent':str(case.c.folder),
    'public_fixture_sha256':file_sha(folder/'public-fixture.json'),'backup':backup})
  finally:case.tearDown()
 for row in results:assert not Path(row['owned_parent']).exists()
 durable_json(out/'evidence.json',{'domain_controller_export_passed':True,'platforms':results,
  'real_provider_calls':0,'paid_calls':0,'Owner_UAT':False,'actual_HTTP_tested':False,'actual_browser_tested':False,
  'cold_restore_tested':False,'publishing_enabled':False,'production_deployed':False,'owned_roots_cleaned':True,
  'full_Mode_A_B_ready':False})
 print(json.dumps({'domain_controller_export_passed':True,'platforms':2,'owned_roots_cleaned':True,
  'real_provider_calls':0,'Owner_UAT':False}))


if __name__=='__main__':main()

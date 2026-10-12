"""Owned localhost browser rehearsal with explicit Meta/publication/identity mocks."""
import argparse,json,sys,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.tests import test_meta_analytics_http as fixture
from services.windows_native.hardening import durable_json
from services.windows_native.backup import create_backup
from services.windows_native.contracts import file_sha


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--platform',choices=['instagram_reels','facebook'],required=True);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
 out=a.output.resolve();assert not out.exists() and out!=ROOT and ROOT not in out.parents;out.mkdir(parents=True)
 case=fixture.MetaAnalyticsHTTPTests('test_signed_queue_actual_worker_and_read_only_source_keep_mock_and_bridge_history')
 case.PLATFORM=a.platform;case.setUp();server=case.server
 try:
  root=server.store.root;project=case.case.project['id'];publication=case.case.completed['publication_id']
  server.runner.thread.start()
  durable_json(out/'browser.json',{'url':'http://127.0.0.1:'+str(server.server_port)+'/?project='+project,
   'fixture_login_token':'vf1.explicit-fixture.'+'x'*48,'platform':a.platform,'project_id':project,'publication_id':publication,
   'workspace_id':case.c.workspace,'owned_root':str(root),'owned_parent':str(case.c.folder),
   'clock':case.c.clock[0].isoformat(),'Owner_UAT':False,'real_provider_calls':0,'paid_calls':0,
   'publishing_enabled':False,'production_deployed':False,'nonplayable_publication_media_fixture':True})
  print('META_ANALYTICS_BROWSER_FIXTURE_READY',flush=True)
  deadline=time.monotonic()+2700;advanced=False
  while not (out/'stop').exists():
   if time.monotonic()>deadline:raise TimeoutError('Owned fixture deadline reached')
   # Match browser wall time; only this owned protocol fixture can fast-forward.
   case.c.clock[0]=datetime.now(timezone.utc)+timedelta(seconds=60 if advanced else 0)
   if (out/'advance-60').exists() and not advanced:
    case.c.clock[0]+=timedelta(seconds=60);case.case.views=250;advanced=True;server.runner.wake.set()
   time.sleep(.5)
  analytics=server.official_analytics.page(project,publication=publication,limit=100)
  refresh=server.official_analytics_refresh.page(project,publication=publication,limit=100)
  assert all(v['status'] not in {'queued','running','retry_scheduled'} for v in analytics['items'])
  durable_json(out/'analytics.json',analytics);durable_json(out/'refresh.json',refresh)
  durable_json(out/'project.json',server.store.get(project));durable_json(out/'provider-calls.json',case.case.calls)
  durable_json(out/'bridge.json',server.bridge.page(limit=100));durable_json(out/'cost.json',server.official_analytics.costs.summary(project))
  backup=create_backup(server.config,out/'owned-state.zip');durable_json(out/'backup.json',backup)
  durable_json(out/'helper.json',{'platform':a.platform,'project_id':project,'publication_id':publication,
   'analytics_count':len(analytics['items']),'refresh_count':len(refresh['items']),'fixture_provider_requests':len(case.case.calls),
   'backup':backup,'real_provider_calls':0,'paid_calls':0,'Owner_UAT':False,'publishing_enabled':False,'production_deployed':False,
   'clock_advanced_by_explicit_fixture_marker':advanced,'clock_follows_wall_time':True,
   'cleanup':'owned fixture lifecycle after export'})
 finally:
  case.tearDown()
 print('META_ANALYTICS_BROWSER_EXPORTED_AND_ROOT_CLEANED',flush=True)


if __name__=='__main__':main()

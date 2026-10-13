"""Owned restored Meta feedback Studio rehearsal; no provider credentials or posting."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.tests.test_meta_feedback_http import MetaFeedbackHTTPFixture
from services.windows_native.hardening import durable_json
from services.windows_native.backup import create_backup

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--platform',choices=['instagram_reels','facebook'],required=True)
 p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();assert not out.exists() and ROOT not in out.parents;out.mkdir(parents=True)
 f=MetaFeedbackHTTPFixture();f.open(a.platform,a.source);owned=f.folder
 try:
  durable_json(out/'browser.json',{'url':'http://127.0.0.1:'+str(f.server.server_port)+'/?project='+f.project,
   'fixture_login_token':'vf1.explicit-fixture.'+'x'*48,'project_id':f.project,'platform':a.platform,
   'owned_root':str(f.root),'owned_parent':str(owned),'Owner_UAT':False,'nonplayable_media_fixture':True,
   'real_provider_calls':0,'paid_calls':0,'publishing_enabled':False,'production_deployed':False})
  print('META_FEEDBACK_BROWSER_FIXTURE_READY',flush=True);deadline=time.monotonic()+2700
  while not (out/'stop').exists():
   if time.monotonic()>deadline:raise TimeoutError('Owned browser fixture deadline reached')
   time.sleep(.5)
  durable_json(out/'winner-history.json',f.server.official_winners.page(f.project,limit=100))
  durable_json(out/'learning-history.json',f.server.official_learning.page(f.project,limit=100))
  f.server.bridge.harvest()
  durable_json(out/'bridge.json',f.server.bridge.page(limit=100));durable_json(out/'project.json',f.server.store.get(f.project))
  durable_json(out/'cost.json',f.server.official_analytics.costs.summary(f.project))
  durable_json(out/'backup.json',create_backup(f.server.config,out/'owned-state.zip'))
  durable_json(out/'helper.json',{'actual_localhost_Studio':True,'fixture_provider_publication_identity_media':True,
   'real_provider_calls':0,'paid_calls':0,'Owner_UAT':False,'publishing_enabled':False,'production_deployed':False,
   'cleanup':'owned fixture lifecycle after export'})
 finally:f.close()
 assert not owned.exists();print('META_FEEDBACK_BROWSER_EXPORTED_AND_ROOT_CLEANED',flush=True)

if __name__=='__main__':main()

"""Fresh-process exact Native Meta fixture recovery; no credentials or replay."""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.backup import restore_backup,database_status
from services.windows_native.contracts import digest,file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh
from app.publishing_wire import OfficialHTTPClient
from services.windows_native.tests.test_publications import CAPABILITIES


def cold(context):
 expected=json.loads(Path(context).read_bytes());source=Path(expected['source'])
 with tempfile.TemporaryDirectory(prefix='vf-meta-analytics-cold-') as temporary:
  root=Path(temporary)/'state';backup=json.loads((source/'backup.json').read_bytes())
  restore_backup(backup['backup_path'],root,expected_sha256=backup['sha256'])
  public=json.loads((source/'public-fixture.json').read_bytes());project=json.loads((source/'project.json').read_bytes())
  store=Store(root);parent=NativePublications(store,CAPABILITIES,workspace_id=public['workspace_id'])
  accounts=NativeOfficialAccounts(store,workspace_id=public['workspace_id'])
  official=NativeOfficialPublications(store,parent,accounts)
  analytics=NativeOfficialAnalytics(official);refresh=NativeOfficialAnalyticsRefresh(analytics)
  with (patch.object(OfficialHTTPClient,'request',side_effect=AssertionError('Recovery cannot call provider')),
        patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Recovery cannot decrypt credentials'))):
   assert store.get(project['id'])==project
   publication=official.get(project['id'],public['publication']['publication_id']);assert publication==public['publication']
   manual=analytics.get(project['id'],public['manual_done']['sync_id']);assert manual==public['manual_done']
   plan=refresh.get(project['id'],public['plan_done']['plan_id']);assert plan==public['plan_done']
   assert analytics.process() is None and refresh.tick() is None
   assert analytics.recover()=={'recovered':0,'unfinished_costs_marked_unknown':0,'automatic_retry':False,'token_returned':False}
   refresh.recover()
   assert analytics.get(project['id'],manual['sync_id'])==manual and refresh.get(project['id'],plan['plan_id'])==plan
   result={'platform':manual['snapshot']['target']['platform'],'project_sha256':digest(project),'manual_sha256':digest(manual),
    'refresh_sha256':digest(plan),'publication_sha256':digest(publication),'snapshot_count':len(plan['occurrences'])+1,
    'provider_calls':0,'credential_decryption':0,'automatic_replay':False,'database':database_status(store.db)}
 return result


def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--output',type=Path);p.add_argument('--cold-context',type=Path);a=p.parse_args()
 if a.cold_context:print(json.dumps(cold(a.cold_context)));return
 source=a.source.resolve();out=a.output.resolve();assert source.is_dir() and not out.exists() and ROOT not in out.parents;out.mkdir(parents=True)
 results=[]
 for platform in ('instagram_reels','facebook'):
  folder=source/platform;context=out/(platform+'-context.json');durable_json(context,{'source':str(folder)})
  process=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--cold-context',str(context)],
      cwd=ROOT,capture_output=True,text=True,timeout=120)
  (out/(platform+'-stdout.log')).write_text(process.stdout,encoding='utf-8')
  (out/(platform+'-stderr.log')).write_text(process.stderr,encoding='utf-8')
  assert process.returncode==0,platform+' cold child failed; inspect retained stderr'
  result=json.loads(process.stdout);durable_json(out/(platform+'-proof.json'),result);results.append(result)
 durable_json(out/'evidence.json',{'separate_process_restore_passed':True,'platforms':results,'real_provider_calls':0,
  'paid_calls':0,'Owner_UAT':False,'real_publishing':False,'production_deployed':False,'full_Mode_A_B_ready':False})
 print(json.dumps({'separate_process_restore_passed':True,'platforms':2,'provider_calls':0,'credential_decryption':0}))


if __name__=='__main__':main()

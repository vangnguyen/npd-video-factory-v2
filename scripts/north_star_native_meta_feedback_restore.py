"""New-process recovery of exact qualified Meta counter/winner/learning histories."""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.backup import restore_backup,database_status
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_winners import NativeOfficialWinners
from services.windows_native.official_learning import NativeOfficialLearning
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.trend_radar import NativeTrendRadar
from services.windows_native.qualified_learning_feedback import NativeQualifiedLearningFeedback
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.tests.test_publications import CAPABILITIES
from services.windows_native.pipeline import Config
from services.windows_native.contracts import digest
from services.windows_native.hardening import durable_json
from app.publishing_wire import OfficialHTTPClient

def cold(source):
 source=Path(source);expected=json.loads((source/'public-fixture.json').read_bytes());backup=json.loads((source/'backup.json').read_bytes())
 with tempfile.TemporaryDirectory(prefix='vf-meta-feedback-cold-') as owned:
  root=Path(owned)/'state';assert root.resolve().parent==Path(owned).resolve()
  restore_backup(backup['backup_path'],root,expected_sha256=backup['sha256']);store=Store(root)
  parent=NativePublications(store,CAPABILITIES,workspace_id=expected['workspace_id'])
  accounts=NativeOfficialAccounts(store,workspace_id=expected['workspace_id'])
  official=NativeOfficialPublications(store,parent,accounts);analytics=NativeOfficialAnalytics(official)
  winners=NativeOfficialWinners(analytics);learning=NativeOfficialLearning(winners)
  intelligence=IntelligenceService(Config(data_root=root),store,idea_provider=FixtureIdeas())
  radar=NativeTrendRadar(intelligence,NativeAnalytics(store,parent),workspace=expected['workspace_id'])
  feedback=NativeQualifiedLearningFeedback(learning,radar);project=expected['project']['id']
  with (patch.object(OfficialHTTPClient,'request',side_effect=AssertionError('Cold source cannot call provider')),
        patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Cold source cannot decrypt'))):
   assert store.get(project)==expected['project']
   assert analytics.get(project,expected['analytics']['sync_id'])==expected['analytics']
   winner=winners.get(project,expected['assessment']['assessment_id']);assert winner==expected['assessment']
   learned=learning.get(project,expected['learning']['learning_id']);assert learned==expected['learning']
   projection=feedback.get(expected['projection']['id']);assert projection==expected['projection']
   assert analytics.process() is None
   result={'platform':expected['analytics']['result']['platform'],'winner_sha256':digest(winner),'learning_sha256':digest(learned),
    'projection_sha256':digest(projection),'learning_observations':learned['observation_count'],'database':database_status(store.db),
    'provider_calls':0,'credential_decryption':0,'automatic_replay':False,'current_credentials_configured':False}
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--child',action='store_true');a=p.parse_args()
 if a.child:print(json.dumps(cold(a.source)));return
 out=a.output.resolve();assert not out.exists() and ROOT not in out.parents;out.mkdir(parents=True);results=[]
 for platform in ('instagram_reels','facebook'):
  completed=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--child','--source',str(a.source/platform)],
    cwd=ROOT,capture_output=True,text=True,timeout=120)
  (out/(platform+'-stdout.log')).write_text(completed.stdout,encoding='utf-8')
  (out/(platform+'-stderr.log')).write_text(completed.stderr,encoding='utf-8')
  assert completed.returncode==0,platform+' child failed; inspect retained stderr'
  result=json.loads(completed.stdout);durable_json(out/(platform+'-proof.json'),result);results.append(result)
 durable_json(out/'evidence.json',{'separate_process_restore_passed':True,'platforms':results,'owned_roots_cleaned':True,
  'real_provider_calls':0,'paid_calls':0,'Owner_UAT':False,'real_publishing':False,'production_deployed':False,'full_Mode_A_B_accepted':False})
 print(json.dumps({'separate_process_restore_passed':True,'platforms':2,'provider_calls':0,'credential_decryption':0}))

if __name__=='__main__':main()

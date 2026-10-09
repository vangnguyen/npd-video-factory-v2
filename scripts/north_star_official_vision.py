"""Retained finite official Vision kernel on actual PNGs and explicit HTTP mocks."""
import argparse, copy, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.contracts import file_sha
from services.windows_native.store import Store
from services.windows_native.vision import NativeVision
from services.windows_native.vision_credentials import NativeVisionKeyVault
from services.windows_native.vision_registry import VisionProfile, NativeVisionFactory
from services.windows_native.official_vision import NativeOfficialVision
from services.windows_native.official_vision_models import Analyze, Action
from services.windows_native.backup import create_backup, restore_backup, database_status
from scripts.north_star_vision_frame_bridge import config_for
from scripts.north_star_google_oauth_operations import journals

WORKSPACE = 'wsp_vision_rehearsal'


def write(path,value):
    raw = json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    assert 'sk-explicit-synthetic-' not in raw and 'Bearer ' not in raw and 'data:image/' not in raw
    with path.open('x',encoding='utf-8',newline='\n') as h:h.write(raw)


def owned(path,kind,fresh=False):
    path = path.resolve()
    if path.parent != Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-vision-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Fresh owned official Vision fixture required')
    return path


def reopen(args):
    root = owned(args.restore_root,'restore'); out = args.output.resolve(); store = Store(root); config = config_for(root)
    vision = NativeVision(store,config,workspace_id=WORKSPACE); runtime = NativeOfficialVision(vision)
    expected = json.loads((out/'expected-runtime-history.json').read_bytes())
    for row in expected: assert runtime.get(row['project_id'],row['vision_id']) == row
    legacy = NativeVision(store,config)
    for row in json.loads((out/'expected-legacy-history.json').read_bytes()): assert legacy.get(row['project_id'],row['vision_id']) == row
    for project in json.loads((out/'expected-budgeted-projects.json').read_bytes()): assert store.get(project['id']) == project
    assert journals(store) == json.loads((out/'expected-journals.json').read_bytes()) and database_status(store.db)['active_operations'] == 0
    assert runtime.recover() == 0
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'all_thirteen_journals_eight_intents_seven_responses_eight_mock_costs_two_budgeted_projects_legacy_histories_exact':True,
        'current_keys_profiles_owner_identity_or_provider_calls_required_for_history':False,
        'recovery_resends_or_renews_consent':False,'real_provider_tested':False,'owner_uat_accepted':False})


def run(args):
    state = owned(args.state_root,'state',True); restored = owned(args.restore_root,'restore',True); out = args.output.resolve()
    prior = args.registry_input.resolve(); frame_input = args.frame_input.resolve()
    if out.exists() or out == ROOT or ROOT in out.parents: raise ValueError('Fresh external runtime evidence required')
    out.mkdir(parents=True); archive = prior/'public-vision-registry.zip'
    write(out/'prior-restore.json',restore_backup(archive,state,expected_sha256=file_sha(archive)))
    store = Store(state); config = config_for(state)
    originals = json.loads((frame_input/'expected-projects.json').read_bytes()); bindings = json.loads((frame_input/'input-bindings.json').read_bytes())
    for project in originals: assert store.get(project['id']) == project
    original_files = {p.relative_to(state).as_posix():file_sha(p) for p in state.rglob('*') if p.is_file()
        and p.suffix != '.sqlite3' and not p.name.endswith(('-wal','-shm'))}
    write(state/'.vf-auth-workspace.json',{'schema':'vf-native-workspace-binding-v1','workspace_id':WORKSPACE})
    raw,data = human_fixture('owner',workspace=WORKSPACE); verifier = [HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)]
    principal = verifier[0].verify('Bearer '+raw); clock = [datetime.now(timezone.utc)]
    private = Path('C:/vf-native-fixture-vision-registry-secrets-01'); vault = NativeVisionKeyVault(private,state,WORKSPACE)
    profile = VisionProfile.model_validate(json.loads((private/'public-vision-registry.json').read_bytes())['profiles'][0])
    receipts = json.loads((prior/'public-key-receipts.json').read_bytes()); private_hashes = {r['reference']:file_sha(vault.path(r['reference'])) for r in receipts}
    modes = ('image-success','video-success','revoke','invalid','missing-usage','timeout','cancel','recover'); mode = [None]; pending = [None]; wire = []
    def change_owner(enabled):
        value = verifier[0].registry.model_dump(mode='json'); value['tokens'][principal.token_id]['enabled'] = enabled
        verifier[0] = HumanAuthVerifier(HumanAuthRegistry.model_validate(value),max_token_ttl_seconds=86400)
    def response(request):
        body = json.loads(request.content); count = sum(v['type']=='input_image' for v in body['input'][0]['content'])
        assert str(request.url) == 'https://api.openai.com/v1/responses' and request.method == 'POST' and body['store'] is False
        wire.append({'kind':mode[0],'frame_count':count,'fixed_endpoint':True,'mock':True})
        payload = response_payload(count)
        if mode[0] == 'revoke': change_owner(False)
        if mode[0] == 'invalid': payload['output'][0]['content'][0]['text'] = 'INVALID EXPLICIT STRUCTURED MOCK'
        if mode[0] == 'missing-usage': payload.pop('usage')
        if mode[0] == 'timeout': raise httpx.ReadTimeout('EXPLICIT SYNTHETIC PROVIDER TIMEOUT',request=request)
        if mode[0] == 'cancel': runtime.cancel(pending[0]['project_id'],pending[0]['vision_id'],Action(expected_snapshot_sha256=pending[0]['snapshot_sha256']),principal=principal)
        if mode[0] == 'recover': runtime.recover()
        return httpx.Response(200,json=payload)
    factory = NativeVisionFactory(profile,vault,operator_enabled=True,transport=httpx.MockTransport(response))
    vision = NativeVision(store,config,workspace_id=WORKSPACE)
    runtime = NativeOfficialVision(vision,factories={profile.profile_id:factory},enabled=True,identity_provider=lambda:verifier[0],clock=lambda:clock[0])
    # Explicit reversible configuration changes only in the newly owned rehearsal clone.
    projects = []
    for original in originals:
        runtime.costs.set_budget(original['id'],original['revision'],'10000'); projects.append(store.get(original['id']))
    expected = []
    for index,kind in enumerate(modes):
        change_owner(True); mode[0] = kind; project = projects[index % 2]; binding = bindings[index % 2]
        payload = Analyze(revision=project['revision'],profile_id=profile.profile_id,expected_configuration_sha256=factory.sha256,
            observation_id=binding['source_observation_id'],acknowledged_external_image_analysis=True,acknowledged_protocol_mock=True,
            max_operation_cost_vnd='500',request_key='retained-official-native-vision-'+kind)
        row,replay = runtime.create(project['id'],payload,principal=principal); assert not replay and row['status'] == 'approved'
        pending[0] = row; done = runtime.process(project['id'],row['vision_id'],Action(expected_snapshot_sha256=row['snapshot_sha256']))
        target = 'succeeded' if index < 2 else 'review_required' if kind in ('revoke','invalid','missing-usage') else 'cancelled' if kind == 'cancel' else 'outcome_unknown'
        assert done['status'] == target
        if done['result']:
            assert done['result']['mock'] and not done['result']['semantic_inference_performed'] and not done['result']['automatic_planning_eligible']
            assert len(done['result']['frames']) == (1 if index == 0 else 8)
        calls = len(wire); assert runtime.process(project['id'],row['vision_id'],Action(expected_snapshot_sha256=row['snapshot_sha256'])) == done
        assert len(wire) == calls and store.get(project['id']) == project
        expected.append(done)
    assert len(wire) == 8 and sum(v['response'] is not None for v in expected) == 7
    assert sum(v['result'] is not None for v in expected) == 2
    assert all(file_sha(state/name) == checksum for name,checksum in original_files.items())
    assert all(file_sha(vault.path(ref)) == checksum for ref,checksum in private_hashes.items())
    legacy = NativeVision(store,config); histories = json.loads((frame_input/'expected-legacy-vision-history.json').read_bytes())
    for row in histories: assert legacy.get(row['project_id'],row['vision_id']) == row
    assert all(row['actual_cost'] is None and not row['paid'] and not row['external_call'] for p in projects for row in runtime.costs.summary(p['id'])['records'])
    write(out/'expected-runtime-history.json',expected); write(out/'expected-legacy-history.json',histories)
    write(out/'original-pre-budget-projects.json',originals); write(out/'expected-budgeted-projects.json',projects)
    write(out/'mock-wire-summary.json',wire); write(out/'cost-summary.json',[runtime.costs.summary(p['id']) for p in projects]); write(out/'expected-journals.json',journals(store))
    backup = create_backup(config,out/'public-official-vision.zip'); write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-official-vision.zip',restored,expected_sha256=backup['sha256']))
    reopen(args)
    sources = ('services/windows_native/official_vision.py','services/windows_native/official_vision_models.py','services/windows_native/tests/test_official_vision.py',
        'services/windows_native/vision_registry.py','services/windows_native/backup.py','apps/api/app/openai_vision_provider.py',
        'apps/api/tests/test_vision_dispatch_admission.py','scripts/north_star_official_vision.py')
    write(out/'evidence.json',{'schema_version':'native-official-vision-runtime-rehearsal-v1','source_sha256':{n:file_sha(ROOT/n) for n in sources},
        'public_backup_sha256':backup['sha256'],'projects':2,'explicit_owned_clone_budget_revisions':2,'original_files_and_legacy_four_histories_and_private_generations_exact':True,
        'project_media_and_timeline_exact_after_budget_configuration':True,'mock_requests':8,'official_intents':8,'complete_responses':7,'mock_semantic_results':2,'cost_operations':8,
        'known_usage_observations':6,'unknown_usage_observations':1,'outcome_unknown_operations':2,'journal_count':len(journals(store)),
        'reused_unique_pngs':9,'new_cpu_jobs':0,'finite_one_use_original_consent_no_retry_known_response_before_late_fence':True,
        'mock_budget_rights_status_are_explicit_not_licenses_or_real_invoices':True,'real_secret_reads':0,'external_provider_calls':0,'paid_operations':0,'real_publications':0,
        'semantic_inference_performed':False,'continuous_tracking_performed':False,'decoded_pts_verified':False,'owner_uat_accepted':False,
        'signed_http_runtime_or_studio_integrated':False,'real_provider_tested':False,'production_deployed':False,
        'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','mock_requests':8,'complete_responses':7,'mock_semantic_results':2,'journal_count':len(journals(store)),'actual_paid_costs':None}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--registry-input',type=Path); p.add_argument('--frame-input',type=Path)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--state-root',type=Path); p.add_argument('--restore-root',type=Path,required=True)
    p.add_argument('--new-process',action='store_true'); args = p.parse_args()
    if args.new_process: reopen(args)
    else: run(args)

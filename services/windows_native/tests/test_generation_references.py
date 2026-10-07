"""Real owned pixels/SQLite; explicit service wires, never real rights or GPU."""
import asyncio,hashlib,io,json,os,tempfile,unittest,uuid
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from PIL import Image
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.generation_models import NativeImageParameters,NativeVideoParameters
from services.windows_native.generation_registry import GenerationCredential,GenerationFactory
from services.windows_native.generation_references import NativeGenerationReferences,selected_references
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config
from services.windows_native.rights_override import NativeRightsOverrides,rights_sha
from services.windows_native.store import Store

TOKEN='explicit-native-reference-fixture-token-32'
WORKSPACE='wsp_native_generation_references_fixture'


class GenerationReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state';self.store=Store(self.root);self.config=Config(data_root=self.root)
        source=Path(self.temp.name)/'explicit-owned-pixels.png';Image.new('RGB',(320,240),(40,90,140)).save(source)
        self.asset=ingest_media(self.config,source,'image/png','EXPLICIT LOCALLY GENERATED REFERENCE FIXTURE',rights_confirmed=True,illustration=False)
        self.project=self.store.create('EXPLICIT REFERENCE FIXTURE','PRIVATE REFERENCE CONTENT');self.project=self.store.append_media(self.project['id'],self.project['revision'],self.asset)
        self.clock=[datetime.now(timezone.utc)];self.service=NativeGenerationReferences(self.store,workspace_id=WORKSPACE,clock=lambda:self.clock[0])
        self.calls=[];self.remote={};self.behavior='normal';self.transport=httpx.MockTransport(self.wire)
        self.factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),owner_enabled=True,transport=self.transport)
        self.overrides=NativeRightsOverrides(self.store,workspace_id=WORKSPACE,enabled=True,clock=lambda:self.clock[0]);self.identity=uuid.uuid4().hex

    def tearDown(self):self.temp.cleanup()

    def change(self,**updates):
        with self.store.transaction() as con:
            project=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(self.project['id'],)).fetchone());doc=project['document']
            doc['assets'][0].update(updates);con.execute('UPDATE projects SET document=?,revision=revision+1,approval=NULL WHERE id=?',(json.dumps(doc),project['id']))
            self.store.version(con,project['id'])
        self.project=self.store.get(self.project['id']);self.asset=deepcopy(self.project['document']['assets'][0])

    def owned(self,**updates):self.change(rights_status='owned',license='EXPLICIT OWNED SYNTHETIC PIXEL FIXTURE, NOT REAL CLEARANCE',**updates)
    def reference(self):return {'asset_id':self.asset['id'],'asset_sha256':self.asset['sha256']}
    def value(self,**options):return NativeImageParameters(prompt='EXPLICIT REFERENCE TRANSFORM FIXTURE',operation='image_to_image',references=[self.reference()],**options)
    def freeze(self,value=None):return self.service.freeze(self.project['id'],self.store.get(self.project['id'])['revision'],value or self.value(),self.factory,fixture_acknowledged=True)
    def stage(self,snapshot):return asyncio.run(self.service.stage(self.identity,snapshot,self.factory))
    def rows(self):
        with self.store.transaction() as con:return [dict(row) for row in con.execute('SELECT * FROM native_generation_reference_admissions')]

    def wire(self,request):
        self.calls.append((request.method,request.url.path));self.assertEqual(request.headers['Authorization'],'Bearer '+TOKEN)
        self.assertEqual(request.headers['X-VF-Workspace-Id'],WORKSPACE);self.assertEqual(request.headers['X-VF-Project-Id'],self.project['id'])
        if request.method=='GET':
            value=self.remote.get(request.url.path.rsplit('/',1)[-1]);return httpx.Response(200,json=value) if value else httpx.Response(404)
        self.assertEqual(request.url.path,'/v1/references');admission=json.loads(request.headers['X-VF-Reference-Admission']);identity=digest(admission)
        self.assertEqual(hashlib.sha256(request.content).hexdigest(),admission['content_sha256'])
        with Image.open(io.BytesIO(request.content)) as image:image.load();width,height=image.size
        # Bridge metadata is an explicit wire fixture; actual Native decode is
        # exercised above and actual bridge FFmpeg intake has separate evidence.
        value={'reference_id':identity,'source_reference':'vf-reference://'+identity,'filename':'reference.jpg','size_bytes':len(request.content),
            'admission':admission,'media':{'full_decode_passed':True,'width':width,'height':height,'qc_passed':False},
            'rights_independently_verified':False,'publishing_authorized':False,'created_at':self.clock[0].isoformat()}
        if self.behavior=='absent':raise httpx.ReadError('EXPLICIT LOST FIXTURE RESPONSE')
        self.remote[identity]=value
        if self.behavior=='lost':raise httpx.ReadError('EXPLICIT LOST FIXTURE RESPONSE')
        if self.behavior=='foreign':return httpx.Response(201,json={**value,'admission':{**admission,'project_id':'0'*32}})
        if self.behavior=='redirect':return httpx.Response(307,headers={'Location':'https://attacker.test/private'})
        if self.behavior=='oversized':return httpx.Response(201,content=b'x'*65537)
        return httpx.Response(201,json=value)

    def grant(self):
        self.project=self.store.get(self.project['id']);return self.overrides.record(self.project['id'],self.asset['id'],{
            'revision':self.project['revision'],'asset_sha256':self.asset['sha256'],'expected_rights_sha256':rights_sha(self.asset),
            'action':'grant','reason':'EXPLICIT OWNER DECISION FIXTURE, NOT LEGAL CLEARANCE','evidence_reference':'document://explicit-native-generation-fixture',
            'valid_days':1,'allow_publishing_review':False,'acknowledged':True,'request_key':'explicit-reference-owner-grant-fixture'},actor='explicit-owner-fixture')

    def test_unknown_attestation_blocks_without_mutation_journal_or_network(self):
        before=self.store.get(self.project['id']);self.assertTrue(self.asset['rights_confirmed']);self.assertEqual(self.asset['rights_status'],'unknown')
        with self.assertRaises(WorkflowError) as error:self.freeze()
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_REFERENCE_RIGHTS_REVIEW_REQUIRED')
        self.assertEqual(self.calls,[]);self.assertEqual(self.rows(),[]);self.assertEqual(self.store.get(self.project['id']),before)

    def test_actual_owned_decode_immutable_issue_and_staging_preserve_raw_rights_and_timeline(self):
        self.owned();before=self.store.get(self.project['id']);snapshot=self.freeze();first=self.service.issue(self.identity,snapshot,self.factory)
        self.clock[0]+=timedelta(seconds=10);self.assertEqual(first,self.service.issue(self.identity,snapshot,self.factory))
        self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0]['state'],'reserved')
        value=self.stage(snapshot);self.assertTrue(value.reference_images[0].startswith('vf-reference://'))
        self.assertEqual(self.calls,[('GET','/v1/references/'+digest(first[0])),('POST','/v1/references')])
        self.assertEqual(self.rows()[0]['state'],'confirmed');self.assertEqual(self.store.get(self.project['id']),before)
        self.assertNotIn(TOKEN,json.dumps(self.rows()));self.assertFalse(json.loads(self.rows()[0]['metadata_json'])['publishing_authorized'])

    def test_fresh_service_reopens_confirmed_ticket_with_exact_get_and_no_repeat_post(self):
        self.owned();snapshot=self.freeze();first=self.stage(snapshot)
        self.service=NativeGenerationReferences(Store(self.root),workspace_id=WORKSPACE,clock=lambda:self.clock[0]);self.calls.clear()
        self.assertEqual(self.stage(snapshot),first);self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][0],'GET')

    def test_lost_upload_response_reconciles_exact_ticket_and_never_reposts(self):
        self.owned();snapshot=self.freeze();self.behavior='lost';first=self.stage(snapshot)
        self.assertEqual([method for method,_ in self.calls],['GET','POST','GET']);self.stage(snapshot)
        self.assertEqual(sum(method=='POST' for method,_ in self.calls),1);self.assertEqual(self.rows()[0]['state'],'confirmed')

    def test_ambiguous_absent_upload_and_expired_intent_never_write_again(self):
        self.owned();snapshot=self.freeze();self.behavior='absent'
        for _ in range(2):
            with self.assertRaises(WorkflowError) as error:self.stage(snapshot)
            self.assertEqual(error.exception.code,'NATIVE_GENERATION_REFERENCE_RECOVERY_REQUIRED')
        self.assertEqual(sum(method=='POST' for method,_ in self.calls),1);self.assertEqual(self.rows()[0]['state'],'dispatching')
        count=len(self.calls);self.clock[0]+=timedelta(minutes=31)
        with self.assertRaises(WorkflowError) as error:self.stage(snapshot)
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_REFERENCE_ADMISSION_EXPIRED');self.assertEqual(len(self.calls),count)

    def test_owner_override_retains_unknown_rights_scoped_hash_and_expiry(self):
        grant=self.grant();snapshot=self.freeze();source=snapshot['sources'][0]
        self.assertEqual(source['rights_status'],'unknown');self.assertEqual(source['authorization_kind'],'explicit_owner_override')
        self.assertEqual(source['override_sha256'],grant['record']['sha256']);self.stage(snapshot)
        self.assertEqual(self.store.get(self.project['id'])['document']['assets'][0]['rights_status'],'unknown')
        self.clock[0]+=timedelta(days=1);before=len(self.calls)
        with self.assertRaises(WorkflowError):self.stage(snapshot)
        self.assertEqual(len(self.calls),before)

    def test_disabling_override_before_dispatch_blocks_even_with_saved_admission(self):
        self.grant();snapshot=self.freeze();self.service.issue(self.identity,snapshot,self.factory);self.overrides.enabled=False
        with self.assertRaises(WorkflowError):self.stage(snapshot)
        self.assertEqual(self.calls,[])

    def test_derived_known_metadata_needs_new_scoped_exception(self):
        self.owned(rights_review_required=True)
        with self.assertRaises(WorkflowError):self.freeze()
        self.grant();snapshot=self.freeze();admission=self.service.issue(self.identity,snapshot,self.factory)[0]
        self.assertEqual(admission['rights_status'],'owned');self.assertEqual(admission['authorization_kind'],'explicit_owner_override')

    def test_fixture_rights_never_use_live_transport_or_owner_exception(self):
        self.owned(explicit_fixture=True);snapshot=self.freeze();self.assertTrue(snapshot['sources'][0]['fixture'])
        with self.assertRaises(WorkflowError):self.service.source(self.store.get(self.project['id']),self.value().references[0],'official')
        self.change(rights_status='unknown')
        with self.assertRaises(WorkflowError):self.grant()
        self.assertEqual(self.calls,[])

    def test_reference_source_cannot_be_foreign_duplicate_changed_or_extension_spoofed(self):
        self.owned();value=self.value();value.references.append(value.references[0].model_copy(update={'asset_sha256':'0'*64}))
        with self.assertRaises(WorkflowError):selected_references(value)
        other=self.store.create('OTHER REFERENCE FIXTURE','private')
        with self.assertRaises(WorkflowError):self.service.freeze(other['id'],other['revision'],self.value(),self.factory,fixture_acknowledged=True)
        path=self.root/'assets'/self.asset['id'];path.write_bytes(b'\xff\xd8\xffnot-decodable');self.change(sha256=file_sha(path),bytes=path.stat().st_size)
        with self.assertRaises(WorkflowError) as error:self.freeze()
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_REFERENCE_DECODE_INVALID');self.assertEqual(self.calls,[])

    def test_linked_actual_source_fails_before_any_provider_or_journal(self):
        self.owned();path=self.root/'assets'/self.asset['id'];other=Path(self.temp.name)/'owned-link.jpg';os.link(path,other)
        with self.assertRaises(WorkflowError) as error:self.freeze()
        self.assertEqual(error.exception.code,'BACKUP_LINKED_PATH_REJECTED');self.assertEqual(self.rows(),[])

    def test_project_snapshot_source_or_provider_configuration_drift_blocks_before_calls(self):
        self.owned();snapshot=self.freeze();self.change(description='EXPLICIT CHANGED DESCRIPTION')
        with self.assertRaises(WorkflowError):self.stage(snapshot)
        self.assertEqual(self.calls,[])
        snapshot=self.freeze();self.factory.credential.bridge_url='http://localhost:9999'
        with self.assertRaises(WorkflowError) as error:self.stage(snapshot)
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_PROVIDER_CONFIGURATION_CHANGED');self.assertEqual(self.calls,[])

    def test_rehashed_foreign_journal_or_false_metadata_is_rejected_before_network(self):
        self.owned();snapshot=self.freeze();self.service.issue(self.identity,snapshot,self.factory)
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_generation_reference_admissions').fetchone();admission=json.loads(row['admission_json']);admission['project_id']='0'*32
            con.execute('UPDATE native_generation_reference_admissions SET admission_json=?,reference_id=?',(json.dumps(admission),digest(admission)))
        with self.assertRaises(WorkflowError):self.stage(snapshot)
        self.assertEqual(self.calls,[])

    def test_all_reference_modes_deduplicate_inputs_and_keep_same_mask_binding(self):
        self.owned()
        for value in [self.value(),NativeImageParameters(prompt='inpaint fixture',operation='inpaint',references=[self.reference(),self.reference()],mask=self.reference()),
            NativeImageParameters(prompt='upscale fixture',operation='upscale',references=[self.reference()],upscale_factor=4),
            NativeVideoParameters(prompt='video fixture',mode='image_to_video',references=[self.reference()]),
            NativeVideoParameters(prompt='video fixture',mode='reference_assisted',references=[self.reference()])]:
            self.identity=uuid.uuid4().hex;snapshot=self.freeze(value);result=self.stage(snapshot);self.assertEqual(len(snapshot['sources']),1)
            if hasattr(result,'mask_reference') and result.mask_reference:self.assertEqual(result.mask_reference,result.reference_images[0])
        # The identical asset/rights/time admission is reusable within this
        # project even when five distinct generation jobs select it.
        self.assertEqual(sum(method=='POST' for method,_ in self.calls),1);self.assertEqual(len(self.rows()),5)

    def test_foreign_oversized_and_redirect_metadata_never_creates_confirmed_false_binding(self):
        self.owned();snapshot=self.freeze();self.behavior='foreign'
        with self.assertRaises(WorkflowError) as error:self.stage(snapshot)
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_REFERENCE_BRIDGE_BINDING_INVALID');self.assertEqual(self.rows()[0]['state'],'dispatching')
        self.remote.clear();self.behavior='oversized';self.identity=uuid.uuid4().hex
        # The response is oversized, but exact independent readback reconciles
        # the remote durable record rather than trusting that response body.
        self.stage(snapshot);self.assertEqual(self.rows()[-1]['state'],'confirmed')
        self.remote.clear();self.behavior='redirect';self.identity=uuid.uuid4().hex;self.stage(snapshot)
        self.assertTrue(all('attacker' not in path for _,path in self.calls))

"""Actual local image/audio/video bytes and durable SQLite; no provider/Owner UAT."""
import copy,hashlib,json,os,subprocess,tempfile,unittest,uuid,wave
from pathlib import Path
from PIL import Image
from pydantic import ValidationError
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.multipart_ingestion import NativeMultipartIngestion,CHUNK_BYTES,subtitle_cues
from services.windows_native.media import library_assets,library_file
from services.windows_native.backup import create_backup,restore_backup,database_status

class MultipartIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name).resolve();self.root=self.folder/'state'
        self.config=Config(data_root=self.root);self.store=Store(self.root);self.project=self.store.create('Multipart local real intake','','media')
        self.service=NativeMultipartIngestion(self.store,self.config,workspace_id='wsp_multipart_fixture')
    def tearDown(self):self.temp.cleanup()
    def body(self,raw,kind='subtitle',mime='application/x-subrip',**kw):
        return {'revision':self.store.get(self.project['id'])['revision'],'kind':kind,'content_type':mime,'filename':'Nội dung không phụ thuộc phần mở rộng.bin',
            'total_bytes':len(raw),'expected_sha256':hashlib.sha256(raw).hexdigest(),'rights_confirmed':True,'illustration':False,'request_key':'multipart-owned-fixture-'+uuid.uuid4().hex,**kw}
    def start(self,raw,**kw):return self.service.create(self.project['id'],self.body(raw,**kw),actor='editor-fixture')[0]
    def send(self,raw,session):
        for offset in range(0,len(raw),CHUNK_BYTES):
            part=raw[offset:offset+CHUNK_BYTES];session=self.service.chunk(self.project['id'],session['upload_id'],offset,hashlib.sha256(part).hexdigest(),part)[0]
        return session
    def finish(self,session,revision=None):
        return self.service.complete(self.project['id'],session['upload_id'],{'revision':revision or self.store.get(self.project['id'])['revision'],'expected_parts_sha256':session['parts_sha256']})[0]
    def assets(self):
        image=self.folder/'alpha.png';Image.new('RGBA',(320,320),(40,180,200,120)).save(image)
        audio=self.folder/'audio.wav'
        with wave.open(str(audio),'wb') as h:h.setnchannels(1);h.setsampwidth(2);h.setframerate(16000);h.writeframes(b'\x02\x00'*32000)
        video=self.folder/'video.mp4'
        result=subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','color=c=blue:s=128x128:d=1',
            '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(video)],capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        return [('video','video/mp4',video.read_bytes()),('audio','audio/wav',audio.read_bytes()),('image','image/png',image.read_bytes()),
                ('logo','image/png',image.read_bytes()),('music','audio/wav',audio.read_bytes()),('subtitle','application/x-subrip','1\n00:00:00,000 --> 00:00:01,000\nTiếng Việt: Cần Giờ.\n'.encode())]
    def test_all_six_types_resume_after_reopen_use_actual_decoders_and_keep_originals(self):
        for kind,mime,raw in self.assets():
            with self.subTest(kind=kind):
                before=self.store.get(self.project['id']);session=self.send(raw,self.start(raw,kind=kind,mime=mime))
                self.service=NativeMultipartIngestion(Store(self.root),self.config,workspace_id=self.service.workspace)
                resumed=self.service.get(self.project['id'],session['upload_id']);self.assertEqual(resumed,session)
                done=self.finish(resumed);asset=done['result']['asset'];self.assertEqual(done['status'],'completed')
                self.assertEqual(asset['source_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(asset['canonical_role'],kind)
                self.assertEqual((self.root/'originals'/asset['original_id']).read_bytes(),raw);self.assertEqual(asset['rights_status'],'unknown')
                current=self.store.get(self.project['id']);self.assertEqual(current['revision'],before['revision']+1);self.assertIsNone(current['approval'])
                self.assertFalse(any(self.service.directory(done['upload_id']).glob('part-*.bin')))
                self.assertEqual(self.service.get(self.project['id'],done['upload_id']),done)
                if kind=='logo':
                    with Image.open(self.root/'assets'/asset['id']) as image:self.assertEqual(image.mode,'RGBA');self.assertEqual(image.getpixel((0,0))[3],120)
                if kind in {'audio','music'}:self.assertEqual(asset['kind'],'audio');self.assertTrue(asset['has_audio']);self.assertGreater(asset['duration_seconds'],0)
                if kind=='subtitle':self.assertIn('Cần Giờ',asset['cues'][0]['text'])
        listing=library_assets(self.service.store);self.assertEqual(len(listing['items']),6)
        for row in listing['items']:self.assertTrue(library_file(self.service.store,row['id'])[0].is_file())
    def test_chunk_checksum_range_replay_and_orphan_recovery_are_exact(self):
        raw=b'x'*(CHUNK_BYTES+50);session=self.start(raw,kind='video',mime='video/mp4');identity=session['upload_id'];part=raw[:CHUNK_BYTES];sha=hashlib.sha256(part).hexdigest()
        with self.assertRaisesRegex(WorkflowError,'CHECKSUM'):self.service.chunk(self.project['id'],identity,0,'a'*64,part)
        with self.assertRaisesRegex(WorkflowError,'RANGE'):self.service.chunk(self.project['id'],identity,1,sha,part)
        self.service.file(identity,'part-0000.bin').write_bytes(part)
        first,replay=self.service.chunk(self.project['id'],identity,0,sha,part);self.assertFalse(replay)
        second,replay=self.service.chunk(self.project['id'],identity,0,sha,part);self.assertTrue(replay);self.assertEqual(first,second)
        other=b'y'*CHUNK_BYTES
        with self.assertRaisesRegex(WorkflowError,'CONFLICT'):self.service.chunk(self.project['id'],identity,0,hashlib.sha256(other).hexdigest(),other)
        with self.assertRaisesRegex(WorkflowError,'INCOMPLETE'):self.finish(first)
        self.assertEqual(self.store.get(self.project['id'])['revision'],1)
    def test_content_magic_is_authoritative_and_bad_upload_never_attaches(self):
        raw=b'not a PNG despite filename and MIME';session=self.send(raw,self.start(raw,kind='image',mime='image/png',filename='picture.png'))
        with self.assertRaisesRegex(WorkflowError,'MAGIC'):self.finish(session)
        self.assertEqual(self.service.get(self.project['id'],session['upload_id'])['status'],'needs_attention')
        self.assertEqual(self.store.get(self.project['id'])['document']['assets'],[])
    def test_duplicate_is_detected_without_new_asset_or_revision_and_completed_replay_is_readonly(self):
        raw=b'1\n00:00:00,000 --> 00:00:01,000\nDuplicate local caption\n'
        done=self.finish(self.send(raw,self.start(raw)));before=self.store.get(self.project['id'])
        duplicate=self.finish(self.send(raw,self.start(raw)));self.assertTrue(duplicate['result']['duplicate'])
        self.assertEqual(duplicate['result']['asset']['id'],done['result']['asset']['id']);self.assertEqual(self.store.get(self.project['id']),before)
        replay,flag=self.service.complete(self.project['id'],done['upload_id'],{'revision':before['revision'],'expected_parts_sha256':done['parts_sha256']});self.assertTrue(flag);self.assertEqual(replay,done)
    def test_original_request_types_workspace_path_and_idempotency_are_closed(self):
        raw=b'caption';body=self.body(raw)
        session,_=self.service.create(self.project['id'],body,actor='fixture')
        replay,flag=self.service.create(self.project['id'],body,actor='fixture');self.assertTrue(flag);self.assertEqual(session,replay)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY'):self.service.create(self.project['id'],{**body,'filename':'other.srt'},actor='fixture')
        for changed in [{'rights_confirmed':1},{'total_bytes':'7'},{'kind':'logo','content_type':'image/jpeg'},{'filename':'../outside.srt'},{'private_path':'outside'}]:
            with self.subTest(changed=changed),self.assertRaises(ValidationError):self.service.create(self.project['id'],{**body,**changed},actor='fixture')
        with self.assertRaisesRegex(WorkflowError,'ID_INVALID'):self.service.directory('../outside')
        other=NativeMultipartIngestion(self.store,self.config,workspace_id='wsp_other')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):other.get(self.project['id'],session['upload_id'])
    def test_final_source_checksum_and_parts_manifest_cannot_be_substituted(self):
        raw=b'1\n00:00:00,000 --> 00:00:01,000\nChecksum\n';session=self.send(raw,self.start(raw,expected_sha256='a'*64))
        with self.assertRaisesRegex(WorkflowError,'PARTS_CHANGED'):self.service.complete(self.project['id'],session['upload_id'],{'revision':1,'expected_parts_sha256':'b'*64})
        with self.assertRaisesRegex(WorkflowError,'SOURCE_CHECKSUM'):self.finish(session)
        self.assertEqual(self.store.get(self.project['id'])['revision'],1)
    def test_stale_attach_requires_explicit_current_revision_without_losing_received_bytes(self):
        raw=b'1\n00:00:00,000 --> 00:00:01,000\nRevision bound\n';session=self.send(raw,self.start(raw))
        self.store.append_media(self.project['id'],1,{'id':'explicit-not-selected.jpg','kind':'image','filename':'Fixture metadata','sha256':'a'*64,'rights_confirmed':True})
        with self.assertRaises(WorkflowError):self.finish(session,revision=1)
        self.assertEqual(self.service.get(self.project['id'],session['upload_id'])['received_bytes'],len(raw))
        done=self.finish(session,revision=2);self.assertEqual(done['result']['attached_revision'],3)
    def test_partial_backup_restore_preserves_chunks_and_can_resume_with_new_root(self):
        raw=b'x'*(CHUNK_BYTES+50);session=self.start(raw,kind='video',mime='video/mp4');part=raw[:CHUNK_BYTES]
        partial=self.service.chunk(self.project['id'],session['upload_id'],0,hashlib.sha256(part).hexdigest(),part)[0]
        backup=create_backup(self.config,self.folder/'partial.zip');destination=self.folder/'restored';restore_backup(self.folder/'partial.zip',destination,expected_sha256=backup['sha256'])
        restored=NativeMultipartIngestion(Store(destination),Config(data_root=destination),workspace_id=self.service.workspace)
        self.assertEqual(restored.get(self.project['id'],session['upload_id']),partial)
        last=raw[CHUNK_BYTES:];resumed,_=restored.chunk(self.project['id'],session['upload_id'],CHUNK_BYTES,hashlib.sha256(last).hexdigest(),last)
        self.assertEqual(resumed['received_bytes'],len(raw));self.assertEqual(database_status(restored.store.db)['active_operations'],0)
    def test_subtitle_text_and_timestamps_keep_vietnamese_without_html_or_unsupported_shapes(self):
        vtt='WEBVTT\n\n00:00.000 --> 00:01.000\nCần Giờ – tiếng Việt.\n'.encode()
        self.assertEqual(subtitle_cues(vtt,'text/vtt')[0]['text'],'Cần Giờ – tiếng Việt.')
        for raw,mime in [(vtt,'application/x-subrip'),(b'WEBVTT\n\n00:00.000 --> 00:01.000\n<script>\n','text/vtt'),(b'1\n00:00:02,000 --> 00:00:01,000\nBad\n','application/x-subrip')]:
            with self.assertRaises(WorkflowError):subtitle_cues(raw,mime)
    def test_registered_chunk_tamper_and_hardlink_are_rejected_before_attachment(self):
        raw=b'1\n00:00:00,000 --> 00:00:01,000\nEvidence\n';session=self.send(raw,self.start(raw));path=self.service.file(session['upload_id'],'part-0000.bin')
        path.write_bytes(b'x'*len(raw))
        with self.assertRaisesRegex(WorkflowError,'CHANGED'):self.service.get(self.project['id'],session['upload_id'])
        path.write_bytes(raw);link=self.folder/'linked.bin';os.link(path,link)
        with self.assertRaisesRegex(WorkflowError,'LINKED'):self.finish(session)
    def test_interrupted_validation_is_reviewable_without_automatic_asset_registration(self):
        raw=b'caption';session=self.start(raw)
        with self.store.transaction() as con:con.execute("UPDATE native_upload_sessions SET status='validating',claim_id='explicit-crash-claim' WHERE upload_id=?",(session['upload_id'],))
        reopened=NativeMultipartIngestion(self.store,self.config,workspace_id=self.service.workspace)
        self.assertEqual(reopened.get(self.project['id'],session['upload_id'])['status'],'needs_attention');self.assertEqual(self.store.get(self.project['id'])['revision'],1)

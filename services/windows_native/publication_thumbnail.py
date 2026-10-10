"""Original thumbnail/current Owner exception binding for dry-run review only."""
import copy
from contextlib import nullcontext
from .contracts import WorkflowError,digest
from .render_thumbnail_rights import NativeRenderThumbnailRights,stamp
from .official_publications import utc


class NativePublicationThumbnailBinding:
    def __init__(self,store,workspace,rights):
        if type(rights) is not NativeRenderThumbnailRights or rights.store is not store or rights.workspace!=workspace:
            raise WorkflowError('NATIVE_PUBLICATION_THUMBNAIL_SCOPE_INVALID',400)
        self.store,self.workspace,self.rights=store,workspace,rights
        self._frozen=(store,workspace,rights,store.root.absolute());self.check()

    def check(self):
        if self._frozen!=(self.store,self.workspace,self.rights,self.store.root.absolute()):
            raise WorkflowError('NATIVE_PUBLICATION_THUMBNAIL_CONFIGURATION_CHANGED')
        self.rights.check()
        if self.rights.store is not self.store or self.rights.workspace!=self.workspace:
            raise WorkflowError('NATIVE_PUBLICATION_THUMBNAIL_SCOPE_INVALID')

    def review(self,job,identity,*,con=None):
        self.check()
        with self.store.transaction() if con is None else nullcontext(con) as owned:
            self.rights.thumbnails.connection(owned)
            selected=self.rights.thumbnails.get(job['project_id'],identity,con=owned);s=selected['snapshot'];b=s['input_binding']
            if (s['request']['render_job_id']!=job['id'] or s['request']['revision']!=job['revision']
                or b['original_snapshot_sha256']!=digest(job['snapshot']) or b['original_document_sha256']!=digest(job['snapshot']['document'])
                or b['record']['observation']['rendered_video_sha256']!=job['result']['qc']['final_sha256']):
                raise WorkflowError('NATIVE_PUBLICATION_THUMBNAIL_FINAL_BINDING_CHANGED')
            exception=self.rights.active(job['project_id'],identity,publishing=True,con=owned)
            if exception is None:raise WorkflowError('NATIVE_PUBLICATION_THUMBNAIL_CURRENT_OWNER_EXCEPTION_REQUIRED')
            original=self.rights.read(owned,self.rights.row(owned,job['project_id'],exception['override_id']))
            authority=self.rights.identity(authority=original['snapshot']['owner_identity'])
            if (digest(authority)!=exception['owner_identity_sha256']
                or not stamp(exception['created_at'])<=utc(self.rights.clock())<stamp(exception['expires_at'])):
                raise WorkflowError('NATIVE_PUBLICATION_THUMBNAIL_CURRENT_OWNER_EXCEPTION_REQUIRED')
            # active() verifies current project, exact decoded PNG/checkpoint/PTS and
            # current Owner. Its separate exception never grants source/final rights.
            return {'schema_version':'native-publication-thumbnail-review-v1','workspace_id':self.workspace,'project_id':job['project_id'],
                'thumbnail_asset_id':identity,'thumbnail_snapshot_sha256':selected['snapshot_sha256'],'render_job_id':job['id'],
                'render_snapshot_sha256':b['original_snapshot_sha256'],'document_sha256':b['original_document_sha256'],
                'final_sha256':b['record']['observation']['rendered_video_sha256'],'image':copy.deepcopy(s['image']),
                'owner_exception':exception,'status':'passed','scope':'dry_run_metadata_review','official_thumbnail_transport_configured':False,
                'original_source_rights_review_still_required':True,'rights_independently_verified':False,'source_asset_rights_granted':False,
                'final_video_approved':False,'provider_authorized':False,'publishing_authorized':False,'owner_uat_accepted':False,'external_calls':0}

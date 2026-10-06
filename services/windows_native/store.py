from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .contracts import Proposal, WorkflowError, digest, file_sha
from .media import MAX_ASSETS, project_assets, scene_bindings, selected_media, validate_bindings
from .hardening import LIFECYCLE, Artifacts, failure, resume_boundary, version_components
from .ingestion import project_input, validate_text


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    """One transaction binds input, approval, idempotency receipt and dispatch intent."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "workflow.sqlite3"
        with self.transaction() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL,
                    approval TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                    request_key TEXT UNIQUE NOT NULL, request_sha TEXT NOT NULL,
                    snapshot TEXT NOT NULL, error TEXT, result TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
                    action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS project_versions (
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL,
                    components TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(project_id,revision));
                CREATE TABLE IF NOT EXISTS job_runtime (
                    job_id TEXT PRIMARY KEY, retry_count INTEGER NOT NULL DEFAULT 0,
                    resume_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS project_dashboard (
                    project_id TEXT PRIMARY KEY, archived INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS render_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    artifact_sha256 TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
                    decision TEXT NOT NULL, reviewer TEXT NOT NULL, note TEXT NOT NULL,
                    created_at TEXT NOT NULL);
            """)
            # Additive history starts with the current preserved document, never invented past versions.
            for row in con.execute("SELECT * FROM projects").fetchall():
                self.version(con, row["id"])

    @contextmanager
    def transaction(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("BEGIN IMMEDIATE")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def event(self, con, project_id, action, payload):
        con.execute("INSERT INTO events(project_id,action,payload,created_at) VALUES(?,?,?,?)",
                    (project_id, action, json.dumps(payload, ensure_ascii=False), now()))

    @staticmethod
    def project(row):
        if row is None:
            raise WorkflowError("PROJECT_NOT_FOUND", 404)
        doc = json.loads(row["document"])
        return {**dict(row), "document": doc, "input": project_input(doc, row["revision"]),
                "approval": json.loads(row["approval"]) if row["approval"] else None}

    def job(self, row, con=None):
        if row is None:
            raise WorkflowError("JOB_NOT_FOUND", 404)
        result = dict(row)
        for key in ("snapshot", "error", "result"):
            result[key] = json.loads(row[key]) if row[key] else None
        result["lifecycle"] = LIFECYCLE[result["status"]]
        runtime = con.execute("SELECT retry_count,resume_count FROM job_runtime WHERE job_id=?", (row["id"],)).fetchone() if con else None
        result.update(dict(runtime) if runtime else {"retry_count": 0, "resume_count": 0})
        last = con.execute("SELECT payload FROM events WHERE action='job_step' AND project_id=? AND json_extract(payload,'$.job_id')=? ORDER BY id DESC LIMIT 1", (result["project_id"], result["id"])).fetchone() if con and result["error"] else None
        step = json.loads(last[0])["step"] if last else result["stage"]
        result["failure"] = failure(result["error"]["code"], result["error"].get("last_stage", step), result["error"].get("http_status")) if result["error"] else None
        review=con.execute("SELECT * FROM render_reviews WHERE job_id=? ORDER BY id DESC LIMIT 1",(row["id"],)).fetchone() if con else None
        result["final_review"]=dict(review) if review else None
        return result

    def version(self, con, identifier):
        project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
        existing = con.execute("SELECT document FROM project_versions WHERE project_id=? AND revision=?", (identifier, project["revision"])).fetchone()
        if existing and digest(json.loads(existing[0])) != digest(project["document"]):
            raise WorkflowError("IMMUTABLE_VERSION_CONFLICT")
        components = version_components(project["document"])
        if project["document"].get("canonical_timeline"):
            components["timeline_version"] = digest(project["document"]["canonical_timeline"])
        if project["document"].get("auto_edit_analyses"):
            components["auto_edit_evidence_version"] = digest({key: project["document"].get(key, [])
                for key in ("auto_edit_analyses", "auto_edit_transcripts")})
        con.execute("INSERT OR IGNORE INTO project_versions VALUES(?,?,?,?,?)",
                    (identifier, project["revision"], json.dumps(project["document"], ensure_ascii=False),
                     json.dumps(components), now()))

    def versions(self, identifier):
        with self.transaction() as con:
            self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
            return [{**dict(r), "document": json.loads(r["document"]), "components": json.loads(r["components"])}
                    for r in con.execute("SELECT * FROM project_versions WHERE project_id=? ORDER BY revision DESC", (identifier,))]

    def log_step(self, job, step, duration, error_code=None, provider=None):
        with self.transaction() as con:
            runtime = con.execute("SELECT retry_count FROM job_runtime WHERE job_id=?", (job["id"],)).fetchone()
            self.event(con, job["project_id"], "job_step", {"job_id": job["id"], "project_id": job["project_id"],
                "step": step, "provider": provider or ("assemblyai" if step in {"asr_upload", "asr_create_transcript", "asr_observe_known_transcript"} else "ffmpeg" if step in {"asr_local_media_analysis", "asr_extract_audio"} else "openai" if "content" in step else "local_vieneu" if "tts" in step else "ffmpeg" if "render" in step else "local_io"),
                "duration": round(duration, 6), "retry_count": runtime[0] if runtime else 0, "error_code": error_code})

    def create(self, name, prompt, input_kind="prompt", *, content_profile=None, production_quality=False):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150:
            raise WorkflowError("PROJECT_NAME_REQUIRED", 400)
        prompt = validate_text(input_kind, prompt)
        identifier = uuid.uuid4().hex
        doc = {"name": name.strip(), "prompt": prompt, "input_kind": input_kind, "proposal": None, "asset": None, "assets": [], "scene_media": [], "documents": []}
        if type(production_quality) is not bool:
            raise WorkflowError('PRODUCTION_QUALITY_SELECTION_INVALID',400)
        if production_quality:
            from .north_star_quality import policy_reference
            doc['production_quality']=policy_reference()
        if content_profile is not None:
            if not isinstance(content_profile,dict) or not all(isinstance(content_profile.get(k),str) and content_profile[k].strip() for k in ('id','name')):
                raise WorkflowError('CONTENT_PROFILE_INVALID',400)
            doc['content_profile']=copy.deepcopy(content_profile)
        stamp = now()
        with self.transaction() as con:
            con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",
                        (identifier, 1, json.dumps(doc, ensure_ascii=False), None, stamp, stamp))
            self.event(con, identifier, "project_created", {"revision": 1})
            self.version(con, identifier)
        return self.get(identifier)

    def get(self, identifier):
        with self.transaction() as con:
            project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
            state=con.execute("SELECT archived FROM project_dashboard WHERE project_id=?",(identifier,)).fetchone()
            project["archived"]=bool(state[0]) if state else False
            project["jobs"] = [self.job(r, con) for r in con.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC", (identifier,))]
            if project['document'].get('content_intelligence'):
                project['script_review'] = self.current_script_review(con, project)
            return project

    @staticmethod
    def current_script_review(con, project):
        row = con.execute("SELECT payload FROM events WHERE project_id=? AND action='human_script_approved' ORDER BY id DESC LIMIT 1", (project['id'],)).fetchone()
        if not row:
            return None
        review = json.loads(row[0])
        proposal = project['document'].get('proposal') or {}
        from .intelligence_lineage import projection
        current_sha = hashlib.sha256(proposal.get('narration', '').encode('utf-8')).hexdigest()
        lineage_sha = digest(projection(project['document'])) if project['document'].get('content_intelligence') else None
        return {**review, 'current': review['script_sha256'] == current_sha and review['lineage_sha256'] == lineage_sha}

    def review_script(self, identifier, revision, reviewer, acknowledged, script_sha256, review_reference=None):
        """Record script-only human approval without approving media or dispatching jobs."""
        import re
        if acknowledged is not True or not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 100:
            raise WorkflowError('HUMAN_SCRIPT_REVIEW_REQUIRED', 400)
        if not isinstance(script_sha256, str) or not re.fullmatch('[a-f0-9]{64}', script_sha256):
            raise WorkflowError('SCRIPT_REVIEW_HASH_REQUIRED', 400)
        if review_reference is not None and (not isinstance(review_reference, dict) or len(json.dumps(review_reference)) > 4000):
            raise WorkflowError('SCRIPT_REVIEW_REFERENCE_INVALID', 400)
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project['document']
            if not doc.get('proposal'):
                raise WorkflowError('SCRIPT_REQUIRED_BEFORE_REVIEW', 400)
            actual_sha = hashlib.sha256(doc['proposal']['narration'].encode('utf-8')).hexdigest()
            if actual_sha != script_sha256:
                raise WorkflowError('SCRIPT_REVIEW_STALE_RELOAD')
            from .intelligence_lineage import projection
            lineage_sha = digest(projection(doc)) if doc.get('content_intelligence') else None
            previous = self.current_script_review(con, project)
            reference = review_reference or {}
            if not previous or not previous['current'] or previous['review_reference'] != reference or previous['reviewer'] != reviewer.strip():
                self.event(con, identifier, 'human_script_approved', {
                    'review_id': uuid.uuid4().hex, 'scope': 'SCRIPT_ONLY', 'script_sha256': actual_sha,
                    'lineage_sha256': lineage_sha, 'reviewed_at_revision': revision,
                    'reviewer': reviewer.strip(), 'approved_at': now(), 'review_reference': reference,
                    'media_approved': False, 'production_approved': False, 'render_dispatched': False})
        return self.get(identifier)

    def list(self, include_archived=False):
        with self.transaction() as con:
            return [{**self.project(row),"archived":bool(row["archived"])} for row in con.execute(
                "SELECT p.*,coalesce(d.archived,0) archived FROM projects p LEFT JOIN project_dashboard d ON p.id=d.project_id WHERE ? OR coalesce(d.archived,0)=0 ORDER BY p.updated_at DESC",(bool(include_archived),))]

    def editable(self, con, identifier, revision):
        project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
        if project["revision"] != revision:
            raise WorkflowError("STALE_VERSION_RELOAD")
        state=con.execute("SELECT archived FROM project_dashboard WHERE project_id=?",(identifier,)).fetchone()
        if state and state[0]:
            raise WorkflowError("PROJECT_ARCHIVED_RESTORE_FIRST")
        if con.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running','retrying')",
                       (identifier,)).fetchone():
            raise WorkflowError("PROJECT_BUSY")
        return project

    def create_from_brief(self, name, lineage):
        from .intelligence_lineage import validate
        validate(lineage)
        identifier=uuid.uuid5(uuid.NAMESPACE_URL,'video-factory/approved-brief/'+lineage['brief']['id']+'/'+lineage['sha256']).hex
        brief=lineage['brief']
        lines=['Tạo kịch bản tiếng Việt để con người kiểm tra từ brief đã duyệt. Dữ kiện là lời nguồn đã nói, chưa xác minh độc lập. Không thêm số liệu hay cam kết ngoài nguồn.',
               'Chủ đề: '+name,'Mục tiêu: '+brief['objective'],'Người xem: '+brief['audience'],'Góc nhìn: '+brief['angle'],'Hook: '+brief['hook'],
               'Các ý chính đề xuất:']+['- '+p for p in brief['talking_points']]+['CTA: '+brief['cta'],'Dữ kiện nguyên văn cần quy nguồn:']+['- '+p for p in brief['key_facts']]+['Nguồn:']
        lines += [s['title']+' — '+s['reference']+' — ngày công bố: '+(s['timestamp'] or 'chưa rõ') for s in lineage['sources'] if s['id'] in brief['source_references']]
        lines += ['Giới hạn:']+['- '+p for p in brief['constraints']]
        prompt=validate_text('idea','\n'.join(lines))
        doc={'name':name[:150],'prompt':prompt,'input_kind':'idea','proposal':None,'asset':None,'assets':[],'scene_media':[],'documents':[],'content_intelligence':lineage}
        stamp=now()
        with self.transaction() as con:
            existing=con.execute('SELECT * FROM projects WHERE id=?',(identifier,)).fetchone()
            if existing:
                previous=json.loads(existing['document']).get('content_intelligence')
                if previous!=lineage: raise WorkflowError('CONTENT_INTELLIGENCE_BRIDGE_CONFLICT')
            else:
                con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(identifier,1,json.dumps(doc,ensure_ascii=False),None,stamp,stamp))
                self.event(con,identifier,'approved_brief_imported_for_script_review',{'brief_id':lineage['brief']['id'],'idea_id':lineage['idea']['id'],'lineage_sha256':lineage['sha256'],'automatic_production':False})
                self.version(con,identifier)
        return self.get(identifier)

    def duplicate(self, identifier, revision):
        with self.transaction() as con:
            project=self.editable(con,identifier,revision); doc=project["document"]
            stamp=now(); copy_id=uuid.uuid4().hex
            doc["duplication"]={"project_id":identifier,"revision":revision,"document_sha256":digest(doc),"created_at":stamp}
            doc["name"]=doc["name"][:139]+" — bản sao"
            # Evidence remains immutable in its source project; new project IDs
            # need their own analysis binding. Saved raw ASR/media can be reused.
            doc.pop("auto_edit_analyses", None)
            doc.pop("auto_edit_transcripts", None)
            con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",(copy_id,1,json.dumps(doc,ensure_ascii=False),None,stamp,stamp))
            self.version(con,copy_id)
            self.event(con,copy_id,"project_duplicated_unapproved",{"source_project":identifier,"source_revision":revision})
        return self.get(copy_id)

    def archive(self, identifier, revision, archived):
        if type(archived) is not bool:
            raise WorkflowError("ARCHIVE_BOOLEAN_REQUIRED",400)
        with self.transaction() as con:
            project=self.project(con.execute("SELECT * FROM projects WHERE id=?",(identifier,)).fetchone())
            if project["revision"]!=revision: raise WorkflowError("STALE_VERSION_RELOAD")
            if con.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running','retrying')",(identifier,)).fetchone():
                raise WorkflowError("PROJECT_BUSY")
            con.execute("INSERT INTO project_dashboard VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET archived=excluded.archived,updated_at=excluded.updated_at",(identifier,int(archived),now()))
            self.event(con,identifier,"project_archived" if archived else "project_restored",{"revision":revision,"recoverable":True})
        return self.get(identifier)

    def reject_content(self, identifier, revision, reviewer, note):
        if not isinstance(reviewer,str) or not 1<=len(reviewer.strip())<=100 or not isinstance(note,str) or not 1<=len(note.strip())<=2000:
            raise WorkflowError("REJECTION_NAME_REASON_REQUIRED",400)
        with self.transaction() as con:
            self.editable(con,identifier,revision)
            con.execute("UPDATE projects SET revision=?,approval=NULL,updated_at=? WHERE id=?",(revision+1,now(),identifier))
            self.version(con,identifier)
            self.event(con,identifier,"human_content_rejected",{"revision":revision,"reviewer":reviewer.strip(),"note":note.strip()})
        return self.get(identifier)

    def verified_render(self, identifier, con):
        job=self.job(con.execute("SELECT * FROM jobs WHERE id=?",(identifier,)).fetchone(),con)
        project=self.editable(con,job["project_id"],job["revision"])
        if job["kind"]!="render" or job["status"]!="succeeded" or not project["approval"] or digest(job["snapshot"]["document"])!=digest(project["document"]) or digest(job["snapshot"]["approval"])!=digest(project["approval"]):
            raise WorkflowError("VIDEO_STALE_OR_NOT_READY")
        checkpoint=Artifacts(self.root/"jobs"/identifier,job).load("render")
        if not checkpoint or checkpoint["result"]!=job["result"] or not job["result"]["qc"]["passed"]:
            raise WorkflowError("RENDER_CHECKPOINT_OR_QC_REQUIRED")
        actual=file_sha(self.root/"jobs"/identifier/"final.mp4")
        if actual!=job["result"]["qc"]["final_sha256"]:
            raise WorkflowError("RENDER_ARTIFACT_CHANGED")
        return job, actual

    def review_render(self, identifier, revision, reviewer, acknowledged, decision, note=""):
        if (decision=="approve" and acknowledged is not True) or not isinstance(reviewer,str) or not 1<=len(reviewer.strip())<=100:
            raise WorkflowError("HUMAN_FINAL_WATCH_LISTEN_REVIEW_REQUIRED",400)
        if not isinstance(decision,str) or decision not in {"approve","reject"} or not isinstance(note,str) or len(note)>2000 or (decision=="reject" and not note.strip()):
            raise WorkflowError("FINAL_REVIEW_DECISION_REASON_INVALID",400)
        with self.transaction() as con:
            job, actual=self.verified_render(identifier,con)
            if revision!=job["revision"]: raise WorkflowError("STALE_VERSION_RELOAD")
            values={"job_id":identifier,"project_id":job["project_id"],"revision":revision,"artifact_sha256":actual,
                    "snapshot_sha256":digest(job["snapshot"]),"decision":decision,"reviewer":reviewer.strip(),"note":note.strip()}
            previous=job["final_review"]
            if not previous or any(previous[k]!=v for k,v in values.items()):
                con.execute("INSERT INTO render_reviews(job_id,project_id,revision,artifact_sha256,snapshot_sha256,decision,reviewer,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",tuple(values.values())+(now(),))
                self.event(con,job["project_id"],"human_final_video_"+decision,values)
            if decision=="reject":
                con.execute("UPDATE projects SET revision=?,approval=NULL,updated_at=? WHERE id=?",(revision+1,now(),job["project_id"]))
                self.version(con,job["project_id"])
        return self.get(job["project_id"])

    def final_video(self, identifier):
        with self.transaction() as con:
            job, actual=self.verified_render(identifier,con)
            review=job["final_review"]
            if not review or review["decision"]!="approve" or review["artifact_sha256"]!=actual or review["snapshot_sha256"]!=digest(job["snapshot"]):
                raise WorkflowError("HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED")
        return job

    def save(self, identifier, revision, *, prompt=None, proposal=None, asset=None, scene_media=None, input_kind=None, scene_options=None, music_enabled=None):
        if prompt is not None and input_kind != "media" and (not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 20000):
            raise WorkflowError("PROMPT_REQUIRED_MAX_20000", 400)
        if proposal is not None:
            try:
                proposal = Proposal.model_validate(proposal).model_dump()
            except ValueError:
                raise WorkflowError("INVALID_PROPOSAL_SCENE_COVERAGE", 400) from None
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            before_shots = copy.deepcopy(doc)
            if proposal is not None and not doc.get("canonical_timeline") and any(not s["narration_excerpt"].strip() for s in proposal["visual_brief"]):
                raise WorkflowError("SILENT_SHOTS_REQUIRE_CANONICAL_TIMELINE", 400)
            if input_kind is not None:
                validate_text(input_kind, prompt if prompt is not None else doc["prompt"])
                if input_kind != doc.get("input_kind", "prompt"):
                    doc["proposal"], doc["scene_media"] = None, []
                doc["input_kind"] = input_kind
            if prompt is not None and prompt != doc["prompt"]:
                doc["prompt"], doc["proposal"] = prompt, None
                doc["scene_media"] = []
            if proposal is not None:
                doc["proposal"] = proposal
            if asset is not None:
                doc["asset"] = asset
                doc["assets"] = [asset]
                doc.pop("scene_media", None)  # Legacy single-image write remains compatible.
            if scene_media is not None:
                doc["scene_media"] = scene_media
            validate_bindings(doc)
            if music_enabled is not None:
                if type(music_enabled) is not bool:
                    raise WorkflowError("MUSIC_ENABLED_MUST_BE_BOOLEAN",400)
                doc["music_enabled"]=music_enabled
            if scene_options is not None:
                from .editor import build_plan
                doc["edit_plan"]=build_plan(doc,scene_options)
            elif any(v is not None for v in (prompt,proposal,asset,scene_media,input_kind,music_enabled)):
                doc.pop("edit_plan",None)
            doc = self.sync_shot_document(doc, before_shots, identifier)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "draft_saved_approval_invalidated", {"revision": revision + 1})
            self.version(con, identifier)
        return self.get(identifier)

    def auto_plan(self, identifier, revision):
        from .editor import build_plan
        with self.transaction() as con:
            project=self.editable(con,identifier,revision); doc=project["document"]
            before_shots = copy.deepcopy(doc)
            plan=build_plan(doc,auto_select=True)
            doc["edit_plan"]=plan
            doc["scene_media"]=[{"scene":s["scene"],"asset_id":s["selected_asset"]} for s in plan["scenes"]]
            validate_bindings(doc)
            doc = self.sync_shot_document(doc, before_shots, identifier)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision+1,json.dumps(doc,ensure_ascii=False),now(),identifier))
            self.version(con,identifier)
            self.event(con,identifier,"editor_plan_saved_review_required",{"revision":revision+1,"plan_sha256":digest(plan)})
        return self.get(identifier)

    def shot_view(self, identifier):
        from .shot_adapter import view
        return view(self, self.get(identifier))

    def mutate_shots(self, identifier, revision, operation):
        from .shot_adapter import mutate
        return mutate(self, identifier, revision, operation)

    @staticmethod
    def sync_shot_document(doc, previous_doc, identifier):
        if previous_doc.get("canonical_timeline"):
            from .shot_adapter import sync_legacy
            return sync_legacy(doc, previous_doc, identifier)
        return doc

    def set_music(self, identifier, revision, music):
        with self.transaction() as con:
            project=self.editable(con,identifier,revision); doc=project["document"]
            before_shots = copy.deepcopy(doc)
            previous=doc.get("edit_plan"); doc["music"]=music; doc["music_enabled"]=True
            if previous:
                from .editor import build_plan, SceneOptions
                doc["edit_plan"]=build_plan(doc,[{k:s[k] for k in SceneOptions.model_fields} for s in previous["scenes"]])
            else: doc.pop("edit_plan",None)
            doc = self.sync_shot_document(doc, before_shots, identifier)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision+1,json.dumps(doc,ensure_ascii=False),now(),identifier))
            self.version(con,identifier)
            self.event(con,identifier,"music_saved_review_required",{"revision":revision+1,"music_id":music["id"],"source_sha256":music["source_sha256"]})
        return self.get(identifier)

    def set_brand(self, identifier, revision, brand_id, template_id, *, duration_mode=None):
        from .branding import choose
        from .editor import build_plan, SceneOptions
        selection=choose(brand_id,template_id,duration_mode=duration_mode) if duration_mode is not None else choose(brand_id,template_id)
        with self.transaction() as con:
            project=self.editable(con,identifier,revision); doc=project["document"]
            before_shots = copy.deepcopy(doc)
            previous=doc.get("edit_plan"); doc["brand_template"]=selection
            try:
                validate_bindings(doc,complete=True)
                complete=bool(doc.get("proposal"))
            except WorkflowError:
                complete=False
            if complete:
                options=[{k:s[k] for k in SceneOptions.model_fields} for s in previous["scenes"]] if previous else None
                doc["edit_plan"]=build_plan(doc,options)
            else: doc.pop("edit_plan",None)
            doc = self.sync_shot_document(doc, before_shots, identifier)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",(revision+1,json.dumps(doc,ensure_ascii=False),now(),identifier))
            self.version(con,identifier)
            self.event(con,identifier,"brand_template_saved_review_required",{"revision":revision+1,"brand_id":brand_id,"template_id":template_id,"selection_sha256":digest(selection)})
        return self.get(identifier)

    def append_document(self, identifier, revision, document):
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            before_shots = copy.deepcopy(doc)
            documents = doc.get("documents", [])
            if len(documents) >= 20:
                raise WorkflowError("DOCUMENT_LIMIT_20", 400)
            doc["documents"] = documents + [document]
            doc = self.sync_shot_document(doc, before_shots, identifier)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.version(con, identifier)
            self.event(con, identifier, "document_uploaded_approval_invalidated", {"revision": revision+1, "document_id": document["id"], "sha256": document["sha256"]})
        return self.get(identifier)

    def set_voice_quality(self, identifier, revision, policy_id):
        """Explicit local revision; setting a policy never approves or dispatches TTS."""
        from .voice_quality import policy_reference
        reference = policy_reference(policy_id)
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            if doc.get('voice_quality') != reference:
                before_shots = copy.deepcopy(doc)
                doc['voice_quality'] = reference
                doc = self.sync_shot_document(doc, before_shots, identifier)
                con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                            (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
                self.version(con, identifier)
                self.event(con, identifier, 'voice_quality_selected_approval_invalidated',
                           {'revision': revision + 1, 'policy': reference, 'automatic_production': False})
        return self.get(identifier)

    def approve(self, identifier, revision, reviewer, acknowledged, *, review_reference=None):
        if acknowledged is not True or not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 100:
            raise WorkflowError("HUMAN_REVIEW_REQUIRED", 400)
        if review_reference is not None and (not isinstance(review_reference, dict)
                or review_reference.get('source') not in {'local_ui_human_review','human_user_reply_in_codex'}
                or len(json.dumps(review_reference)) > 4000):
            raise WorkflowError('HUMAN_REVIEW_REFERENCE_INVALID',400)
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            from .voice_quality import resolve_policy
            resolve_policy(doc)
            if not doc["proposal"]:
                raise WorkflowError("CONTENT_AND_IMAGE_REQUIRED")
            from .north_star_quality import validate_tts_names
            validate_tts_names(doc,Proposal.model_validate(doc['proposal']))
            from .editor import validate_plan
            validate_plan(doc)
            if doc.get("canonical_timeline"):
                from .shot_adapter import validate_document
                validate_document(doc)
            selected_media(doc)
            previous=project["approval"]
            if (not previous or previous["revision"]!=revision or previous["snapshot_sha256"]!=digest(doc)
                    or previous.get('review_reference')!=review_reference):
                approval = {"revision": revision, "snapshot_sha256": digest(doc),
                            "reviewer": reviewer.strip(), "approved_at": now(), "source": "local_ui_human_review"}
                if review_reference is not None:
                    approval.update(source=review_reference['source'],review_reference=review_reference)
                con.execute("UPDATE projects SET approval=?,updated_at=? WHERE id=?",
                            (json.dumps(approval, ensure_ascii=False), now(), identifier))
                self.event(con, identifier, "human_content_approved", approval)
        return self.get(identifier)

    def enqueue(self, identifier, revision, kind, request_key):
        if kind not in {"content", "render", "asr", "auto_edit_analysis"} or not isinstance(request_key, str) or not 8 <= len(request_key) <= 100:
            raise WorkflowError("INVALID_JOB_REQUEST", 400)
        identity = digest({"project_id": identifier, "revision": revision, "kind": kind})
        with self.transaction() as con:
            existing = con.execute("SELECT * FROM jobs WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["request_sha"] != identity:
                    raise WorkflowError("IDEMPOTENCY_KEY_CONFLICT")
                return self.job(existing, con)
            project = self.editable(con, identifier, revision)
            doc, approval = project["document"], project["approval"]
            if doc.get("canonical_timeline"):
                from .shot_adapter import validate_document
                validate_document(doc)
            if doc.get("content_intelligence"):
                from .intelligence_lineage import projection
                projection(doc)
            if kind == "asr":
                from .asr import pending_assets
                if not pending_assets(doc):
                    raise WorkflowError("ASR_NO_UNANALYZED_MEDIA", 400)
                if con.execute("SELECT 1 FROM jobs WHERE project_id=? AND revision=? AND kind='asr'",
                               (identifier, revision)).fetchone():
                    raise WorkflowError("ASR_EXISTING_JOB_RESUME_REQUIRED")
            if kind == "auto_edit_analysis":
                from .auto_edit_analysis import pending
                if not pending(doc, identifier):
                    raise WorkflowError("AUTO_EDIT_NO_PENDING_VIDEO", 400)
            if kind == "render" and (not approval or approval["revision"] != revision
                                     or approval["snapshot_sha256"] != digest(doc)):
                raise WorkflowError("HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
            if kind == "render":
                selected_media(doc)
            identifier_job, stamp = uuid.uuid4().hex, now()
            snapshot = {"document": doc, "approval": approval}
            con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (identifier_job, identifier, revision, kind, "queued", "queued", request_key, identity,
                         json.dumps(snapshot, ensure_ascii=False), None, None, stamp, stamp))
            self.event(con, identifier, "job_queued", {"job_id": identifier_job, "kind": kind, "revision": revision})
            con.execute("INSERT INTO job_runtime(job_id) VALUES(?)", (identifier_job,))
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier_job,)).fetchone(), con)

    def claim(self):
        with self.transaction() as con:
            row = con.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            con.execute("UPDATE jobs SET status='running',stage='starting',updated_at=? WHERE id=?", (now(), row["id"]))
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone(), con)

    def stage(self, identifier, stage):
        with self.transaction() as con:
            retry = stage.startswith("retrying:")
            step = stage.split(":", 1)[1] if retry else stage
            con.execute("UPDATE jobs SET status=?,stage=?,updated_at=? WHERE id=? AND status IN ('running','retrying')",
                        ("retrying" if retry else "running", step, now(), identifier))
            if retry:
                con.execute("INSERT OR IGNORE INTO job_runtime(job_id) VALUES(?)", (identifier,))
                con.execute("UPDATE job_runtime SET retry_count=retry_count+1 WHERE job_id=?", (identifier,))

    def finish(self, job, result=None, error=None):
        with self.transaction() as con:
            row = con.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if row is None or row["status"] not in {"running", "retrying"}:
                raise WorkflowError("JOB_STATE_CONFLICT")
            status = "failed" if error else ("awaiting_review" if job["kind"] == "content" else "succeeded")
            if result and job["kind"] == "content":
                project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone())
                if project["revision"] != job["revision"]:
                    raise WorkflowError("STALE_CONTENT_RESULT")
                doc = project["document"]
                before_shots = copy.deepcopy(doc)
                doc["proposal"] = Proposal.model_validate(result["proposal"]).model_dump()
                if not before_shots.get("canonical_timeline") and any(not s["narration_excerpt"].strip() for s in doc["proposal"]["visual_brief"]):
                    raise WorkflowError("SILENT_SHOTS_REQUIRE_CANONICAL_TIMELINE", 400)
                doc["scene_media"] = []  # New proposal requires deliberate source choices.
                doc.pop("edit_plan",None)
                doc = self.sync_shot_document(doc, before_shots, project["id"])
                con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                            (project["revision"] + 1, json.dumps(doc, ensure_ascii=False), now(), project["id"]))
                self.version(con, project["id"])
            if result and job["kind"] == "asr":
                from .asr import analysis_for_asset
                project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone())
                if project["revision"] != job["revision"] or digest(project["document"]) != digest(job["snapshot"]["document"]):
                    raise WorkflowError("ASR_STALE_RESULT")
                doc = project["document"]
                before_shots = copy.deepcopy(doc)
                incoming = result["media_analysis"]
                assets = {a["id"]: a for a in project_assets(doc)}
                if len({r["asset_id"] for r in incoming}) != len(incoming):
                    raise WorkflowError("ASR_DUPLICATE_RESULT")
                for record in incoming:
                    if record["asset_id"] not in assets or not analysis_for_asset({"media_analysis": [record]}, assets[record["asset_id"]]):
                        raise WorkflowError("ASR_RESULT_SOURCE_BINDING_MISMATCH")
                replaced = {r["asset_id"] for r in incoming}
                doc["media_analysis"] = [r for r in doc.get("media_analysis", []) if r["asset_id"] not in replaced] + incoming
                doc.pop("edit_plan",None)
                doc = self.sync_shot_document(doc, before_shots, project["id"])
                con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                            (project["revision"]+1, json.dumps(doc, ensure_ascii=False), now(), project["id"]))
                self.version(con, project["id"])
                self.event(con, project["id"], "media_analyzed_approval_invalidated", {"job_id": job["id"], "assets": sorted(replaced)})
            if result and job["kind"] == "auto_edit_analysis":
                from .auto_edit_analysis import save_result
                project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone())
                if project["revision"] != job["revision"] or digest(project["document"]) != digest(job["snapshot"]["document"]):
                    raise WorkflowError("AUTO_EDIT_STALE_RESULT")
                save_result(self, con, project, result)
            con.execute("UPDATE jobs SET status=?,stage=?,error=?,result=?,updated_at=? WHERE id=?",
                        (status, status, json.dumps(error) if error else None,
                         json.dumps(result, ensure_ascii=False) if result else None, now(), job["id"]))
            self.event(con, job["project_id"], "job_finished", {"job_id": job["id"], "status": status, "error": error})

    def recover(self):
        # Unstarted jobs are safe to drain. Dispatched/ambiguous work is NEVER replayed.
        with self.transaction() as con:
            for row in con.execute("SELECT * FROM jobs WHERE status IN ('running','retrying')").fetchall():
                error = {"code": "INTERRUPTED_NO_AUTOMATIC_REPLAY", "last_stage": row["stage"]}
                con.execute("UPDATE jobs SET status='interrupted',stage='interrupted',error=?,updated_at=? WHERE id=?",
                            (json.dumps(error), now(), row["id"]))
                self.event(con, row["project_id"], "job_interrupted", {"job_id": row["id"], **error})

    def get_job(self, identifier):
        with self.transaction() as con:
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone(), con)

    def resume(self, identifier):
        with self.transaction() as con:
            job = self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone(), con)
            if job["status"] in {"queued", "running", "retrying"} and job["resume_count"]:
                return job  # Double-click/repeated resume keeps one job/output receipt.
            if job["status"] not in {"failed", "interrupted"}:
                raise WorkflowError("JOB_NOT_RESUMABLE")
            project = self.editable(con, job["project_id"], job["revision"])
            if digest({"document": project["document"], "approval": project["approval"]}) != digest(job["snapshot"]):
                raise WorkflowError("STALE_RESUME_SNAPSHOT")
            if job["resume_count"] >= 3:
                raise WorkflowError("RESUME_LIMIT_REACHED")
            resume_boundary(self.root, job)
            con.execute("INSERT OR IGNORE INTO job_runtime(job_id) VALUES(?)", (identifier,))
            con.execute("UPDATE job_runtime SET resume_count=resume_count+1 WHERE job_id=?", (identifier,))
            con.execute("UPDATE jobs SET status='queued',stage='resume_queued',error=NULL,result=NULL,updated_at=? WHERE id=?", (now(), identifier))
            self.event(con, job["project_id"], "job_resume_requested", {"job_id": identifier, "previous_error": job["error"]})
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone(), con)

    def append_media(self, identifier, revision, asset):
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            before_shots = copy.deepcopy(doc)
            library = project_assets(doc)
            if len(library) >= MAX_ASSETS:
                raise WorkflowError("PROJECT_MEDIA_LIMIT_50", 400)
            doc["scene_media"] = scene_bindings(doc)
            doc["assets"] = library + [asset]
            doc.pop("edit_plan",None)
            validate_bindings(doc)
            doc = self.sync_shot_document(doc, before_shots, identifier)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "media_uploaded_approval_invalidated", {"revision": revision + 1, "asset_id": asset["id"], "kind": asset["kind"]})
            self.version(con, identifier)
        return self.get(identifier)

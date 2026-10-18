"""Local casting/library edits. Existing session, CSRF and role checks precede body parsing."""
import re
from .contracts import WorkflowError
from .dialogue_binding import NativeDialogueCompiler,specification
from .dialogue_plan import build
from .dialogue_runtime import providers_for

VOICE=r'nvoice_[a-f0-9]{32}'
PROJECT=r'[a-f0-9]{32}'
GLOBAL=r'/api/(?:voice-library(?:/presets|/import-installed|/'+VOICE+r')?|voice-auditions(?:/nsample_[a-f0-9]{32}/audio)?|drama-series)'
LOCAL=r'/api/projects/('+PROJECT+r')/drama-casting(?:/(compile|takes|series-save|series-apply))?'
def handles(path):return re.fullmatch(GLOBAL,path.partition('?')[0]) is not None or re.fullmatch(LOCAL,path.partition('?')[0]) is not None

def dispatch(handler,*,write=False):
    path=handler.path
    if '?' in path:raise WorkflowError('DRAMA_QUERY_INVALID',400)
    server=handler.server;library=server.voice_library
    if not write:
        if path=='/api/voice-auditions':return handler.reply(server.voice_auditions.page())
        sample=re.fullmatch('/api/voice-auditions/(nsample_[a-f0-9]{32})/audio',path)
        if sample:return handler.file(server.voice_auditions.audio(sample[1]),video=True)
        if path=='/api/voice-library/presets':
            from .dialogue_vieneu import catalog
            return handler.reply(catalog(server.config))
        if path=='/api/voice-library':return handler.reply(library.page())
        match=re.fullmatch('/api/voice-library/('+VOICE+')',path)
        if match:return handler.reply(library.get(match[1]))
        if path=='/api/drama-series':return handler.reply(server.drama_series.page())
        match=re.fullmatch(LOCAL,path)
        if not match or match[2]:raise WorkflowError('ROUTE_NOT_FOUND',404)
        project=server.store.get(match[1]);casting=server.drama_casting.view(match[1]);diagnostic=None;error=None;compiled=False
        from .auto_edit_timeline import is_auto_edit
        if is_auto_edit(project['document']):raise WorkflowError('DRAMA_NARRATED_PROJECT_REQUIRED',400)
        from .shot_adapter import shots
        values=shots(project['document'])
        if casting['casting']:
            try:
                providers=providers_for(server.config)
                diagnostic=build(casting['casting']['configuration'],library,provider_signatures={k:v.configuration_sha256 for k,v in providers.items()})
                from .dialogue_binding import validate
                validate(project['document'],library,project_id=project['id'],providers=providers);compiled=True
            except WorkflowError as reason:error=reason.code
        return handler.reply({'schema_version':'native-drama-studio.v1','workspace_id':library.workspace,'project_id':project['id'],'revision':project['revision'],
            'casting':casting['casting'],'compiled_current':compiled,'needs_attention':diagnostic['needs_attention'] if diagnostic else [],'error_code':error,
            'shots':[{'shot_id':v['shot_id'],'scene':i+1,'narration':v['narration'],'narration_enabled':v['narration_enabled']} for i,v in enumerate(values)],
            'provider_calls':0,'human_voice_uat_complete':False})
    body=handler.read_body(max_bytes=1500000)
    def authorized():
        if server.access is not None:server.access.authorize(handler.auth_session,'POST',path)
    actor=handler.auth_session.principal.token_id if getattr(handler,'auth_session',None) else 'loopback-owner'
    if path=='/api/voice-library/import-installed':
        if body!={'acknowledged':True}:raise WorkflowError('VOICE_IMPORT_ACKNOWLEDGEMENT_REQUIRED',400)
        from .voice_presets import register_installed
        return handler.reply(register_installed(library,server.config,actor_ref=actor,authorization_check=authorized))
    if path=='/api/voice-auditions':return handler.reply(server.voice_auditions.submit(body,authorization_check=authorized),status=202)
    if path=='/api/voice-library':return handler.reply(library.create(body,actor_ref=actor,authorization_check=authorized))
    match=re.fullmatch('/api/voice-library/('+VOICE+')',path)
    if match:return handler.reply(library.update(match[1],body,actor_ref=actor,authorization_check=authorized))
    match=re.fullmatch(LOCAL,path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,action=match.groups()
    if action=='compile':return handler.reply(NativeDialogueCompiler(server.store,library,providers_for(server.config)).compile(project,body,actor_ref=actor,authorization_check=authorized))
    if action=='takes':return handler.reply(server.dialogue_takes.create(project,body,actor_ref=actor,authorization_check=authorized))
    if action in {'series-save','series-apply'}:return handler.reply(server.drama_series.write(project,body,apply=action=='series-apply',actor_ref=actor,authorization_check=authorized))
    return handler.reply(server.drama_casting.save(project,body,actor_ref=actor,authorization_check=authorized))

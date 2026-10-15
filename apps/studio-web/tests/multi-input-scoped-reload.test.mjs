import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {timelineTranscriptId} from '../timeline-history.mjs';
import {initializeMultiInput} from '../multi-input.mjs';
const clone = structuredClone;

// Explicit fake DOM/timers/GET transport. No browser, server, media, model or provider execution.
function fixture(name = 'new', {job = 'queued', withContent = true} = {}) {
  const scene = {scene_id: 'scene_' + name, narration: name + ' narration', visual_brief: name + ' visual', duration_seconds: 4,
    duration_mode: 'auto', pause_after_seconds: .18, fit: 'contain', transition: 'cut', architectural_render: false,
    media_strategy: 'user_asset', asset_id: 'ast_new_scene_asset', analysis_id: null, source_start: 0, original_audio: 'mute'};
  const doc = {input_kind: 'script', original_text: name + ' original', script: name + ' script', supplied_facts: [name + ' fact'],
    protected_terms: [name + ' term'], scenes: [scene], approved: true, facts_needing_source: [], generator: 'deterministic-user-draft'};
  return {content: withContent ? {project_version_id: 'pv_' + name, snapshot: {content: doc}, provenance: {script_diff: [name + ' diff']}} : null,
    plan: {items: [{scene_id: scene.scene_id, strategy: 'user_asset', status: name + '-ready'}]},
    provider: {provider_key: 'contract', status: 'FIXTURE_ONLY'}, generation: {job: job ? {job_id: 'job_' + name, status: job} : null, provider_status: 'FIXTURE_ONLY', proposal: null}};
}

function fakeDom(trace) {
  const nodes = new Map(); let rows = [];
  const decode = value => String(value ?? '').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  class Element {
    constructor(id) {this.id = id; this.handlers = new Map(); this.dataset = {}; this.fields = {}; this.raw = {value: '', textContent: '', innerHTML: '', disabled: false}; this.checked = false;}
    get value() {return this.raw.value;} set value(v) {trace.push(['value', this.id, v]); this.raw.value = v;}
    get textContent() {return this.raw.textContent;} set textContent(v) {trace.push(['text', this.id, v]); this.raw.textContent = v;}
    get disabled() {return this.raw.disabled;} set disabled(v) {trace.push(['disabled', this.id, v]); this.raw.disabled = v;}
    get innerHTML() {return this.raw.innerHTML;} set innerHTML(v) {
      trace.push(['html', this.id, v]); this.raw.innerHTML = v;
      if (this.id === 'mvp-scenes') rows = [...String(v).matchAll(/<article class="mvp-scene"[^>]*>([\s\S]*?)<\/article>/g)].map((match, index) => {
        const row = new Element('row-' + index), html = match[1];
        for (const name of ['narration','visual','media','duration','duration-mode','pause','fit','transition','render','audio']) {
          const field = row.fields[name] = new Element('row-' + index + '-' + name);
          const tag = html.match(new RegExp('<(?:input|textarea|select)[^>]*data-field="' + name + '"[^>]*>'))?.[0] ?? '';
          field.raw.value = decode(name === 'narration' ? html.match(/<textarea[^>]*>([\s\S]*?)<\/textarea>/)?.[1] : tag.match(/value="([^"]*)"/)?.[1]);
          field.checked = /\schecked(?:\s|>)/.test(tag);
        }
        return row;
      });
    }
    addEventListener(name, fn) {this.handlers.set(name, fn);}
    querySelectorAll() {return [...nodes.values(), ...rows.flatMap(row => Object.values(row.fields))];}
    querySelector(selector) {return this.fields[selector.match(/data-field=["']?([^\]"']+)/)?.[1]];}
    closest() {return null;}
  }
  const get = id => {if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id);};
  return {getElementById: get, querySelectorAll: selector => selector === '.mvp-scene' ? rows : [], nodes, get,
    snapshot: () => ({nodes: [...nodes].map(([id, node]) => [id, {...node.raw}, {...node.dataset}]),
      rows: rows.map(row => Object.fromEntries(Object.entries(row.fields).map(([name, field]) => [name, {...field.raw, checked: field.checked}])))}),
    contentSnapshot: () => Object.fromEntries(['mvp-kind','mvp-original','mvp-script','mvp-facts','mvp-protected','mvp-scenes',
      'mvp-status','mvp-plan','mvp-script-diff','mvp-provider-status','mvp-generation-status','mvp-proposal'].map(id => [id, {...get(id).raw, disabled: undefined}]))};
}
function harness({state = {workspaceId: 'wsp_fixture', projectId: 'prj_fixture', assets: [], analyses: [], timeline: null}, initial = fixture('old'), apiHandler} = {}) {
  const trace = [], dom = fakeDom(trace), calls = [], timerActions = [], timers = new Map(), toasts = [], effects = [];
  let currentFixture = initial, nextTimer = 0, token = 'original-token', handler = apiHandler;
  const response = path => path.endsWith('/content') ? currentFixture.content : path.endsWith('/storyboard-media-plan') ? currentFixture.plan
    : path.endsWith('/content-provider') ? currentFixture.provider : path.endsWith('/content-generation') ? currentFixture.generation : null;
  const api = async (path, options = {}) => {
    const call = {path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null}; calls.push(call);
    return handler ? handler(call, () => clone(response(path))) : clone(response(path));
  };
  const editor = initializeMultiInput({api, getState: () => state, dom,
    refresh: async () => effects.push('refresh'), refreshProjects: async () => effects.push('refresh-projects'),
    toast: (...args) => toasts.push(args), uploadFetch: async () => {throw Error('no uploads');},
    setTimer: (fn, ms) => {const id = ++nextTimer; timers.set(id, {fn, ms}); timerActions.push(['set', id, ms]); return id;},
    clearTimer: id => {timers.delete(id); timerActions.push(['clear', id]);}});
  editor.setBusy(false);
  const boundary = () => JSON.stringify([state.workspaceId, state.projectId, state.principal, token, state.drafts]);
  const captureGuard = () => {const captured = boundary(); return () => captured === boundary();};
  const command = id => dom.get(id).handlers.get('click')?.({preventDefault() {}});
  return {state, editor, dom, trace, calls, timerActions, timers, toasts, effects, api, captureGuard, command,
    setFixture: value => {currentFixture = value;}, setHandler: value => {handler = value;}, setToken: value => {token = value;}, getToken: () => token,
    async tick(id = [...timers.keys()].at(-1)) {const timer = timers.get(id); assert.ok(timer); timers.delete(id); await timer.fn();}};
}
async function seeded() {const h = harness(); await h.editor.reload(); h.trace.length = 0; h.calls.length = 0; h.timerActions.length = 0; return h;}

test('prepare is staging only until its synchronous apply closure is called', async () => {
  const h = await seeded(), before = h.dom.snapshot(), timers = [...h.timers], busy = h.editor.isBusy(); h.setFixture(fixture('new'));
  const apply = await h.editor.prepareReload({isCurrent: h.captureGuard()});
  assert.equal(typeof apply, 'function'); assert.deepEqual(h.dom.snapshot(), before); assert.deepEqual([...h.timers], timers);
  assert.deepEqual(h.trace, []); assert.deepEqual(h.timerActions, []); assert.equal(h.editor.isBusy(), busy);
  assert.deepEqual(h.calls.map(c => c.path.split('/').at(-1)), ['content','storyboard-media-plan','content-provider','content-generation']);
  assert.ok(h.calls.every(c => c.method === 'GET'));
  h.state.assets = [{asset_id: 'ast_new_scene_asset', filename: 'NEW_ASSET_OPTION', content_type: 'image/png'}];
  const returned = apply(); assert.equal(returned?.then, undefined);
  assert.equal(h.dom.get('mvp-script').value, 'new script'); assert.match(h.dom.get('mvp-scenes').innerHTML, /NEW_ASSET_OPTION/);
  assert.match(h.dom.get('mvp-plan').textContent, /new-ready/); assert.match(h.dom.get('mvp-generation-status').textContent, /job_new/);
  assert.match(h.dom.get('mvp-provider-status').textContent, /Fixture offline/); assert.deepEqual([...h.timers.values()].map(t => t.ms), [700]);
  const installed = h.dom.snapshot(), timerCount = h.timerActions.length; assert.throws(apply, /ALREADY_APPLIED/);
  assert.deepEqual(h.dom.snapshot(), installed); assert.equal(h.timerActions.length, timerCount);
});

for (const suffix of ['content','storyboard-media-plan','content-provider','content-generation']) for (const drift of ['authority','project','workspace'])
  test(`late ${drift} at ${suffix} discards staging with no DOM/state/timer adoption`, async () => {
    const h = await seeded(), before = h.dom.snapshot(), timers = [...h.timers]; h.setFixture(fixture('new'));
    let release, entered; const reached = new Promise(r => {entered = r;});
    h.setHandler(async (c, response) => {const value = response(); if (c.path.endsWith('/' + suffix)) {entered(); await new Promise(r => {release = r;});} return value;});
    const work = h.editor.prepareReload({isCurrent: h.captureGuard()}); await reached;
    assert.deepEqual(h.dom.snapshot(), before); assert.deepEqual(h.timerActions, []);
    if (drift === 'authority') h.setToken('changed-token'); if (drift === 'project') h.state.projectId = 'prj_other'; if (drift === 'workspace') h.state.workspaceId = 'wsp_other';
    const currentState = clone(h.state); release(); await assert.rejects(work, /CONTEXT_CHANGED/);
    assert.deepEqual(h.dom.snapshot(), before); assert.deepEqual(h.state, currentState); assert.deepEqual([...h.timers], timers);
    assert.deepEqual(h.timerActions, []); assert.deepEqual(h.trace, []); assert.ok(h.calls.every(c => c.method === 'GET' && c.path.includes('/prj_fixture/')));
  });

for (const drift of ['authority','project','workspace','draft']) test(`apply rechecks ${drift} before any DOM/internal/timer change`, async () => {
  const h = await seeded(), before = h.dom.snapshot(), timers = [...h.timers]; h.setFixture(fixture('new'));
  const apply = await h.editor.prepareReload({isCurrent: h.captureGuard()});
  if (drift === 'authority') h.setToken('changed'); if (drift === 'project') h.state.projectId = 'prj_other';
  if (drift === 'workspace') h.state.workspaceId = 'wsp_other'; if (drift === 'draft') h.state.drafts = 'keep unsaved words';
  assert.throws(apply, /CONTEXT_CHANGED/); assert.deepEqual(h.dom.snapshot(), before); assert.deepEqual([...h.timers], timers);
  assert.deepEqual(h.trace, []); assert.deepEqual(h.timerActions, []);
});

test('failed/abandoned prepare keeps internal generation and version used by explicit normal controls', async () => {
  const h = await seeded(); h.setFixture(fixture('new')); await h.editor.prepareReload({isCurrent: h.captureGuard()});
  await h.command('mvp-generation-cancel'); const cancel = h.calls.find(c => c.method === 'POST'); assert.match(cancel.path, /job_old\/cancel$/);
  await h.command('mvp-generate'); const generate = h.calls.find(c => c.method === 'POST' && c.path.endsWith('/content-generation'));
  assert.equal(generate.body.expected_content_version_id, 'pv_old');
});
test('normal reload/save preserve content version and scene control semantics', async () => {
  const h = await seeded(); h.dom.get('mvp-script').value = 'changed manually'; await h.command('mvp-save');
  const write = h.calls.find(c => c.method === 'PUT'); assert.equal(write.body.expected_content_version_id, 'pv_old');
  assert.equal(write.body.document.script, 'changed manually'); assert.equal(write.body.document.scenes[0].narration, 'old narration');
  assert.equal(h.effects.includes('refresh'), true);
});
test('normal active generation polling remains GET-only and stops scheduling after review readiness', async () => {
  const h = await seeded(); assert.deepEqual([...h.timers.values()].map(t => t.ms), [700]); h.setFixture(fixture('ready', {job: 'awaiting_review'}));
  await h.tick(); assert.equal(h.calls.length, 1); assert.equal(h.calls[0].method, 'GET'); assert.match(h.dom.get('mvp-generation-status').textContent, /awaiting_review/); assert.equal(h.timers.size, 0);
});
test('applying a staged view invalidates an older in-flight generation poll without canceling its new timer', async () => {
  const h = await seeded(); let release, entered, held = false; const reached = new Promise(r => {entered = r;});
  h.setHandler(async (c, response) => {const value = response(); if (!held && c.path.endsWith('/content-generation')) {held = true; entered(); await new Promise(r => {release = r;});} return value;});
  const oldPoll = h.tick(); await reached; h.setFixture(fixture('new'));
  const apply = await h.editor.prepareReload({isCurrent: h.captureGuard()}); apply();
  const before = h.dom.snapshot(), timers = [...h.timers], timerCount = h.timerActions.length; release(); await oldPoll;
  assert.deepEqual(h.dom.snapshot(), before); assert.deepEqual([...h.timers], timers); assert.equal(h.timerActions.length, timerCount);
});
test('no project stages zero calls and clears old content/provider/generation only on apply', async () => {
  const h = await seeded(); h.state.projectId = null; const before = h.dom.snapshot();
  const apply = await h.editor.prepareReload({isCurrent: h.captureGuard()}); assert.equal(h.calls.length, 0); assert.deepEqual(h.dom.snapshot(), before);
  apply(); assert.equal(h.dom.get('mvp-script').value, ''); assert.equal(h.dom.get('mvp-scenes').innerHTML, '');
  assert.equal(h.dom.get('mvp-provider-status').textContent, 'Chưa chọn project.'); assert.match(h.dom.get('mvp-generation-status').textContent, /Chưa có job/); assert.equal(h.timers.size, 0);
});
test('content absence skips only media plan; provider and generation still stage together', async () => {
  const h = harness({initial: fixture('empty', {withContent: false, job: null})}); const apply = await h.editor.prepareReload({isCurrent: h.captureGuard()});
  assert.deepEqual(h.calls.map(c => c.path.split('/').at(-1)), ['content','content-provider','content-generation']); apply();
  assert.equal(h.dom.get('mvp-plan').textContent, ''); assert.equal(h.dom.get('mvp-script').value, '');
});

function crossModule({gate = null} = {}) {
  const captured = JSON.parse(readFileSync(new URL('./fixtures/source-linked-edit/asgi.json', import.meta.url), 'utf8'));
  const timeline = clone(captured.responses.timeline_before.body), transcriptId = timelineTranscriptId(timeline);
  const state = {workspaceId: timeline.workspace_id, projectId: timeline.project_id, projectLoading: 0,
    principal: {subject: 'usr:read-fixture', expires_at: '2100-01-01T00:00:00Z'}, timeline: null, assets: [], analyses: [], mediaPlans: [], versions: [],
    transcriptDrafts: new Map(), playhead: 99, selectedClipId: 'old-selection', redoStack: ['redo'], undoStack: ['undo'], preview: null, productionPackage: null};
  const contentFixture = fixture('root', {job: null}), effects = [], permit = Symbol('initial-read');
  const asset = {asset_id: 'ast_new_scene_asset', filename: 'ROOT_NEW_ASSET_OPTION', content_type: 'image/png'};
  let release, entered; const reached = new Promise(r => {entered = r;});
  const h = harness({state, initial: contentFixture, apiHandler: async (c, fallback) => {
    assert.equal(c.method, 'GET'); if (gate && c.path.endsWith('/' + gate)) {entered(); await new Promise(r => {release = r;});}
    if (c.path.endsWith('/assets')) return [asset];
    if (c.path.endsWith('/analyses')) return [{analysis_id: timeline.source_analysis_id, transcript: {transcript_id: transcriptId}}];
    if (c.path.endsWith('/timeline')) return timeline;
    if (c.path.endsWith('/timeline/versions')) return captured.responses.history_before.body;
    if (c.path.endsWith('/analytics')) return {latest_sync: null};
    if (c.path.endsWith('/subtitle-templates')) return {templates: []};
    if (c.path.endsWith('/production-package')) return null;
    if (['content','storyboard-media-plan','content-provider','content-generation'].some(suffix => c.path.endsWith('/' + suffix))) return fallback();
    return [];
  }});
  const code = readFileSync(new URL('../studio.js', import.meta.url), 'utf8'), start = code.indexOf('async function loadProject('), end = code.indexOf('\nfunction renderNoProject(', start);
  assert.ok(start >= 0 && end > start); const peer = {sync() {}, isWorking: () => false, isPending: () => true, isDirty: () => true, reload: async () => effects.push('peer-read')};
  const args = ['state','initialProjectRead','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld','sourceLinkedEditor','sqlAudioProcessing','videoWordReview','variantNarration',
    'audioReview','stockReview','toast','sessionToken','productionWorkbenchDraft','audioWorkbenchDraft','$','videoReview','multiInput','variantFamilies',
    'stopPreviewPolling','stopProductionPolling','stopAnalyticsPolling','setSaveStatus','api','timelineTranscriptId','render','startPreviewPolling','startProductionPolling','startAnalyticsPolling'];
  const actual = new Function(...args, 'let multiInputBaseline="old-baseline";\n' + code.slice(start, end) + '\nreturn {run:loadProject,baseline:()=>multiInputBaseline};')(
    state, permit, () => true, () => true, () => true, peer, peer, peer, peer, peer, peer, (...a) => effects.push(['toast', ...a]),
    h.getToken, () => 'production-draft', () => JSON.stringify(h.dom.contentSnapshot()), id => h.dom.get(id.slice(1)), peer, h.editor, peer,
    () => effects.push('stop-preview'), () => effects.push('stop-production'), () => effects.push('stop-analytics'), (...a) => effects.push(['status', ...a]),
    h.api, timelineTranscriptId, () => effects.push('render'), () => effects.push('start-preview'), () => effects.push('start-production'), () => effects.push('start-analytics'));
  return {...h, effects, timeline, asset, permit, reached, release: () => release(), runRoot: actual.run, baseline: actual.baseline};
}
test('actual full Root loadProject and actual multi-input apply hydrate new canonical assets in one synchronous adoption', async () => {
  const h = crossModule(); await h.runRoot({initialRead: h.permit});
  assert.deepEqual(h.state.timeline, h.timeline); assert.deepEqual(h.state.assets, [h.asset]);
  assert.equal(h.dom.get('mvp-script').value, 'root script'); assert.match(h.dom.get('mvp-scenes').innerHTML, /ROOT_NEW_ASSET_OPTION/);
  assert.match(h.dom.get('mvp-status').textContent, /pv_root/); assert.equal(h.effects.filter(e => e === 'render').length, 1);
  assert.equal(h.effects.some(e => Array.isArray(e) && e[0] === 'toast'), false); assert.ok(h.calls.every(c => c.method === 'GET'));
  assert.equal(h.state.projectLoading, 0); assert.equal(h.editor.isBusy(), false); assert.equal(h.baseline(), JSON.stringify(h.dom.contentSnapshot()));
});
test('actual Root plus actual multi-input discards late authority drift at generation GET without partial canonical/workbench install', async () => {
  const h = crossModule({gate: 'content-generation'}), before = h.dom.contentSnapshot(), work = h.runRoot({initialRead: h.permit}); await h.reached;
  assert.equal(h.state.timeline, null); assert.deepEqual(h.state.assets, []); h.setToken('different-root-token'); h.release(); await work;
  assert.equal(h.state.timeline, null); assert.deepEqual(h.state.assets, []); assert.deepEqual(h.dom.contentSnapshot(), before);
  assert.equal(h.effects.includes('render'), false); assert.equal(h.timers.size, 0); assert.equal(h.baseline(), 'old-baseline');
  assert.ok(h.calls.every(c => c.method === 'GET')); assert.equal(h.state.projectLoading, 0);
});

import assert from 'node:assert/strict';
import test from 'node:test';
import {canManageAnalyticsRefresh, refreshIntent, initializeAnalyticsRefresh} from '../analytics-refresh.mjs';

const parent = {publication_id: 'pub_fixture', project_id: 'prj_fixture', workspace_id: 'wsp_fixture',
  platform: 'youtube', status: 'published', mode: 'live', dry_run: false, receipt: {remote_post_id: 'abcDEfgHI_1'}};
const state = () => ({projectId: 'prj_fixture', workspaceId: 'wsp_fixture', workspaceSlug: 'fixture',
  principal: {workspace_roles: {wsp_fixture: 'owner'}}, publications: [parent]});
const values = {publicationId: 'pub_fixture', mode: 'fixture', fixtureProfile: 'normal', firstRun: '2026-10-08T08:00',
  intervalHours: '24', maxRuns: '7', lookbackDays: '7', includeRevenue: false, enabled: false, acknowledged: false};

test('only exact workspace Owner manages intent; defaults preserve disabled fixture state', () => {
  assert.equal(canManageAnalyticsRefresh({...state(), principal: {workspace_roles: {foreign: 'owner', wsp_fixture: 'editor'}}}), false);
  const body = refreshIntent(state(), values);
  assert.equal(body.enabled, false); assert.equal(body.fixture_profile, 'normal'); assert.equal(body.query_policy, 'cumulative');
  assert.equal(body.first_run_at, new Date(values.firstRun).toISOString());
  assert.throws(() => refreshIntent({...state(), workspaceId: 'foreign'}, values));
  assert.throws(() => refreshIntent(state(), {...values, enabled: true}), /Xác nhận/);
});

test('report policy is explicit and invalid dates/numbers/implicit booleans reject', () => {
  const body = refreshIntent(state(), {...values, mode: 'official', includeRevenue: true});
  assert.equal(body.query_policy, 'rolling_complete_days'); assert.equal(body.lookback_days, 7); assert.equal(body.include_revenue, true);
  for (const change of [{firstRun: '2026-02-30T08:00'}, {maxRuns: '366'}, {intervalHours: '1.5'}, {intervalHours: ''},
    {enabled: 1}, {mode: 'unknown'}, {mode: 'official', lookbackDays: '0'}]) assert.throws(() => refreshIntent(state(), {...values, ...change}));
  const tiktok = state(); tiktok.publications = [{...parent, platform: 'tiktok'}];
  assert.equal(refreshIntent(tiktok, {...values, mode: 'official'}).query_policy, 'cumulative');
});

function harness() {
  const elements = new Map();
  class Element {
    constructor() {this.value = ''; this.checked = false; this.textContent = ''; this.children = []; this.listeners = {};}
    replaceChildren() {this.children = [];}
    append(value) {this.children.push(value);}
    addEventListener(key, fn) {this.listeners[key] = fn;}
  }
  const root = {querySelector(key) {if (!elements.has(key)) elements.set(key, new Element()); return elements.get(key);},
    createElement() {return new Element();}};
  const get = id => root.querySelector(`#${id}`);
  for (const [id, value] of Object.entries({'analytics-publication': 'pub_fixture', 'analytics-mode': 'fixture', 'analytics-fixture-profile': 'normal',
    'analytics-refresh-first': values.firstRun, 'analytics-refresh-interval': '24', 'analytics-refresh-runs': '7', 'analytics-refresh-lookback': '7'})) get(id).value = value;
  const current = state(), calls = [], errors = []; let counter = 0, plans = [];
  let handler = async (path, options = {}) => {
    if (!options.method) return plans;
    if (path.endsWith('/state')) {
      const body = JSON.parse(options.body), previous = plans[0];
      plans = [{...previous, enabled: body.enabled, revision: body.expected_revision + 1}]; return plans[0];
    }
    const config = JSON.parse(options.body);
    const plan = {plan_id: 'arp_fixture', project_id: current.projectId, workspace_id: current.workspaceId, publication_id: 'pub_fixture',
      revision: 1, enabled: config.enabled, run_count: 0, max_runs: config.max_runs, next_due_at: config.first_run_at,
      updated_by: '<img onerror=unsafe()>', config};
    plans = [plan]; return plan;
  };
  const controller = initializeAnalyticsRefresh({root, getState: () => current, api: async (...args) => {calls.push(args); return handler(...args);},
    toast: message => errors.push(message), uuid: () => String(++counter)});
  controller.sync(); return {controller, get, current, calls, errors, plans: () => plans, handler: fn => {handler = fn;}};
}

test('explicit creation retains one key across failure/replay and renders text nodes', async () => {
  const h = harness(); assert.equal(h.calls.length, 0);
  await h.controller.create(); await h.controller.create();
  assert.equal(h.calls.length, 2); assert.equal(h.calls[0][1].headers['Idempotency-Key'], h.calls[1][1].headers['Idempotency-Key']);
  assert.equal(h.get('analytics-refresh-rows').children.length, 1);
  assert.equal(h.get('analytics-refresh-rows').children[0].children[5].textContent, '<img onerror=unsafe()>');
  assert.equal(JSON.parse(h.calls[0][1].body).enabled, false);
});

test('Owner state change uses current revision and never chains a mutation', async () => {
  const h = harness(); await h.controller.create(); h.get('analytics-refresh-ack').checked = true;
  await h.controller.change(h.plans()[0]);
  assert.deepEqual(JSON.parse(h.calls[1][1].body), {expected_revision: 1, enabled: true, acknowledged_read_only: true});
  assert.equal(h.plans()[0].revision, 2); assert.equal(h.calls.length, 2);
  await h.controller.change(h.plans()[0]);
  assert.equal(JSON.parse(h.calls[2][1].body).expected_revision, 2); assert.equal(h.plans()[0].enabled, false);
});

test('viewer reads plans and cannot create or change them', async () => {
  const h = harness(); await h.controller.create(); h.calls.length = 0;
  h.current.principal.workspace_roles.wsp_fixture = 'viewer'; h.controller.sync();
  await h.controller.create(); await h.controller.change(h.plans()[0]); assert.equal(h.calls.length, 0);
  await h.controller.refresh(); assert.equal(h.calls.length, 1); assert.equal(h.calls[0][1], undefined);
});

test('late creation response cannot populate another project', async () => {
  const h = harness(); let resolve;
  h.handler(() => new Promise(value => {resolve = value;})); const pending = h.controller.create();
  h.current.projectId = 'prj_new'; h.current.publications = []; h.controller.sync();
  resolve({plan_id: 'arp_old', project_id: 'prj_fixture', workspace_id: 'wsp_fixture', publication_id: 'pub_fixture', config: {provider_mode: 'fixture'}});
  await pending; assert.equal(h.get('analytics-refresh-rows').children.length, 0);
});

test('unknown state outcome does not automatically retry POST', async () => {
  const h = harness(); await h.controller.create(); h.get('analytics-refresh-ack').checked = true;
  h.handler(async () => {throw new Error('EXPLICIT UNKNOWN STATE FIXTURE');});
  await h.controller.change(h.plans()[0]); assert.equal(h.calls.length, 2);
  assert(h.errors.at(-1).includes('Đọc lại trạng thái'));
});

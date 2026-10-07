import assert from 'node:assert/strict';
import test from 'node:test';
import {analyticsSyncPlan, canCollectAnalytics, analyticsSeries, snapshotDelta, analyticsChartPaths, initializeAnalyticsConsole} from '../analytics-console.mjs';

const publication = {publication_id: 'pub_fixture', project_id: 'prj_fixture', workspace_id: 'wsp_fixture', platform: 'youtube',
  status: 'published', mode: 'live', dry_run: false, mock: true, receipt: {remote_post_id: 'abcDEfgHI_1', mock: true, external_action: false}};
const snapshot = {snapshot_id: 'snap_a', ...publication, collected_at: '2026-10-07T01:00:00Z', provider_key: 'fixture-analytics-v1',
  source_kind: 'fixture', metrics: {views: 0, revenue: null}, evidence: {}};
const baseState = () => ({workspaceId: 'wsp_fixture', workspaceSlug: 'fixture', projectId: 'prj_fixture',
  principal: {workspace_roles: {wsp_fixture: 'editor'}}, publications: [publication], analyticsProviders: [
    {platform: 'youtube', mode: 'official', supports_sync: true, external_calls_enabled: false}]});
const selection = {publicationId: 'pub_fixture', mode: 'official', startDate: '2026-10-01', endDate: '2026-10-06', includeRevenue: false};

test('workspace role, exact publication and configured source govern collection', () => {
  assert.equal(canCollectAnalytics({workspace_roles: {foreign: 'owner', wsp_fixture: 'viewer'}}, 'wsp_fixture'), false);
  assert.equal(canCollectAnalytics({workspace_roles: {'slug:fixture': 'editor'}}, 'wsp_fixture', 'fixture'), true);
  assert.deepEqual(analyticsSyncPlan(baseState(), selection).query, {start_date: '2026-10-01', end_date: '2026-10-06', include_revenue: false});
  for (const change of [{projectId: 'foreign'}, {workspaceId: 'foreign'}, {principal: {platform_role: 'viewer'}}, {analyticsProviders: []}])
    assert.throws(() => analyticsSyncPlan({...baseState(), ...change}, selection));
  assert.throws(() => analyticsSyncPlan({...baseState(), analyticsProviders: [{platform: 'youtube', mode: 'official', supports_sync: true, external_calls_enabled: true}]}, selection), /Receipt mô phỏng/);
});

test('explicit fixture profile, dates and TikTok cumulative semantics', () => {
  assert.equal(analyticsSyncPlan(baseState(), {publicationId: 'pub_fixture', mode: 'fixture', fixtureProfile: 'normal'}).fixture_profile, 'normal');
  for (const changes of [{startDate: '2026-02-30'}, {endDate: '2026-09-30'}, {endDate: '2027-10-02'}, {includeRevenue: 1}])
    assert.throws(() => analyticsSyncPlan(baseState(), {...selection, ...changes}));
  const state = baseState(); state.publications = [{...publication, platform: 'tiktok'}]; state.analyticsProviders[0].platform = 'tiktok';
  assert.equal(analyticsSyncPlan(state, selection).query, undefined);
});

test('history retains zero/null and refuses foreign, fixture/provider and report-interval comparisons', () => {
  const current = {...snapshot, snapshot_id: 'snap_b', collected_at: '2026-10-07T02:00:00Z', metrics: {views: 10, revenue: null}};
  const points = analyticsSeries([current, snapshot, {...snapshot, workspace_id: 'foreign'}], 'views', {...baseState(), publicationId: 'pub_fixture', mode: 'fixture'});
  assert.deepEqual(points.map(point => point.value), [0, 10]);
  assert.equal(snapshotDelta(snapshot, current, 'views'), 10); assert.equal(snapshotDelta(snapshot, current, 'revenue'), null);
  for (const changes of [{mock: false}, {source_kind: 'official_api'}, {publication_id: 'foreign'},
    {evidence: {query: {start_date: '2026-10-02', end_date: '2026-10-06'}}}]) assert.equal(snapshotDelta(snapshot, {...current, ...changes}, 'views'), null);
});

test('chart leaves null gaps and source changes disconnected', () => {
  const points = [0, null, 10, 12].map((value, index) => ({value, time: `2026-10-07T0${index}:00:00Z`, scope: index === 3 ? 'different-report' : 'same-report'}));
  const chart = analyticsChartPaths(points);
  assert.equal(chart.paths.length, 3); assert.equal(chart.minimum, 0); assert.equal(chart.maximum, 12);
  assert(chart.paths.every(path => !path.d.includes(' L ')));
  assert.deepEqual(analyticsChartPaths([{value: null, time: '2026-10-07T00:00:00Z'}]), {paths: [], minimum: null, maximum: null});
});

function harness() {
  const elements = new Map();
  class Element {
    constructor() {this.value = ''; this.checked = false; this.children = []; this.listeners = {}; this.textContent = '';}
    addEventListener(name, fn) {this.listeners[name] = fn;}
    replaceChildren() {this.children = []; this.value = '';}
    append(child) {this.children.push(child);}
  }
  const root = {querySelector(id) {if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);}, createElement() {return new Element();}};
  const get = id => root.querySelector(`#${id}`); get('analytics-mode').value = 'fixture'; get('analytics-fixture-profile').value = 'normal';
  get('analytics-publication').value = 'pub_fixture'; get('analytics-history-metric').value = 'views';
  const state = baseState(), calls = [], queued = []; let counter = 0, handler;
  handler = async (path, options = {}) => {
    if (options.method === 'POST') return {sync_id: `sync_${counter}`, project_id: state.projectId, publication_id: 'pub_fixture', provider_mode: 'fixture', status: 'queued'};
    if (path.includes('/observations')) return {workspace_id: state.workspaceId, project_id: state.projectId, publication_id: 'pub_fixture',
      provider_mode: 'fixture', items: [snapshot], total_count: 1, next_cursor: null};
    return {project_id: state.projectId, publication_id: 'pub_fixture', latest_sync: null};
  };
  const controller = initializeAnalyticsConsole({api: async (...args) => {calls.push(args); return handler(...args);}, getState: () => state, root,
    onReport: report => {state.analyticsReport = report; state.activeAnalyticsSync = report?.latest_sync ?? null;},
    onQueued: sync => {queued.push(sync); state.activeAnalyticsSync = sync;}, toast: () => {}, uuid: () => String(++counter)});
  controller.sync();
  return {controller, state, get, calls, queued, handler: fn => {handler = fn;}};
}

test('loading history sends only scoped GETs and text nodes preserve untrusted strings', async () => {
  const h = harness(); await h.controller.refresh();
  assert.equal(h.calls.length, 2); assert(h.calls.every(([path, options]) => !options?.method && path.includes('/publications/pub_fixture/analytics')));
  assert.equal(h.get('analytics-history-rows').children.length, 1);
  assert.equal(h.get('analytics-history-rows').children[0].children[3].textContent, '0');
});

test('one explicit click creates one sync; confirmed completion permits a fresh requested refresh', async () => {
  const h = harness(); await h.controller.collect(); assert.equal(h.queued.length, 1);
  await h.controller.collect(); assert.equal(h.queued.length, 1);
  h.state.activeAnalyticsSync.status = 'succeeded'; h.controller.sync(); await h.controller.collect();
  assert.equal(h.queued.length, 2); const posts = h.calls.filter(([, options]) => options?.method === 'POST');
  assert.notEqual(posts[0][1].headers['Idempotency-Key'], posts[1][1].headers['Idempotency-Key']);
  assert.equal(JSON.parse(posts[0][1].body).fixture_profile, 'normal');
});

test('unknown request failure reuses its key on explicit retry', async () => {
  const h = harness(); h.handler(async () => {throw new Error('explicit transport fixture failure');});
  await h.controller.collect(); await h.controller.collect();
  assert.equal(h.calls[0][1].headers['Idempotency-Key'], h.calls[1][1].headers['Idempotency-Key']);
});

test('late history response cannot populate another project', async () => {
  const h = harness(); let resolveReport, resolveHistory;
  h.handler(path => new Promise(resolve => {if (path.includes('/observations')) resolveHistory = resolve; else resolveReport = resolve;}));
  const pending = h.controller.refresh(); h.state.projectId = 'prj_new'; h.state.publications = []; h.controller.sync();
  resolveReport({project_id: 'prj_fixture', publication_id: 'pub_fixture'}); resolveHistory({items: [snapshot]}); await pending;
  assert.equal(h.state.analyticsReport, null); assert.equal(h.get('analytics-history-rows').children.length, 0);
});

test('viewer can read but cannot enqueue observations', async () => {
  const h = harness(); h.state.principal.workspace_roles.wsp_fixture = 'viewer'; h.controller.sync();
  await h.controller.collect(); assert.equal(h.calls.length, 0);
  await h.controller.refresh(); assert.equal(h.calls.length, 2);
});

test('older pages are explicit reads, deduplicate and stop at the visible bound', async () => {
  const h = harness(); let page = 0;
  h.handler(async path => {
    if (!path.includes('/observations')) return {project_id: h.state.projectId, publication_id: 'pub_fixture'};
    page += 1;
    const items = Array.from({length: 50}, (_, index) => ({...snapshot, snapshot_id: `ams_page_${page}_${index}`}));
    return {workspace_id: h.state.workspaceId, project_id: h.state.projectId, publication_id: 'pub_fixture', provider_mode: 'fixture',
      items, next_cursor: `ams_next_page_${page}`, total_count: 900};
  });
  await h.controller.refresh(); assert.equal(page, 1);
  assert.equal(h.get('analytics-history-rows').children.length, 50);
  for (let count = 0; count < 12; count++) await h.controller.more();
  assert.equal(page, 10); assert.equal(h.get('analytics-history-rows').children.length, 500);
  assert.equal(h.get('analytics-history-more').disabled, true);
  assert(h.calls.every(([, options]) => !options?.method));
  assert(h.calls.at(-1)[0].includes('cursor=ams_next_page_9'));
});

test('foreign source page is rejected and does not replace displayed history', async () => {
  const h = harness(); await h.controller.refresh();
  h.handler(async path => path.includes('/observations') ? {workspace_id: 'foreign', project_id: h.state.projectId,
    publication_id: 'pub_fixture', provider_mode: 'fixture', items: [snapshot], next_cursor: null, total_count: 1}
    : {project_id: h.state.projectId, publication_id: 'pub_fixture'});
  await h.controller.refresh();
  assert.equal(h.get('analytics-history-rows').children.length, 1);
});

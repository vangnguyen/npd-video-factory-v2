import assert from 'node:assert/strict';
import test from 'node:test';
import {canCreateLearning, learningIntent, initializeChannelLearning} from '../channel-learning.mjs';

const parent = {publication_id: 'pub_fixture', project_id: 'prj_fixture', workspace_id: 'wsp_fixture', status: 'published', mode: 'live', dry_run: false, receipt: {remote_post_id: 'fixture'}};
const state = () => ({projectId: 'prj_fixture', workspaceId: 'wsp_fixture', principal: {workspace_roles: {wsp_fixture: 'editor'}}, publications: [parent]});
const selection = {publicationId: 'pub_fixture', mode: 'official', groupPosts: '3', controlPosts: '3', difference: '10'};
const snapshot = () => ({learning_snapshot_id: 'lsn_fixture', workspace_id: 'wsp_fixture', project_id: 'prj_fixture', publication_id: 'pub_fixture',
  schema_version: 'channel-learning-snapshot-v1', recommendation_only: true, autonomous_execution: false, content_sha256: 'a'.repeat(64),
  created_at: '2026-10-07T00:00:00Z', observations: [], scope: {source_kind: 'official_api', mock: true, niche: 'real_estate'},
  dimensions: ['hook', 'trend_family', 'duration', 'visual_strategy', 'subtitle_style', 'voice_profile', 'publishing_window'].map(dimension => ({dimension, groups: []}))});

test('exact scoped editing roles and official live publication required', () => {
  assert.deepEqual(learningIntent(state(), selection).policy, {minimum_group_posts: 3, minimum_control_posts: 3, maximum_posts: 100, minimum_score_difference: 10});
  assert.equal(canCreateLearning({...state(), principal: {workspace_roles: {wsp_fixture: 'reviewer'}}}), true);
  for (const invalid of [{principal: {workspace_roles: {other: 'owner', wsp_fixture: 'viewer'}}}, {workspaceId: 'other'}]) assert.throws(() => learningIntent({...state(), ...invalid}, selection));
  for (const invalid of [{mode: 'fixture'}, {groupPosts: '2'}, {groupPosts: '3.5'}, {controlPosts: '51'}, {difference: 'NaN'}, {difference: ''}, {difference: '101'}]) assert.throws(() => learningIntent(state(), {...selection, ...invalid}));
});

function harness() {
  const nodes = new Map();
  class Node {constructor() {this.value = ''; this.checked = false; this.children = []; this.textContent = ''; this.listeners = {};}
    replaceChildren() {this.children = [];}
    append(node) {this.children.push(node);}
    addEventListener(name, fn) {this.listeners[name] = fn;}}
  const root = {querySelector(id) {if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id);}, createElement() {return new Node();}};
  const get = id => root.querySelector(`#${id}`), current = state(), calls = [], errors = []; let counter = 0;
  for (const [id, value] of Object.entries({'analytics-publication': 'pub_fixture', 'analytics-mode': 'official', 'learning-group-posts': '3', 'learning-control-posts': '3', 'learning-score-difference': '10'})) get(id).value = value;
  let handler = async (path, options) => options?.method ? snapshot() : [snapshot()];
  const controller = initializeChannelLearning({root, getState: () => current, api: async (...args) => {calls.push(args); return handler(...args);}, toast: message => errors.push(message), uuid: () => String(++counter)});
  controller.sync(); return {controller, get, current, calls, errors, handler(fn) {handler = fn;}};
}

test('loading does not mutate; creation is explicit and advice requires a reviewed selection', async () => {
  const h = harness(); assert.equal(h.calls.length, 0); assert.deepEqual(h.controller.advice(), {});
  await h.controller.create(); assert.equal(h.calls.length, 1); assert.deepEqual(h.controller.advice(), {});
  h.get('learning-use-advice').checked = true; assert.deepEqual(h.controller.advice(), {learning_snapshot_id: 'lsn_fixture'});
  assert.equal(JSON.parse(h.calls[0][1].body).provider_mode, 'official');
  assert.match(h.get('learning-note').textContent, /Dữ liệu mô phỏng/);
  assert.match(h.get('learning-note').textContent, /giờ đăng thật/);
});

test('unknown outcome retains key, confirmed result permits a fresh explicit snapshot', async () => {
  const h = harness(); h.handler(async () => {throw new Error('lost reply');}); await h.controller.create();
  h.handler(async () => snapshot()); await h.controller.create(); await h.controller.create();
  assert.equal(h.calls[0][1].headers['Idempotency-Key'], h.calls[1][1].headers['Idempotency-Key']);
  assert.notEqual(h.calls[1][1].headers['Idempotency-Key'], h.calls[2][1].headers['Idempotency-Key']);
});

test('changing scope discards late responses and disables old reviewed advice', async () => {
  const h = harness(); let resolve; h.handler(() => new Promise(done => {resolve = done;}));
  const pending = h.controller.create(); h.current.projectId = 'prj_other'; h.controller.sync(); resolve(snapshot()); await pending;
  assert.equal(h.get('learning-history').children.length, 0); assert.deepEqual(h.controller.advice(), {});
  assert.equal(h.get('learning-use-advice').disabled, true);
});

test('provider-scope and autonomous-execution contradictions reject without binding advice', async () => {
  for (const change of [{workspace_id: 'foreign'}, {autonomous_execution: true}, {recommendation_only: false}, {content_sha256: 'bad'}]) {
    const h = harness(); h.handler(async () => ({...snapshot(), ...change})); await h.controller.create();
    assert.equal(h.errors.length, 1); assert.deepEqual(h.controller.advice(), {});
  }
});

test('history and feature annotations render only as text nodes', async () => {
  const h = harness(), value = snapshot(); value.dimensions[0].groups = [{value: '<img onerror=unsafe()>', sample_count: 3, control_count: 3,
    state: 'recommendation_candidate', score_difference: 20, snapshot_ids: ['ams_fixture'], control_snapshot_ids: ['ams_other']}];
  h.handler(async () => [value]); await h.controller.read();
  assert.equal(h.get('learning-rows').children[0].children[1].textContent, '<img onerror=unsafe()>');
  assert.equal(h.get('learning-history').children.length, 1); assert.deepEqual(h.controller.advice(), {});
});

test('changing mode prevents fixture history from being attached as channel advice', async () => {
  const h = harness(); await h.controller.read(); h.get('learning-use-advice').checked = true;
  h.get('analytics-mode').value = 'fixture'; assert.deepEqual(h.controller.advice(), {});
  assert.equal(h.get('learning-create').disabled, true);
});

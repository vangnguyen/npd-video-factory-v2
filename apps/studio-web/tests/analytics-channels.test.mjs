import assert from 'node:assert/strict';
import test from 'node:test';
import {initializeAnalyticsChannels} from '../analytics-channels.mjs';

function harness() {
  const elements = new Map();
  class Element {
    constructor() {this.value = ''; this.textContent = ''; this.children = []; this.listeners = {};}
    replaceChildren() {this.children = [];}
    append(value) {this.children.push(value);}
    addEventListener(key, listener) {this.listeners[key] = listener;}
  }
  const root = {querySelector(key) {if (!elements.has(key)) elements.set(key, new Element()); return elements.get(key);},
    createElement() {return new Element();}};
  const get = id => root.querySelector(`#${id}`); get('analytics-mode').value = 'fixture';
  const state = {workspaceId: 'wsp_fixture', principal: {workspace_roles: {wsp_fixture: 'viewer'}}}, calls = [], errors = [];
  const video = {publication_id: 'pub_fixture', project_id: 'prj_fixture', title: '<img onerror=unsafe()>', binding_state: 'fixture_unverified',
    latest_snapshot: {workspace_id: 'wsp_fixture', project_id: 'prj_fixture', publication_id: 'pub_fixture', platform: 'youtube',
      source_kind: 'fixture', provider_key: 'fixture-v1', mock: true, metrics: {views: 0, watch_time: null, completion_rate: null}}};
  const channel = {channel_key: 'fixture-channel', platform: 'youtube', target_account_id: 'UC_fixture', profile_id: 'ppf_fixture',
    profile_version: 1, provider_key: 'fixture-v1', provider_mode: 'fixture', mock: true, videos: [video]};
  const page = {workspace_id: 'wsp_fixture', provider_mode: 'fixture', publications_in_page: 1, channels: [channel], next_cursor: null};
  let handler = async () => page;
  const controller = initializeAnalyticsChannels({root, getState: () => state, api: async path => {calls.push(path); return handler(path);}, toast: message => errors.push(message)});
  controller.sync(); return {controller, state, get, calls, errors, page, video, channel, handler: value => {handler = value;}};
}

test('viewer explicitly reads channel observations, preserves null/zero and renders untrusted text', async () => {
  const h = harness(); assert.equal(h.calls.length, 0); await h.controller.refresh();
  assert.equal(h.calls.length, 1); assert(h.calls[0].startsWith('/api/v1/workspaces/wsp_fixture/analytics/channels?provider_mode=fixture'));
  const cells = h.get('analytics-channel-rows').children[0].children;
  assert.equal(cells[3].textContent, '<img onerror=unsafe()>'); assert.equal(cells[9].textContent, '0');
  assert.equal(cells[10].textContent, 'Không có dữ liệu'); assert.equal(cells[6].textContent, 'Mô phỏng');
});

test('channel pages merge only same channel key, are explicit and retain distinct targets', async () => {
  const h = harness(); h.handler(async path => {
    if (!path.includes('cursor=')) return {...h.page, next_cursor: 'pub_page_cursor'};
    return {...h.page, publications_in_page: 2, channels: [
      {...h.channel, videos: [h.video, {...h.video, publication_id: 'pub_second', latest_snapshot: null}]},
      {...h.channel, channel_key: 'other-account', target_account_id: 'UC_other', videos: [{...h.video, publication_id: 'pub_other', latest_snapshot: null}]}]};
  });
  await h.controller.refresh(); assert.equal(h.calls.length, 1);
  await h.controller.more(); assert.equal(h.calls.length, 2);
  assert.equal(h.get('analytics-channel-rows').children.length, 3);
  assert.equal(h.get('analytics-channel-more').disabled, true);
  assert(h.calls[1].includes('cursor=pub_page_cursor'));
});

test('late channel response cannot appear in another workspace or source', async () => {
  const h = harness(); let resolve;
  h.handler(() => new Promise(value => {resolve = value;})); const pending = h.controller.refresh();
  h.state.workspaceId = 'wsp_new'; h.controller.sync(); resolve(h.page); await pending;
  assert.equal(h.get('analytics-channel-rows').children.length, 0);
  h.handler(async () => h.page); await h.controller.refresh(); assert.equal(h.errors.length, 1);
  assert.equal(h.get('analytics-channel-rows').children.length, 0);
});

test('malformed or foreign observation cannot populate a scoped channel', async () => {
  const h = harness(); h.handler(async () => ({...h.page, channels: [{...h.channel, videos: [{...h.video,
    latest_snapshot: {...h.video.latest_snapshot, workspace_id: 'foreign'}}]}]}));
  await h.controller.refresh(); assert.equal(h.errors.length, 1); assert.equal(h.get('analytics-channel-rows').children.length, 0);
  assert.equal(h.calls.length, 1);
});

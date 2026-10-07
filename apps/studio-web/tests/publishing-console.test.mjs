import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {isPublishingOwner, publishApprovalPayload, usablePublishGrant, initializePublishingConsole} from '../publishing-console.mjs';

const publication = {publication_id: 'pub_fixture', project_id: 'prj_fixture', workspace_id: 'wsp_fixture',
  mode: 'live', status: 'awaiting_publish_approval', final_render_id: 'rnd_fixture', output_asset_id: 'ast_fixture',
  request_fingerprint: 'a'.repeat(64)};
const review = {...publication, owner_gates_enabled: true, artifact_sha256: 'b'.repeat(64),
  target_binding_sha256: 'c'.repeat(64), binding_sha256: 'd'.repeat(64),
  target_binding: {target_account_id: 'Fixture account'}, metadata: {title: '<img onerror=attack>', privacy: 'private'}};
const grant = {publish_approval_id: 'pua_' + 'e'.repeat(32), publication_id: publication.publication_id,
  workspace_id: publication.workspace_id, binding_sha256: review.binding_sha256,
  target_binding_sha256: review.target_binding_sha256, scope: 'PUBLISH_ONLY', revoked: false,
  expires_at: '2099-01-01T00:00:00Z'};

test('owner role is exact workspace/global/slug scope and never a foreign owner role', () => {
  assert.equal(isPublishingOwner({workspace_roles: {foreign: 'owner', wsp_fixture: 'viewer'}}, 'wsp_fixture'), false);
  assert.equal(isPublishingOwner({workspace_roles: {wsp_fixture: 'owner'}}, 'wsp_fixture'), true);
  assert.equal(isPublishingOwner({workspace_roles: {'slug:fixture': 'owner'}}, 'wsp_fixture', 'fixture'), true);
  assert.equal(isPublishingOwner({workspace_roles: {'*': 'owner'}}, 'wsp_fixture'), true);
  assert.equal(isPublishingOwner({platform_role: 'editor'}, 'wsp_fixture'), false);
  assert.equal(isPublishingOwner({platform_role: 'owner'}, 'wsp_fixture'), true);
});

test('consent body binds exact loaded review hashes and explicit acknowledgment', () => {
  assert.deepEqual(publishApprovalPayload(review, publication, true), {
    expected_fingerprint: 'a'.repeat(64), expected_artifact_sha256: 'b'.repeat(64),
    expected_target_sha256: 'c'.repeat(64), acknowledged: true});
  for (const changed of [{project_id: 'foreign'}, {workspace_id: 'foreign'}, {publication_id: 'foreign'},
    {owner_gates_enabled: false}, {artifact_sha256: 'missing'}, {request_fingerprint: 'e'.repeat(64)},
    {final_render_id: 'rnd_foreign'}, {output_asset_id: 'ast_foreign'}]) {
    assert.throws(() => publishApprovalPayload({...review, ...changed}, publication, true));
  }
  assert.throws(() => publishApprovalPayload(review, publication, 1));
  assert.throws(() => publishApprovalPayload(review, {...publication, mode: 'dry_run'}, true));
});

test('expired/revoked/mismatched consent cannot enqueue and never invents permission', () => {
  assert.equal(usablePublishGrant(grant, review, Date.parse('2026-10-07T00:00:00Z')), true);
  for (const changed of [{revoked: true}, {scope: 'PRODUCTION'}, {workspace_id: 'foreign'},
    {target_binding_sha256: 'f'.repeat(64)}, {binding_sha256: 'f'.repeat(64)}, {expires_at: 'not a date'},
    {expires_at: '2000-01-01T00:00:00Z'}, {publish_approval_id: 'bad'}]) {
    assert.equal(usablePublishGrant({...grant, ...changed}, review), false);
  }
  assert.equal(usablePublishGrant(null, review), false);
});

function harness({owner = true, enabled = true} = {}) {
  const elements = new Map();
  class Element {
    constructor() {this.value = ''; this.checked = false; this.options = []; this.listeners = {}; this.textContent = '';}
    addEventListener(name, fn) {this.listeners[name] = fn;}
    replaceChildren() {this.options = []; this.value = '';}
    append(row) {this.options.push(row);}
  }
  const root = {querySelector(selector) {if (!elements.has(selector)) elements.set(selector, new Element()); return elements.get(selector);},
    createElement() {return new Element();}};
  root.querySelector('#publishing-platform').value = 'youtube';
  const state = {principal: {workspace_roles: {wsp_fixture: owner ? 'owner' : 'viewer'}}, workspaceId: 'wsp_fixture',
    projectId: 'prj_fixture', activePublication: publication, publications: [publication],
    publishingPlatforms: [{platform: 'youtube', live_execution_enabled: enabled}],
    productionPackage: {current_for_timeline: true, approval: {status: 'approved'}, latest_final_render: {status: 'ready', qc_status: 'passed'}}};
  const calls = [], toasts = []; let approved = false;
  const api = async (path, options = {}) => {
    calls.push({path, ...options});
    if (path.endsWith('/publishing-profiles')) return [{target: {workspace_id: 'wsp_fixture', profile_id: 'ppf_fixture', platform: 'youtube', profile_version: 1, target_account_id: 'Fixture'}}];
    if (path === '/api/v1/publishing-platforms') return state.publishingPlatforms;
    if (path.endsWith('/publish-review')) return {...review, owner_gates_enabled: enabled, active_publish_approval: approved ? grant : null};
    if (options.method !== 'POST' && path.endsWith('/publishing-work')) return null;
    if (path.endsWith('/publish-approval/revoke')) {approved = false; return {...grant, revoked: true};}
    if (path.endsWith('/publish-approval')) {approved = true; return grant;}
    if (path.endsWith('/publishing-work')) return {status: 'queued', work_id: 'pwj_fixture'};
    return publication;
  };
  const controller = initializePublishingConsole({api, getState: () => state, root,
    publicationPayload: () => ({metadata: {title: 'Fixture'}}), setPublication: row => {state.activePublication = row;},
    toast: (message, error) => toasts.push({message, error}), uuid: () => 'explicit-fixture-uuid'});
  return {controller, state, calls, root, toasts, get: id => root.querySelector(`#${id}`)};
}

test('read refresh does not approve enqueue or send provider traffic; review uses textContent', async () => {
  const h = harness(); h.controller.sync(); await h.controller.refresh();
  assert.equal(h.calls.length, 5); assert(h.calls.every(call => !call.method));
  assert.equal(h.get('publishing-consent').disabled, true);
  assert.equal(h.get('publishing-enqueue').disabled, true);
  assert(h.get('publishing-review-text').textContent.includes('<img onerror=attack>'));
  assert.equal(h.get('publishing-review-text').innerHTML, undefined);
});

test('explicit consent then separate queue and revocation; no click chains another mutation', async () => {
  const h = harness(); h.controller.sync(); await h.controller.refresh();
  h.get('publishing-acknowledge').checked = true;
  await h.get('publishing-consent').listeners.click();
  assert.equal(h.calls.filter(call => call.method === 'POST').length, 1);
  assert(h.calls.at(-1).path.endsWith('/publish-approval'));
  assert.equal(h.get('publishing-enqueue').disabled, false);
  await h.get('publishing-enqueue').listeners.click();
  assert.deepEqual(JSON.parse(h.calls.at(-1).body), {publish_approval_id: grant.publish_approval_id});
  assert.equal(h.get('publishing-enqueue').disabled, true);
  await h.get('publishing-revoke').listeners.click();
  assert(h.calls.at(-1).path.endsWith('/publish-approval/revoke'));
  assert.equal(h.get('publishing-enqueue').disabled, true);
});

test('viewer and disabled deployments cannot use consent controls; switch clears acknowledgment', async () => {
  for (const options of [{owner: false}, {enabled: false}]) {
    const h = harness(options); h.controller.sync(); await h.controller.refresh();
    h.get('publishing-acknowledge').checked = true;
    await h.get('publishing-consent').listeners.click();
    assert.equal(h.calls.filter(call => call.method === 'POST').length, 0);
    assert.equal(h.get('publishing-enqueue').disabled, true);
    assert.equal(h.toasts.at(-1).error, true);
  }
  const h = harness(); h.controller.sync(); await h.controller.refresh();
  h.get('publishing-acknowledge').checked = true;
  h.state.activePublication = {...publication, publication_id: 'pub_other'}; h.controller.sync();
  assert.equal(h.get('publishing-acknowledge').checked, false);
  assert.equal(h.get('publishing-consent').disabled, true);
});

test('Studio shell exposes separate controls with disabled defaults', async () => {
  const html = await readFile(new URL('../studio.html', import.meta.url), 'utf8');
  for (const id of ['publishing-prepare', 'publishing-consent', 'publishing-enqueue', 'publishing-revoke']) {
    assert.match(html, new RegExp(`id="${id}"[^>]*disabled`));
  }
  const studio = await readFile(new URL('../studio.js', import.meta.url), 'utf8');
  assert(studio.includes('initializePublishingConsole') && studio.includes('state.principal = principal'));
});

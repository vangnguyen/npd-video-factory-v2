// Workspace analytics reads only. Account totals and autonomous actions are absent.
export function initializeAnalyticsChannels({api, getState, root = document, toast}) {
  const $ = id => root.querySelector(`#${id}`);
  let scope = '', revision = 0, busy = false, channels = [], nextCursor = null, loaded = 0;
  const key = () => JSON.stringify([getState().workspaceId, $('analytics-mode').value]);
  function row(tag, text) {const value = root.createElement(tag); value.textContent = text; return value;}
  function render() {
    const table = $('analytics-channel-rows'); table.replaceChildren();
    for (const channel of channels) for (const video of channel.videos) {
      const snapshot = video.latest_snapshot, query = snapshot?.evidence?.query;
      const tr = row('tr', '');
      const bindingLabel = {matched: 'Khớp bằng chứng snapshot', fixture_unverified: 'Mô phỏng, chưa xác minh',
        unbound: 'Chưa liên kết', mismatch: 'Bằng chứng không khớp', not_collected: 'Chưa thu thập'}[video.binding_state] ?? 'Chưa xác minh';
      for (const value of [channel.platform, channel.target_account_id ?? 'Chưa có tài khoản',
          `${channel.profile_id ?? 'Chưa có profile'} · v${channel.profile_version ?? '—'}`,
          video.title, `${video.project_id} / ${video.publication_id}`, bindingLabel,
          snapshot ? (snapshot.mock ? 'Mô phỏng' : 'Provider') : 'Chưa thu thập',
          snapshot?.collected_at ?? '—', query ? `${query.start_date} → ${query.end_date}` : 'Counter / fixture',
          snapshot?.metrics?.views ?? 'Không có dữ liệu', snapshot?.metrics?.watch_time ?? 'Không có dữ liệu',
          snapshot?.metrics?.completion_rate ?? 'Không có dữ liệu']) tr.append(row('td', String(value)));
      table.append(tr);
    }
    $('analytics-channel-note').textContent = `Đã đọc ${loaded} publication (tối đa 500/lần xem). Mỗi video giữ khoảng report riêng. Không cộng reach, tỷ lệ hoặc suy ra tổng tài khoản. Mô phỏng không xác nhận tài khoản thật.`;
    $('analytics-channel-refresh').disabled = busy || !getState().workspaceId;
    $('analytics-channel-more').disabled = busy || !nextCursor || loaded >= 500;
  }
  function sync() {
    const next = key();
    if (next !== scope) {scope = next; revision += 1; busy = false; channels = []; nextCursor = null; loaded = 0;}
    render();
  }
  async function read({more = false} = {}) {
    sync(); if (busy || !getState().workspaceId || more && (!nextCursor || loaded >= 500)) return;
    const state = getState(), mode = $('analytics-mode').value, captured = key(), ownRevision = revision, cursor = more ? nextCursor : null;
    busy = true; render();
    try {
      const path = `/api/v1/workspaces/${encodeURIComponent(state.workspaceId)}/analytics/channels?provider_mode=${encodeURIComponent(mode)}&limit=50`
        + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '');
      const page = await api(path);
      if (captured !== key() || ownRevision !== revision) return;
      if (page?.workspace_id !== state.workspaceId || page.provider_mode !== mode || !Array.isArray(page.channels) || page.channels.length > 100
          || !Number.isInteger(page.publications_in_page) || page.publications_in_page < 0 || page.publications_in_page > 50
          || page.next_cursor !== null && !/^pub_[A-Za-z0-9_-]{4,60}$/.test(page.next_cursor ?? '')
          || cursor && page.next_cursor === cursor) throw new Error('Channel analytics scope không khớp.');
      for (const channel of page.channels) {
        if (channel.provider_mode !== mode || !Array.isArray(channel.videos) || channel.videos.length > 100)
          throw new Error('Channel analytics scope không khớp.');
        for (const video of channel.videos) {
          const snapshot = video.latest_snapshot;
          if (snapshot && (snapshot.workspace_id !== state.workspaceId || snapshot.project_id !== video.project_id
              || snapshot.publication_id !== video.publication_id || snapshot.platform !== channel.platform
              || snapshot.source_kind !== (mode === 'fixture' ? 'fixture' : 'official_api') || snapshot.mock !== channel.mock
              || snapshot.provider_key !== channel.provider_key)) throw new Error('Channel observation scope không khớp.');
        }
      }
      const merged = new Map((more ? channels : []).map(value => [value.channel_key, {...value, videos: [...value.videos]}]));
      for (const channel of page.channels) {
        const previous = merged.get(channel.channel_key);
        const videos = [...new Map([...(previous?.videos ?? []), ...channel.videos].map(value => [value.publication_id, value])).values()];
        merged.set(channel.channel_key, {...channel, videos});
      }
      channels = [...merged.values()]; loaded = (more ? loaded : 0) + page.publications_in_page; nextCursor = page.next_cursor;
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; render();}}
  }
  $('analytics-channel-refresh').addEventListener('click', () => read());
  $('analytics-channel-more').addEventListener('click', () => read({more: true}));
  $('analytics-mode').addEventListener('change', sync);
  return {sync, refresh: () => read(), more: () => read({more: true})};
}

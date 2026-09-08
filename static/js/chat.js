const LS = {
  get: (k, f) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : f; } catch { return f; } },
  set: (k, v) => { localStorage.setItem(k, JSON.stringify(v)); }
};

const CHAT_CSS = `:root {
  --chat-bg: #f3f4f6;
  --panel: #ffffff;
  --panel-border: #e5e7eb;
  --muted: #6b7280;
  --text: #0f172a;
  --primary: #4f46e5;
  --primary-soft: #eef2ff;
  --sent: #4f46e5;
  --sent-text: #ffffff;
  --received: #ffffff;
  --match-a: #fde68a;
  --match-b: #fca5a5;
}

.chat-shell {
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  display: grid;
  grid-template-rows: auto 1fr;
  grid-template-columns: 1fr;
  height: calc(100dvh - 140px);
  max-height: 860px;
  margin: 1rem auto;
  width: min(1100px, 100%);
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 24px;
  overflow: hidden;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--panel-border);
  background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,255,255,0.7));
  backdrop-filter: blur(10px);
}
.chat-header-left { display:flex; align-items:center; gap:0.75rem; min-width:0; }
.chat-back { color:var(--text); text-decoration:none; font-weight:700; padding:0.25rem 0.5rem; border-radius:12px; }
.chat-back:hover { background:#f1f5f9; }
.chat-title { font-weight:900; color:var(--text); font-size:1.05rem; }
.chat-subtitle { font-size:0.8rem; color:var(--muted); }

.chat-body {
  display: grid;
  grid-template-columns: minmax(260px, 320px) 1fr;
  min-height: 0;
}
@media (max-width: 860px) {
  .chat-body { grid-template-columns: 1fr; }
  .chat-sidebar { display:none; }
  .chat-shell.open-sidebar .chat-sidebar { display:block; position:fixed; inset:0; z-index:50; width:100%; max-width:320px; }
}

.chat-sidebar {
  display:flex; flex-direction:column;
  border-right:1px solid var(--panel-border);
  background:#fafafa;
  min-height:0;
}
.chat-search {
  display:flex; gap:0.5rem; padding:0.75rem;
  border-bottom:1px solid var(--panel-border);
}
.chat-search input {
  flex:1; padding:0.6rem 0.75rem; border-radius:12px;
  border:1px solid var(--panel-border); background:#fff; color:var(--text);
}
.chat-peers {
  overflow:auto; flex:1; padding:0.5rem;
}
.peer-item {
  display:flex; align-items:center; gap:0.75rem;
  padding:0.7rem 0.75rem; border-radius:14px; cursor:pointer;
  transition: background 0.2s;
}
.peer-item:hover, .peer-item.active { background:#eef2ff; }
.peer-avatar {
  width:40px; height:40px; border-radius:50%;
  background:#e5e7eb; color:#374151; display:grid; place-items:center; font-weight:800;
}
.peer-name { font-weight:700; color:var(--text); font-size:0.95rem; }
.peer-meta { font-size:0.8rem; color:var(--muted); }

.chat-main { display:flex; flex-direction:column; min-height:0; position:relative; }
.chat-placeholder {
  position:absolute; inset:0; display:grid; place-items:center; padding:2rem;
}
.chat-placeholder-box { text-align:center; max-width:420px; }
.chat-placeholder-emoji { font-size:3.5rem; }
.chat-placeholder h2 { color:var(--text); margin-top:0.5rem; }

.chat-room {
  display:flex; flex-direction:column; min-height:0;
  background:
    radial-gradient( circle at 20% 20%, rgba(79,70,229,0.06), transparent 35% ),
    radial-gradient( circle at 80% 80%, rgba(244,63,94,0.06), transparent 35% ),
    var(--chat-bg);
}
.chat-room-header {
  display:flex; align-items:center; justify-content:space-between; gap:1rem;
  padding:0.75rem 1.25rem; border-bottom:1px solid var(--panel-border);
  background: linear-gradient(180deg, rgba(255,255,255,0.85), rgba(255,255,255,0.55));
  backdrop-filter: blur(8px);
}
.chat-room-meta { display:flex; align-items:center; gap:0.6rem; }
.chat-meta-badge {
  display:inline-flex; align-items:center; gap:0.35rem;
  padding:0.3rem 0.7rem; border-radius:999px;
  font-size:0.78rem; font-weight:800; border:1px solid var(--panel-border);
  background:#fff; color:var(--text);
}
.chat-meta-badge.is-crush { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
.chat-meta-badge.is-match { background:#fef3c7; color:#92400e; border-color:#fde68a; }

.chat-messages {
  flex:1; overflow:auto; padding:1.25rem;
  display:flex; flex-direction:column; gap:0.6rem;
}
.chat-empty { color:var(--muted); padding:1rem; text-align:center; }

.bubble-wrap {
  display:flex; gap:0.6rem; max-width:72%;
}
.bubble-wrap.mine { align-self:flex-end; flex-direction:row-reverse; }
.bubble-wrap.theirs { align-self:flex-start; }

.bubble {
  padding:0.7rem 1rem; border-radius:18px;
  border:1px solid transparent;
  color:var(--text); background:var(--received);
  box-shadow:0 2px 0 rgba(15,23,42,0.04);
  word-wrap:break-word;
}
.bubble.mine {
  background: linear-gradient(135deg,#4f46e5,#6366f1);
  color:#fff; border-color:#4338ca;
  border-bottom-right-radius:6px;
}
.bubble.theirs {
  background:#fff;
  border-color:#e5e7eb;
  border-bottom-left-radius:6px;
}
.bubble.meta { margin-top:0.3rem; font-size:0.72rem; opacity:0.7; display:flex; gap:0.5rem; align-items:center; }

/* Match theming */
.chat-room.is-match .bubble.mine {
  background: linear-gradient(135deg,#fde68a,#fca5a5);
  color:#5b21b6; border-color:#fcd34d;
}
.chat-room.is-match .chat-room-header {
  background: linear-gradient(180deg,#fff1f2,#fff7ed);
}
.chat-room.is-match .chat-room-meta .chat-meta-badge.is-match { box-shadow: 0 0 0 4px rgba(253,230,138,0.35); }

.chat-composer {
  display:flex; gap:0.5rem; align-items:center; padding:0.75rem 1rem;
  border-top:1px solid var(--panel-border); background:#fff;
}
.chat-composer input[type="text"] {
  flex:1; padding:0.75rem 1rem; border-radius:999px;
  border:1px solid var(--panel-border); background:#f8fafc; color:var(--text);
}
.chat-composer input:focus { outline:none; border-color:var(--primary); background:#fff; box-shadow: 0 0 0 4px var(--primary-soft); }
.btn { padding:0.6rem 1rem; border-radius:12px; border:none; font-weight:800; cursor:pointer; }
.btn.primary { background:var(--primary); color:#fff; box-shadow: 0 6px 16px rgba(79,70,229,0.25); }
.btn.send { border-radius:999px; padding:0.65rem 1.1rem; }
.chip { background:#f1f5f9; color:var(--text); padding:0.45rem 0.8rem; border-radius:999px; border:1px solid var(--panel-border); font-weight:700; cursor:pointer; }

.emoji-picker { position:absolute; bottom:64px; left:12px; background:#fff; border:1px solid var(--panel-border); border-radius:16px; padding:0.5rem; box-shadow: 0 20px 40px rgba(15,23,42,0.12); }
.emoji-grid { display:grid; grid-template-columns: repeat(8, 1fr); gap:0.25rem; }
.emoji-grid button { background:transparent; border:0; font-size:1.25rem; padding:0.25rem; cursor:pointer; border-radius:10px; }
.emoji-grid button:hover { background:#f1f5f9; }

.timer-pill { display:inline-flex; align-items:center; gap:0.35rem; padding:0.25rem 0.7rem; border-radius:999px; font-size:0.75rem; font-weight:800; color:#7c3aed; background:#f5f3ff; border:1px solid #e9d5ff; }

.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border-width:0; }

`;

function buildEmojiPicker() {
  const emojis = ["😀","😂","😍","😎","😭","😡","👍","👎","🎉","🔥","❤️","👀","🤔","😅","🤣","🙏","👋","🤝","✨","🚀","💬","📎","📸","🎵","📚","✅","❌","⚠️","💡","📅"];
  const grid = document.getElementById('emojiGrid');
  if (!grid) return;
  grid.innerHTML = emojis.map(e => `<button type="button" data-emoji="${e}" aria-label="${e}">${e}</button>`).join('');
}

function $(sel, ctx = document) { return ctx.querySelector(sel); }

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function safeColor(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = Math.imul(17, h) + str.charCodeAt(i) | 0;
  const hue = Math.abs(h) % 360;
  return `hsl(${hue}, 70%, 55%)`;
}

function initials(name) {
  return (name || '?').split(' ').map(n => n[0]).slice(0,2).join('').toUpperCase();
}

function persistMsg(peerId, msg) {
  const key = 'chat_history:' + [peerId, getMyId()].sort().join('_');
  const list = LS.get(key, []);
  list.push(msg);
  const maxAge = 7 * 24 * 60 * 60 * 1000;
  const now = Date.now();
  const filtered = list.filter(m => (now - new Date(m.ts).getTime()) < maxAge);
  LS.set(key, filtered);
}

async function loadHistory(peerId) {
  // Prefer server-side history (Supabase, encrypted) over localStorage
  const myId = getMyId();
  if (myId && peerId) {
    try {
      const res = await fetch(`/api/chat/history/${encodeURIComponent(peerId)}`, {
        headers: { 'Accept': 'application/json' }
      });
      const data = await res.json();
      if (data.success && data.messages && data.messages.length) {
        return data.messages;
      }
    } catch (e) {
      // Fall back to localStorage if server fetch fails
      console.debug('Server history fetch failed:', e);
    }
  }
  const key = 'chat_history:' + [peerId, getMyId()].sort().join('_');
  const maxAge = 7 * 24 * 60 * 60 * 1000;
  const now = Date.now();
  return (LS.get(key, []) || []).filter(m => (now - new Date(m.ts).getTime()) < maxAge);
}

function getMyId() {
  try {
    const u = JSON.parse(sessionStorage.getItem('user') || '{}');
    return u.uid || u.id || u.user_id || window.__CURRENT_USER__?.uid || '';
  } catch { return window.__CURRENT_USER__?.uid || ''; }
}

let chatSocket = null;

function peerName(peerId) {
  const peer = document.querySelector(`.peer-item[data-peer-id="${CSS.escape(peerId)}"] .peer-name`);
  return peer?.textContent?.replace('✅', '').trim() || 'New message';
}

function showChatAlert(peerId, msg) {
  const isOpen = LS.get('current_peer') === peerId && !document.getElementById('chatRoom')?.hidden;
  if (isOpen && document.visibilityState === 'visible') return;
  const sender = msg.sender_meta?.name || peerName(peerId);
  const preview = (msg.text || '').slice(0, 140);
  document.title = `● ${sender}: ${preview || 'New message'}`;
  if (window.Notification?.permission === 'granted') {
    const options = { body: preview, tag: `chat-${peerId}`, renotify: true };
    navigator.serviceWorker?.ready.then(registration => registration.showNotification(`New message from ${sender}`, options))
      .catch(() => new Notification(`New message from ${sender}`, options));
  }
}

function receiveMessage(msg) {
  if (!msg?.from || msg.from === getMyId()) return;
  const peerId = msg.from;
  const key = 'chat_history:' + [peerId, getMyId()].sort().join('_');
  const list = LS.get(key, []);
  if (!list.some(m => m.ts === msg.ts && m.text === msg.text && m.from === msg.from)) {
    list.push(msg);
    LS.set(key, list);
  }
  if (LS.get('current_peer') === peerId) {
    renderHistory(peerId);
    chatSocket?.emit('chat_delivered', { to: peerId, ts: msg.ts, msg_id: msg.msg_id || '' });
  }
  showChatAlert(peerId, msg);
  window._fetchNotifications?.(true);
  loadPeers($('#peerSearch')?.value || '');
}

function connectChatSocket() {
  if (!window.io) return;
  chatSocket = window.io({ transports: ['websocket', 'polling'], withCredentials: true });
  chatSocket.on('connect', () => {
    const peerId = LS.get('current_peer');
    if (peerId) chatSocket.emit('chat_join', { peer: peerId });
  });
  chatSocket.on('chat_receive', receiveMessage);
}

function getPreloadPeer() {
  const pattern = /\/chat\/([^/?#]+)/;
  const m = pattern.exec(location.pathname);
  const el = document.getElementById('preloadPeer');
  return m ? decodeURIComponent(m[1]) : (el ? el.value || el.textContent.trim() : '');
}

function getUserInfo(userId) {
  const profileEl = document.getElementById('chatUserProfile');
  try {
    return profileEl ? JSON.parse(profileEl.textContent) : null;
  } catch { return null; }
}

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function setCrushBadge(peerId) {
  const wrap = document.getElementById('chatRoomHeader');
  if (!wrap) return;
  ['is-crush','is-match'].forEach(c => wrap.classList.remove(c));
  const crush = LS.get('chat_state:' + peerId, {});
  if (crush.is_match) wrap.classList.add('is-match');
  else if (crush.is_crush) wrap.classList.add('is-crush');
}

function openChat(peerId) {
  LS.set('current_peer', peerId);
  document.querySelectorAll('.peer-item').forEach(el => el.classList.toggle('active', el.dataset.peerId === peerId));

  document.getElementById('chatPlaceholder').hidden = true;
  const room = document.getElementById('chatRoom');
  room.hidden = false;
  room.classList.add('open');

  const info = getUserInfo(peerId);
  const name = info?.name || peerId;
  $('#chatRoomTitle').textContent = name;
  const avatar = $('#chatRoomAvatar');
  if (avatar) {
    avatar.textContent = initials(name);
    avatar.style.background = `linear-gradient(145deg, ${safeColor(peerId)}, #4243b6)`;
  }
  const meta = $('#chatRoomMeta');
  meta.innerHTML = '';

  const state = LS.get('chat_state:' + peerId, {});
  if (state.is_match) {
    const b = document.createElement('span');
    b.className = 'chat-meta-badge is-match';
    b.textContent = '💞 Match';
    meta.appendChild(b);
  } else if (state.is_crush) {
    const b = document.createElement('span');
    b.className = 'chat-meta-badge is-crush';
    b.textContent = '💘 Crush';
    meta.appendChild(b);
  }

  setCrushBadge(peerId);
  room.classList.toggle('is-match', !!(state.is_match));
  $('#chatSubtitle').textContent = (state.is_match ? '💞 Matched — ' : '') + name;

  if (chatSocket?.connected) chatSocket.emit('chat_join', { peer: peerId });

  renderHistory(peerId);
  $('#chatInput').focus();
}
async function renderHistory(peerId) {
  const container = $('#chatMessages');
  const messages = await loadHistory(peerId);
  if (!messages || !messages.length) { container.innerHTML = '<div class="chat-empty">No messages yet</div>'; return; }
  const myId = getMyId();
  container.innerHTML = '';
  const frag = document.createDocumentFragment();
  messages.forEach(msg => {
    const isMine = msg.from === myId;
    const wrap = document.createElement('div');
    wrap.className = 'bubble-wrap ' + (isMine ? 'mine' : 'theirs');
    wrap.setAttribute('data-ts', msg.ts);

    const bubble = document.createElement('div');
    bubble.className = 'bubble ' + (isMine ? 'mine' : 'theirs');

    const text = document.createElement('div');
    text.className = 'bubble-text';
    text.innerHTML = linkifyAbhiHub(escapeHtml(msg.text));
    bubble.appendChild(text);

    const meta = document.createElement('div');
    meta.className = 'bubble meta';
    const left = document.createElement('span');
    left.textContent = formatTime(msg.ts) || '';
    const timer = document.createElement('span');
    timer.className = 'timer-pill';
    updateTimerText(timer, msg.ts);
    meta.appendChild(left);
    meta.appendChild(timer);
    bubble.appendChild(meta);

    const avatar = document.createElement('div');
    avatar.className = 'peer-avatar';
    avatar.style.background = isMine ? '#eef2ff' : safeColor(peerId);
    avatar.style.color = isMine ? '#4f46e5' : '#fff';
    avatar.textContent = isMine ? 'Me' : initials(getUserInfo(peerId)?.name || peerId);
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    frag.appendChild(wrap);
  });
  container.appendChild(frag);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch] || ch));
}

function linkifyAbhiHub(html) {
  return html.replace(/(https?:\/\/)?(www\.)?abhihub\.edu\.eu\.org(\/[^\s)]*)?/gi, match => {
    const href = /^https?:\/\//i.test(match) ? match : 'https://' + match.replace(/^www\./i, '');
    return `<a class="abhihub-link" href="${href}" target="_blank" rel="noopener">${match}</a>`;
  });
}

function updateTimerText(timerEl, iso) {
  const sentAt = new Date(iso).getTime();
  const expiresAt = sentAt + (7 * 24 * 60 * 60 * 1000);
  const remaining = expiresAt - Date.now();
  if (remaining > 0) {
    timerEl.textContent = 'Disappears ' + new Intl.RelativeTimeFormat(navigator.language, { numeric: 'auto' }).format(Math.max(1, Math.round(remaining / 1000 / 60)), 'minute');
    timerEl.style.color = '#7c3aed';
    timerEl.style.background = '#f5f3ff';
    timerEl.style.borderColor = '#e9d5ff';
  } else {
    timerEl.textContent = 'Disappeared';
    timerEl.style.color = '#ef4444';
    timerEl.style.background = '#fef2f2';
    timerEl.style.borderColor = '#fecaca';
  }
}

function startDisappearingCleanup(peerId) {
  if (startDisappearingCleanup._timers.has(peerId)) return;
  const tick = () => {
    const container = $('#chatMessages');
    if (!container || LS.get('current_peer') !== peerId) return;
    const messages = LS.get('chat_history:' + [peerId, getMyId()].sort().join('_'), []);
    if (!messages.length) { container.innerHTML = '<div class="chat-empty">No messages yet</div>'; }
    const now = Date.now();
    let changed = false;
    for (const node of Array.from(container.children)) {
      const raw = node.getAttribute('data-ts');
      const ts = raw ? new Date(raw).getTime() : NaN;
      if (Number.isNaN(ts)) continue;
      const remaining = ts + 7*24*60*60*1000 - now;
      const timer = node.querySelector('.timer-pill');
      if (!timer) continue;
      if (remaining <= 0) {
        node.style.transition = 'opacity 0.4s';
        node.style.opacity = '0';
        setTimeout(() => { node.remove(); changed = true; }, 450);
      } else {
        timer.textContent = 'Disappears ' + new Intl.RelativeTimeFormat(navigator.language, { numeric: 'auto' }).format(Math.max(1, Math.round(remaining / 1000 / 60)), 'minute');
      }
    }
    if (changed) {
      const key = 'chat_history:' + [peerId, getMyId()].sort().join('_');
      const list = LS.get(key, []);
      const fresh = list.filter(m => (now - new Date(m.ts).getTime()) < 7 * 24 * 60 * 60 * 1000);
      LS.set(key, fresh);
    }
  };
  startDisappearingCleanup._timers.set(peerId, setInterval(tick, 30000));
  tick();
}
startDisappearingCleanup._timers = new Map();

async function loadPeers(q = '') {
  const list = $('#peerList');
  list.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const url = q ? `/api/chat/search-peers?q=${encodeURIComponent(q)}` : `/api/chat/search-peers?q=__suggested__`;
    const data = await fetchJson(url);
    const users = (data.users || []).concat(data.suggested || []);
    const seen = new Set();
    const unique = [];
    for (const u of users) { const id = u.id || u.user_id; if (!id || seen.has(id)) continue; seen.add(id); unique.push(u); }
    if (!unique.length) { list.innerHTML = '<div class="empty">No peers found</div>'; return; }

    const current = LS.get('current_peer') || getPreloadPeer();
    list.innerHTML = unique.map(u => {
      const id = u.id || u.user_id;
      const active = id === current ? 'active' : '';
      const badge = (u.is_verified ? ' ✅' : '');
      return `<div class="peer-item ${active}" data-peer-id="${id}" data-action="chatOpenPeer">
        <div class="peer-avatar" style="background:${safeColor(id)}22; color:${safeColor(id)}">${initials(u.full_name)}</div>
        <div>
          <div class="peer-name">${(u.full_name || 'Student') + badge}</div>
          <div class="peer-meta">${u.rank_title || 'Student'}${u.college_name ? ' · ' + u.college_name : ''}</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = `<div class="empty">${e.message || 'Load failed'}</div>`;
  }
}

async function loadCrushState(peerId) {
  try {
    const data = await fetchJson(`/api/crush/status/${encodeURIComponent(peerId)}`);
    LS.set('chat_state:' + peerId, { is_crush: !!data.is_crush, is_match: !!data.is_match, crushes_remaining: data.crushes_remaining });
    setCrushBadge(peerId);
    const room = document.getElementById('chatRoom');
    if (room) room.classList.toggle('is-match', !!data.is_match);
  } catch { /* ignore */ }
}

async function sendMessage() {
  const input = $('#chatInput');
  const peerId = LS.get('current_peer');
  const text = (input.value || '').trim();
  if (!peerId || !text) return;

  const msg = {
    from: getMyId(), text, ts: new Date().toISOString(),
    sender_meta: { name: window.__CURRENT_USER__?.name || 'A student' }
  };
  const myId = getMyId();
  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const list = LS.get(key, []);
  list.push(msg);
  LS.set(key, list);

  if (chatSocket?.connected) {
    chatSocket.emit('chat_send', { to: peerId, text, ts: msg.ts, sender_meta: msg.sender_meta });
  } else {
    try {
      await fetchJson('/api/chat/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ to: peerId, text, ts: msg.ts, sender_meta: msg.sender_meta })
      });
    } catch (error) {
      list.pop();
      LS.set(key, list);
      renderHistory(peerId);
      window.alert('Message could not be sent. Please check your connection and try again.');
      return;
    }
  }

  input.value = '';
  renderHistory(peerId);
}

document.addEventListener('DOMContentLoaded', () => {
  // This file is loaded by the shared layout. Only initialise it on the chat page.
  if (!document.querySelector('.chat-shell')) return;

  buildEmojiPicker();
  connectChatSocket();

  const preload = getPreloadPeer();
  if (preload) openChat(preload);

  loadPeers();

  document.addEventListener('click', async (e) => {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;
    const action = actionEl.getAttribute('data-action');

    if (action === 'chatOpenPeer') {
      const item = actionEl.closest('.peer-item');
      const peerId = item?.dataset.peerId;
      if (!peerId) return;
      openChat(peerId);
      await loadCrushState(peerId);
      return;
    }
    if (action === 'chatNewConversation') {
      document.getElementById('chatPlaceholder').hidden = false;
      document.getElementById('chatRoom').hidden = true;
      LS.set('current_peer', '');
      $('#chatSubtitle').textContent = 'Open a conversation';
      $('#peerSearch').focus();
      return;
    }
    if (action === 'chatEnableNotifications') {
      if (window.PushNotifications?.isSupported()) {
        const result = await window.PushNotifications.subscribe();
        actionEl.textContent = result.success ? 'Alerts enabled' : 'Alerts unavailable';
      } else if (window.Notification) {
        const permission = await window.Notification.requestPermission();
        actionEl.textContent = permission === 'granted' ? 'Alerts enabled' : 'Alerts blocked';
      }
      return;
    }
    if (action === 'chatRefreshPeers') {
      loadPeers($('#peerSearch').value || '');
      return;
    }
    if (action === 'chatToggleEmoji') {
      const picker = document.getElementById('emojiPicker');
      picker.hidden = !picker.hidden;
      return;
    }
  });

  $('#peerSearch')?.addEventListener('input', (e) => loadPeers(e.target.value));

  document.getElementById('emojiGrid')?.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-emoji]');
    if (!btn) return;
    const input = document.getElementById('chatInput');
    input.value = (input.value || '') + btn.dataset.emoji;
    input.focus();
  });

  document.getElementById('chatComposer')?.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage();
  });

});

if (typeof window !== 'undefined') { window.ChatApp = { openChat, loadPeers, sendMessage }; }

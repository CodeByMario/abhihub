const LS = {
  get: (k, f) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : f; } catch { return f; } },
  set: (k, v) => { localStorage.setItem(k, JSON.stringify(v)); }
};

const ChatSound = {
  ctx: null,
  get enabled() { return LS.get('chat_sound_enabled', true); },
  set enabled(v) { LS.set('chat_sound_enabled', !!v); },
  init() {
    try {
      if (!this.ctx && (window.AudioContext || window.webkitAudioContext)) {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (this.ctx && this.ctx.state === 'suspended') {
        this.ctx.resume().catch(() => {});
      }
    } catch (_) {}
  },
  playSend() {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.ctx || this.ctx.state !== 'running') return;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      const now = this.ctx.currentTime;
      osc.type = 'sine';
      osc.frequency.setValueAtTime(480, now);
      osc.frequency.exponentialRampToValueAtTime(740, now + 0.07);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.07);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(now);
      osc.stop(now + 0.07);
    } catch (_) {}
  },
  playReceive() {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.ctx || this.ctx.state !== 'running') return;
      const now = this.ctx.currentTime;
      const osc1 = this.ctx.createOscillator();
      const gain1 = this.ctx.createGain();
      osc1.frequency.setValueAtTime(659.25, now);
      gain1.gain.setValueAtTime(0.08, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
      osc1.connect(gain1);
      gain1.connect(this.ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.08);

      const osc2 = this.ctx.createOscillator();
      const gain2 = this.ctx.createGain();
      osc2.frequency.setValueAtTime(880, now + 0.08);
      gain2.gain.setValueAtTime(0.08, now + 0.08);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc2.connect(gain2);
      gain2.connect(this.ctx.destination);
      osc2.start(now + 0.08);
      osc2.stop(now + 0.2);
    } catch (_) {}
  },
  playReaction() {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.ctx || this.ctx.state !== 'running') return;
      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(523.25, now);
      osc.frequency.exponentialRampToValueAtTime(1046.50, now + 0.12);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(now);
      osc.stop(now + 0.12);
    } catch (_) {}
  }
};

['pointerdown', 'keydown', 'touchstart'].forEach(evt => {
  document.addEventListener(evt, () => ChatSound.init(), { once: true });
});

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
.msg-status { font-weight:700; }

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
  const isDuplicate = list.some(m => (m.msg_id && m.msg_id === msg.msg_id) || (m.ts === msg.ts && m.text === msg.text));
  if (isDuplicate) return;

  list.push(msg);
  LS.set(key, list);
  showPeerTyping(false, peerId);
  ChatSound.playReceive();

  if (LS.get('current_peer') === peerId && !document.getElementById('chatRoom')?.hidden) {
    appendMessageBubble(msg, false, peerId, 'delivered');
    chatSocket?.emit('chat_read', { to: peerId, ts: msg.ts, msg_id: msg.msg_id || '' });
    updateStudyStreakBadge(peerId, list);
  } else {
    chatSocket?.emit('chat_delivered', { to: peerId, ts: msg.ts, msg_id: msg.msg_id || '' });
    showChatAlert(peerId, msg);
  }
  window._fetchNotifications?.(true);
  loadPeers($('#peerSearch')?.value || '');
}

let typingTimeout = null;
function handleTypingInput(peerId) {
  if (!chatSocket?.connected || !peerId) return;
  chatSocket.emit('chat_typing', { to: peerId, is_typing: true });
  clearTimeout(typingTimeout);
  typingTimeout = setTimeout(() => {
    chatSocket.emit('chat_typing', { to: peerId, is_typing: false });
  }, 2200);
}

function showPeerTyping(isTyping, peerId) {
  const container = $('#chatMessages');
  if (!container || LS.get('current_peer') !== peerId) return;
  let bubble = document.getElementById('chatPeerTypingBubble');
  if (isTyping) {
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.id = 'chatPeerTypingBubble';
      bubble.className = 'bubble-wrap theirs';
      const name = getPeerDisplayName(peerId);
      bubble.innerHTML = `
        <div class="peer-avatar" style="background:${safeColor(peerId)};color:#fff">${initials(name)}</div>
        <div class="typing-indicator" aria-label="${escapeHtml(name)} is typing">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
          <span style="font-size:0.75rem;color:#64748b;margin-left:5px;font-weight:600">${escapeHtml(name)} is typing…</span>
        </div>
      `;
      container.appendChild(bubble);
      container.scrollTop = container.scrollHeight;
    }
  } else if (bubble) {
    bubble.remove();
  }
}

function connectChatSocket() {
  if (!window.io) return;
  chatSocket = window.io({ transports: ['websocket', 'polling'], withCredentials: true });
  chatSocket.on('connect', () => {
    const peerId = LS.get('current_peer');
    if (peerId) chatSocket.emit('chat_join', { peer: peerId });
  });
  chatSocket.on('chat_peer_typing', (data) => {
    if (data?.from === LS.get('current_peer')) {
      showPeerTyping(!!data.is_typing, data.from);
    }
  });
  chatSocket.on('chat_receive', receiveMessage);
  chatSocket.on('chat_received', (data) => {
    updateMessageStatus(data.msg_id || data.ts, 'delivered');
  });
  chatSocket.on('chat_read_receipt', (data) => {
    updateMessageStatus(data.msg_id || data.ts, 'read');
  });
  chatSocket.on('chat_message_ack', (data) => {
    updateMessageStatus(data.msg_id || data.ts, 'sent');
    if (data.error) showSendError(data.error);
  });
  chatSocket.on('chat_peer_react', (data) => {
    if (!data?.emoji) return;
    const targetId = data.msg_id || data.ts;
    let wrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(targetId)}"]`);
    if (!wrap) wrap = document.querySelector(`.bubble-wrap[data-ts="${CSS.escape(targetId)}"]`);
    if (wrap) {
      renderReactionBadge(wrap, data.emoji);
      ChatSound.playReaction();
      popXpEffect(5, 'Study React');
    }
  });
  chatSocket.on('chat_peer_file_fulfilled', (data) => {
    if (!data?.file_url) return;
    const targetId = data.msg_id || data.ts;
    const peerId = LS.get('current_peer');
    if (peerId) {
      const myId = getMyId();
      const key = 'chat_history:' + [peerId, myId].sort().join('_');
      const list = LS.get(key, []);
      const targetMsg = list.find(m => (data.msg_id && m.msg_id === data.msg_id) || (data.ts && m.ts === data.ts));
      if (targetMsg) {
        const bestResourceUrl = data.resource_url || (data.doc_id ? `/resources/${data.doc_id}` : data.file_url);
        targetMsg.file_req.file_url = bestResourceUrl;
        targetMsg.file_req.file_name = data.file_name;
        if (data.title) targetMsg.file_req.title = data.title;
        targetMsg.file_req.doc_id = data.doc_id;
        targetMsg.file_req.resource_url = bestResourceUrl;
        targetMsg.file_req.status = 'fulfilled';
        LS.set(key, list);
      }
      let wrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(targetId)}"]`);
      if (!wrap && data.ts) wrap = document.querySelector(`.bubble-wrap[data-ts="${CSS.escape(data.ts)}"]`);
      if (wrap) {
        const bubble = wrap.querySelector('.bubble');
        if (bubble && targetMsg) renderBubbleBody(bubble, targetMsg, targetMsg.from === myId);
        ChatSound.playReceive();
        popXpEffect(15, 'File Received XP');
      }
    }
  });
  chatSocket.on('chat_peer_file_status', (data) => {
    if (!data?.status) return;
    const targetId = data.msg_id || data.ts;
    const peerId = LS.get('current_peer');
    if (peerId) {
      const myId = getMyId();
      const key = 'chat_history:' + [peerId, myId].sort().join('_');
      const list = LS.get(key, []);
      const targetMsg = list.find(m => (data.msg_id && m.msg_id === data.msg_id) || (data.ts && m.ts === data.ts));
      if (targetMsg) {
        if (!targetMsg.file_req) targetMsg.file_req = {};
        targetMsg.file_req.status = data.status;
        LS.set(key, list);
      }
      let wrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(targetId)}"]`);
      if (!wrap && data.ts) wrap = document.querySelector(`.bubble-wrap[data-ts="${CSS.escape(data.ts)}"]`);
      if (wrap) {
        const bubble = wrap.querySelector('.bubble');
        if (bubble && targetMsg) renderBubbleBody(bubble, targetMsg, targetMsg.from === myId);
        if (data.status === 'rejected') {
          ChatSound.playReceive();
        }
      }
    }
  });
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

function popXpEffect(amount = 10, label = 'Study XP') {
  const container = document.querySelector('.chat-main') || document.body;
  const pop = document.createElement('div');
  pop.className = 'xp-pop';
  pop.textContent = `+${amount} ${label} ⚡`;
  container.appendChild(pop);
  setTimeout(() => pop.remove(), 1200);
}

function updateStudyMomentum(peerId, messages) {
  const bar = document.getElementById('chatMomentumBar');
  if (!bar) return;
  const count = (messages || []).length;
  const days = new Set();
  (messages || []).forEach(m => {
    if (m.ts) {
      try { days.add(new Date(m.ts).toISOString().slice(0, 10)); } catch (_) {}
    }
  });
  const streakDays = Math.max(1, days.size);
  const totalXp = count * 10;
  const level = Math.floor(totalXp / 100) + 1;
  const currentLevelXp = totalXp % 100;
  const titles = ['Exam Buddy', 'Study Partner', 'Scholar', 'Prep Master', 'Academic Elite'];
  const rank = titles[Math.min(titles.length - 1, level - 1)];

  const streakEl = document.getElementById('momentumStreakText');
  if (streakEl) streakEl.textContent = `${streakDays}-Day Streak`;
  const levelEl = document.getElementById('momentumLevelText');
  if (levelEl) levelEl.textContent = `Level ${level} ${rank}`;
  const xpEl = document.getElementById('momentumXpText');
  if (xpEl) xpEl.textContent = `${currentLevelXp} / 100 XP`;
  const fillEl = document.getElementById('momentumProgressFill');
  if (fillEl) fillEl.style.width = `${Math.max(6, currentLevelXp)}%`;
}

function attachReactionBar(wrap, msg) {
  if (!wrap || wrap.querySelector('.reaction-bar')) return;
  const bar = document.createElement('div');
  bar.className = 'reaction-bar';
  const emojis = ['❤️', '💡', '🔥', '👏', '💯'];
  bar.innerHTML = emojis.map(em => `<button type="button" class="reaction-btn" data-action="chatReact" data-emoji="${em}" title="React ${em}">${em}</button>`).join('');
  wrap.appendChild(bar);
  if (msg?.reaction) {
    renderReactionBadge(wrap, msg.reaction);
  }
}

function renderReactionBadge(wrap, emoji) {
  if (!wrap || !emoji) return;
  let badge = wrap.querySelector('.bubble-reaction-badge');
  if (!badge) {
    badge = document.createElement('div');
    badge.className = 'bubble-reaction-badge';
    wrap.appendChild(badge);
  }
  badge.textContent = emoji;
}

function updateStudyStreakBadge(peerId, messages) {
  const meta = $('#chatRoomMeta');
  if (meta) {
    const existing = meta.querySelector('.chat-meta-badge.is-streak');
    if (existing) existing.remove();
  }

  if (messages && messages.length) {
    const days = new Set();
    messages.forEach(m => {
      if (m.ts) {
        try { days.add(new Date(m.ts).toISOString().slice(0, 10)); } catch (_) {}
      }
    });
    const count = days.size;
    if (count > 0 && meta) {
      const badge = document.createElement('span');
      badge.className = 'chat-meta-badge is-streak';
      badge.textContent = count > 1 ? `🔥 ${count}d Streak` : `⚡ Study Duo`;
      badge.title = `${count} active study day(s) together`;
      meta.appendChild(badge);
    }
  }
  updateStudyMomentum(peerId, messages);
}

function getPeerDisplayName(peerId) {
  const el = document.querySelector(`.peer-item[data-peer-id="${CSS.escape(peerId)}"] .peer-name`);
  if (el) {
    const n = el.textContent.replace('✅', '').trim();
    if (n) return n;
  }
  return LS.get('peer_name_' + peerId, '');
}

async function updatePeerHeader(peerId) {
  let name = getPeerDisplayName(peerId);
  if (!name || name === 'Student') {
    try {
      const res = await fetchJson(`/api/chat/user-info/${encodeURIComponent(peerId)}`);
      if (res?.success && res?.user?.name) {
        name = res.user.name;
        LS.set('peer_name_' + peerId, name);
      }
    } catch (_) {}
  }
  name = name || 'Student';
  const titleEl = $('#chatRoomTitle');
  if (titleEl) titleEl.textContent = name;
  const avatarEl = $('#chatRoomAvatar');
  if (avatarEl) {
    avatarEl.textContent = initials(name);
    avatarEl.style.background = `linear-gradient(145deg, ${safeColor(peerId)}, #4243b6)`;
  }
  const subEl = $('#chatSubtitle');
  if (subEl) subEl.textContent = 'Active · ' + name;
}

let activePollTimer = null;
function startActivePeerSync(peerId) {
  clearInterval(activePollTimer);
  activePollTimer = setInterval(async () => {
    if (LS.get('current_peer') !== peerId || document.hidden) return;
    try {
      const serverMessages = await loadHistory(peerId);
      if (serverMessages && serverMessages.length) {
        syncNewMessages(peerId, serverMessages);
      }
    } catch (_) {}
  }, 2500);
}

function syncNewMessages(peerId, serverMessages) {
  const container = $('#chatMessages');
  if (!container || LS.get('current_peer') !== peerId) return;
  const myId = getMyId();
  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const localList = LS.get(key, []);
  let hasNew = false;

  serverMessages.forEach(sMsg => {
    const exists = localList.some(l => (l.msg_id && l.msg_id === sMsg.msg_id) || (l.ts === sMsg.ts && l.text === sMsg.text));
    if (!exists) {
      localList.push(sMsg);
      hasNew = true;
      const isMine = sMsg.from === myId;
      appendMessageBubble(sMsg, isMine, peerId, sMsg.status || 'delivered');
      if (!isMine) {
        ChatSound.playReceive();
        chatSocket?.emit('chat_read', { to: peerId, ts: sMsg.ts, msg_id: sMsg.msg_id || '' });
      }
    } else if (sMsg.status) {
      updateMessageStatus(sMsg.msg_id || sMsg.ts, sMsg.status);
    }
  });

  if (hasNew) {
    LS.set(key, localList);
    updateStudyStreakBadge(peerId, localList);
  }
}

function closeChat() {
  LS.set('current_peer', '');
  const room = document.getElementById('chatRoom');
  if (room) {
    room.hidden = true;
    room.classList.remove('open');
  }
  const shell = document.querySelector('.chat-shell');
  if (shell) shell.classList.remove('room-open');
  document.querySelectorAll('.peer-item').forEach(el => el.classList.remove('active'));
  const placeholder = document.getElementById('chatPlaceholder');
  if (placeholder && window.innerWidth > 760) {
    placeholder.hidden = false;
  }
  const subEl = document.getElementById('chatSubtitle');
  if (subEl) subEl.textContent = 'Open a conversation';
}

function openChat(peerId) {
  LS.set('current_peer', peerId);
  document.querySelectorAll('.peer-item').forEach(el => el.classList.toggle('active', el.dataset.peerId === peerId));

  const placeholder = document.getElementById('chatPlaceholder');
  if (placeholder) placeholder.hidden = true;
  const room = document.getElementById('chatRoom');
  if (room) {
    room.hidden = false;
    room.classList.add('open');
  }
  const shell = document.querySelector('.chat-shell');
  if (shell) shell.classList.add('room-open');

  updatePeerHeader(peerId);

  const meta = $('#chatRoomMeta');
  if (meta) meta.innerHTML = '';

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

  if (chatSocket?.connected) {
    chatSocket.emit('chat_join', { peer: peerId });
    chatSocket.emit('chat_read', { to: peerId, ts: new Date().toISOString() });
  }

  renderHistory(peerId);
  const myId = getMyId();
  updateStudyMomentum(peerId, LS.get('chat_history:' + [peerId, myId].sort().join('_'), []));
  startActivePeerSync(peerId);
  $('#chatInput')?.focus();
}

function filterActive3DayMessages(list) {
  const cutoff = Date.now() - (3 * 24 * 60 * 60 * 1000);
  return (list || []).filter(m => {
    if (!m) return false;
    if (!m.ts) return true;
    const t = new Date(m.ts).getTime();
    return isNaN(t) || t >= cutoff;
  });
}

async function renderHistory(peerId) {
  const container = $('#chatMessages');
  if (!container) return;

  const myId = getMyId();
  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const localMessages = filterActive3DayMessages(LS.get(key, []));
  LS.set(key, localMessages);

  if (localMessages.length) {
    _renderMessageList(container, localMessages, myId, peerId);
    updateStudyStreakBadge(peerId, localMessages);
  } else {
    container.innerHTML = '<div class="chat-empty">Loading messages…</div>';
  }

  try {
    const serverMessages = await loadHistory(peerId);
    if (serverMessages && serverMessages.length) {
      const seen = new Set();
      const rawMerged = [];
      for (const m of localMessages.concat(serverMessages)) {
        const idKey = m.msg_id || (m.ts + ':' + m.text);
        if (!seen.has(idKey)) {
          seen.add(idKey);
          rawMerged.push(m);
        }
      }
      const merged = filterActive3DayMessages(rawMerged);
      merged.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
      LS.set(key, merged);
      _renderMessageList(container, merged, myId, peerId);
      updateStudyStreakBadge(peerId, merged);
    } else if (!localMessages.length) {
      container.innerHTML = '<div class="chat-empty">No messages yet. Send a message to start!</div>';
    }
  } catch (_) {
    if (!localMessages.length) {
      container.innerHTML = '<div class="chat-empty">No messages yet. Send a message to start!</div>';
    }
  }
}

function renderBubbleBody(bubble, msg, isMine) {
  let contentDiv = bubble.querySelector('.bubble-content');
  if (!contentDiv) {
    contentDiv = document.createElement('div');
    contentDiv.className = 'bubble-content';
    const meta = bubble.querySelector('.meta');
    if (meta) bubble.insertBefore(contentDiv, meta);
    else bubble.appendChild(contentDiv);
  }
  contentDiv.innerHTML = '';

  let fileReq = msg.file_req;
  if (!fileReq && typeof msg.text === 'string' && (msg.text.includes('Requested File:') || msg.msg_type === 'file_request')) {
    const rawTitle = msg.text.replace(/^[📑\s]*Requested File:\s*/i, '').trim();
    fileReq = {
      title: rawTitle,
      details: '',
      status: 'awaiting',
      file_url: 'yet_to_add'
    };
  }

  if (fileReq) {
    if (fileReq.status === 'rejected') {
      contentDiv.innerHTML = `
        <div class="file-req-card rejected">
          <div class="file-req-badge rejected">✕ Request Declined</div>
          <div class="file-req-title">${escapeHtml(fileReq.title)}</div>
          ${fileReq.meta_info ? `<div class="file-req-meta">${escapeHtml(fileReq.meta_info)}</div>` : ''}
          <div class="file-req-status rejected">This study material request was declined.</div>
        </div>
      `;
    } else if (fileReq.status === 'fulfilled' || (fileReq.file_url && fileReq.file_url !== 'yet_to_add')) {
      let resourceLink = fileReq.resource_url || (fileReq.doc_id ? `/resources/${fileReq.doc_id}` : (fileReq.file_url || '#'));
      if (resourceLink.startsWith('/resource/')) {
        resourceLink = resourceLink.replace('/resource/', '/resources/');
      }
      contentDiv.innerHTML = `
        <div class="file-req-card fulfilled">
          <div class="file-req-badge ready">${fileReq.resource_url || fileReq.doc_id ? '🌐 Published to Library' : '✅ File Attached'}</div>
          <div class="file-req-title">${escapeHtml(fileReq.title || fileReq.file_name || 'Study Material')}</div>
          ${fileReq.meta_info ? `<div class="file-req-meta">${escapeHtml(fileReq.meta_info)}</div>` : ''}
          <div class="file-req-info">
            <span class="file-icon">📄</span>
            <span class="file-name">${escapeHtml(fileReq.file_name || 'Study Material')}</span>
          </div>
          <div class="file-req-actions">
            <a href="${escapeHtml(resourceLink)}" target="_blank" class="btn-open-material" title="Open in AbhiHub Viewer">
              👁️ Open in AbhiHub Viewer
            </a>
          </div>
        </div>
      `;
      // Auto-upgrade legacy /static/uploads/chat/ URLs to /resources/<doc_id>
      if (!fileReq.doc_id && fileReq.file_url && fileReq.file_url.includes('/static/uploads/chat/')) {
        const cleanFn = fileReq.file_url.split('/').pop();
        fetch(`/api/chat/resolve-doc?filename=${encodeURIComponent(cleanFn)}`)
          .then(r => r.json())
          .then(res => {
            if (res.success && res.resource_url) {
              fileReq.doc_id = res.doc_id;
              fileReq.resource_url = res.resource_url;
              fileReq.file_url = res.resource_url;
              const linkEl = contentDiv.querySelector('.btn-open-material');
              if (linkEl) linkEl.href = res.resource_url;
              const badgeEl = contentDiv.querySelector('.file-req-badge');
              if (badgeEl) badgeEl.textContent = '🌐 Published to Library';
              const peerId = LS.get('current_peer');
              if (peerId) {
                const myId = getMyId();
                const key = 'chat_history:' + [peerId, myId].sort().join('_');
                const list = LS.get(key, []);
                const found = list.find(m => (msg.msg_id && m.msg_id === msg.msg_id) || (msg.ts && m.ts === msg.ts));
                if (found && found.file_req) {
                  found.file_req.doc_id = res.doc_id;
                  found.file_req.resource_url = res.resource_url;
                  found.file_req.file_url = res.resource_url;
                  LS.set(key, list);
                }
              }
            }
          }).catch(() => {});
      }
    } else if (isMine) {
      contentDiv.innerHTML = `
        <div class="file-req-card mine">
          <div class="file-req-badge">📑 File Requested</div>
          <div class="file-req-title">${escapeHtml(fileReq.title)}</div>
          ${fileReq.meta_info ? `<div class="file-req-meta">${escapeHtml(fileReq.meta_info)}</div>` : ''}
          ${fileReq.details ? `<div class="file-req-desc">${escapeHtml(fileReq.details)}</div>` : ''}
          <div class="file-req-status awaiting">⏳ Awaiting peer response & attachment</div>
        </div>
      `;
    } else {
      contentDiv.innerHTML = `
        <div class="file-req-card theirs">
          <div class="file-req-badge">📑 File Requested from You</div>
          <div class="file-req-title">${escapeHtml(fileReq.title)}</div>
          ${fileReq.meta_info ? `<div class="file-req-meta">${escapeHtml(fileReq.meta_info)}</div>` : ''}
          ${fileReq.details ? `<div class="file-req-desc">${escapeHtml(fileReq.details)}</div>` : ''}
          <div class="file-req-actions">
            <button type="button" class="btn-accept-file" data-action="chatAcceptFile" data-msg-id="${escapeHtml(msg.msg_id || '')}" data-ts="${escapeHtml(msg.ts || '')}">
              ✓ Accept & Attach File
            </button>
            <button type="button" class="btn-reject-file" data-action="chatRejectFile" data-msg-id="${escapeHtml(msg.msg_id || '')}" data-ts="${escapeHtml(msg.ts || '')}">
              ✕ Decline
            </button>
          </div>
        </div>
      `;
    }
  } else if (msg.file_attachment) {
    const att = msg.file_attachment;
    let viewUrl = att.resource_url || (att.doc_id ? `/resources/${att.doc_id}` : (att.file_url || '#'));
    if (viewUrl.startsWith('/resource/')) {
      viewUrl = viewUrl.replace('/resource/', '/resources/');
    }
    contentDiv.innerHTML = `
      <div class="file-req-card fulfilled">
        <div class="file-req-badge ready">${att.resource_url || att.doc_id ? '🌐 Published to Library' : '📎 Shared File'}</div>
        <div class="file-req-title">${escapeHtml(att.file_name || 'File Attachment')}</div>
        <div class="file-req-info">
          <span class="file-icon">📄</span>
          <span class="file-name">${escapeHtml(att.file_name || 'Study Material')}</span>
        </div>
        <div class="file-req-actions">
          <a href="${escapeHtml(viewUrl)}" target="_blank" class="btn-open-material" title="Open in AbhiHub Viewer">
            👁️ Open in AbhiHub Viewer
          </a>
        </div>
      </div>
    `;
    // Auto-upgrade legacy /static/uploads/chat/ URLs to /resources/<doc_id>
    if (!att.doc_id && att.file_url && att.file_url.includes('/static/uploads/chat/')) {
      const cleanFn = att.file_url.split('/').pop();
      fetch(`/api/chat/resolve-doc?filename=${encodeURIComponent(cleanFn)}`)
        .then(r => r.json())
        .then(res => {
          if (res.success && res.resource_url) {
            att.doc_id = res.doc_id;
            att.resource_url = res.resource_url;
            att.file_url = res.resource_url;
            const linkEl = contentDiv.querySelector('.btn-open-material');
            if (linkEl) linkEl.href = res.resource_url;
            const badgeEl = contentDiv.querySelector('.file-req-badge');
            if (badgeEl) badgeEl.textContent = '🌐 Published to Library';
          }
        }).catch(() => {});
    }
  } else {
    contentDiv.className = 'bubble-content bubble-text';
    contentDiv.innerHTML = linkifyAbhiHub(escapeHtml(msg.text));
  }
}

function _renderMessageList(container, messages, myId, peerId) {
  container.innerHTML = '';
  const frag = document.createDocumentFragment();
  const peerName = getPeerDisplayName(peerId);
  messages.forEach(msg => {
    const isMine = msg.from === myId;
    const wrap = document.createElement('div');
    wrap.className = 'bubble-wrap ' + (isMine ? 'mine' : 'theirs');
    wrap.setAttribute('data-ts', msg.ts);
    if (msg.msg_id) wrap.setAttribute('data-msg-id', msg.msg_id);

    const bubble = document.createElement('div');
    bubble.className = 'bubble ' + (isMine ? 'mine' : 'theirs');

    const meta = document.createElement('div');
    meta.className = 'meta';
    const left = document.createElement('span');
    left.textContent = formatTime(msg.ts) || '';
    meta.appendChild(left);

    if (isMine) {
      const statusSpan = document.createElement('span');
      statusSpan.className = 'msg-status ' + (msg.status || 'sent');
      statusSpan.textContent = msg.status === 'read' ? '✓✓' : (msg.status === 'delivered' ? '✓✓' : (msg.status === 'pending' ? '⏱️' : '✓'));
      meta.appendChild(statusSpan);
    }

    bubble.appendChild(meta);
    renderBubbleBody(bubble, msg, isMine);

    if (!isMine) {
      const avatar = document.createElement('div');
      avatar.className = 'peer-avatar';
      avatar.style.background = safeColor(peerId);
      avatar.style.color = '#fff';
      avatar.textContent = initials(peerName);
      wrap.appendChild(avatar);
    }
    wrap.appendChild(bubble);
    attachReactionBar(wrap, msg);
    frag.appendChild(wrap);
  });
  container.appendChild(frag);
  container.scrollTop = container.scrollHeight;
}

function appendMessageBubble(msg, isMine, peerId, status = 'sent') {
  const container = $('#chatMessages');
  if (!container) return;

  if (msg.msg_id && container.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(msg.msg_id)}"]`)) {
    return;
  }
  if (msg.ts && container.querySelector(`.bubble-wrap[data-ts="${CSS.escape(msg.ts)}"]`)) {
    return;
  }

  const empty = container.querySelector('.chat-empty, .empty');
  if (empty) empty.remove();

  const wrap = document.createElement('div');
  wrap.className = 'bubble-wrap ' + (isMine ? 'mine' : 'theirs');
  wrap.setAttribute('data-ts', msg.ts);
  if (msg.msg_id) wrap.setAttribute('data-msg-id', msg.msg_id);

  const bubble = document.createElement('div');
  bubble.className = 'bubble ' + (isMine ? 'mine' : 'theirs');

  const meta = document.createElement('div');
  meta.className = 'meta';
  const left = document.createElement('span');
  left.textContent = formatTime(msg.ts) || '';
  meta.appendChild(left);

  if (isMine) {
    const statusSpan = document.createElement('span');
    statusSpan.className = 'msg-status ' + status;
    statusSpan.textContent = status === 'pending' ? '⏱️' : (status === 'delivered' ? '✓✓' : (status === 'read' ? '✓✓' : '✓'));
    meta.appendChild(statusSpan);
  }

  bubble.appendChild(meta);
  renderBubbleBody(bubble, msg, isMine);

  if (!isMine) {
    const avatar = document.createElement('div');
    avatar.className = 'peer-avatar';
    avatar.style.background = safeColor(peerId);
    avatar.style.color = '#fff';
    avatar.textContent = initials(getPeerDisplayName(peerId));
    wrap.appendChild(avatar);
  }
  wrap.appendChild(bubble);
  attachReactionBar(wrap, msg);

  const typingBubble = document.getElementById('chatPeerTypingBubble');
  if (typingBubble) {
    container.insertBefore(wrap, typingBubble);
  } else {
    container.appendChild(wrap);
  }
  container.scrollTop = container.scrollHeight;
}

let currentFulfillTarget = null;
function handleFulfillFileClick(btn) {
  const msgId = btn.getAttribute('data-msg-id');
  const ts = btn.getAttribute('data-ts');
  currentFulfillTarget = { msgId, ts, btn };
  const fileInput = document.getElementById('chatFulfillFileInput');
  if (fileInput) {
    fileInput.value = '';
    fileInput.click();
  }
}

function handleRejectFileClick(btn) {
  const msgId = btn.getAttribute('data-msg-id');
  const ts = btn.getAttribute('data-ts');
  const peerId = LS.get('current_peer');
  if (!peerId) return;

  const myId = getMyId();
  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const list = LS.get(key, []);
  const targetMsg = list.find(m => (msgId && m.msg_id === msgId) || (ts && m.ts === ts));
  if (targetMsg) {
    if (!targetMsg.file_req) targetMsg.file_req = {};
    targetMsg.file_req.status = 'rejected';
    LS.set(key, list);
  }

  let wrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(msgId)}"]`);
  if (!wrap && ts) wrap = document.querySelector(`.bubble-wrap[data-ts="${CSS.escape(ts)}"]`);
  if (wrap) {
    const bubble = wrap.querySelector('.bubble');
    if (bubble && targetMsg) renderBubbleBody(bubble, targetMsg, false);
  }

  chatSocket?.emit('chat_file_status', {
    to: peerId,
    msg_id: msgId,
    ts: ts,
    status: 'rejected'
  });
}

async function uploadFulfillFile(file) {
  if (!file || !currentFulfillTarget) return;
  const { msgId, ts, btn } = currentFulfillTarget;
  const peerId = LS.get('current_peer');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Uploading…';
  }

  const myId = getMyId();
  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const list = LS.get(key, []);
  const targetMsg = list.find(m => (msgId && m.msg_id === msgId) || (ts && m.ts === ts));
  const reqData = targetMsg?.file_req || {};

  const formData = new FormData();
  formData.append('file', file);
  if (reqData.title) formData.append('title', reqData.title);
  if (reqData.subject) formData.append('subject', reqData.subject);
  if (reqData.subject_id) formData.append('subject_id', reqData.subject_id);
  if (reqData.subject_abbr) formData.append('subject_abbr', reqData.subject_abbr);
  if (reqData.subject_code) formData.append('subject_code', reqData.subject_code);
  if (reqData.college_id) formData.append('college_id', reqData.college_id);
  if (reqData.college_abbr) formData.append('college_abbr', reqData.college_abbr);
  if (reqData.branch_id || reqData.department_id) formData.append('branch_id', reqData.branch_id || reqData.department_id);
  if (reqData.branch_abbr) formData.append('branch_abbr', reqData.branch_abbr);
  if (reqData.program) formData.append('program', reqData.program);
  if (reqData.category) formData.append('category', reqData.category);
  if (reqData.year) formData.append('year', reqData.year);
  if (reqData.semester) formData.append('semester', reqData.semester);
  if (reqData.unit) formData.append('unit', reqData.unit);
  if (reqData.details || reqData.meta_info) formData.append('details', reqData.details || reqData.meta_info);

  try {
    const res = await fetch('/api/chat/upload-file', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      alert(data.error || 'Upload failed');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '✓ Accept & Attach File';
      }
      return;
    }

    if (targetMsg) {
      if (!targetMsg.file_req) targetMsg.file_req = {};
      const bestResourceUrl = data.resource_url || (data.doc_id ? `/resources/${data.doc_id}` : data.file_url);
      targetMsg.file_req.file_url = bestResourceUrl;
      targetMsg.file_req.file_name = data.file_name;
      if (data.title) targetMsg.file_req.title = data.title;
      targetMsg.file_req.doc_id = data.doc_id;
      targetMsg.file_req.resource_url = bestResourceUrl;
      targetMsg.file_req.status = 'fulfilled';
      LS.set(key, list);
    }

    let wrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(msgId)}"]`);
    if (!wrap && ts) wrap = document.querySelector(`.bubble-wrap[data-ts="${CSS.escape(ts)}"]`);
    if (wrap) {
      const bubble = wrap.querySelector('.bubble');
      if (bubble && targetMsg) renderBubbleBody(bubble, targetMsg, false);
    }

    const emitUrl = data.resource_url || (data.doc_id ? `/resources/${data.doc_id}` : data.file_url);
    chatSocket?.emit('chat_file_fulfilled', {
      to: peerId,
      msg_id: msgId,
      ts: ts,
      file_url: emitUrl,
      file_name: data.file_name,
      title: data.title || targetMsg?.file_req?.title,
      file_size: data.file_size,
      doc_id: data.doc_id,
      resource_url: emitUrl
    });

    ChatSound.playReceive();
    popXpEffect(20, 'File Attached XP');
  } catch (err) {
    console.error('[chat] File upload error:', err);
    alert('File upload failed. Please try again.');
    if (btn) {
      btn.disabled = false;
      btn.textContent = '✓ Accept & Attach File';
    }
  }
}

let isSubmittingReq = false;
function submitFileRequest(title, details, metaInfo = '', extra = {}) {
  const peerId = LS.get('current_peer');
  if (!peerId || !title || isSubmittingReq) return;
  isSubmittingReq = true;
  setTimeout(() => { isSubmittingReq = false; }, 1200);

  const msgId = 'c_req_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
  const ts = new Date().toISOString();
  const myId = getMyId();

  const msg = {
    msg_id: msgId,
    from: myId,
    to: peerId,
    msg_type: 'file_request',
    text: `📑 Requested File: ${title}`,
    file_req: {
      title,
      subject: extra.subject || title,
      subject_id: extra.subject_id || '',
      subject_abbr: extra.subject_abbr || '',
      subject_code: extra.subject_code || '',
      college_id: extra.college_id || '',
      college_abbr: extra.college_abbr || '',
      branch_id: extra.branch_id || extra.department_id || '',
      branch_abbr: extra.branch_abbr || '',
      department_id: extra.department_id || extra.branch_id || '',
      program: extra.program || 'b.tech',
      details,
      meta_info: metaInfo,
      category: extra.category || 'Notes',
      year: extra.year || '2025',
      semester: extra.semester || '',
      unit: extra.unit || '',
      status: 'awaiting',
      file_url: 'yet_to_add',
      file_name: ''
    },
    ts,
    status: 'pending',
    sender_meta: { name: window.__CURRENT_USER__?.name || 'A student' }
  };

  ChatSound.playSend();
  appendMessageBubble(msg, true, peerId, 'pending');
  popXpEffect(10, 'Request XP');

  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const list = LS.get(key, []);
  list.push(msg);
  LS.set(key, list);
  updateStudyStreakBadge(peerId, list);

  if (chatSocket?.connected) {
    chatSocket.emit('chat_send', {
      to: peerId,
      text: msg.text,
      ts,
      msg_id: msgId,
      msg_type: 'file_request',
      file_req: msg.file_req,
      sender_meta: msg.sender_meta
    });
  } else {
    httpSendMessage(peerId, msg);
  }
}

async function uploadDirectFile(file) {
  if (!file) return;
  const peerId = LS.get('current_peer');
  if (!peerId) {
    alert('Please open a conversation first.');
    return;
  }
  const myId = getMyId();
  const msgId = 'c_att_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
  const ts = new Date().toISOString();

  const pendingMsg = {
    msg_id: msgId,
    from: myId,
    to: peerId,
    msg_type: 'file_share',
    text: `📎 Shared File: ${file.name}`,
    file_attachment: {
      file_url: '#',
      file_name: file.name,
      file_size: file.size
    },
    ts,
    status: 'pending',
    sender_meta: { name: window.__CURRENT_USER__?.name || 'A student' }
  };

  ChatSound.playSend();
  appendMessageBubble(pendingMsg, true, peerId, 'pending');
  popXpEffect(15, 'Upload XP');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/chat/upload-file', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      alert(data.error || 'Upload failed');
      updateMessageStatus(msgId, 'failed');
      return;
    }

    const bestResourceUrl = data.resource_url || (data.doc_id ? `/resources/${data.doc_id}` : data.file_url);
    pendingMsg.text = `📎 Shared File: ${data.file_name}`;
    pendingMsg.file_attachment.file_url = bestResourceUrl;
    pendingMsg.file_attachment.file_name = data.file_name;
    pendingMsg.file_attachment.doc_id = data.doc_id;
    pendingMsg.file_attachment.resource_url = bestResourceUrl;
    pendingMsg.status = 'sent';

    const key = 'chat_history:' + [peerId, myId].sort().join('_');
    const list = LS.get(key, []);
    list.push(pendingMsg);
    LS.set(key, list);
    updateStudyStreakBadge(peerId, list);

    let wrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(msgId)}"]`);
    if (wrap) {
      const bubble = wrap.querySelector('.bubble');
      if (bubble) renderBubbleBody(bubble, pendingMsg, true);
      updateMessageStatus(msgId, 'sent');
    }

    if (chatSocket?.connected) {
      chatSocket.emit('chat_send', {
        to: peerId,
        text: pendingMsg.text,
        ts,
        msg_id: msgId,
        msg_type: 'file_share',
        file_attachment: pendingMsg.file_attachment,
        sender_meta: pendingMsg.sender_meta
      });
    } else {
      httpSendMessage(peerId, pendingMsg);
    }
  } catch (err) {
    console.error('[chat] Direct upload error:', err);
    alert('File upload failed.');
    updateMessageStatus(msgId, 'failed');
  }
}

function escapeHtml(str) {
  return (str || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch] || ch));
}

function linkifyAbhiHub(html) {
  if (!html) return '';

  const abhihubPattern = /(https?:\/\/(?:www\.)?(?:abhihub\.edu\.eu\.org|app\.abhihub\.run\.place|localhost(?::\d+)?|127\.0\.0\.1(?::\d+)?)[^\s<>"']*|(?:www\.)?abhihub\.edu\.eu\.org[^\s<>"']*|(?<=^|\s)(\/(?:resource|pyq|subject|notes|store-room|leaderboard)[^\s<>"']*))/gi;

  let replaced = html.replace(abhihubPattern, (match) => {
    let cleanHref = match.trim();
    if (cleanHref.startsWith('/')) {
      // relative path
    } else if (!/^https?:\/\//i.test(cleanHref)) {
      cleanHref = 'https://' + cleanHref.replace(/^www\./i, '');
    }

    let urlPath = cleanHref;
    try {
      if (cleanHref.startsWith('/')) {
        urlPath = cleanHref;
      } else {
        const u = new URL(cleanHref);
        urlPath = u.pathname + u.search;
      }
    } catch (_) {}

    let icon = '🚀';
    let title = 'AbhiHub Resource';
    let actionText = 'Open in AbhiHub';

    if (urlPath.includes('/resource/') || urlPath.includes('/resources/')) {
      icon = '📄';
      title = 'Study Material / Document';
      actionText = 'View in AbhiHub Viewer';
    } else if (urlPath.includes('/pyq')) {
      icon = '📑';
      title = 'Exam Papers & PYQs';
      actionText = 'Browse Papers';
    } else if (urlPath.includes('/notes')) {
      icon = '📝';
      title = 'Curated Study Notes';
      actionText = 'Read Notes';
    } else if (urlPath.includes('/subject/')) {
      icon = '📚';
      title = 'Subject Study Hub';
      actionText = 'Explore Subject';
    } else if (urlPath.includes('/leaderboard')) {
      icon = '🏆';
      title = 'Study Leaderboard';
      actionText = 'Check Ranking';
    } else if (urlPath.includes('/store-room')) {
      icon = '📦';
      title = 'Store Room';
      actionText = 'Open Store Room';
    }

    const shortPath = urlPath.length > 30 ? urlPath.slice(0, 28) + '…' : urlPath;

    return `
      <div class="chat-abhihub-card-wrap">
        <a href="${escapeHtml(cleanHref)}" target="_blank" rel="noopener" class="chat-abhihub-card">
          <span class="chat-abhihub-card-icon">${icon}</span>
          <span class="chat-abhihub-card-content">
            <span class="chat-abhihub-card-title">${title}</span>
            <span class="chat-abhihub-card-action">${actionText} • ${escapeHtml(shortPath)}</span>
          </span>
          <span class="chat-abhihub-card-arrow">↗</span>
        </a>
      </div>
    `;
  });

  const externalPattern = /(https?:\/\/[^\s<>"']+)/gi;
  replaced = replaced.replace(externalPattern, (url) => {
    if (url.includes('chat-abhihub-card') || url.includes('<a ')) return url;
    return `<a href="${url}" target="_blank" rel="noopener" class="chat-ext-link">${url}</a>`;
  });

  return replaced;
}

function updateTimerText(timerEl, iso) {
  const sentAt = new Date(iso).getTime();
  const expiresAt = sentAt + (3 * 24 * 60 * 60 * 1000);
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

function updateMessageStatus(idOrTs, status) {
  if (!idOrTs) return;
  let bubbleWrap = document.querySelector(`.bubble-wrap[data-msg-id="${CSS.escape(idOrTs)}"]`);
  if (!bubbleWrap) {
    bubbleWrap = document.querySelector(`.bubble-wrap[data-ts="${CSS.escape(idOrTs)}"]`);
  }
  if (!bubbleWrap) return;
  const bubble = bubbleWrap.querySelector('.bubble');
  const metaDiv = bubble?.querySelector('.bubble.meta');
  if (!metaDiv) return;

  let statusEl = metaDiv.querySelector('.msg-status');
  if (!statusEl) {
    statusEl = document.createElement('span');
    statusEl.className = 'msg-status';
    metaDiv.appendChild(statusEl);
  }

  statusEl.className = 'msg-status ' + status;
  if (status === 'sent') {
    statusEl.textContent = '✓';
    statusEl.style.color = '#94a3b8';
  } else if (status === 'delivered') {
    statusEl.textContent = '✓✓';
    statusEl.style.color = '#64748b';
  } else if (status === 'read') {
    statusEl.textContent = '✓✓';
    statusEl.style.color = '#3b82f6';
  } else if (status === 'pending') {
    statusEl.textContent = '⏱️';
    statusEl.style.color = '#cbd5e1';
  } else if (status === 'failed') {
    statusEl.textContent = '⚠️';
    statusEl.style.color = '#ef4444';
  }
}

function showSendError(errorMsg) {
  const input = document.getElementById('chatInput');
  const statusBar = document.getElementById('chatSendStatus') || (() => {
    const div = document.createElement('div');
    div.id = 'chatSendStatus';
    div.style.cssText = 'color:#ef4444; font-size:0.7rem; margin-top:0.25rem; font-weight:600; display:none;';
    input?.parentElement?.appendChild(div);
    return div;
  })();
  if (statusBar) {
    statusBar.textContent = errorMsg;
    statusBar.style.display = 'block';
    setTimeout(() => { statusBar.style.display = 'none'; }, 3000);
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
  if (!list) return;
  list.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const url = q ? `/api/chat/search-peers?q=${encodeURIComponent(q)}` : `/api/chat/search-peers?q=__suggested__`;
    const data = await fetchJson(url);
    const users = (data.users || []).concat(data.suggested || []);
    const seen = new Set();
    const unique = [];
    for (const u of users) {
      const id = u.id || u.user_id;
      if (!id || seen.has(id)) continue;
      seen.add(id);
      unique.push(u);
      if (u.full_name) {
        LS.set('peer_name_' + id, u.full_name);
      }
    }
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

    if (current) {
      updatePeerHeader(current);
    }
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
  const text = (input?.value || '').trim();
  if (!peerId || !text) return;

  const msgId = 'c_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
  const ts = new Date().toISOString();
  const myId = getMyId();

  const msg = {
    msg_id: msgId,
    from: myId,
    to: peerId,
    text,
    ts,
    status: 'pending',
    sender_meta: { name: window.__CURRENT_USER__?.name || 'A student' }
  };

  // 1. Optimistic instant visual render (0ms latency)
  input.value = '';
  ChatSound.playSend();
  appendMessageBubble(msg, true, peerId, 'pending');
  popXpEffect(10, 'Study XP');

  // 2. Persist to local storage
  const key = 'chat_history:' + [peerId, myId].sort().join('_');
  const list = LS.get(key, []);
  list.push(msg);
  LS.set(key, list);
  updateStudyStreakBadge(peerId, list);

  // 3. Inform peer typing ended
  chatSocket?.emit('chat_typing', { to: peerId, is_typing: false });

  // 4. WebSocket transmission with ACK and HTTP fallback
  if (chatSocket?.connected) {
    let ackReceived = false;
    const ackHandler = (data) => {
      if (data.msg_id === msgId || data.ts === ts) {
        ackReceived = true;
        updateMessageStatus(msgId, 'sent');
      }
    };
    chatSocket.once('chat_message_ack', ackHandler);
    setTimeout(() => {
      chatSocket.off('chat_message_ack', ackHandler);
      if (!ackReceived) {
        httpSendMessage(peerId, msg);
      }
    }, 3500);

    chatSocket.emit('chat_send', {
      to: peerId,
      text,
      ts,
      msg_id: msgId,
      msg_type: msg.msg_type || 'text',
      file_req: msg.file_req || null,
      file_attachment: msg.file_attachment || null,
      sender_meta: msg.sender_meta
    });
  } else {
    await httpSendMessage(peerId, msg);
  }
}

async function httpSendMessage(peerId, msg) {
  try {
    const res = await fetchJson('/api/chat/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        to: peerId,
        text: msg.text,
        ts: msg.ts,
        msg_id: msg.msg_id,
        msg_type: msg.msg_type || 'text',
        file_req: msg.file_req || null,
        file_attachment: msg.file_attachment || null,
        sender_meta: msg.sender_meta
      })
    });
    if (res.success && res.message) {
      updateMessageStatus(msg.msg_id || msg.ts, 'sent');
      return true;
    }
    return false;
  } catch (error) {
    console.error('[chat] HTTP send failed:', error);
    updateMessageStatus(msg.msg_id || msg.ts, 'failed');
    return false;
  }
}

function getAcronym(str) {
  if (!str) return '';
  const stopWords = new Set(['and', 'of', 'the', 'in', 'for', 'to', 'with', 'on', 'at', '&']);
  const words = str.replace(/[^a-zA-Z0-9\s]/g, ' ').split(/\s+/).filter(w => w && !stopWords.has(w.toLowerCase()));
  if (words.length === 1 && words[0].length <= 6) return words[0].toUpperCase();
  if (words.length > 1) {
    const acronym = words.map(w => w[0]).join('').toUpperCase();
    if (acronym.length >= 2) return acronym;
  }
  return str.replace(/[^a-zA-Z0-9]/g, '').slice(0, 6).toUpperCase();
}

let academicTaxonomy = {
  colleges: [],
  departments: [],
  initialized: false,
  isCustomSubject: false
};

async function initChatAcademicTaxonomy() {
  const colSelect = document.getElementById('chatReqCollege');
  const branchSelect = document.getElementById('chatReqBranch');
  const semSelect = document.getElementById('chatReqSem');
  const subjSelect = document.getElementById('chatReqSubject');
  const toggleSubjBtn = document.getElementById('chatToggleCustomSubjectBtn');
  const customSubjWrap = document.getElementById('chatReqCustomSubjectWrap');
  const customSubjName = document.getElementById('chatReqCustomSubjectName');
  const customSubjCode = document.getElementById('chatReqCustomSubjectCode');
  const newColInput = document.getElementById('chatReqNewCollege');
  const newBranchInput = document.getElementById('chatReqNewBranch');
  const typeSelect = document.getElementById('chatReqType');
  const unitSelect = document.getElementById('chatReqUnit');
  const yearSelect = document.getElementById('chatReqYear');
  const titleInput = document.getElementById('chatReqTitle');

  if (!colSelect || !branchSelect) return;

  function updateAutoTitle() {
    if (!titleInput) return;
    const colObj = academicTaxonomy.colleges.find(c => c.id === colSelect?.value);
    const colAbbr = (colObj?.abbreviation || getAcronym(colObj?.name || newColInput?.value || '')).trim().toUpperCase();

    const deptObj = academicTaxonomy.departments.find(d => d.id === branchSelect?.value);
    const deptAbbr = (deptObj?.abbreviation || getAcronym(deptObj?.name || newBranchInput?.value || '')).trim().toUpperCase();

    let sName = '';
    let sCode = '';
    if (academicTaxonomy.isCustomSubject || subjSelect?.value === '__new__') {
      sName = customSubjName?.value.trim() || '';
      sCode = (customSubjCode?.value.trim() || '').toUpperCase();
    } else if (subjSelect?.value) {
      const selOpt = subjSelect.options[subjSelect.selectedIndex];
      sName = selOpt?.dataset.name || '';
      sCode = (selOpt?.dataset.code || '').toUpperCase();
    }

    const subjAbbr = getAcronym(sName);
    const unitVal = unitSelect?.value || 'Full Syllabus';
    const typeVal = (typeSelect?.value || 'Notes').replace(/[^a-zA-Z0-9]/g, '').trim();
    const yearVal = yearSelect?.value || '2025';

    const tags = [colAbbr, deptAbbr, subjAbbr].filter(Boolean);
    let header = tags.join(' - ');
    if (sCode && !header.includes(sCode)) {
      header = header ? `${header} (${sCode})` : sCode;
    }

    const detailParts = [];
    if (unitVal) detailParts.push(unitVal);
    if (typeVal) detailParts.push(typeVal);
    if (yearVal) detailParts.push(yearVal);

    const autoTitle = header ? `${header} - ${detailParts.join(' · ')}` : detailParts.join(' · ');
    titleInput.placeholder = autoTitle;
    if (!titleInput.dataset.userEdited || titleInput.value === titleInput.dataset.lastAuto) {
      titleInput.value = autoTitle;
      titleInput.dataset.lastAuto = autoTitle;
    }
  }

  function renderColleges(selectedId = '') {
    colSelect.innerHTML = '<option value="" disabled selected>Select College / Institution</option>';
    academicTaxonomy.colleges.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.abbreviation ? `${c.name} (${c.abbreviation})` : c.name;
      if (selectedId && c.id === selectedId) opt.selected = true;
      colSelect.appendChild(opt);
    });
    const newOpt = document.createElement('option');
    newOpt.value = '__new__';
    newOpt.textContent = '➕ + Add New College...';
    colSelect.appendChild(newOpt);
  }

  function renderBranches(branchesList, selectedId = '') {
    const list = branchesList || academicTaxonomy.departments || [];
    branchSelect.innerHTML = '<option value="" disabled selected>Select Branch / Department</option>';
    list.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.abbreviation ? `${d.name} (${d.abbreviation})` : d.name;
      if (selectedId && d.id === selectedId) opt.selected = true;
      branchSelect.appendChild(opt);
    });
    const newOpt = document.createElement('option');
    newOpt.value = '__new__';
    newOpt.textContent = '➕ + Add New Branch...';
    branchSelect.appendChild(newOpt);
  }

  async function loadSubjects() {
    const branchId = branchSelect.value;
    const semVal = semSelect?.value || '';
    const semNum = semVal.replace(/\D/g, '');

    if (!branchId || branchId === '__new__') {
      subjSelect.innerHTML = '<option value="" disabled selected>Select branch first</option>';
      const newOpt = document.createElement('option');
      newOpt.value = '__new__';
      newOpt.textContent = '➕ + Add New Subject...';
      subjSelect.appendChild(newOpt);
      updateAutoTitle();
      return;
    }

    subjSelect.innerHTML = '<option value="" disabled selected>Loading subjects…</option>';
    try {
      const url = `/api/subjects?department_id=${encodeURIComponent(branchId)}${semNum ? '&semester=' + semNum : ''}`;
      const res = await fetch(url);
      const data = await res.json();
      const subjects = data.subjects || [];

      subjSelect.innerHTML = '<option value="" disabled selected>Select Subject</option>';
      subjects.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.dataset.name = s.name;
        opt.dataset.code = s.subject_code || '';
        opt.textContent = s.subject_code ? `${s.name} (${s.subject_code})` : s.name;
        subjSelect.appendChild(opt);
      });

      const newOpt = document.createElement('option');
      newOpt.value = '__new__';
      newOpt.textContent = '➕ + Add New Subject...';
      subjSelect.appendChild(newOpt);
    } catch (_) {
      subjSelect.innerHTML = '<option value="" disabled selected>Failed to load subjects</option>';
      const newOpt = document.createElement('option');
      newOpt.value = '__new__';
      newOpt.textContent = '➕ + Add New Subject...';
      subjSelect.appendChild(newOpt);
    }
    updateAutoTitle();
  }

  function toggleCustomSubject(forceCustom = null) {
    academicTaxonomy.isCustomSubject = forceCustom !== null ? forceCustom : !academicTaxonomy.isCustomSubject;
    if (academicTaxonomy.isCustomSubject) {
      if (customSubjWrap) customSubjWrap.style.display = 'block';
      subjSelect.required = false;
      if (customSubjName) {
        customSubjName.required = true;
        customSubjName.focus();
      }
      if (toggleSubjBtn) toggleSubjBtn.textContent = '← Choose Existing Subject';
    } else {
      if (customSubjWrap) customSubjWrap.style.display = 'none';
      subjSelect.required = true;
      if (customSubjName) {
        customSubjName.required = false;
        customSubjName.value = '';
      }
      if (toggleSubjBtn) toggleSubjBtn.textContent = '+ Add New Subject';
    }
    updateAutoTitle();
  }

  if (!academicTaxonomy.initialized) {
    academicTaxonomy.initialized = true;

    titleInput?.addEventListener('input', () => {
      if (titleInput.value !== titleInput.dataset.lastAuto) {
        titleInput.dataset.userEdited = 'true';
      }
    });

    colSelect.addEventListener('change', async () => {
      if (colSelect.value === '__new__') {
        if (newColInput) {
          newColInput.style.display = 'block';
          newColInput.required = true;
          newColInput.focus();
        }
        renderBranches(academicTaxonomy.departments);
      } else {
        if (newColInput) {
          newColInput.style.display = 'none';
          newColInput.required = false;
          newColInput.value = '';
        }
        try {
          const res = await fetch(`/api/departments?college_id=${encodeURIComponent(colSelect.value)}`);
          const data = await res.json();
          if (data.success && data.departments && data.departments.length > 0) {
            renderBranches(data.departments);
          } else {
            renderBranches(academicTaxonomy.departments);
          }
        } catch (_) {
          renderBranches(academicTaxonomy.departments);
        }
      }
      loadSubjects();
      updateAutoTitle();
    });

    newColInput?.addEventListener('input', updateAutoTitle);

    branchSelect.addEventListener('change', () => {
      if (branchSelect.value === '__new__') {
        if (newBranchInput) {
          newBranchInput.style.display = 'block';
          newBranchInput.required = true;
          newBranchInput.focus();
        }
      } else {
        if (newBranchInput) {
          newBranchInput.style.display = 'none';
          newBranchInput.required = false;
          newBranchInput.value = '';
        }
      }
      loadSubjects();
      updateAutoTitle();
    });

    newBranchInput?.addEventListener('input', updateAutoTitle);

    semSelect?.addEventListener('change', () => {
      loadSubjects();
      updateAutoTitle();
    });

    typeSelect?.addEventListener('change', updateAutoTitle);
    unitSelect?.addEventListener('change', updateAutoTitle);
    yearSelect?.addEventListener('change', updateAutoTitle);

    customSubjName?.addEventListener('input', updateAutoTitle);
    customSubjCode?.addEventListener('input', updateAutoTitle);

    toggleSubjBtn?.addEventListener('click', () => toggleCustomSubject());

    subjSelect?.addEventListener('change', () => {
      if (subjSelect.value === '__new__') {
        toggleCustomSubject(true);
      } else {
        updateAutoTitle();
      }
    });

    // Initial fetch of colleges, departments, and user profile
    try {
      const [colRes, deptRes, profRes] = await Promise.all([
        fetch('/api/colleges').then(r => r.json()).catch(() => ({})),
        fetch('/api/departments').then(r => r.json()).catch(() => ({})),
        fetch('/api/profile').then(r => r.json()).catch(() => ({}))
      ]);

      academicTaxonomy.colleges = colRes.colleges || [];
      academicTaxonomy.departments = deptRes.departments || [];

      const userCollegeId = profRes.college_id || '';
      const userBranchId = profRes.department_id || '';

      renderColleges(userCollegeId);
      renderBranches(academicTaxonomy.departments, userBranchId);

      if (userCollegeId && userBranchId) {
        loadSubjects();
      }
    } catch (e) {
      console.warn('[chat] Taxonomy fetch error:', e);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (!document.querySelector('.chat-shell')) return;

  buildEmojiPicker();
  connectChatSocket();

  const preload = getPreloadPeer();
  if (preload) openChat(preload);

  loadPeers();

  // Audio chime toggle
  const soundBtn = document.getElementById('chatSoundToggle');
  if (soundBtn) {
    soundBtn.textContent = ChatSound.enabled ? '🔔' : '🔕';
    soundBtn.addEventListener('click', () => {
      ChatSound.enabled = !ChatSound.enabled;
      soundBtn.textContent = ChatSound.enabled ? '🔔' : '🔕';
      if (ChatSound.enabled) ChatSound.playSend();
    });
  }

  // Live typing indicator listener
  const chatInput = document.getElementById('chatInput');
  chatInput?.addEventListener('input', () => {
    const peerId = LS.get('current_peer');
    if (peerId) handleTypingInput(peerId);
  });

  // Frictionless academic icebreakers
  document.getElementById('chatIcebreakers')?.addEventListener('click', (e) => {
    const chip = e.target.closest('.icebreaker-chip');
    if (!chip) return;
    const text = chip.dataset.text || chip.textContent.trim();
    if (chatInput) {
      chatInput.value = text;
      chatInput.focus();
    }
  });

  document.addEventListener('click', async (e) => {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;
    const action = actionEl.getAttribute('data-action');

    if (action === 'chatReact') {
      const emoji = actionEl.getAttribute('data-emoji') || actionEl.textContent.trim();
      const wrap = actionEl.closest('.bubble-wrap');
      if (!wrap || !emoji) return;
      renderReactionBadge(wrap, emoji);
      ChatSound.playReaction();
      popXpEffect(5, 'Reaction XP');
      const peerId = LS.get('current_peer');
      const msgId = wrap.getAttribute('data-msg-id');
      const msgTs = wrap.getAttribute('data-ts');
      if (peerId) {
        const myId = getMyId();
        const key = 'chat_history:' + [peerId, myId].sort().join('_');
        const list = LS.get(key, []);
        const target = list.find(m => (msgId && m.msg_id === msgId) || (msgTs && m.ts === msgTs));
        if (target) {
          target.reaction = emoji;
          LS.set(key, list);
          updateStudyMomentum(peerId, list);
        }
        chatSocket?.emit('chat_react', { to: peerId, msg_id: msgId, ts: msgTs, emoji });
      }
      return;
    }

    if (action === 'chatBackToPeers') {
      closeChat();
      return;
    }

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
    if (action === 'chatDirectUpload') {
      const input = document.getElementById('chatDirectFileInput');
      if (input) {
        input.value = '';
        input.click();
      }
      return;
    }
    if (action === 'chatOpenRequestModal') {
      const modal = document.getElementById('chatRequestModal');
      if (modal) {
        initChatAcademicTaxonomy();
        if (typeof modal.showModal === 'function') modal.showModal();
        else modal.style.display = 'block';
        document.getElementById('chatReqTitle')?.focus();
      }
      return;
    }
    if (action === 'chatCloseRequestModal') {
      const modal = document.getElementById('chatRequestModal');
      if (modal) {
        if (typeof modal.close === 'function') modal.close();
        else modal.style.display = 'none';
      }
      return;
    }
    if (action === 'chatAcceptFile' || action === 'chatFulfillFile') {
      handleFulfillFileClick(actionEl);
      return;
    }
    if (action === 'chatRejectFile') {
      handleRejectFileClick(actionEl);
      return;
    }
    if (action === 'chatToggleEmoji') {
      const picker = document.getElementById('emojiPicker');
      picker.hidden = !picker.hidden;
      return;
    }
  });

  initChatAcademicTaxonomy();

  document.getElementById('chatRequestForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn?.disabled) return;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = '⏳ Saving…';
    }

    try {
      const colSelect = document.getElementById('chatReqCollege');
      const branchSelect = document.getElementById('chatReqBranch');
      const newColInput = document.getElementById('chatReqNewCollege');
      const newBranchInput = document.getElementById('chatReqNewBranch');
      const semSelect = document.getElementById('chatReqSem');
      const subjSelect = document.getElementById('chatReqSubject');
      const customSubjName = document.getElementById('chatReqCustomSubjectName');
      const customSubjCode = document.getElementById('chatReqCustomSubjectCode');

      let collegeId = colSelect?.value || '';
      let branchId = branchSelect?.value || '';
      let subjectId = '';
      let subjectName = '';

      // 1. If new college entered, add to colleges table
      if (collegeId === '__new__' && newColInput?.value.trim()) {
        try {
          const res = await fetch('/api/colleges', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newColInput.value.trim() })
          });
          const cdata = await res.json();
          if (cdata.success && cdata.college?.id) {
            collegeId = cdata.college.id;
            academicTaxonomy.colleges.push(cdata.college);
          }
        } catch (err) {
          console.error('[chat] Failed to add new college:', err);
        }
      }

      // 2. If new branch entered, add to departments table
      if (branchId === '__new__' && newBranchInput?.value.trim()) {
        try {
          const res = await fetch('/api/departments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: newBranchInput.value.trim(),
              college_id: collegeId && collegeId !== '__new__' ? collegeId : ''
            })
          });
          const ddata = await res.json();
          if (ddata.success && ddata.department?.id) {
            branchId = ddata.department.id;
            academicTaxonomy.departments.push(ddata.department);
          }
        } catch (err) {
          console.error('[chat] Failed to add new branch:', err);
        }
      }

      const semVal = semSelect?.value || 'Semester 5';
      const semNum = parseInt(semVal.replace(/\D/g, '') || '5', 10);
      const isCustomSubj = academicTaxonomy.isCustomSubject || subjSelect?.value === '__new__';

      // 3. If new subject, add to subjects table
      if (isCustomSubj && customSubjName?.value.trim()) {
        const rawName = customSubjName.value.trim();
        const rawCode = customSubjCode?.value.trim() || '';
        try {
          const res = await fetch('/api/subjects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: rawName,
              subject_code: rawCode,
              department_id: branchId && branchId !== '__new__' ? branchId : '',
              semester: semNum
            })
          });
          const sdata = await res.json();
          if (sdata.success && sdata.subject?.id) {
            subjectId = sdata.subject.id;
            subjectName = sdata.subject.name || rawName;
          } else {
            subjectName = rawName;
          }
        } catch (err) {
          console.error('[chat] Failed to add new subject:', err);
          subjectName = rawName;
        }
      } else if (subjSelect?.value && subjSelect.value !== '__new__') {
        subjectId = subjSelect.value;
        subjectName = subjSelect.options[subjSelect.selectedIndex]?.dataset.name || subjSelect.options[subjSelect.selectedIndex]?.textContent.trim();
      }

      // 4. Resolve abbreviations
      const colObj = academicTaxonomy.colleges.find(c => c.id === collegeId);
      const colAbbr = (colObj?.abbreviation || getAcronym(colObj?.name || newColInput?.value || '')).trim().toUpperCase();

      const deptObj = academicTaxonomy.departments.find(d => d.id === branchId);
      const deptAbbr = (deptObj?.abbreviation || getAcronym(deptObj?.name || newBranchInput?.value || '')).trim().toUpperCase();

      let selectedSubjCode = '';
      if (subjSelect?.value && subjSelect.value !== '__new__') {
        const selOpt = subjSelect.options[subjSelect.selectedIndex];
        selectedSubjCode = selOpt?.dataset?.code || '';
      }
      const rawCode = customSubjCode?.value.trim() || selectedSubjCode || '';
      const subjCode = rawCode.toUpperCase();
      const subjAbbr = getAcronym(subjectName);

      const prog = document.getElementById('chatReqProgram')?.value || 'b.tech';
      const type = document.getElementById('chatReqType')?.value || 'Notes 📝';
      const year = document.getElementById('chatReqYear')?.value || '2025';
      const unit = document.getElementById('chatReqUnit')?.value || 'Full Syllabus';
      const title = document.getElementById('chatReqTitle')?.value.trim();
      const details = document.getElementById('chatReqDetails')?.value.trim() || '';

      if (!title && !subjectName) {
        alert('Please select or enter a subject name');
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Send Request';
        }
        return;
      }

      const prefixTags = [colAbbr, deptAbbr, subjAbbr].filter(Boolean);
      let header = prefixTags.join(' - ');
      if (subjCode && !header.includes(subjCode)) {
        header = header ? `${header} (${subjCode})` : subjCode;
      }

      const cleanType = (type || 'Notes').replace(/[^a-zA-Z0-9]/g, '').trim();
      let displayTitle = '';
      if (title && title.startsWith(header)) {
        displayTitle = title;
      } else if (title && title.toLowerCase() !== subjectName.toLowerCase()) {
        displayTitle = header ? `${header} - ${title} - ${unit} ${cleanType} ${year}` : `${title} - ${unit} ${cleanType} ${year}`;
      } else {
        displayTitle = header ? `${header} - ${unit} ${cleanType} ${year}` : `${subjectName} (${type})`;
      }

      const metaParts = [prog.toUpperCase(), semVal, unit, year].filter(Boolean);
      const metaInfo = metaParts.join(' · ');

      submitFileRequest(displayTitle, details, metaInfo, {
        category: type,
        year: year,
        semester: semVal,
        unit: unit,
        subject: subjectName || title,
        subject_id: subjectId,
        subject_abbr: subjAbbr,
        subject_code: subjCode,
        college_id: collegeId && collegeId !== '__new__' ? collegeId : '',
        college_abbr: colAbbr,
        branch_id: branchId && branchId !== '__new__' ? branchId : '',
        branch_abbr: deptAbbr,
        program: prog
      });

      const modal = document.getElementById('chatRequestModal');
      if (modal) {
        if (typeof modal.close === 'function') modal.close();
        else modal.style.display = 'none';
      }

      if (customSubjName) customSubjName.value = '';
      if (customSubjCode) customSubjCode.value = '';
      if (document.getElementById('chatReqTitle')) document.getElementById('chatReqTitle').value = '';
      if (document.getElementById('chatReqDetails')) document.getElementById('chatReqDetails').value = '';
    } catch (err) {
      console.error('[chat] Submit error:', err);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Send Request';
      }
    }
  });

  document.getElementById('chatDirectFileInput')?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (file) uploadDirectFile(file);
  });

  document.getElementById('chatFulfillFileInput')?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (file) uploadFulfillFile(file);
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


/**
 * Tarika AI Assistant - History & Conversation Module
 * Manages conversation list, switching, renaming, deleting, and history panel state.
 */
(function() {
  'use strict';

  window.TarikaState = window.TarikaState || {
    activeDocId: null,
    activeDocTitle: '',
    activeConversationId: localStorage.getItem('ai_active_convo_id') || null,
    chatHistory: [],
    currentExamData: null,
    currentExamIdx: 0,
    examUserAnswers: {},
    examCheckedStatus: {},
    examTimerInterval: null,
    examTimeRemaining: 0,
    sessionLocalDegraded: false,
    isRequestInFlight: false,
    isHistoryOpen: false,
    currentAbortController: null
  };

  window.showAiToast = function(msg, linkHref, linkText = 'Log in') {
    const drawer = document.getElementById('abhiAiDrawer');
    if (!drawer) return;
    const existing = drawer.querySelector('.ai-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'ai-toast';
    toast.innerHTML = `
      <span>${msg}</span>
      ${linkHref ? `<a href="${linkHref}">${linkText}</a>` : ''}
    `;
    drawer.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 4000);
  };

  window.toggleHistoryPanel = function(force) {
    const pnl = document.getElementById('aiHistoryPanel');
    if (!pnl) return;
    const shouldOpen = typeof force === 'boolean' ? force : (pnl.style.display === 'none' || !pnl.style.display);
    window.TarikaState.isHistoryOpen = shouldOpen;
    pnl.style.display = shouldOpen ? 'flex' : 'none';
    if (shouldOpen) {
      window.loadConversationHistory();
      pnl.focus();
    }
  };

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && window.TarikaState.isHistoryOpen) {
      window.toggleHistoryPanel(false);
    }
  });

  window.loadConversationHistory = async function() {
    const listEl = document.getElementById('aiHistoryList');
    if (!listEl) return;
    listEl.innerHTML = '<div style="font-size:12px; color:var(--tarika-muted); padding:16px; text-align:center;">Loading conversation history...</div>';
    try {
      const res = await fetch('/api/ai/conversations?limit=30');
      if (res.status === 401) {
        listEl.innerHTML = `
          <div style="font-size:12px; color:var(--tarika-muted); padding:20px; text-align:center;">
            <div style="font-size:22px; margin-bottom:8px;">🔒</div>
            <div style="font-weight:600; color:var(--tarika-ink); margin-bottom:4px;">Log in to save your chats</div>
            <div style="font-size:11px; margin-bottom:12px;">Saved conversations sync across devices.</div>
            <a href="/login?next=${encodeURIComponent(window.location.pathname)}" style="display:inline-block; background:var(--tarika-brand); color:#fff; padding:6px 14px; border-radius:6px; font-weight:600; text-decoration:none; font-size:11.5px;">Log In</a>
          </div>
        `;
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.success && data.conversations && data.conversations.length > 0) {
        listEl.innerHTML = '';
        data.conversations.forEach(c => {
          const item = document.createElement('div');
          item.className = 'ai-history-item' + (c.id === window.TarikaState.activeConversationId ? ' active' : '');
          const dt = c.last_message_at ? new Date(c.last_message_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '';
          const escapedTitle = (c.title || 'Conversation').replace(/'/g, "\\'");
          item.innerHTML = `
            <div style="flex:1; min-width:0; cursor:pointer;" onclick="openConversation('${c.id}')">
              <div class="ai-history-title" title="${c.title || 'Conversation'}">${c.title || 'Conversation'}</div>
              <div class="ai-history-date">${dt} • ${c.current_context_type || 'chat'}</div>
            </div>
            <div class="ai-history-actions">
              <button type="button" class="ai-history-action-btn" onclick="renameConversation('${c.id}', '${escapedTitle}', event)" title="Rename chat">✏️</button>
              <button type="button" class="ai-history-action-btn del" onclick="deleteConversation('${c.id}', event)" title="Delete chat">🗑️</button>
            </div>
          `;
          listEl.appendChild(item);
        });
      } else {
        listEl.innerHTML = '<div style="font-size:12px; color:var(--tarika-muted); padding:16px; text-align:center;">No saved conversations yet. Start a new chat!</div>';
      }
    } catch (err) {
      listEl.innerHTML = `
        <div style="font-size:12px; color:#ef4444; padding:16px; text-align:center;">
          <div>Failed to load history.</div>
          <button type="button" class="ai-history-retry-btn" onclick="loadConversationHistory()">Retry</button>
        </div>
      `;
    }
  };

  window.renameConversation = async function(convoId, currentTitle, e) {
    if (e) e.stopPropagation();
    const newTitle = prompt('Rename this conversation:', currentTitle || '');
    if (!newTitle || !newTitle.trim() || newTitle.trim() === currentTitle) return;
    try {
      const res = await fetch(`/api/ai/conversations/${convoId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() })
      });
      if (res.ok) {
        window.loadConversationHistory();
      } else {
        window.showAiToast('Failed to rename conversation.');
      }
    } catch (err) {
      window.showAiToast('Error renaming conversation.');
    }
  };

  window.startNewChat = function() {
    if (typeof window.abortCurrentGeneration === 'function') window.abortCurrentGeneration();
    window.TarikaState.activeConversationId = null;
    localStorage.removeItem('ai_active_convo_id');
    window.TarikaState.chatHistory.length = 0;
    window.TarikaState.activeDocId = null;
    window.TarikaState.activeDocTitle = '';
    const ctxBar = document.getElementById('aiContextBar');
    if (ctxBar) ctxBar.style.display = 'none';
    const msgList = document.getElementById('aiMsgList');
    if (msgList) {
      msgList.innerHTML = `
        <div class="ai-bubble assistant">
          👋 Hi! I'm <strong>Tarika</strong>, your personal study assistant for AbhiHub. Started a fresh conversation for you. What would you like to study or find today?
        </div>
      `;
    }
    const pnl = document.getElementById('aiHistoryPanel');
    if (pnl) pnl.style.display = 'none';
    document.getElementById('aiChatInput')?.focus();
  };

  window.openConversation = async function(convoId) {
    if (!convoId) return;
    if (typeof window.abortCurrentGeneration === 'function') window.abortCurrentGeneration();
    window.TarikaState.activeConversationId = convoId;
    localStorage.setItem('ai_active_convo_id', convoId);
    const pnl = document.getElementById('aiHistoryPanel');
    if (pnl) pnl.style.display = 'none';

    const msgList = document.getElementById('aiMsgList');
    if (!msgList) return;
    msgList.innerHTML = '<div class="ai-bubble thinking">Loading conversation...</div>';

    try {
      const res = await fetch(`/api/ai/conversations/${convoId}`);
      const data = await res.json();
      msgList.innerHTML = '';
      window.TarikaState.chatHistory.length = 0;

      if (data.success && data.messages && data.messages.length > 0) {
        data.messages.forEach(m => {
          window.TarikaState.chatHistory.push({ role: m.role, content: m.content });
          const bub = document.createElement('div');
          bub.className = `ai-bubble ${m.role === 'user' ? 'user' : 'assistant'}`;
          if (m.role === 'user') {
            bub.textContent = m.content;
          } else {
            bub.innerHTML = window.formatAiMarkdown ? window.formatAiMarkdown(m.content) : m.content;
            if (window.postProcessAiBubble) window.postProcessAiBubble(bub);
          }
          msgList.appendChild(bub);
        });
        msgList.scrollTop = msgList.scrollHeight;
      } else {
        msgList.innerHTML = '<div class="ai-bubble assistant">👋 Conversation loaded. Ask anything to continue!</div>';
      }
    } catch (err) {
      msgList.innerHTML = '<div class="ai-bubble assistant">⚠️ Could not load conversation messages.</div>';
    }
  };

  window.deleteConversation = async function(convoId, e) {
    if (e) e.stopPropagation();
    if (!confirm('Are you sure you want to delete this conversation?')) return;
    try {
      const res = await fetch(`/api/ai/conversations/${convoId}`, { method: 'DELETE' });
      if (res.ok) {
        if (window.TarikaState.activeConversationId === convoId) {
          window.startNewChat();
        } else {
          window.loadConversationHistory();
        }
      } else {
        window.showAiToast('Failed to delete conversation.');
      }
    } catch (err) {
      window.showAiToast('Error deleting conversation.');
    }
  };

  // Multi-tab session freshness (Task 4.6)
  window.addEventListener('focus', () => {
    if (window.TarikaState && window.TarikaState.isHistoryOpen) {
      window.loadConversationHistory();
    }
  });
})();

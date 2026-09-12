(function () {
  class StoreRoomAI {
    constructor({ apiAskUrl, docIdGetter }) {
      this.apiAskUrl = apiAskUrl;
      this.getDocId = docIdGetter;
      this.isSending = false;
      this.messagesEl = document.getElementById('aiChatMessages');
      this.inputEl = document.getElementById('aiChatInput');
      this.sendBtn = document.getElementById('aiChatSendBtn');
      this.toggleBtn = document.getElementById('aiChatToggleBtn');
      this.panelEl = document.getElementById('aiChatPanel');

      this.init();
    }

    init() {
      if (!this.messagesEl || !this.inputEl || !this.sendBtn) return;

      this.sendBtn.addEventListener('click', () => this.onSend());
      this.inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.onSend();
        }
      });

      this.toggleBtn?.addEventListener('click', () => this.toggle());

      // Seed
      this.renderSystem('Ask about this paper image. Tip: try “What is the topic?” or “Summarize the question”.');
    }

    toggle() {
      if (!this.panelEl) return;
      const isOpen = this.panelEl.getAttribute('data-open') === 'true';
      this.panelEl.setAttribute('data-open', String(!isOpen));
    }

    async onSend() {
      if (this.isSending) return;

      const question = (this.inputEl.value || '').trim();
      if (!question) return;

      this.inputEl.value = '';
      this.appendUser(question);
      this.setSending(true);

      const doc_id = this.getDocId?.();
      if (!doc_id) {
        this.renderSystem('No document id available for AI.');
        this.setSending(false);
        return;
      }

      try {
        const res = await fetch(this.apiAskUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ doc_id, question })
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
          const msg = data.message || 'AI request failed';
          this.renderError(msg);
          return;
        }

        this.appendAssistant(data.answer || '(No answer)');
      } catch (e) {
        this.renderError(e?.message || 'Network error');
      } finally {
        this.setSending(false);
      }
    }

    setSending(v) {
      this.isSending = v;
      if (this.sendBtn) this.sendBtn.disabled = v;
    }

    appendUser(text) {
      this.appendBubble('user', text);
    }

    appendAssistant(text) {
      this.appendBubble('assistant', text);
    }

    renderSystem(text) {
      this.appendBubble('system', text);
    }

    renderError(text) {
      this.appendBubble('error', text);
    }

    appendBubble(kind, text) {
      const wrapper = document.createElement('div');
      wrapper.className = `ai-msg ai-msg-${kind}`;

      const bubble = document.createElement('div');
      bubble.className = 'ai-bubble';
      bubble.textContent = text;

      wrapper.appendChild(bubble);
      this.messagesEl.appendChild(wrapper);
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
  }

  // Expose initializer after DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    // doc id comes from StoreRoomUI state
    const getDocId = () => {
      const sr = window.StoreRoom;
      if (!sr) return null;
      const f = sr.state?.activeFile;
      if (!f) return null;

      // Prefer these common keys
      return (
        f.record_id ||
        f.document_id ||
        f.id ||
        f.storage_id ||
        f.doc_id ||
        null
      );
    };

    new StoreRoomAI({
      apiAskUrl: '/api/ask-paper',
      docIdGetter: getDocId
    });
  });
})();


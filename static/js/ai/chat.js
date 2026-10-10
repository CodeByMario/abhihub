/**
 * Tarika AI Assistant - Core Chat & Model Routing Module
 * Handles message send loop, WebLLM / Cloud routing, streaming, and UI interactions.
 */
(function() {
  'use strict';

  // Task 5.6: Ensure single instance when loaded inside app_shell iframe
  if (window.self !== window.top) {
    const launcher = document.getElementById('abhiAiLauncher');
    const drawer = document.getElementById('abhiAiDrawer');
    if (launcher) launcher.style.display = 'none';
    if (drawer) drawer.style.display = 'none';
    return;
  }

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

  window.abortCurrentGeneration = function() {
    if (window.TarikaState.currentAbortController) {
      try { window.TarikaState.currentAbortController.abort(); } catch (e) {}
      window.TarikaState.currentAbortController = null;
    }
    window.TarikaState.isRequestInFlight = false;
    const sendBtn = document.getElementById('aiSendBtn');
    if (sendBtn) {
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '➔';
      sendBtn.title = 'Send message';
      sendBtn.disabled = false;
    }
    const modelBadge = document.getElementById('aiDrawerModelBadge');
    if (modelBadge && modelBadge.dataset.origText) {
      modelBadge.textContent = modelBadge.dataset.origText;
      delete modelBadge.dataset.origText;
    }
  };

  function getActiveModelDisplayName(modelId) {
    const m = modelId || localStorage.getItem('ai_preferred_model') || '01-ai/yi-large';
    const opt = document.querySelector(`.ai-model-opt[data-model="${m}"]`);
    if (opt) return opt.getAttribute('data-display') || opt.textContent.trim();
    if (m.includes('Llama-3.2-1B')) return 'Llama 3.2 1B (Local)';
    if (m.includes('Qwen2.5-0.5B')) return 'Qwen 0.5B (Local)';
    if (m.includes('Qwen2.5-1.5B')) return 'Qwen 1.5B (Local)';
    if (m.includes('SmolLM2')) return 'SmolLM2 360M (Local)';
    if (m.includes('yi-large')) return 'yi-large';
    if (m.includes('deepseek-r1')) return 'DeepSeek R1';
    if (m.includes('llama-3.3-70b')) return 'Llama 3.3 70B';
    if (m.includes('gemini')) return 'Gemini 2.0 Flash';
    if (m.includes('qwen-2.5-72b')) return 'Qwen 2.5 72B';
    return m.split('/').pop().replace(/:free/i, '');
  }

  // ── Document & Context Detector ────────────────────────────────
  function detectOpenDocument() {
    window.TarikaState.activeDocId = null;
    window.TarikaState.activeDocTitle = '';

    if (window.__CURRENT_DOC__ && window.__CURRENT_DOC__.id) {
      window.TarikaState.activeDocId = window.__CURRENT_DOC__.id;
      window.TarikaState.activeDocTitle = window.__CURRENT_DOC__.title || '';
    } else if (window.VALID_DOC_ID) {
      window.TarikaState.activeDocId = window.VALID_DOC_ID;
    }

    if (!window.TarikaState.activeDocId) {
      const viewerIframe = document.querySelector('iframe[src*="/api/view-doc/"], iframe[src*="viewer.html"]');
      if (viewerIframe && viewerIframe.src) {
        const m = viewerIframe.src.match(/\/api\/view-doc\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
        if (m) window.TarikaState.activeDocId = m[1];
      }
    }

    if (!window.TarikaState.activeDocId) {
      const uuidMatch = window.location.href.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
      if (uuidMatch) {
        window.TarikaState.activeDocId = uuidMatch[0];
      } else {
        const match = window.location.pathname.match(/\/resource\/([^\/\?]+)/);
        if (match) window.TarikaState.activeDocId = match[1].replace('-view', '');
        else {
          const urlParams = new URLSearchParams(window.location.search);
          const rid = urlParams.get('record_id') || urlParams.get('doc_id') || urlParams.get('pdf_name') || urlParams.get('id');
          if (rid) window.TarikaState.activeDocId = rid;
        }
      }
    }

    if (!window.TarikaState.activeDocTitle) {
      const heading = document.querySelector('.resource-title, .reader-title, h1');
      if (heading && heading.textContent.trim()) {
        window.TarikaState.activeDocTitle = heading.textContent.trim();
      } else {
        window.TarikaState.activeDocTitle = document.title.replace('— AbhiHub', '').replace('— AbhiHub Reader', '').trim();
      }
    }

    const ctxBar = document.getElementById('aiContextBar');
    const ctxDocName = document.getElementById('aiContextDocName');
    const isUploadPage = window.location.pathname.includes('/upload') || window.location.pathname.includes('/bulk-upload');
    const isSubjectPage = window.location.pathname.includes('/subject') || window.location.pathname.includes('/branch');

    if (ctxBar && ctxDocName) {
      if (window.TarikaState.activeDocId || (window.TarikaState.activeDocTitle && window.TarikaState.activeDocTitle !== 'AbhiHub')) {
        ctxDocName.textContent = '📄 ' + (window.TarikaState.activeDocTitle.slice(0, 40) || 'Active Document');
        ctxBar.style.display = 'block';
      } else if (isUploadPage) {
        ctxDocName.textContent = '📤 Upload Assistant';
        ctxBar.style.display = 'block';
      } else if (isSubjectPage) {
        const subTitle = document.querySelector('h1')?.textContent?.trim() || 'Subject';
        ctxDocName.textContent = '📚 ' + subTitle.slice(0, 40);
        ctxBar.style.display = 'block';
      } else {
        ctxBar.style.display = 'none';
      }
    }
  }

  window.setTarikaDocContext = function(docId, docTitle) {
    if (docId) window.TarikaState.activeDocId = docId;
    if (docTitle) window.TarikaState.activeDocTitle = docTitle;
    const ctxBar = document.getElementById('aiContextBar');
    const ctxDocName = document.getElementById('aiContextDocName');
    if (ctxBar && ctxDocName) {
      if (window.TarikaState.activeDocId || (window.TarikaState.activeDocTitle && window.TarikaState.activeDocTitle !== 'AbhiHub')) {
        ctxDocName.textContent = '📄 ' + (window.TarikaState.activeDocTitle.slice(0, 40) || 'Active Document');
        ctxBar.style.display = 'block';
      } else {
        ctxBar.style.display = 'none';
      }
    }
  };

  function routeAppUrl(url) {
    if (typeof window.navigateTo === 'function') {
      window.navigateTo(url);
    } else if (window.parent && typeof window.parent.navigateTo === 'function') {
      window.parent.navigateTo(url);
    } else {
      window.location.href = url;
    }
  }

  window.toggleAbhiAiDrawer = function() {
    const drw = document.getElementById('abhiAiDrawer');
    if (!drw) return;
    const isOpen = drw.classList.toggle('open');
    drw.setAttribute('aria-hidden', String(!isOpen));
    if (isOpen) {
      detectOpenDocument();
      window.updateModelBadgeDisplay();
      setTimeout(() => document.getElementById('aiChatInput')?.focus(), 150);
    }
  };

  window.askAiAboutFile = function(promptText) {
    const input = document.getElementById('aiChatInput');
    if (input) input.value = promptText;
    window.sendAiMessage();
  };

  window.quickSend = function(text) {
    const input = document.getElementById('aiChatInput');
    if (input) input.value = text;
    window.sendAiMessage();
  };

  // ── Main Send Message & Streaming Loop ─────────────────────────
  window.sendAiMessage = async function() {
    const input = document.getElementById('aiChatInput');
    const sendBtn = document.getElementById('aiSendBtn');
    const msgList = document.getElementById('aiMsgList');
    if (!input || !sendBtn || !msgList) return;

    // Double-click / Enter guard: if request in flight and clicked again, trigger stop (Task 4.2 & 4.3)
    if (window.TarikaState.isRequestInFlight) {
      window.abortCurrentGeneration();
      return;
    }

    let query = input.value.trim();
    // Task 4.1: Empty or whitespace-only: silent return
    if (!query) return;

    // Task 4.1: Very long message: trim at 4,000 chars and notify user
    if (query.length > 4000) {
      query = query.slice(0, 4000);
      if (window.showAiToast) window.showAiToast('Message trimmed to 4,000 characters.');
    }

    detectOpenDocument();

    const uBubble = document.createElement('div');
    uBubble.className = 'ai-bubble user';
    uBubble.setAttribute('dir', 'auto');
    uBubble.textContent = query;
    msgList.appendChild(uBubble);
    input.value = '';

    const preferredModel = localStorage.getItem('ai_preferred_model') || null;
    const preferredProvider = localStorage.getItem('ai_provider') || null;
    const isLocalWebLlm = (preferredProvider === 'webllm' || (preferredModel && (preferredModel.includes('MLC') || preferredModel.startsWith('webllm'))));
    const activeModelName = getActiveModelDisplayName(preferredModel);

    const thinking = document.createElement('div');
    thinking.className = 'ai-bubble thinking';
    const docNote = window.TarikaState.activeDocId ? ' analyzing document &' : '';
    thinking.innerHTML = `
      <span class="ai-thinking-badge" style="display:inline-flex; align-items:center; gap:5px; font-weight:600; font-style:normal; color:var(--tarika-brand, #2563eb);">
        <span class="ai-thinking-dot" style="display:inline-block; width:7px; height:7px; border-radius:50%; background:currentColor; animation:pulse 1s infinite alternate;"></span>
        <span>${activeModelName}</span>
      </span>
      <span class="ai-typing-indicator" title="Typing..."><span></span><span></span><span></span></span>
      <span style="margin-left:4px;">is${docNote} typing response...</span>
    `;
    msgList.appendChild(thinking);
    msgList.scrollTop = msgList.scrollHeight;

    const modelBadge = document.getElementById('aiDrawerModelBadge');
    if (modelBadge) {
      if (!modelBadge.dataset.origText) modelBadge.dataset.origText = modelBadge.textContent;
      modelBadge.textContent = `${activeModelName} (Typing…)`;
    }

    window.TarikaState.isRequestInFlight = true;
    window.TarikaState.currentAbortController = new AbortController();

    // Toggle Send button to Stop button (Task 4.2 & 4.3)
    sendBtn.classList.add('stop');
    sendBtn.textContent = '⏹';
    sendBtn.title = 'Stop generation';
    sendBtn.disabled = false;

    // Check for direct navigation commands
    const navMatch = query.match(/^(?:go\s+to|open|navigate\s+to|take\s+me\s+to)\s+(upload|search|pyqs?|bookmarks?|saved|profile|settings|notifications|ranking|leaderboard|store\s*room|home)\b/i);
    if (navMatch) {
      const rawDest = navMatch[1].toLowerCase();
      let destination = 'home';
      if (rawDest.includes('upload')) destination = 'upload';
      else if (rawDest.includes('search') || rawDest.includes('pyq')) destination = 'search';
      else if (rawDest.includes('bookmark') || rawDest.includes('saved')) destination = 'bookmarks';
      else if (rawDest.includes('profile')) destination = 'profile';
      else if (rawDest.includes('setting')) destination = 'settings';
      else if (rawDest.includes('notification')) destination = 'notifications';
      else if (rawDest.includes('ranking') || rawDest.includes('leaderboard')) destination = 'ranking';
      else if (rawDest.includes('store')) destination = 'store_room';

      thinking.remove();
      const aBubble = document.createElement('div');
      aBubble.className = 'ai-bubble assistant';
      aBubble.setAttribute('dir', 'auto');
      aBubble.innerHTML = `🚀 <strong>Navigating</strong><br><span style="font-size:12px; color:var(--tarika-muted);">Taking you to /${destination}...</span>`;
      msgList.appendChild(aBubble);
      msgList.scrollTop = msgList.scrollHeight;
      setTimeout(() => { routeAppUrl('/' + destination); }, 800);
      window.abortCurrentGeneration();
      return;
    }

    const historySnapshot = window.TarikaState.chatHistory.slice(-6);
    window.TarikaState.chatHistory.push({ role: 'user', content: query });

    // ── Dedicated On-Device WebLLM Execution & Edge-Case Fallback Handler ──
    async function executeWebLlm(targetModelOverride = null, isFallback = false) {
      if (!document.body.contains(thinking)) msgList.appendChild(thinking);
      const modelLabel = getActiveModelDisplayName(targetModelOverride || preferredModel || 'Llama-3.2-1B-Instruct-q4f16_1-MLC');
      thinking.innerHTML = `
        <span class="ai-thinking-badge" style="display:inline-flex; align-items:center; gap:5px; font-weight:600; font-style:normal; color:#10b981;">
          <span class="ai-thinking-dot" style="display:inline-block; width:7px; height:7px; border-radius:50%; background:currentColor; animation:pulse 1s infinite alternate;"></span>
          <span>${modelLabel}</span>
        </span>
        <span class="ai-typing-indicator" title="Typing..."><span></span><span></span><span></span></span>
        <span style="margin-left:4px;">${isFallback ? '(Fallback) is typing on-device...' : 'is typing on-device...'}</span>
      `;

      let core;
      try {
        core = await import('/static/js/ai/webllm-core.js');
      } catch (importErr) {
        return renderWebLlmFailure({
          title: 'WebLLM Core Module Unavailable',
          detail: 'Could not load the client-side WebLLM engine module from server.',
          actionable: 'Please check your connection or refresh the page.'
        });
      }

      if (!window.__tarikaWebLlmManager) {
        window.__tarikaWebLlmManager = new core.AbhiHubWebLLMManager();
      }
      const mgr = window.__tarikaWebLlmManager;

      // Check device WebGPU support before attempting load
      const gpuCheck = await mgr.checkWebGPU();
      if (!gpuCheck.supported) {
        const diag = await mgr.diagnoseIssue(new Error(gpuCheck.reason));
        return renderWebLlmFailure(diag);
      }

      let targetModel = targetModelOverride || (preferredModel && preferredModel.includes('MLC')
        ? preferredModel.replace('webllm:', '')
        : (preferredModel && preferredModel !== 'auto' ? preferredModel : (mgr.deviceInfo.recommendedModelId || 'Llama-3.2-1B-Instruct-q4f16_1-MLC')));
      if (!targetModel.includes('MLC')) {
        targetModel = mgr.deviceInfo.recommendedModelId || 'Llama-3.2-1B-Instruct-q4f16_1-MLC';
      }

      try {
        await mgr.initEngine(targetModel, (report) => {
          if (window.TarikaState.currentAbortController?.signal?.aborted) throw new DOMException('User aborted', 'AbortError');
          const pct = Math.min(100, Math.max(0, Math.round((report.progress || 0) * 100)));
          const txt = report.text || 'Preparing weights...';
          thinking.innerHTML = `
            <div style="font-size:12px; font-weight:600; margin-bottom:4px;">⚡ ${isFallback ? 'Fallback Model:' : 'Loading local model:'} ${targetModel}</div>
            <div style="font-size:11px; color:var(--tarika-muted);">${txt} ${pct > 0 ? `(${pct}%)` : ''}</div>
            <div class="ai-download-progress"><div class="ai-download-progress-bar" style="width: ${pct}%;"></div></div>
          `;
        });

        thinking.remove();
        const aBubble = document.createElement('div');
        aBubble.className = 'ai-bubble assistant';
        aBubble.setAttribute('dir', 'auto');
        msgList.appendChild(aBubble);

        if (isFallback) {
          window.updateModelBadgeFallback('WebLLM (Fallback)');
          if (window.showAiToast) window.showAiToast('Switched to On-Device WebLLM (Fallback)');
        }

        let fullText = '';
        const docPrompt = window.TarikaState.activeDocTitle ? ` Currently viewing document: "${window.TarikaState.activeDocTitle}".` : '';
        const systemPrompt = `You are Tarika — the personal study assistant for AbhiHub.${docPrompt}\nAnswer clearly and concisely. Format math formulas with LaTeX ($...$).`;

        const msgs = [
          ...historySnapshot.filter(h => h && h.role && h.role !== 'system').map(h => ({ role: h.role, content: h.content })),
          { role: 'user', content: query }
        ];

        await mgr.generateStream(msgs, (delta, currentFull) => {
          if (window.TarikaState.currentAbortController?.signal?.aborted) return;
          fullText = currentFull || (fullText + (delta || ''));
          const formatted = window.formatAiMarkdown ? window.formatAiMarkdown(fullText) : fullText;
          aBubble.innerHTML = formatted + ' <span class="ai-typing-indicator" title="Typing response..."><span></span><span></span><span></span></span>';
          msgList.scrollTop = msgList.scrollHeight;
        }, { systemPrompt });

        aBubble.innerHTML = window.formatAiMarkdown ? window.formatAiMarkdown(fullText) : fullText;

        if (window.TarikaState.currentAbortController?.signal?.aborted) {
          aBubble.innerHTML += ' <span style="font-size:11px; color:var(--tarika-muted);">[Generation stopped]</span>';
        }

        if (window.postProcessAiBubble) window.postProcessAiBubble(aBubble);
        window.TarikaState.chatHistory.push({ role: 'assistant', content: fullText });
        if (window.TarikaState.chatHistory.length > 12) window.TarikaState.chatHistory.splice(0, window.TarikaState.chatHistory.length - 12);
        window.abortCurrentGeneration();
        input.focus();
      } catch (localErr) {
        if (localErr.name === 'AbortError') {
          thinking.remove();
          window.abortCurrentGeneration();
          return;
        }

        // Edge Case: If VRAM or heavy model failed, auto-attempt ultra-lightweight SmolLM2 360M
        if (targetModel !== 'SmolLM2-360M-Instruct-q4f16_1-MLC' && /out of memory|buffer allocation|allocation failed|device lost|vram/i.test(localErr.message || '')) {
          console.warn(`[WebLLM] ${targetModel} exceeded VRAM. Auto-attempting ultra-lightweight SmolLM2-360M fallback...`);
          return executeWebLlm('SmolLM2-360M-Instruct-q4f16_1-MLC', true);
        }

        const diag = await mgr.diagnoseIssue(localErr, targetModel);
        renderWebLlmFailure(diag);
      }
    }

    function renderWebLlmFailure(diag) {
      thinking.remove();
      const errBubble = document.createElement('div');
      errBubble.className = 'ai-bubble assistant';
      errBubble.setAttribute('dir', 'auto');
      errBubble.innerHTML = `
        <div style="background:rgba(239,68,68,0.06); border:1px solid rgba(239,68,68,0.22); border-radius:10px; padding:12px 14px;">
          <div style="font-weight:700; color:#ef4444; font-size:13px; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
            <span>⚠️</span> <span>WebLLM Fallback Diagnostic: ${diag.title || 'Model Issue'}</span>
          </div>
          <div style="font-size:12.5px; color:var(--tarika-text, #1e293b); line-height:1.45; margin-bottom:8px;">
            ${diag.detail || 'The on-device model could not be initialized on this hardware.'}
          </div>
          <div style="font-size:11.5px; color:#475569; background:rgba(255,255,255,0.7); border:1px solid rgba(226,232,240,0.8); border-radius:6px; padding:6px 10px;">
            <strong>Fix / Resolution:</strong> ${diag.actionable || 'Check browser hardware acceleration and try again.'}
          </div>
        </div>
      `;
      msgList.appendChild(errBubble);
      msgList.scrollTop = msgList.scrollHeight;
      window.abortCurrentGeneration();
    }

    // Direct WebLLM execution if user explicitly selected it
    if (isLocalWebLlm && !window.TarikaState.sessionLocalDegraded) {
      return executeWebLlm(null, false);
    }

    // Server execution with automatic fallback to WebLLM
    try {
      const res = await fetch('/api/ai/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: window.TarikaState.currentAbortController.signal,
        body: JSON.stringify({
          message: query,
          conversation_id: window.TarikaState.activeConversationId,
          doc_id: window.TarikaState.activeDocId,
          doc_title: window.TarikaState.activeDocTitle,
          model: preferredModel,
          history: historySnapshot
        })
      });

      if (res.status === 401 || res.redirected) {
        thinking.remove();
        const errBubble = document.createElement('div');
        errBubble.className = 'ai-bubble assistant';
        errBubble.setAttribute('dir', 'auto');
        errBubble.innerHTML = '⚠️ Please <a href="/login" style="color:#60a5fa;">log in</a> to use the assistant.';
        msgList.appendChild(errBubble);
        return;
      }

      let data;
      try {
        data = await res.json();
      } catch (e) {
        data = { success: false, message: `Server error (${res.status})` };
      }

      if (data.success) {
        thinking.remove();
        const aBubble = document.createElement('div');
        aBubble.className = 'ai-bubble assistant';
        aBubble.setAttribute('dir', 'auto');

        if (data.conversation_id) {
          window.TarikaState.activeConversationId = data.conversation_id;
          localStorage.setItem('ai_active_convo_id', window.TarikaState.activeConversationId);
        }

        window.TarikaState.chatHistory.push({ role: 'assistant', content: data.reply || '' });
        if (window.TarikaState.chatHistory.length > 12) window.TarikaState.chatHistory.splice(0, window.TarikaState.chatHistory.length - 12);

        msgList.appendChild(aBubble);
        msgList.scrollTop = msgList.scrollHeight;

        if (window.streamAiResponse) {
          await window.streamAiResponse(aBubble, data.reply || '', () => {
            attachActionsAndAutoOpen(data, aBubble);
          });
        } else {
          aBubble.innerHTML = window.formatAiMarkdown ? window.formatAiMarkdown(data.reply || '') : (data.reply || '');
          if (window.postProcessAiBubble) window.postProcessAiBubble(aBubble);
          attachActionsAndAutoOpen(data, aBubble);
        }
      } else {
        // Server AI provider failed / busy / quota exceeded -> FALLBACK TO WEBLLM!
        console.warn('[AI] Server provider failed, triggering WebLLM fallback:', data.message);
        return executeWebLlm(null, true);
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        thinking.remove();
        const errBubble = document.createElement('div');
        errBubble.className = 'ai-bubble assistant';
        errBubble.setAttribute('dir', 'auto');
        errBubble.innerHTML = '<span style="color:var(--tarika-muted); font-size:12px;">⏹ Generation stopped by user.</span>';
        msgList.appendChild(errBubble);
      } else {
        // Network drop / Server connection failed -> FALLBACK TO WEBLLM!
        console.warn('[AI] Server connection dropped, triggering WebLLM fallback:', err.message);
        return executeWebLlm(null, true);
      }
    } finally {
      window.abortCurrentGeneration();
      input.focus();
    }
  };

  function attachActionsAndAutoOpen(data, aBubble) {
    const msgList = document.getElementById('aiMsgList');
    if (data.actions && data.actions.length > 0) {
      data.actions.forEach(act => {
        const card = document.createElement('div');
        card.className = 'ai-action-card';
        card.innerHTML = `
          <div style="flex:1; min-width:0;">
            <span class="ai-card-badge">${act.category || 'DOC'}</span>
            <div class="ai-card-title" title="${act.title}" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${act.title}</div>
          </div>
          <div style="display:flex; gap:6px; flex-shrink:0;">
            <a href="${act.url}" class="ai-card-btn" target="_self">Open ➔</a>
            <button type="button" class="ai-card-btn tarika-bookmark-btn" data-doc-id="${act.id}" style="background:#334155; color:#f8fafc; border:none; cursor:pointer;">⭐ Save</button>
          </div>
        `;
        aBubble.appendChild(card);
      });

      aBubble.querySelectorAll('.ai-card-btn[href]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const href = btn.getAttribute('href');
          if (href && !href.startsWith('javascript:')) {
            e.preventDefault();
            routeAppUrl(href);
          }
        });
      });

      aBubble.querySelectorAll('.tarika-bookmark-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const docId = btn.getAttribute('data-doc-id');
          if (!docId) return;
          btn.disabled = true;
          btn.textContent = 'Saving...';
          try {
            const bResp = await fetch('/api/ai/tool', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ tool_name: 'bookmark_resource', arguments: { resource_id: docId } })
            });
            if (bResp.status === 401) {
              btn.textContent = '⭐ Save';
              btn.disabled = false;
              if (window.showAiToast) window.showAiToast('Log in to save this document.', `/login?next=${encodeURIComponent(window.location.pathname)}`);
              return;
            }
            const bData = await bResp.json();
            if (bData.success) {
              btn.textContent = 'Saved ✓';
              btn.style.background = '#16a34a';
            } else {
              btn.textContent = 'Failed';
              btn.disabled = false;
            }
          } catch (e) {
            btn.textContent = 'Failed';
            btn.disabled = false;
          }
        });
      });
    }

    if (data.auto_open) {
      const autoNotif = document.createElement('div');
      autoNotif.style.fontSize = '11px';
      autoNotif.style.color = '#34d399';
      autoNotif.style.marginTop = '6px';
      autoNotif.textContent = 'Opening document in 2 seconds...';
      aBubble.appendChild(autoNotif);
      setTimeout(() => { routeAppUrl(data.auto_open); }, 1800);
    }
    if (msgList) msgList.scrollTop = msgList.scrollHeight;
  }

  // ── Unified Event Delegation ───────────────────────────────────
  function initEventDelegation() {
    const drawer = document.getElementById('abhiAiDrawer');
    if (drawer) {
      drawer.addEventListener('click', function(e) {
        const anchor = e.target.closest('a');
        if (anchor) {
          const href = anchor.getAttribute('href');
          if (href && !href.startsWith('javascript:') && !href.startsWith('#')) {
            e.preventDefault();
            routeAppUrl(href);
            return;
          }
        }

        const promptBtn = e.target.closest('[data-action="prompt"]');
        if (promptBtn) {
          const promptText = promptBtn.getAttribute('data-prompt');
          if (promptText) {
            window.askAiAboutFile(promptText);
          }
        }
      });
    }

    const chatInput = document.getElementById('aiChatInput');
    if (chatInput) {
      chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          window.sendAiMessage();
        }
      });
    }

    const modelBadge = document.getElementById('aiDrawerModelBadge');
    const modelMenu = document.getElementById('aiDrawerModelMenu');
    if (modelBadge && modelMenu) {
      modelBadge.addEventListener('click', function(e) {
        e.stopPropagation();
        const isOpen = modelMenu.classList.toggle('show');
        modelBadge.setAttribute('aria-expanded', String(isOpen));
      });
      modelBadge.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const isOpen = modelMenu.classList.toggle('show');
          modelBadge.setAttribute('aria-expanded', String(isOpen));
        }
      });
      document.addEventListener('click', function(e) {
        if (!modelMenu.contains(e.target) && e.target !== modelBadge) {
          modelMenu.classList.remove('show');
          modelBadge.setAttribute('aria-expanded', 'false');
        }
      });
      modelMenu.querySelectorAll('.ai-model-opt').forEach(btn => {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          const mid = this.getAttribute('data-model');
          const p = this.getAttribute('data-provider');
          const d = this.getAttribute('data-display');
          window.switchAiModel(mid, p, d);
        });
      });
    }

    const sendBtn = document.getElementById('aiSendBtn');
    if (sendBtn) {
      sendBtn.addEventListener('click', function() {
        window.sendAiMessage();
      });
    }
  }

  window.updateModelBadgeFallback = function(fallbackText) {
    const badge = document.getElementById('aiDrawerModelBadge');
    if (!badge) return;
    badge.innerHTML = `<span style="color:#f59e0b; font-weight:700;">⚠️ ${fallbackText || 'Cloud Fallback'}</span> <span style="font-size:8px; opacity:0.75;">▼</span>`;
    badge.title = 'Local model degraded — running on Cloud for this session';
  };

  window.updateModelBadgeDisplay = function() {
    const badge = document.getElementById('aiDrawerModelBadge');
    if (!badge) return;
    const prefProvider = localStorage.getItem('ai_provider');
    const prefModel = localStorage.getItem('ai_preferred_model') || '01-ai/yi-large';
    let displayName = 'yi-large';
    if (prefProvider === 'webllm' || (prefModel && prefModel.includes('MLC'))) {
      if (prefModel.includes('1B')) displayName = 'Llama 3.2 1B';
      else if (prefModel.includes('0.5B')) displayName = 'Qwen 0.5B';
      else if (prefModel.includes('1.5B')) displayName = 'Qwen 1.5B';
      else displayName = 'WebLLM Local';
    } else if (prefProvider === 'ollama' || prefModel.includes('llama3.2:latest')) {
      displayName = 'Ollama Local';
    } else if (prefModel) {
      const raw = prefModel.includes('/') ? prefModel.split('/')[1] : prefModel;
      displayName = raw.replace(':free', '');
    }
    badge.innerHTML = `${displayName} <span style="font-size:8px; opacity:0.75;">▼</span>`;

    document.querySelectorAll('.ai-model-opt').forEach(opt => {
      opt.classList.toggle('active', opt.dataset.model === prefModel);
    });
  };

  window.switchAiModel = async function(modelId, provider, displayName) {
    window.abortCurrentGeneration(); // Task 4.5: Cancel old request before switching engines
    window.TarikaState.sessionLocalDegraded = false; // Task 3.7: User manual selection resets degraded state

    // Task 3.3 & 3.4: WebGPU and Storage quota validation
    if (provider === 'webllm' && window.AIRouter) {
      const gpuCheck = await window.AIRouter.checkWebGpuSupport();
      if (!gpuCheck.supported) {
        if (window.showAiToast) window.showAiToast(gpuCheck.reason || 'WebGPU is not supported on this browser/device.');
        return;
      }
      const reqMb = (modelId && modelId.includes('0.5B')) ? 850 : 2500;
      const quotaCheck = await window.AIRouter.checkStorageQuota(reqMb);
      if (!quotaCheck.hasSpace) {
        if (window.showAiToast) window.showAiToast(quotaCheck.message || 'Not enough storage space. Please clear browser storage.');
        return;
      }
    } else if (provider === 'ollama' && window.AIRouter) {
      // Task 3.8: Probe Ollama with CORS / offline distinction
      const oCheck = await window.AIRouter.probeOllama('http://127.0.0.1:11434', modelId);
      if (!oCheck.available) {
        if (window.showAiToast) window.showAiToast(oCheck.message);
      }
    }

    localStorage.setItem('ai_preferred_model', modelId);
    localStorage.setItem('ai_provider', provider);
    localStorage.setItem('abhihub_ai_model', modelId);
    if (provider === 'webllm') {
      window.dispatchEvent(new CustomEvent('abhihub_ai_config_change', { detail: { modelId: modelId } }));
    }
    window.updateModelBadgeDisplay();
    const menu = document.getElementById('aiDrawerModelMenu');
    if (menu) {
      menu.classList.remove('show');
      const badge = document.getElementById('aiDrawerModelBadge');
      if (badge) badge.setAttribute('aria-expanded', 'false');
    }
  };

  async function checkAndApplyWebGpuStatus() {
    if (window.AIRouter && typeof window.AIRouter.checkWebGpuSupport === 'function') {
      const res = await window.AIRouter.checkWebGpuSupport();
      const webLlmBtns = document.querySelectorAll('.ai-model-opt[data-provider="webllm"]');
      if (!res.supported) {
        webLlmBtns.forEach(btn => {
          btn.classList.add('disabled');
          btn.title = res.reason || 'WebGPU unsupported on this device/browser';
        });
        const prefProvider = localStorage.getItem('ai_provider');
        if (prefProvider === 'webllm') {
          localStorage.setItem('ai_provider', 'openrouter');
          localStorage.setItem('ai_preferred_model', '01-ai/yi-large');
          window.updateModelBadgeDisplay();
        }
      }
    }
  }

  // ── Global Error & Rejection Boundary (Task 1.8) ────────────────
  window.addEventListener('error', (event) => {
    const fn = (event.filename || '').toLowerCase();
    const msg = (event.message || '').toLowerCase();
    if (fn.includes('ai') || fn.includes('tarika') || msg.includes('ai') || msg.includes('tarika')) {
      if (window.showAiToast) window.showAiToast('Something went wrong. Try again.');
    }
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = String(event.reason || '').toLowerCase();
    if (reason.includes('ai') || reason.includes('tarika') || reason.includes('fetch')) {
      if (window.showAiToast) window.showAiToast('Something went wrong. Try again.');
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initEventDelegation();
      detectOpenDocument();
      window.updateModelBadgeDisplay();
      checkAndApplyWebGpuStatus();
    });
  } else {
    initEventDelegation();
    detectOpenDocument();
    window.updateModelBadgeDisplay();
    checkAndApplyWebGpuStatus();
  }
})();

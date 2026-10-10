/**
 * ai_router.js — Unified Client-Side AI Engine Router & Fallback Coordinator
 * 
 * Manages the 3 Tarika engines:
 * 1. On-Device WebLLM (Offline, private, WebGPU)
 * 2. Local Ollama (Developer localhost)
 * 3. Server Cloud (Groq, Gemini, OpenRouter)
 * 
 * Routing Policy (Task 3.1):
 * - Attempts the user's selected engine first.
 * - If selected engine fails or is unavailable, falls back to Server Cloud.
 * - Never silently falls back to a paid BYOK provider without user selection.
 * - Updates model badge (#aiDrawerModelBadge) and displays fallback notices (Task 3.2).
 */

(function(global) {
  'use strict';

  // ── Session State & Health Flags ─────────────────────────────────
  let sessionWebGpuUnhealthy = false;
  let activeWebllmEngine = null;
  let downloadAbortController = null;
  let isDownloadPaused = false;

  const AIRouter = {
    // ── 3.3 WebGPU Hardware & Browser Capability Check ─────────────
    async checkWebGpuSupport() {
      if (sessionWebGpuUnhealthy) {
        return { supported: false, reason: 'WebGPU disabled for this session due to a previous memory/device error.' };
      }
      if (!navigator.gpu) {
        return {
          supported: false,
          reason: 'WebGPU is not supported or disabled in your browser. (Supported on Chrome 113+, Edge 113+, Safari 18+).'
        };
      }
      try {
        const adapter = await navigator.gpu.requestAdapter();
        if (!adapter) {
          return { supported: false, reason: 'No compatible GPU adapter found on this device.' };
        }
        return { supported: true, adapter };
      } catch (err) {
        return { supported: false, reason: `WebGPU initialization failed: ${err.message}` };
      }
    },

    // ── 3.4 Storage Quota Check ────────────────────────────────────
    async checkStorageQuota(requiredMb = 850) {
      if (!navigator.storage || !navigator.storage.estimate) {
        return { hasSpace: true, freeMb: null };
      }
      try {
        const est = await navigator.storage.estimate();
        const availableBytes = (est.quota || 0) - (est.usage || 0);
        const freeMb = Math.round(availableBytes / (1024 * 1024));
        const requiredWithMargin = requiredMb + 200; // 200 MB safety margin
        if (freeMb < requiredWithMargin) {
          return {
            hasSpace: false,
            freeMb: freeMb,
            message: `Not enough storage space (${freeMb} MB free, ~${requiredWithMargin} MB needed). Please clear browser storage.`
          };
        }
        return { hasSpace: true, freeMb: freeMb };
      } catch (e) {
        return { hasSpace: true, freeMb: null };
      }
    },

    // ── 3.8 Browser-Side Ollama Connectivity & Diagnosis ───────────
    async probeOllama(host = 'http://127.0.0.1:11434', targetModel = null) {
      const cleanHost = host.replace(/\/+$/, '');
      const ctrl = new AbortController();
      const timeoutId = setTimeout(() => ctrl.abort(), 3500);

      try {
        const res = await fetch(`${cleanHost}/api/tags`, {
          method: 'GET',
          signal: ctrl.signal
        });
        clearTimeout(timeoutId);

        if (!res.ok) {
          return {
            available: false,
            type: 'status_error',
            message: `Ollama returned HTTP error ${res.status}.`
          };
        }

        const data = await res.json();
        const models = (data.models || []).map(m => m.name || m.model);

        if (targetModel && !models.some(m => m.toLowerCase().includes(targetModel.toLowerCase()))) {
          return {
            available: false,
            type: 'model_missing',
            models: models,
            message: `Model "${targetModel}" is not installed in Ollama. Run: \`ollama pull ${targetModel}\``
          };
        }

        return {
          available: true,
          models: models,
          message: `Ollama connected (${models.length} local models found).`
        };
      } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
          return {
            available: false,
            type: 'timeout',
            message: 'Ollama connection timed out. Ensure "ollama serve" is running.'
          };
        }
        if (err.name === 'TypeError' || String(err).includes('Failed to fetch') || String(err).includes('NetworkError')) {
          return {
            available: false,
            type: 'cors_or_offline',
            message: 'Cannot reach Ollama. If running, enable CORS with: \`OLLAMA_ORIGINS="*" ollama serve\`'
          };
        }
        return {
          available: false,
          type: 'unknown',
          message: `Ollama check failed: ${err.message}`
        };
      }
    },

    // ── 3.6 / 3.7 WebLLM Health & Device Recovery ──────────────────
    markWebGpuUnhealthy(reason) {
      sessionWebGpuUnhealthy = true;
      if (activeWebllmEngine && typeof activeWebllmEngine.unload === 'function') {
        try { activeWebllmEngine.unload(); } catch (e) {}
      }
      activeWebllmEngine = null;
      console.warn(`[AIRouter] WebGPU marked unhealthy for this session: ${reason}`);
    },

    attachDeviceLostHandler(device) {
      if (device && device.lost) {
        device.lost.then((info) => {
          console.error('[AIRouter] GPU Device Lost:', info.message);
          this.markWebGpuUnhealthy('GPU device lost: ' + info.message);
          if (global.showAiToast) {
            global.showAiToast('GPU device lost. Switched to server model.');
          }
        });
      }
    },

    // ── Update Model Badge & Fallback Notice (Task 3.2) ────────────
    updateBadge(engineName, isFallback = false) {
      const badge = document.getElementById('aiDrawerModelBadge');
      if (badge) {
        badge.textContent = engineName;
      }
      if (isFallback && global.showAiToast) {
        global.showAiToast(`Switched to Cloud Model (${engineName})`);
      }
    },

    // ── 3.1 Master Execution with Fallback ──────────────────────────
    async executeRequest({ message, docContext, preferredProvider, preferredModel, history, onChunk, onComplete, onError }) {
      const selected = (preferredProvider || localStorage.getItem('ai_provider') || 'openrouter').toLowerCase();

      // Track whether we need to fall back
      let triedLocal = false;

      // 1. Try On-Device WebLLM if selected
      if (selected === 'webllm' && !sessionWebGpuUnhealthy) {
        triedLocal = true;
        const gpuCheck = await this.checkWebGpuSupport();
        if (!gpuCheck.supported) {
          console.warn('[AIRouter] WebGPU not available, falling back to server:', gpuCheck.reason);
          return this._executeServerCloud({ message, docContext, preferredModel: '01-ai/yi-large', history, isFallback: true, onComplete, onError });
        }

        try {
          if (global.TarikaWebLLM && typeof global.TarikaWebLLM.generateStream === 'function') {
            this.updateBadge('WebLLM (Local)', false);
            const res = await global.TarikaWebLLM.generateStream({
              prompt: message,
              docContext: docContext,
              onChunk: onChunk
            });
            if (onComplete) onComplete(res);
            return;
          }
        } catch (webllmErr) {
          console.warn('[AIRouter] WebLLM error, unloading and falling back to Cloud:', webllmErr);
          this.markWebGpuUnhealthy(webllmErr.message || 'Execution failed');
          return this._executeServerCloud({ message, docContext, preferredModel: '01-ai/yi-large', history, isFallback: true, onComplete, onError });
        }
      }

      // 2. Try Local Ollama if selected
      if ((selected === 'ollama' || selected === 'local') && !triedLocal) {
        triedLocal = true;
        const ollamaCheck = await this.probeOllama('http://127.0.0.1:11434', preferredModel);
        if (!ollamaCheck.available) {
          if (global.showAiToast) global.showAiToast(ollamaCheck.message);
          console.warn('[AIRouter] Ollama unavailable, falling back to Cloud:', ollamaCheck.message);
          return this._executeServerCloud({ message, docContext, preferredModel: '01-ai/yi-large', history, isFallback: true, onComplete, onError });
        }
      }

      // 3. Server Cloud Execution
      return this._executeServerCloud({ message, docContext, preferredModel, history, isFallback: false, onComplete, onError });
    },

    // ── Internal Server Cloud Execution with 60s Timeout (Task 3.9) ─
    async _executeServerCloud({ message, docContext, preferredModel, history, isFallback, onChunk, onComplete, onError }) {
      if (isFallback) {
        this.updateBadge('Cloud (Auto)', true);
      }

      const ctrl = new AbortController();
      const timeoutId = setTimeout(() => ctrl.abort(), 60000); // 60s server timeout

      try {
        const resp = await fetch('/api/ai/assistant', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: ctrl.signal,
          body: JSON.stringify({
            message: message,
            doc_id: docContext ? docContext.id : undefined,
            doc_title: docContext ? docContext.title : undefined,
            model: preferredModel,
            history: history || []
          })
        });
        clearTimeout(timeoutId);

        if (!resp.ok) {
          if (resp.status === 429) {
            throw new Error('Provider rate limit reached (429).');
          }
          if (resp.status >= 500) {
            throw new Error('Server AI provider error (500).');
          }
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.message || `Server error (${resp.status})`);
        }

        const data = await resp.json();
        if (onComplete) onComplete(data);
      } catch (err) {
        clearTimeout(timeoutId);
        // Fall back to On-Device WebLLM instead of any free cloud model
        if (!isFallback) {
          console.warn('[AIRouter] Cloud provider failed, falling back to on-device WebLLM:', err.message);
          return this.executeWebLlmFallback({ message, docContext, history, onChunk, onComplete, onError, originalError: err });
        }
        const errMsg = err.name === 'AbortError'
          ? 'Server request timed out after 60 seconds.'
          : (err.message || 'Failed to complete request.');
        if (onError) onError(errMsg);
      }
    },

    // ── Fallback Execution to WebLLM with Issue Diagnosis ────────────
    async executeWebLlmFallback({ message, docContext, history, onChunk, onComplete, onError, originalError }) {
      this.updateBadge('WebLLM (Fallback)', true);
      try {
        const core = await import('/static/js/ai/webllm-core.js');
        const mgr = window.__tarikaWebLlmManager || new core.AbhiHubWebLLMManager();
        window.__tarikaWebLlmManager = mgr;

        // Perform hardware & capability check
        const gpuCheck = await mgr.checkWebGPU();
        if (!gpuCheck.supported) {
          const diag = await mgr.diagnoseIssue(new Error(gpuCheck.reason));
          if (onError) onError(`[WebLLM Fallback Unavailable] ${diag.title}: ${diag.detail} (${diag.actionable})`);
          return;
        }

        const targetModel = mgr.deviceInfo.recommendedModelId || 'Llama-3.2-1B-Instruct-q4f16_1-MLC';
        await mgr.initEngine(targetModel);

        const docPrompt = docContext ? ` Currently viewing document: "${docContext.title || ''}".` : '';
        const systemPrompt = `You are Tarika — study buddy on AbhiHub.${docPrompt} Answer clearly with LaTeX ($...$).`;
        const msgs = [
          ...(history || []).filter(h => h && h.role && h.role !== 'system'),
          { role: 'user', content: message }
        ];

        let full = '';
        await mgr.generateStream(msgs, (delta, currentFull) => {
          full = currentFull || (full + (delta || ''));
          if (onChunk) onChunk(delta, full);
        }, { systemPrompt });

        if (onComplete) onComplete({ success: true, reply: full, provider: 'webllm' });
      } catch (webllmErr) {
        let diagDetail = webllmErr.message || 'Unknown WebLLM error';
        try {
          const core = await import('/static/js/ai/webllm-core.js');
          const mgr = window.__tarikaWebLlmManager || new core.AbhiHubWebLLMManager();
          const diag = await mgr.diagnoseIssue(webllmErr);
          diagDetail = `${diag.title}: ${diag.detail} — Fix: ${diag.actionable}`;
        } catch (_) {}
        if (onError) onError(`[WebLLM Failed] ${diagDetail}`);
      }
    }
  };

  global.AIRouter = AIRouter;
})(typeof window !== 'undefined' ? window : this);

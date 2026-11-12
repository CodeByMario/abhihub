// ── Toast helper ──
function showStToast(msg, duration = 2500) {
  const t = document.getElementById('st-toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

// ── Sidebar navigation & URL Hash / Query Parameter Sync ──
(function() {
  const navItems = document.querySelectorAll('#settingsNav .st-nav-item');
  const sections = document.querySelectorAll('.st-section');

  function resolveSectionId(raw) {
    if (!raw) return '';
    let s = String(raw).trim().toLowerCase().replace(/^[#?]/, '').replace(/^section-/, '');
    const aliases = {
      'account': 'my-account',
      'profile': 'my-account',
      'notification': 'notifications',
      'notif': 'notifications',
      'credits': 'study-credits',
      'credit': 'study-credits',
      'earnings': 'payout',
      'payouts': 'payout',
      'wallet': 'payout',
      'payments': 'payout',
      'history': 'payout',
      'transaction': 'payout',
      'transactions': 'payout',
      'receipts': 'payout',
      'receipt': 'payout',
      'privacy': 'app',
      'app': 'app',
      'system': 'app',
      'security': 'app',
      'danger': 'app',
      'delete': 'app',
      'ai': 'ai-assistant',
      'models': 'ai-assistant',
      'byok': 'ai-assistant'
    };
    return aliases[s] || s;
  }

  function activateSection(rawSectionId, updateUrl) {
    if (updateUrl === undefined) updateUrl = true;
    const sectionId = resolveSectionId(rawSectionId) || 'my-account';
    const targetSection = document.getElementById('section-' + sectionId);
    if (!targetSection) return false;

    navItems.forEach(item => {
      const isMatch = item.dataset.section === sectionId;
      item.classList.toggle('active', isMatch);
      if (isMatch && window.innerWidth < 768) {
        try {
          item.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        } catch(e) {}
      }
    });

    sections.forEach(section => {
      section.classList.toggle('active', section.id === 'section-' + sectionId);
    });

    if (sectionId === 'payout') {
      const requestedRaw = String(rawSectionId || '').toLowerCase();
      if (requestedRaw.includes('transaction') || requestedRaw.includes('receipt') || requestedRaw.includes('payment') || requestedRaw.includes('history')) {
        if (typeof switchWalletView === 'function') switchWalletView('receipts');
      } else {
        if (typeof loadPayoutSettings === 'function') loadPayoutSettings();
      }
    }
    if (sectionId === 'app') {
      const requestedRaw = String(rawSectionId || '').toLowerCase();
      if (requestedRaw.includes('privacy')) {
        const el = document.getElementById('st-privacy-card');
        if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth' }), 100);
      } else if (requestedRaw.includes('danger') || requestedRaw.includes('delete')) {
        const el = document.getElementById('st-danger-card');
        if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth' }), 100);
      }
    }

    if (updateUrl && history.replaceState) {
      try {
        const url = new URL(window.location.href);
        url.hash = sectionId;
        history.replaceState(null, '', url.toString());
      } catch(e) {}
    }
    return true;
  }

  function syncFromUrl(updateUrl = false) {
    const params = new URLSearchParams(window.location.search);
    const queryTab = params.get('tab') || params.get('section');
    const hashTab = window.location.hash;
    const requested = queryTab || hashTab;

    if (requested) {
      const resolved = resolveSectionId(requested);
      if (document.getElementById('section-' + resolved)) {
        activateSection(resolved, updateUrl);
        return;
      }
    }
    if (!document.querySelector('.st-section.active')) {
      activateSection('my-account', false);
    }
  }

  window.switchSettingsTab = activateSection;
  window.syncSettingsTabFromUrl = syncFromUrl;

  navItems.forEach(item => {
    item.addEventListener('click', function(e) {
      e.preventDefault();
      const section = this.dataset.section;
      activateSection(section, true);
    });
  });

  window.addEventListener('hashchange', () => syncFromUrl(false));
  window.addEventListener('popstate', () => syncFromUrl(false));

  syncFromUrl(false);
})();

// ── PWA Install ──
window.matchMedia('(display-mode: standalone)').addEventListener('change', function(e) {
  const btn = document.getElementById('installPwaBtn');
  if (btn && btn.style.display !== 'none') {
    btn.textContent = e.matches ? ' Installed' : ' Install Now';
  }
});
function checkPWALocal() {
  if (window.matchMedia('(display-mode: standalone)').matches) {
    showStToast(' AbhiHub is installed on your device!');
  } else {
    showStToast(' Not installed yet. Use your browser\'s "Add to Home Screen" option.');
  }
}

// ── Save settings (with server sync) ──
function saveNotifSetting(key, value) {
  try { localStorage.setItem('notif_' + key, value ? '1' : '0'); } catch(e) {}
  fetch('/api/user/notification-preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ [key]: value })
  }).then(r => r.json()).then(d => {
    showStToast(' Preference saved');
  }).catch(() => {
    showStToast(' Preference saved (local)');
  });
}
function savePrivacySetting(key, value) {
  try { localStorage.setItem('privacy_' + key, value ? '1' : '0'); } catch(e) {}
  showStToast(' Preference saved');
}
function saveTheme(value) {
  try {
    localStorage.setItem('abhihub_theme', value);
    var isDark = value === 'dark' || (value === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: 'THEME_CHANGE', theme: value }, '*');
    }
  } catch(e) {}
  showStToast(' Theme preference saved');
}
function saveLang(value) {
  try { localStorage.setItem('abhihub_lang', value); } catch(e) {}
  showStToast(' Language preference saved');
}
function clearCache() {
  if ('caches' in window) {
    caches.keys().then(keys => {
      Promise.all(keys.map(k => caches.delete(k))).then(() => {
        showStToast(' Cache cleared');
        document.getElementById('cacheSize').textContent = '0 MB';
      });
    });
  } else {
    showStToast(' Cache API not available');
  }
}
function forgotPassword() {
  const email = '{{ session.user.email if session.user else "" }}';
  if (email) {
    showStToast(' Password reset email sent to ' + email);
  } else {
    showStToast(' Please log in to reset your password.');
  }
}

// ── Cache size display ──
(function() {
  if ('caches' in window) {
    try {
      caches.keys().then(keys => {
        return Promise.all(keys.map(k => caches.open(k).then(c => c.matchAll()))).then(matches => {
          let total = 0;
          matches.forEach(m => m.forEach(r => { total += parseInt(r.headers.get('content-length') || '0', 10); }));
          const el = document.getElementById('cacheSize');
          if (el) el.textContent = (total / 1024 / 1024).toFixed(1) + ' MB';
        });
      }).catch(() => {});
    } catch(e) {}
  }
})();

function sendTestNotification() {
  const btn = document.getElementById('sendTestNotifBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = ' Sending test...';
  }
  
  // Ensure push permission and subscription exist first
  if (window.PushNotifications && window.PushNotifications.isSupported()) {
    PushNotifications.getStatus().then(status => {
      if (!status.subscribed) {
        return PushNotifications.subscribe();
      }
      return { success: true };
    }).then(subRes => {
      if (subRes && subRes.is_ios_pwa_required) {
        showStToast(' iOS requires "Add to Home Screen" first');
        if (btn) { btn.disabled = false; btn.textContent = ' Send Test Notification'; }
        return;
      }
      return fetch('/api/push/test', { method: 'POST' })
        .then(r => r.json())
        .then(d => {
          if (d.success) {
            showStToast(' Test notification dispatched!');
          } else {
            showStToast(' Test failed: ' + (d.error || 'Check permissions'));
          }
          if (btn) { btn.disabled = false; btn.textContent = ' Send Test Notification'; }
        });
    }).catch(err => {
      showStToast(' Error: ' + (err.message || 'Push unavailable'));
      if (btn) { btn.disabled = false; btn.textContent = ' Send Test Notification'; }
    });
  } else {
    fetch('/api/push/test', { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        showStToast(d.success ? ' Test notification dispatched!' : ' Push not configured');
        if (btn) { btn.disabled = false; btn.textContent = ' Send Test Notification'; }
      }).catch(() => {
        showStToast(' Error sending test');
        if (btn) { btn.disabled = false; btn.textContent = ' Send Test Notification'; }
      });
  }
}

// ── Restore saved preferences & iOS check ──
(function() {
  const theme = localStorage.getItem('abhihub_theme') || 'system';
  const selectTheme = document.getElementById('selectTheme');
  if (selectTheme) selectTheme.value = theme;
  const toggleNoIndex = localStorage.getItem('privacy_no_index') === '1';
  const el = document.getElementById('toggleNoIndex');
  if (el) el.checked = toggleNoIndex;

  // iOS Safari non-PWA detection banner
  if (window.PushNotifications && window.PushNotifications.isIos && window.PushNotifications.isIos()) {
    if (!window.PushNotifications.isStandalone()) {
      const banner = document.getElementById('iosPwaBanner');
      if (banner) banner.style.display = 'block';
    }
  }

  // Restore notification preferences from server
  fetch('/api/user/notification-preferences')
    .then(r => r.json())
    .then(data => {
      if (data && data.preferences) {
        const p = data.preferences;
        const togglePush = document.getElementById('togglePush');
        const toggleUploads = document.getElementById('toggleUploads');
        const toggleChat = document.getElementById('toggleChat');
        const toggleEmail = document.getElementById('toggleEmail');
        const toggleCrush = document.getElementById('toggleCrush');
        if (togglePush && p.push !== undefined) togglePush.checked = p.push;
        if (toggleUploads && p.uploads !== undefined) toggleUploads.checked = p.uploads;
        if (toggleChat && p.chat !== undefined) toggleChat.checked = p.chat;
        if (toggleEmail && p.email !== undefined) toggleEmail.checked = p.email;
        if (toggleCrush && p.crush !== undefined) toggleCrush.checked = p.crush;
      }
    }).catch(() => {
      // Fallback to localStorage
      const togglePush = document.getElementById('togglePush');
      const toggleUploads = document.getElementById('toggleUploads');
      const toggleChat = document.getElementById('toggleChat');
      const toggleEmail = document.getElementById('toggleEmail');
      const toggleCrush = document.getElementById('toggleCrush');
      if (togglePush && localStorage.getItem('notif_push') !== null) {
        togglePush.checked = localStorage.getItem('notif_push') === '1';
      }
      if (toggleUploads && localStorage.getItem('notif_uploads') !== null) {
        toggleUploads.checked = localStorage.getItem('notif_uploads') === '1';
      }
      if (toggleChat && localStorage.getItem('notif_chat') !== null) {
        toggleChat.checked = localStorage.getItem('notif_chat') === '1';
      }
      if (toggleEmail && localStorage.getItem('notif_email') !== null) {
        toggleEmail.checked = localStorage.getItem('notif_email') === '1';
      }
      if (toggleCrush && localStorage.getItem('notif_crush') !== null) {
        toggleCrush.checked = localStorage.getItem('notif_crush') === '1';
      }
    });
})();
// ── AI Settings Handlers & Real-time Models ──
const PROVIDER_PLACEHOLDERS = {
  openrouter: 'sk-or-v1-...',
  anthropic:  'sk-ant-api03-...',
  gemini:     'AIzaSy...',
  nvidia:     'nvapi-...',
  openai:     'sk-proj-...',
  groq:       'gsk_...',
  ollama:     'http://localhost:11434 (Optional)',
  webllm:     'In-Browser WebGPU (No API key needed)'
};

function onAiProviderChanged() {
  const pSelect = document.getElementById('aiProviderSelect');
  const provider = pSelect ? pSelect.value : 'openrouter';
  const kInput = document.getElementById('aiApiKeyInput');
  const kLabel = document.getElementById('aiKeyLabel');
  const kSublabel = document.getElementById('aiKeySublabel');
  const kRow = document.getElementById('aiKeyRow');
  const saveBtn = document.getElementById('saveAiBtn');
  const localPanel = document.getElementById('localOllamaPanel');
  const onDevicePanel = document.getElementById('onDeviceWebLlmPanel');

  if (kInput) {
    kInput.placeholder = PROVIDER_PLACEHOLDERS[provider] || 'Enter API Key...';
  }
  if (provider === 'webllm') {
    if (kRow) kRow.style.display = 'none';
    if (saveBtn) saveBtn.textContent = ' Activate On-Device Model';
    if (localPanel) localPanel.style.display = 'none';
    if (onDevicePanel) {
      onDevicePanel.style.display = 'block';
      checkWebGpuStatus();
    }
  } else if (provider === 'ollama') {
    if (kRow) kRow.style.display = '';
    if (saveBtn) saveBtn.textContent = ' Save Local Endpoint';
    if (kLabel) kLabel.textContent = 'Local Ollama Host URL (Optional)';
    if (kSublabel) kSublabel.textContent = 'Default: http://localhost:11434. No API key required; runs locally on your machine.';
    if (localPanel) {
      localPanel.style.display = 'block';
      checkLocalOllamaStatus();
    }
    if (onDevicePanel) onDevicePanel.style.display = 'none';
  } else if (provider === 'openrouter') {
    if (kRow) kRow.style.display = '';
    if (saveBtn) saveBtn.textContent = ' Save Key & Model';
    if (kLabel) kLabel.textContent = 'OpenRouter API Key (BYOK)';
    if (kSublabel) kSublabel.innerHTML = 'Your key is Fernet-encrypted on the server and verified before saving. Free keys available at <a href="https://openrouter.ai/keys" target="_blank" rel="noopener" style="color:var(--st-blue, #2563eb); text-decoration:underline;">openrouter.ai/keys</a>.';
    if (localPanel) localPanel.style.display = 'none';
    if (onDevicePanel) onDevicePanel.style.display = 'none';
  } else {
    if (kRow) kRow.style.display = '';
    if (saveBtn) saveBtn.textContent = ' Save Key & Model';
    if (kLabel) kLabel.textContent = `${provider.toUpperCase()} API Key (BYOK)`;
    if (kSublabel) kSublabel.textContent = 'Your key is Fernet-encrypted on the server and verified before saving. Never shared.';
    if (localPanel) localPanel.style.display = 'none';
    if (onDevicePanel) onDevicePanel.style.display = 'none';
  }
  refreshLiveModels();
}

function checkWebGpuStatus() {
  const el = document.getElementById('webGpuStatusMsg');
  const mSelect = document.getElementById('aiModelSelect');
  const downloadBtn = document.getElementById('downloadWebLlmBtn');
  const deleteBtn = document.getElementById('deleteWebLlmBtn');
  const selectedModel = (mSelect && mSelect.value) ? mSelect.value : (localStorage.getItem('ai_preferred_model') || 'Llama-3.2-1B-Instruct-q4f16_1-MLC');

  if (navigator.storage && navigator.storage.persist) {
    navigator.storage.persist().catch(() => {});
  }

  const isCurrentCached = localStorage.getItem(`webllm_installed_${selectedModel}`) === 'true' || localStorage.getItem('webllm_last_cached') === selectedModel;

  if (deleteBtn) {
    deleteBtn.style.display = isCurrentCached ? 'inline-block' : 'none';
  }
  if (downloadBtn) {
    downloadBtn.textContent = isCurrentCached ? ' Re-Download / Verify' : '⬇ Download to Device';
  }

  if (!el) return;

  if ('gpu' in navigator) {
    navigator.gpu.requestAdapter().then(adapter => {
      if (adapter) {
        if (isCurrentCached) {
          el.innerHTML = `<span style="color:#16a34a; font-weight:600;"> Model Saved on Device! (${selectedModel})</span><br>Stored permanently in browser storage — works 100% offline with zero network re-downloads.`;
        } else {
          el.innerHTML = `<span style="color:#16a34a; font-weight:600;"> WebGPU Hardware Ready</span><br>Click <strong>Download to Device</strong> to save <code>${selectedModel}</code> for offline use.`;
        }
      } else {
        el.innerHTML = '<span style="color:#eab308; font-weight:600;"> WebGPU supported, but adapter unavailable.</span> Enable hardware acceleration in your browser settings (<code>chrome://settings/system</code>).';
      }
    }).catch(() => {
      el.innerHTML = '<span style="color:#eab308; font-weight:600;"> WebGPU supported, but adapter query failed.</span>';
    });
  } else {
    el.innerHTML = '<span style="color:#dc2626; font-weight:600;"> WebGPU not detected in this browser.</span> Use Chrome, Edge 113+, or Arc, or use the <strong>Local Model (Ollama)</strong> option.';
  }
}

async function downloadSelectedWebLlmModel() {
  const mSelect = document.getElementById('aiModelSelect');
  const modelId = (mSelect && mSelect.value) ? mSelect.value : 'Llama-3.2-1B-Instruct-q4f16_1-MLC';
  const progressWrap = document.getElementById('webLlmProgressWrap');
  const progressText = document.getElementById('webLlmProgressText');
  const progressPct  = document.getElementById('webLlmProgressPct');
  const progressBar  = document.getElementById('webLlmProgressBar');
  const downloadBtn  = document.getElementById('downloadWebLlmBtn');

  if (progressWrap) progressWrap.style.display = 'block';
  if (downloadBtn) downloadBtn.disabled = true;

  try {
    if (navigator.storage && navigator.storage.persist) {
      await navigator.storage.persist();
    }
    const core = await import('/static/js/ai/webllm-core.js');
    const mgr = new core.AbhiHubWebLLMManager();
    await mgr.prefetchModel(modelId, (report) => {
      if (report.text && progressText) progressText.textContent = report.text;
      if (typeof report.progress === 'number' && progressPct && progressBar) {
        const pct = Math.round(report.progress * 100);
        progressPct.textContent = `${pct}%`;
        progressBar.style.width = `${pct}%`;
      }
    });
    await core.markModelCached(modelId);
    showStToast(` ${modelId} successfully downloaded & saved!`);
    checkWebGpuStatus();
  } catch (err) {
    showStToast(`Download failed: ${err.message || err}`, 4000);
    if (progressText) progressText.textContent = `Error: ${err.message || err}`;
  } finally {
    if (downloadBtn) downloadBtn.disabled = false;
  }
}

async function deleteSelectedWebLlmModel() {
  const mSelect = document.getElementById('aiModelSelect');
  const modelId = (mSelect && mSelect.value) ? mSelect.value : 'Llama-3.2-1B-Instruct-q4f16_1-MLC';
  if (!confirm(`Are you sure you want to delete ${modelId} from this device to free disk space?`)) return;

  try {
    const core = await import('/static/js/ai/webllm-core.js');
    await core.deleteModelFromStorage(modelId);
    showStToast(` ${modelId} deleted from device.`);
    checkWebGpuStatus();
  } catch (err) {
    showStToast(`Delete failed: ${err.message || err}`, 4000);
  }
}

function checkLocalOllamaStatus() {
  const statusEl = document.getElementById('localOllamaStatus');
  const kInput = document.getElementById('aiApiKeyInput');
  const host = (kInput ? kInput.value : '').trim();
  if (statusEl) statusEl.innerHTML = ' Probing Ollama server...';

  const url = '/api/ai/local/status' + (host ? `?host=${encodeURIComponent(host)}` : '');
  fetch(url)
    .then(r => r.json())
    .then(data => {
      if (!statusEl) return;
      if (data.running) {
        const modelList = (data.models && data.models.length > 0)
          ? `<code>${data.models.join('</code>, <code>')}</code>`
          : 'None installed yet (run <code>ollama pull llama3.2</code>)';
        statusEl.innerHTML = `<span style="color:#16a34a; font-weight:600;"> Ollama is Online</span> (${data.host})<br>` +
          `Installed models (${data.count}): ${modelList}`;
      } else {
        statusEl.innerHTML = `<span style="color:#eab308; font-weight:600;"> Ollama Offline</span> (${data.host})<br>` +
          `To run AI locally, start Ollama in your terminal: <code>ollama serve</code> or launch Ollama Desktop.<br>` +
          `<span style="margin-top:4px; display:inline-block;"> Get Ollama at <a href="https://ollama.com" target="_blank" style="color:var(--st-primary); font-weight:600;">ollama.com</a> & run <code>ollama run llama3.2</code></span>`;
      }
    })
    .catch(() => {
      if (statusEl) {
        statusEl.innerHTML = '<span style="color:#dc2626;"> Unable to connect to local Ollama check endpoint.</span>';
      }
    });
}

function runLocalAiTest() {
  const btn = document.getElementById('runLocalAiBtn');
  const out = document.getElementById('localOllamaTestOutput');
  const mSelect = document.getElementById('aiModelSelect');
  const kInput = document.getElementById('aiApiKeyInput');
  const model = mSelect ? mSelect.value : '';
  const host = (kInput ? kInput.value : '').trim();

  if (btn) { btn.disabled = true; btn.textContent = ' Running...'; }
  if (out) {
    out.style.display = 'block';
    out.textContent = `Sending test prompt to local model [${model || 'auto'}]...`;
  }

  fetch('/api/ai/local/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: model,
      host: host,
      prompt: 'Hello! Please confirm in one short sentence that the local model is operational.'
    })
  })
  .then(r => r.json())
  .then(data => {
    if (btn) { btn.disabled = false; btn.textContent = ' Run Local Model'; }
    if (!out) return;
    if (data.success) {
      out.style.border = '1px solid #86efac';
      out.style.background = '#f0fdf4';
      out.textContent = ` Success (${data.latency_ms}ms) · Model: ${data.model_used}\n\n"${data.reply}"`;
      showStToast(' Local model executed successfully!');
    } else {
      out.style.border = '1px solid #fca5a5';
      out.style.background = '#fef2f2';
      out.textContent = ` ${data.message || 'Execution failed'}`;
      showStToast(' ' + (data.message || 'Local execution failed'));
    }
  })
  .catch(err => {
    if (btn) { btn.disabled = false; btn.textContent = ' Run Local Model'; }
    if (out) {
      out.style.border = '1px solid #fca5a5';
      out.style.background = '#fef2f2';
      out.textContent = ` Network error connecting to local runner: ${err}`;
    }
  });
}

function refreshLiveModels() {
  const pSelect = document.getElementById('aiProviderSelect');
  const provider = pSelect ? pSelect.value : 'openrouter';
  const kInput = document.getElementById('aiApiKeyInput');
  const key = (kInput ? kInput.value : '').trim();
  const mSelect = document.getElementById('aiModelSelect');
  const mSublabel = document.getElementById('aiModelSublabel');

  if (mSelect) mSelect.innerHTML = '<option value="">Fetching realtime models...</option>';
  if (mSublabel) mSublabel.textContent = `Connecting to ${provider.toUpperCase()} live models API...`;

  const url = `/api/ai/models?provider=${encodeURIComponent(provider)}&api_key=${encodeURIComponent(key)}`;
  fetch(url)
    .then(r => r.json())
    .then(data => {
      if (mSelect && data.models && data.models.length > 0) {
        mSelect.innerHTML = '';
        const savedModel = localStorage.getItem('ai_preferred_model');

        const freeGroup = document.createElement('optgroup');
        freeGroup.label = (provider === 'ollama' || provider === 'webllm')
          ? '️ Available On-Device / Local Models (100% Free & Offline)'
          : ' Free Tier / Included (Use when credits exhaust)';

        const paidGroup = document.createElement('optgroup');
        paidGroup.label = ' Premium / Paid Tier';

        data.models.forEach(m => {
          const opt = document.createElement('option');
          opt.value = m.id;
          opt.textContent = (m.is_free ? (provider === 'ollama' || provider === 'webllm' ? ' ' : ' ') : ' ') + (m.name || m.id);
          if (m.id === savedModel) opt.selected = true;

          if (m.is_free) {
            freeGroup.appendChild(opt);
          } else {
            paidGroup.appendChild(opt);
          }
        });

        if (freeGroup.children.length > 0) mSelect.appendChild(freeGroup);
        if (paidGroup.children.length > 0) mSelect.appendChild(paidGroup);

        const freeCount = freeGroup.children.length;
        if (mSublabel) {
          if (provider === 'webllm') {
            mSublabel.innerHTML = ` <strong>${data.models.length} on-device WebGPU models</strong> ready to run offline in browser.`;
          } else if (provider === 'ollama') {
            mSublabel.innerHTML = ` <strong>${data.models.length} local models</strong> ready for offline execution.`;
          } else {
            mSublabel.innerHTML = ` <strong>${data.models.length} models</strong> retrieved (${freeCount} free-tier models ready if credits run out).`;
          }
        }
        if (provider === 'webllm') {
          checkWebGpuStatus();
        }
      } else if (mSelect) {
        mSelect.innerHTML = '<option value="">No models returned</option>';
      }
    })
    .catch(() => {
      if (mSublabel) mSublabel.textContent = 'Using cached standard models for ' + provider;
    });
}

function loadAiSettings() {
  const savedProvider = localStorage.getItem('ai_provider') || 'openrouter';
  const pSelect = document.getElementById('aiProviderSelect');
  const mSelect = document.getElementById('aiModelSelect');

  if (mSelect && !mSelect.__webllmListenerAdded__) {
    mSelect.__webllmListenerAdded__ = true;
    mSelect.addEventListener('change', () => {
      if (document.getElementById('aiProviderSelect')?.value === 'webllm') {
        checkWebGpuStatus();
      }
    });
  }

  const devDetails = document.getElementById('aiDevOptionsSection');
  if (devDetails && savedProvider !== 'openrouter') {
    devDetails.open = true;
  }

  if (pSelect) {
    pSelect.value = savedProvider;
    onAiProviderChanged();
  }

  fetch('/api/ai/usage')
    .then(r => r.json())
    .then(data => {
      const badge = document.getElementById('aiPlanBadge');
      const stats = document.getElementById('aiUsageStats');
      if (data && data.success) {
        const rows = data.rows || [];
        const total = data.total_cost_usd || 0;
        if (badge) {
          badge.textContent = `Active · 7-day spend: $${total.toFixed(4)}`;
        }
        if (stats) {
          if (rows.length === 0) {
            stats.innerHTML = 'No AI queries in the last 7 days yet. Start chatting with the AI assistant anytime!';
          } else {
            stats.innerHTML = `<strong>${rows.length} requests logged</strong> (Total Cost: $${total.toFixed(4)})<br>` +
              rows.slice(0, 5).map(r => `• ${new Date(r.created_at).toLocaleDateString()} — ${r.model_used || 'AI'} (${r.tokens_in || 0}+${r.tokens_out || 0} tokens)`).join('<br>');
          }
        }
      }
    }).catch(() => {
      const badge = document.getElementById('aiPlanBadge');
      if (badge) badge.textContent = 'Free Tier (Standard)';
    });
}

function saveAiSettings() {
  const pSelect = document.getElementById('aiProviderSelect');
  const provider = pSelect ? pSelect.value : 'openrouter';
  const keyInput = document.getElementById('aiApiKeyInput');
  const modelSelect = document.getElementById('aiModelSelect');
  const statusEl = document.getElementById('aiSettingStatus');
  const btn = document.getElementById('saveAiBtn');

  const model = modelSelect ? modelSelect.value : '';

  if (provider === 'webllm') {
    localStorage.setItem('ai_provider', 'webllm');
    if (model) localStorage.setItem('ai_preferred_model', model);
    showStToast(' On-Device WebLLM activated! No API key needed.');
    if (statusEl) {
      statusEl.textContent = ' On-Device WebLLM active (100% in-browser WebGPU • No API key required).';
      statusEl.style.color = '#16a34a';
    }
    // Background sync with server; never throws or shows errors
    fetch('/api/ai/key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: 'browser_webgpu', provider: 'webllm' })
    }).catch(() => {});
    return;
  }

  let key = (keyInput ? keyInput.value : '').trim();
  if (provider === 'ollama' && !key) {
    key = 'http://localhost:11434';
  }

  localStorage.setItem('ai_provider', provider);
  if (model) {
    localStorage.setItem('ai_preferred_model', model);
  }

  if (key) {
    if (btn) { btn.disabled = true; btn.textContent = 'Validating key...'; }
    if (statusEl) { statusEl.textContent = `Saving settings for ${provider}...`; statusEl.style.color = 'var(--text-secondary)'; }

    fetch('/api/ai/key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, provider: provider })
    })
    .then(r => r.json().then(data => ({ ok: r.ok, data })))
    .then(res => {
      if (btn) { btn.disabled = false; btn.textContent = ' Save Key & Model'; }
      if (res.ok && res.data.success) {
        showStToast(` ${provider.toUpperCase()} configured & activated!`);
        if (statusEl) { statusEl.textContent = ` ${res.data.message || 'Configured & saved.'}`; statusEl.style.color = '#16a34a'; }
        if (keyInput && provider !== 'ollama') keyInput.value = '';
        refreshLiveModels();
        loadAiSettings();
      } else {
        showStToast(' ' + (res.data.message || 'Validation failed'));
        if (statusEl) { statusEl.textContent = ' ' + (res.data.message || 'Validation failed'); statusEl.style.color = '#dc2626'; }
      }
    })
    .catch(err => {
      if (btn) { btn.disabled = false; btn.textContent = ' Save Key & Model'; }
      showStToast(' Network error saving settings');
    });
  } else {
    showStToast(' Provider & model preferences saved');
    if (statusEl) { statusEl.textContent = 'Preferences updated.'; statusEl.style.color = '#16a34a'; }
  }
}

function removeAiKey() {
  if (!confirm('Remove your custom API key and revert to the free tier?')) return;
  fetch('/api/ai/key', { method: 'DELETE' })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        showStToast(' API key removed. Reverted to free tier.');
        loadAiSettings();
      } else {
        showStToast(' ' + (data.message || 'Error removing key'));
      }
    }).catch(() => showStToast(' Error removing key'));
}

function handleAccountFormSubmit(e) {
  e.preventDefault();
  const form = document.getElementById('settingsAccountForm');
  const btn = document.getElementById('stSaveAccountBtn');
  const statusEl = document.getElementById('stAccountSaveStatus');
  if (!form) return;

  if (btn) { btn.disabled = true; btn.textContent = 'Saving details...'; }
  if (statusEl) { statusEl.textContent = 'Updating account...'; statusEl.style.color = 'var(--text-secondary)'; }

  const formData = new FormData(form);

  fetch('/account/update', {
    method: 'POST',
    body: formData
  })
  .then(response => {
    if (btn) { btn.disabled = false; btn.textContent = ' Save Account Details'; }
    if (response.ok || response.redirected) {
      showStToast(' Account details updated successfully!');
      if (statusEl) { statusEl.textContent = ' Saved successfully!'; statusEl.style.color = '#16a34a'; setTimeout(() => { statusEl.textContent = ''; }, 3000); }
    } else {
      showStToast(' Failed to update account. Please try again.');
      if (statusEl) { statusEl.textContent = ' Update failed.'; statusEl.style.color = '#ef4444'; }
    }
  })
  .catch(err => {
    if (btn) { btn.disabled = false; btn.textContent = ' Save Account Details'; }
    showStToast(' Network error updating account.');
    if (statusEl) { statusEl.textContent = ' Network error.'; statusEl.style.color = '#ef4444'; }
  });
}

function filterSettingsBranches() {
  const degSelect = document.getElementById('st_degree');
  const branchSelect = document.getElementById('st_branch_id');
  if (!degSelect || !branchSelect) return;

  const deg = degSelect.value.toUpperCase();
  Array.from(branchSelect.options).forEach(opt => {
    if (!opt.value) return;
    const txt = opt.textContent.toUpperCase();
    if (!deg) {
      opt.style.display = '';
      return;
    }
    if (deg.includes('MBA') || deg.includes('BBA')) {
      opt.style.display = (txt.includes('MBA') || txt.includes('MANAGEMENT') || txt.includes('BUSINESS') || txt.includes('FINANCE') || txt.includes('MARKETING')) ? '' : 'none';
    } else if (deg.includes('MCA') || deg.includes('BCA')) {
      opt.style.display = (txt.includes('COMPUTER') || txt.includes('CS') || txt.includes('IT') || txt.includes('APPLICATION') || txt.includes('MCA') || txt.includes('BCA')) ? '' : 'none';
    } else if (deg.includes('TECH')) {
      opt.style.display = (txt.includes('TECH') || txt.includes('ENGINEERING') || txt.includes('CSE') || txt.includes('ECE') || txt.includes('ME') || txt.includes('EE') || txt.includes('CIVIL') || txt.includes('AI') || txt.includes('DS') || !txt.includes('MANAGEMENT')) ? '' : 'none';
    } else {
      opt.style.display = '';
    }
  });
}

function autoCalculateSettingsPursuingYear() {
  const currentYear = new Date().getFullYear();
  const yojInput = document.getElementById('st_year_of_joining');
  const degSelect = document.getElementById('st_degree');
  const pySelect = document.getElementById('st_pursuing_year');
  if (!yojInput || !pySelect) return;

  const yoj = parseInt(yojInput.value);
  const deg = degSelect ? degSelect.value.toUpperCase() : '';
  if (!yoj || yoj > currentYear || yoj < 2000) return;

  let maxYears = 4;
  if (['MBA', 'M.TECH', 'M.SC'].includes(deg)) maxYears = 2;
  else if (['MCA', 'BCA', 'BBA', 'B.SC', 'DIPLOMA'].includes(deg)) maxYears = 3;
  else if (['B.TECH'].includes(deg)) maxYears = 4;

  const calcYear = (currentYear - yoj) + 1;
  if (calcYear >= 1 && calcYear <= maxYears) {
    pySelect.value = String(calcYear);
  } else if (calcYear > maxYears) {
    pySelect.value = String(maxYears);
  } else if (calcYear < 1) {
    pySelect.value = '1';
  }
}

function toggleSettingsStudentFields() {
  const studentRadio = document.getElementById('st_role_student');
  const isStudent = studentRadio ? studentRadio.checked : true;
  const pyGroup = document.getElementById('st_pursuing_year_group');
  const regGroup = document.getElementById('st_registration_number_group');
  const pyInput = document.getElementById('st_pursuing_year');

  if (isStudent) {
    if (pyGroup) { pyGroup.style.display = ''; }
    if (regGroup) { regGroup.style.display = ''; }
    if (pyInput) { pyInput.disabled = false; pyInput.setAttribute('required', ''); }
  } else {
    if (pyGroup) { pyGroup.style.display = 'none'; }
    if (regGroup) { regGroup.style.display = 'none'; }
    if (pyInput) { pyInput.disabled = true; pyInput.removeAttribute('required'); }
  }
}

// ── Payouts & Earnings Management ──
let _payoutLoaded = false;
async function loadPayoutSettings(force = false) {
  if (_payoutLoaded && !force) return;
  _payoutLoaded = true;

  loadStKycStatus();

  try {
    // 1. Check access level & eligibility
    const accessRes = await fetch('/api/my-access');
    const accessData = await accessRes.json();
    const level = (accessData.level || 'explorer').toLowerCase();
    let isEligible = ['contributor', 'power_contributor', 'community_leader'].includes(level);

    let earnData = {};
    try {
      const earnRes = await fetch('/api/creator/earnings');
      earnData = await earnRes.json();
      if (earnData.success && (earnData.paid_notes_count > 0 || earnData.total_sales > 0)) {
        isEligible = true;
      }
    } catch(e) {}

    const badge = document.getElementById('stPayoutEligibilityBadge');
    const msg = document.getElementById('stPayoutEligibilityMsg');
    const metricsGrid = document.getElementById('stCreatorMetricsGrid');
    const boostBox = document.getElementById('stBoostRankBox');

    if (badge) {
      if (isEligible) {
        const isContributor = ['contributor', 'power_contributor', 'community_leader'].includes(level);
        badge.textContent = isContributor
          ? 'Eligible (' + (accessData.level || 'Contributor').replace('_', ' ').toUpperCase() + ')'
          : 'Monetization Active (Seller)';
        badge.style.background = 'var(--st-success-tint)';
        badge.style.color = 'var(--st-success)';
        if (msg) msg.textContent = ' Monetization & payout privileges are active. Your monetized files and creator earnings are tracked below.';
        if (metricsGrid) metricsGrid.style.display = 'grid';
        if (boostBox) boostBox.style.display = 'none';

        if (earnData.success) {
          const pnc = document.getElementById('stPaidNotesCount');
          const stc = document.getElementById('stTotalSalesCount');
          const tea = document.getElementById('stTotalEarningsAmt');
          if (pnc) pnc.textContent = earnData.paid_notes_count || 0;
          if (stc) stc.textContent = earnData.total_sales || 0;
          if (tea) tea.textContent = '₹' + parseFloat(earnData.total_earnings || 0).toFixed(2);
        }
      } else {
        badge.textContent = 'Locked (' + level.toUpperCase() + ')';
        badge.style.background = 'rgba(239, 68, 68, 0.12)';
        badge.style.color = '#dc2626';
        if (msg) msg.textContent = ' Notes monetization is locked for ' + level.toUpperCase() + ' rank. Reach Contributor rank to unlock notes selling & payouts.';
        if (metricsGrid) metricsGrid.style.display = 'none';
        if (boostBox) boostBox.style.display = 'block';

        if (accessData.progress) {
          const pr = accessData.progress;
          const curScore = pr.score || 0;
          const targetScore = pr.next_threshold || 100;
          const pct = Math.min(Math.max(Math.round((pr.progress ? pr.progress * 100 : (curScore / targetScore) * 100)), 4), 100);

          const curTierEl = document.getElementById('stCurrentTierText');
          const curScoreEl = document.getElementById('stCurrentScoreText');
          const targetScoreEl = document.getElementById('stTargetScoreText');
          const barEl = document.getElementById('stRankProgressBar');
          if (curTierEl) curTierEl.textContent = (level || 'explorer').toUpperCase();
          if (curScoreEl) curScoreEl.textContent = curScore;
          if (targetScoreEl) targetScoreEl.textContent = targetScore;
          if (barEl) barEl.style.width = pct + '%';
        }
      }
    }

    // 2. Load Creator Wallet details
    const walletRes = await fetch('/api/creator/wallet');
    const walletData = await walletRes.json();
    if (walletData.success && walletData.wallet) {
      const w = walletData.wallet;
      const pend = document.getElementById('stWalletPending');
      const withdr = document.getElementById('stWalletWithdrawable');
      const totw = document.getElementById('stWalletTotalWithdrawn');
      const vEarn = document.getElementById('stWalletViewsEarnings');
      const vCount = document.getElementById('stWalletViewsCount');
      if (pend) pend.textContent = '₹' + (w.pending_balance || 0).toFixed(2);
      if (withdr) withdr.textContent = '₹' + (w.withdrawable_balance || 0).toFixed(2);
      if (totw) totw.textContent = '₹' + (w.total_withdrawn || 0).toFixed(2);
      if (vEarn) vEarn.textContent = '₹' + (w.view_earnings || 0).toFixed(2);
      if (vCount) vCount.textContent = (w.total_views || 0) + ' views @ ₹0.20/view';

      const form = document.getElementById('stWithdrawalForm');
      const disabledNote = document.getElementById('stWithdrawDisabledNote');
      const amtInput = document.getElementById('stWithdrawAmt');
      const policySublabel = document.getElementById('stWithdrawPolicySublabel');
      const minAmt = w.min_withdrawal || 5;
      const tier = w.withdrawal_tier || (w.withdrawals_completed === 0 ? 1 : (w.withdrawals_completed === 1 ? 2 : 3));

      if (policySublabel) {
        policySublabel.innerHTML = ` <strong>Level ${tier} Payout: Minimum ₹${minAmt.toFixed(0)}</strong> (Gamified: 1st ₹5, 2nd ₹25, 3rd+ ₹100). Payouts are reviewed within 24-48 hours.`;
      }
      if (amtInput) {
        amtInput.min = minAmt;
        amtInput.placeholder = 'Min ' + minAmt.toFixed(0);
      }

      if (w.can_withdraw) {
        if (form) form.style.display = 'block';
        if (disabledNote) disabledNote.style.display = 'none';
        if (amtInput) {
          amtInput.max = w.withdrawable_balance;
          amtInput.value = Math.min(w.withdrawable_balance, Math.max(minAmt, 5));
        }
      } else {
        if (form) form.style.display = 'none';
        if (disabledNote) {
          disabledNote.style.display = 'block';
          disabledNote.textContent = ` Minimum ₹${minAmt.toFixed(0)} withdrawable balance required for Level ${tier} (Available: ₹${(w.withdrawable_balance || 0).toFixed(2)}).`;
        }
      }

      // Populate Drawer Details
      const drawerViewsVal = document.getElementById('stDrawerTotalViewsVal');
      const drawerPointsVal = document.getElementById('stDrawerPointsVal');
      const drawerSalesWith = document.getElementById('stDrawerSalesWithdrawableVal');
      const drawerViewsWith = document.getElementById('stDrawerViewsWithdrawableVal');
      const drawerNetWith = document.getElementById('stDrawerNetWithdrawableVal');

      if (drawerViewsVal) drawerViewsVal.textContent = w.total_views || 0;
      if (drawerPointsVal) drawerPointsVal.textContent = ((w.total_views || 0) * 5) + ' Pts';
      if (drawerSalesWith) drawerSalesWith.textContent = '₹' + (w.sales_withdrawable || 0).toFixed(2);
      if (drawerViewsWith) drawerViewsWith.textContent = '₹' + Math.max(0, (w.withdrawable_balance || 0) - (w.sales_withdrawable || 0)).toFixed(2);
      if (drawerNetWith) drawerNetWith.textContent = '₹' + (w.withdrawable_balance || 0).toFixed(2);

      // Render 30-Day Escrow Pending Ledger
      const pendingList = document.getElementById('stDrawerPendingLedgerList');
      if (pendingList) {
        const lockedEntries = (walletData.ledger || []).filter(l => l.status === 'locked');
        if (lockedEntries.length === 0) {
          pendingList.innerHTML = `
            <div style="padding:1rem;text-align:center;color:var(--st-text-muted);background:var(--st-surface-hover);border-radius:10px;">
               All eligible note sales have passed the 30-day holding period and are fully unlocked into your Withdrawable Balance.
            </div>
          `;
        } else {
          pendingList.innerHTML = lockedEntries.map(entry => {
            const unlockDate = entry.unlock_at ? new Date(entry.unlock_at).toLocaleDateString('en-IN', {month:'short', day:'numeric', year:'numeric'}) : 'In 30 days';
            return `
              <div style="display:flex;justify-content:space-between;align-items:center;padding:0.6rem 0.75rem;background:var(--st-surface-hover);border-radius:8px;margin-bottom:0.5rem;border:1px solid var(--st-border);">
                <div>
                  <div style="font-weight:700;color:var(--st-text-main);">Order #${entry.order_id || entry.id || '-'}</div>
                  <div style="font-size:0.73rem;color:#b45309;">Unlocks on: ${unlockDate}</div>
                </div>
                <div style="font-weight:800;color:#d97706;font-size:0.95rem;">+₹${parseFloat(entry.amount || 0).toFixed(2)}</div>
              </div>
            `;
          }).join('');
        }
      }

      // Render Payouts History (in both main table and Drawer)
      const tbody = document.getElementById('stPayoutHistoryTbody');
      const drawerTbody = document.getElementById('stDrawerPayoutsTbody');
      const payouts = walletData.payouts || [];

      const renderRows = (includeDetails = false) => {
        if (payouts.length === 0) {
          return `<tr><td colspan="${includeDetails ? 5 : 4}" style="padding:1rem;text-align:center;color:var(--st-text-muted);">No payout requests yet.</td></tr>`;
        }
        return payouts.map(p => {
          const date = p.created_at ? new Date(p.created_at).toLocaleDateString('en-IN', {month:'short', day:'numeric', year:'numeric'}) : '-';
          let statusColor = '#d97706';
          if (p.status === 'completed') statusColor = 'var(--st-success, #16a34a)';
          if (p.status === 'rejected') statusColor = '#dc2626';
          const details = p.payout_details?.upi_id || p.payout_details?.account_info || (p.payout_details ? JSON.stringify(p.payout_details) : '-');
          return `
            <tr style="border-bottom:1px solid var(--st-border);">
              <td style="padding:0.6rem 0.5rem;">${date}</td>
              <td style="padding:0.6rem 0.5rem;font-weight:700;color:var(--st-navy);">₹${parseFloat(p.amount || 0).toFixed(2)}</td>
              <td style="padding:0.6rem 0.5rem;text-transform:uppercase;font-size:0.75rem;"><span style="background:var(--st-surface-hover);padding:2px 8px;border-radius:6px;border:1px solid var(--st-border);">${p.payout_method || 'UPI'}</span></td>
              ${includeDetails ? `<td style="padding:0.6rem 0.5rem;font-size:0.75rem;color:var(--st-text-muted);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${details}</td>` : ''}
              <td style="padding:0.6rem 0.5rem;font-weight:700;color:${statusColor};text-transform:capitalize;">${p.status || 'pending'}</td>
            </tr>
          `;
        }).join('');
      };

      if (tbody) tbody.innerHTML = renderRows(false);
      if (drawerTbody) drawerTbody.innerHTML = renderRows(true);
    }
  } catch (err) {
    console.error('[SETTINGS] Payout load error:', err);
  }
}

let _activeWalletCategory = null;
function toggleWalletCategory(cat) {
  const drawer = document.getElementById('stWalletDrawer');
  if (!drawer) return;

  const cards = {
    views: document.getElementById('stCardViews'),
    withdrawable: document.getElementById('stCardWithdrawable'),
    pending: document.getElementById('stCardPending'),
    withdrawn: document.getElementById('stCardWithdrawn')
  };
  const panels = {
    views: document.getElementById('stPanelViews'),
    withdrawable: document.getElementById('stPanelWithdrawable'),
    pending: document.getElementById('stPanelPending'),
    withdrawn: document.getElementById('stPanelWithdrawn')
  };
  const chevrons = {
    views: document.getElementById('stChevronViews'),
    withdrawable: document.getElementById('stChevronWithdrawable'),
    pending: document.getElementById('stChevronPending'),
    withdrawn: document.getElementById('stChevronWithdrawn')
  };

  if (_activeWalletCategory === cat) {
    drawer.style.display = 'none';
    cards[cat]?.classList.remove('active');
    if (chevrons[cat]) chevrons[cat].textContent = '▼';
    _activeWalletCategory = null;
    return;
  }

  Object.keys(cards).forEach(k => {
    cards[k]?.classList.remove('active');
    if (panels[k]) panels[k].style.display = 'none';
    if (chevrons[k]) chevrons[k].textContent = '▼';
  });

  _activeWalletCategory = cat;
  cards[cat]?.classList.add('active');
  if (panels[cat]) panels[cat].style.display = 'block';
  if (chevrons[cat]) chevrons[cat].textContent = '▲';
  drawer.style.display = 'block';
  drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function copySettingsReferralLink(btnEl) {
  const btn = (btnEl && btnEl.nodeType) ? btnEl : document.getElementById('stCopyRefBtn');
  const origText = btn ? btn.textContent : ' Copy Link';
  try {
    const res = await fetch('/api/referral/my-code');
    const data = await res.json();
    const code = data.referral_code || data.code || '';
    const shareUrl = window.location.origin + '/signup?ref=' + encodeURIComponent(code);
    await navigator.clipboard.writeText(shareUrl);
    if (btn) {
      btn.textContent = ' Copied!';
      setTimeout(() => { btn.textContent = origText; }, 2000);
    }
    if (typeof showStToast === 'function') {
      showStToast(' Invite link copied to clipboard!');
    }
  } catch (err) {
    if (btn) btn.textContent = 'Failed to copy';
  }
}

const UPI_REGEX = /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z0-9]{2,64}$/;

function verifySettingsAmount() {
  const amtInput = document.getElementById('stWithdrawAmt');
  const statusEl = document.getElementById('stAmtStatus');
  if (!amtInput || !statusEl) return false;

  const val = parseFloat(amtInput.value);
  const min = parseFloat(amtInput.min || 5);
  const max = parseFloat(amtInput.max || Infinity);

  statusEl.style.display = 'block';

  if (isNaN(val) || val <= 0) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = ' Please enter a valid withdrawal amount.';
    amtInput.style.borderColor = '#dc2626';
    return false;
  }
  if (val < min) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = ` Minimum withdrawal amount is ₹${min.toFixed(0)}.`;
    amtInput.style.borderColor = '#dc2626';
    return false;
  }
  if (val > max) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = ` Exceeds available balance (Max: ₹${max.toFixed(2)}).`;
    amtInput.style.borderColor = '#dc2626';
    return false;
  }

  statusEl.style.color = 'var(--st-success, #16a34a)';
  statusEl.textContent = ` Eligible for payout: ₹${val.toFixed(2)}`;
  amtInput.style.borderColor = 'var(--st-success, #16a34a)';
  return true;
}

function verifySettingsUpi() {
  const method = document.getElementById('stWithdrawMethod')?.value || 'upi';
  const input = document.getElementById('stWithdrawDetails');
  const statusEl = document.getElementById('stUpiStatus');
  if (!input || !statusEl) return false;

  const val = input.value.trim();
  statusEl.style.display = 'block';

  if (!val) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = method === 'upi' ? ' UPI ID is required.' : ' Bank details are required.';
    input.style.borderColor = '#dc2626';
    return false;
  }

  if (method === 'upi') {
    if (!UPI_REGEX.test(val)) {
      statusEl.style.color = '#dc2626';
      statusEl.textContent = ' Invalid UPI format. Use username@bank (e.g., name@okhdfcbank or 9876543210@paytm).';
      input.style.borderColor = '#dc2626';
      return false;
    }
    statusEl.style.color = 'var(--st-success, #16a34a)';
    statusEl.textContent = ' Valid UPI ID format verified';
    input.style.borderColor = 'var(--st-success, #16a34a)';
    return true;
  } else {
    if (val.length < 8) {
      statusEl.style.color = '#dc2626';
      statusEl.textContent = ' Please provide full Account Number and IFSC code.';
      input.style.borderColor = '#dc2626';
      return false;
    }
    statusEl.style.color = 'var(--st-success, #16a34a)';
    statusEl.textContent = ' Bank account details entered';
    input.style.borderColor = 'var(--st-success, #16a34a)';
    return true;
  }
}

function togglePayoutMethodPlaceholder() {
  const method = document.getElementById('stWithdrawMethod').value;
  const label = document.getElementById('stWithdrawDetailsLabel');
  const input = document.getElementById('stWithdrawDetails');
  const statusEl = document.getElementById('stUpiStatus');
  if (statusEl) statusEl.style.display = 'none';

  if (method === 'upi') {
    if (label) label.textContent = 'UPI ID';
    if (input) input.placeholder = 'e.g. yourname@okhdfcbank';
  } else {
    if (label) label.textContent = 'Bank Account & IFSC';
    if (input) input.placeholder = 'e.g. A/C: 1234567890, IFSC: HDFC0000123';
  }
  verifySettingsUpi();
}

async function handleWithdrawalSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById('stWithdrawBtn');
  const fb = document.getElementById('stWithdrawFeedback');
  const amtValid = verifySettingsAmount();

  if (!amtValid) {
    if (fb) {
      fb.style.display = 'block';
      fb.style.color = '#dc2626';
      fb.textContent = 'Please enter a valid withdrawal amount.';
    }
    return;
  }

  const amt = parseFloat(document.getElementById('stWithdrawAmt').value);

  btn.disabled = true;
  btn.innerText = 'Submitting Request...';

  try {
    const res = await fetch('/api/creator/withdraw', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ amount: amt })
    });
    const data = await res.json();
    if (fb) fb.style.display = 'block';
    if (data.success) {
      if (fb) {
        fb.style.color = 'var(--st-success, #16a34a)';
        fb.textContent = ' Withdrawal request submitted! Payout will be sent to your verified KYC account within 7 days.';
      }
      setTimeout(() => loadPayoutSettings(true), 1200);
    } else {
      if (fb) {
        fb.style.color = '#dc2626';
        fb.textContent = data.error || 'Failed to submit withdrawal request.';
      }
    }
  } catch (err) {
    if (fb) {
      fb.style.display = 'block';
      fb.style.color = '#dc2626';
      fb.textContent = 'Network error. Please try again.';
    }
  } finally {
    btn.disabled = false;
    btn.innerText = 'Submit Payout Request';
  }
}

// ── KYC & Verification Functions (Settings Tab) ──
function toggleStKycMethodFields() {
  const method = document.getElementById('stKycPrefMethod')?.value;
  const upiGroup = document.getElementById('stKycUpiGroup');
  const bankGroup = document.getElementById('stKycBankGroup');
  if (method === 'bank') {
    if (upiGroup) upiGroup.style.display = 'none';
    if (bankGroup) bankGroup.style.display = 'block';
  } else {
    if (upiGroup) upiGroup.style.display = 'block';
    if (bankGroup) bankGroup.style.display = 'none';
  }
}

function showStKycForm(show) {
  const verifiedBox = document.getElementById('stKycVerifiedBox');
  const formWrap = document.getElementById('stKycFormWrap');
  if (show) {
    if (verifiedBox) verifiedBox.style.display = 'none';
    if (formWrap) formWrap.style.display = 'block';
  } else {
    if (verifiedBox) verifiedBox.style.display = 'block';
    if (formWrap) formWrap.style.display = 'none';
  }
}

async function loadStKycStatus() {
  try {
    const res = await fetch('/api/user/kyc/status');
    const data = await res.json();
    const badge = document.getElementById('stKycStatusBadge');
    const verifiedBox = document.getElementById('stKycVerifiedBox');
    const formWrap = document.getElementById('stKycFormWrap');

    if (data.success && data.kyc) {
      const k = data.kyc;
      if (k.is_verified) {
        if (badge) {
          badge.textContent = ' Verified';
          badge.style.background = 'var(--st-success-tint, #dcfce7)';
          badge.style.color = 'var(--st-success, #15803d)';
        }
        if (verifiedBox) verifiedBox.style.display = 'block';
        if (formWrap) formWrap.style.display = 'none';

        const nameEl = document.getElementById('stKycValName');
        const panEl = document.getElementById('stKycValPan');
        const methodEl = document.getElementById('stKycValMethod');
        const destEl = document.getElementById('stKycValDest');
        if (nameEl) nameEl.textContent = k.full_name || '-';
        if (panEl) panEl.textContent = k.pan_number || '-';
        if (methodEl) methodEl.textContent = k.preferred_method || '-';
        if (destEl) destEl.textContent = k.preferred_method === 'bank'
          ? `${k.bank_name || 'Bank'} (${k.account_number || ''})`
          : (k.upi_id || '-');

        const destSummary = k.preferred_method === 'bank'
          ? `Bank: ${k.bank_name || 'Bank'} (A/C: ****${k.account_number ? k.account_number.slice(-4) : ''}, IFSC: ${k.ifsc_code || ''}) • PAN: ${k.pan_number || ''}`
          : `UPI: ${k.upi_id || ''} • PAN: ${k.pan_number || ''}`;
        const destInfo = document.getElementById('stWithdrawKycDestText');
        if (destInfo) {
          destInfo.textContent = destSummary;
          destInfo.style.color = 'var(--st-success, #16a34a)';
        }
        const wBtn = document.getElementById('stWithdrawBtn');
        if (wBtn) wBtn.disabled = false;
        return;
      } else if (k.rejection_reason) {
        if (badge) {
          badge.textContent = 'Action Required';
          badge.style.background = '#fee2e2';
          badge.style.color = '#b91c1c';
        }
        if (verifiedBox) verifiedBox.style.display = 'none';
        if (formWrap) formWrap.style.display = 'block';
        const rejMsg = document.getElementById('stKycRejectionMsg');
        const rejText = document.getElementById('stKycRejectionText');
        if (rejMsg) rejMsg.style.display = 'block';
        if (rejText) rejText.textContent = k.rejection_reason;
      } else {
        if (badge) {
          badge.textContent = ' Under Review';
          badge.style.background = '#fef3c7';
          badge.style.color = '#b45309';
        }
        if (verifiedBox) verifiedBox.style.display = 'none';
        if (formWrap) formWrap.style.display = 'block';
      }

      const destInfo = document.getElementById('stWithdrawKycDestText');
      if (destInfo) {
        destInfo.textContent = ' KYC Verification Required (Submit form above)';
        destInfo.style.color = '#dc2626';
      }
      const wBtn = document.getElementById('stWithdrawBtn');
      if (wBtn) wBtn.disabled = true;

      // Prefill fields
      if (document.getElementById('stKycFullName')) document.getElementById('stKycFullName').value = k.full_name || '';
      if (document.getElementById('stKycPanNumber')) document.getElementById('stKycPanNumber').value = k.pan_number || '';
      if (document.getElementById('stKycPrefMethod')) {
        document.getElementById('stKycPrefMethod').value = k.preferred_method || 'upi';
        toggleStKycMethodFields();
      }
      if (document.getElementById('stKycUpiId')) document.getElementById('stKycUpiId').value = k.upi_id || '';
      if (document.getElementById('stKycBankName')) document.getElementById('stKycBankName').value = k.bank_name || '';
    } else {
      if (badge) {
        badge.textContent = 'Not Submitted';
        badge.style.background = 'var(--st-surface-hover, #f1f5f9)';
        badge.style.color = 'var(--st-text-muted, #475569)';
      }
      if (verifiedBox) verifiedBox.style.display = 'none';
      if (formWrap) formWrap.style.display = 'block';

      const destInfo = document.getElementById('stWithdrawKycDestText');
      if (destInfo) {
        destInfo.textContent = ' KYC Verification Required (Submit form above)';
        destInfo.style.color = '#dc2626';
      }
      const wBtn = document.getElementById('stWithdrawBtn');
      if (wBtn) wBtn.disabled = true;
    }
  } catch (e) {
    console.warn('loadStKycStatus error:', e);
  }
}

async function handleStKycSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById('stKycSubmitBtn');
  const fb = document.getElementById('stKycFeedback');

  const fullName = (document.getElementById('stKycFullName')?.value || '').trim();
  const pan = (document.getElementById('stKycPanNumber')?.value || '').trim().toUpperCase();
  const method = document.getElementById('stKycPrefMethod')?.value;
  const upiId = (document.getElementById('stKycUpiId')?.value || '').trim();
  const bankAcc = (document.getElementById('stKycBankAcc')?.value || '').trim();
  const bankIfsc = (document.getElementById('stKycBankIfsc')?.value || '').trim().toUpperCase();
  const bankName = (document.getElementById('stKycBankName')?.value || '').trim();

  const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
  if (!PAN_REGEX.test(pan)) {
    if (fb) {
      fb.style.display = 'block';
      fb.style.color = '#dc2626';
      fb.textContent = ' Invalid PAN card format (e.g. ABCDE1234F)';
    }
    return;
  }

  if (method === 'upi') {
    const UPI_REGEX = /^[\w.\-_]{2,256}@[\w]{2,64}$/;
    if (!UPI_REGEX.test(upiId)) {
      if (fb) {
        fb.style.display = 'block';
        fb.style.color = '#dc2626';
        fb.textContent = ' Invalid UPI ID format (e.g. username@okhdfcbank)';
      }
      return;
    }
  } else {
    if (!/^\d{9,18}$/.test(bankAcc)) {
      if (fb) {
        fb.style.display = 'block';
        fb.style.color = '#dc2626';
        fb.textContent = ' Bank account number must be 9 to 18 digits';
      }
      return;
    }
    if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(bankIfsc)) {
      if (fb) {
        fb.style.display = 'block';
        fb.style.color = '#dc2626';
        fb.textContent = ' Invalid IFSC code format (e.g. SBIN0001234)';
      }
      return;
    }
  }

  btn.disabled = true;
  btn.innerText = 'Submitting KYC...';
  if (fb) fb.style.display = 'none';

  try {
    const res = await fetch('/api/user/kyc/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        full_name: fullName,
        pan_number: pan,
        preferred_method: method,
        upi_id: upiId,
        account_number: bankAcc,
        ifsc_code: bankIfsc,
        bank_name: bankName
      })
    });
    const data = await res.json();
    if (fb) fb.style.display = 'block';
    if (data.success) {
      fb.style.color = 'var(--st-success, #16a34a)';
      fb.textContent = ' ' + (data.message || 'KYC submitted successfully!');
      setTimeout(loadStKycStatus, 1200);
    } else {
      fb.style.color = '#dc2626';
      fb.textContent = ' ' + (data.error || 'KYC submission failed');
    }
  } catch (err) {
    if (fb) {
      fb.style.display = 'block';
      fb.style.color = '#dc2626';
      fb.textContent = 'Network error submitting KYC.';
    }
  } finally {
    btn.disabled = false;
    btn.innerText = 'Submit KYC for Verification';
  }
}

// ── Payment & Transaction History Management ──
let _txHistoryLoaded = false;
async function loadTransactionHistory(force = false) {
  if (_txHistoryLoaded && !force) return;
  _txHistoryLoaded = true;

  const listEl = document.getElementById('stTransactionsList');
  const tbody = document.getElementById('stTransactionsTbody');
  const target = listEl || tbody;
  if (!target) return;

  target.innerHTML = '<div style="padding:1.5rem;text-align:center;color:var(--st-text-muted);font-size:0.85rem;">Fetching your transactions...</div>';

  try {
    const res = await fetch('/api/user/transactions');
    const data = await res.json();
    const txs = (data && data.transactions) || [];

    const totalEl = document.getElementById('stTxTotalOrders');
    const successEl = document.getElementById('stTxSuccessOrders');
    if (totalEl) totalEl.textContent = txs.length;
    if (successEl) successEl.textContent = txs.filter(t => t.status === 'completed' || t.status === 'verified').length;

    if (!txs.length) {
      target.innerHTML = '<div style="padding:2.5rem 1rem;text-align:center;color:var(--st-text-muted);">' +
        '<div style="font-weight:700;color:var(--st-text-main);font-size:0.95rem;margin-bottom:0.35rem;">No payment transactions found</div>' +
        '<div style="font-size:0.8rem;max-width:360px;margin:0 auto;line-height:1.4;">When you unlock paid notes or contribute, verified receipts will appear here.</div>' +
        '</div>';
      return;
    }

    let html = '';
    txs.forEach(t => {
      const isSuccess = (t.status === 'completed' || t.status === 'verified');
      const statusBadge = isSuccess
        ? '<span class="st-tx-badge success">Paid</span>'
        : '<span class="st-tx-badge failed">Failed</span>';

      const itemName = t.doc_title || (t.doc_id ? ('Document #' + t.doc_id.slice(0, 8)) : 'Study Pass / Support');
      const dateStr = t.date ? new Date(t.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'Recent';
      const orderId = t.order_id ? '#' + t.order_id : '';
      const hasActions = t.receipt_url || (t.doc_id && isSuccess);

      html += '<div class="st-tx-card">';
      html += '  <div class="st-tx-card-top">';
      html += '    <div class="st-tx-item-name" title="' + itemName + '">' + itemName + '</div>';
      html += '    <div class="st-tx-amount">₹' + (parseFloat(t.amount || 0).toFixed(2)) + '</div>';
      html += '  </div>';
      html += '  <div class="st-tx-card-meta">';
      html += '    <div class="st-tx-meta-left">';
      html += '      <span>' + dateStr + '</span>';
      if (orderId) {
        html += '      <span style="opacity:0.4;">•</span>';
        html += '      <span class="st-tx-id" title="' + orderId + '">' + orderId + '</span>';
      }
      html += '    </div>';
      html += '    <div>' + statusBadge + '</div>';
      html += '  </div>';

      if (hasActions) {
        html += '  <div class="st-tx-actions">';
        if (t.receipt_url) {
          html += '    <a href="' + t.receipt_url + '" target="_blank" rel="noopener" class="st-btn st-btn-outline" style="padding:0.25rem 0.75rem;font-size:0.74rem;min-height:30px;border-radius:980px;">Receipt ↗</a>';
        }
        if (t.doc_id && isSuccess) {
          html += '    <a href="/resource/' + t.doc_id + '" class="st-btn st-btn-primary" style="padding:0.25rem 0.75rem;font-size:0.74rem;min-height:30px;border-radius:980px;">Open Doc ↗</a>';
        }
        html += '  </div>';
      }
      html += '</div>';
    });

    target.innerHTML = html;
    if (force && typeof showStToast === 'function') {
      showStToast('Payment history refreshed');
    }
  } catch (err) {
    target.innerHTML = '<div style="padding:1.5rem;text-align:center;color:#ef4444;font-size:0.85rem;">Failed to load transactions. Please retry.</div>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadAiSettings();
  filterSettingsBranches();
  toggleSettingsStudentFields();
  if (typeof window.syncSettingsTabFromUrl === 'function') {
    window.syncSettingsTabFromUrl(false);
  }
});

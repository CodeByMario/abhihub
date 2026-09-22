'use strict';

let selectedFiles = [];
let isUploading = false;
let cropperInst = null;
let currentCropId = null;
let currentMetaId = null;
let uploadedFingerprints = new Set(); // duplicate guard (session-scoped)

function fileFingerprint(item) {
  var f = item.file;
  return [f.name, f.size, f.lastModified || 0].join('|');
}

function fmtSize(b) {
  if (b < 1024) return b + 'B';
  if (b < 1048576) return (b / 1024).toFixed(1) + 'KB';
  return (b / 1048576).toFixed(2) + 'MB';
}
function uid() {
  return 'f_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
}
function gv(id) { return (document.getElementById(id) || {}).value || ''; }

async function computeFileHash(file) {
  try {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  } catch (e) {
    console.error("Hashing failed", e);
    return fileFingerprint({ file: file }); // Fallback
  }
}

// Upload progress state (shared between processUploadBatch + uploadOne)
var _progBar = null;
var _progFloat = null;
var _progText = null;
var _progTotal = 0;
var _progDone = 0;
var _progCurrentFile = '';
var _progCurrentPct = 0;
var _statusModalOpen = false;
var _duplicateDecisions = {};

function updateProgressUI() {
  if (_progBar) {
    var overall = _progTotal > 0
      ? ((_progDone + (_progCurrentPct / 100)) / _progTotal) * 100
      : 0;
    _progBar.style.width = Math.min(overall, 100) + '%';
  }
  if (_progFloat) {
    _progFloat.innerHTML = _progCurrentFile
      ? '⬆ ' + _progCurrentFile + ' (' + _progCurrentPct + '%)'
      : ('Uploading ' + _progDone + ' / ' + _progTotal + ' — Play Game 🎮');
  }
  if (_progText) {
    _progText.innerText = 'Uploading ' + (_progDone + (_progCurrentPct > 0 ? 1 : 0)) + ' / ' + _progTotal;
  }
}

function setFileStatus(id, status, progress, msg) {
  var container = document.getElementById('uploadFileList');
  if (!container) {
    container = document.createElement('div');
    container.id = 'uploadFileList';
    var overlay = document.getElementById('uploadOverlay');
    if (overlay) {
      var panels = overlay.querySelectorAll('div');
      if (panels.length > 0) overlay.insertBefore(container, panels[panels.length - 1]);
      else overlay.appendChild(container);
    }
  }

  var entry = document.getElementById('fs-' + id);
  if (!entry) {
    entry = document.createElement('div');
    entry.id = 'fs-' + id;
    entry.className = 'fs-entry';

    var icon = document.createElement('span');
    icon.className = 'fs-icon';
    entry.appendChild(icon);

    var nameEl = document.createElement('span');
    nameEl.className = 'fs-name';
    entry.appendChild(nameEl);

    var bar = document.createElement('div');
    bar.className = 'fs-bar';
    var fill = document.createElement('div');
    fill.className = 'fs-fill';
    bar.appendChild(fill);
    entry.appendChild(bar);

    var pct = document.createElement('span');
    pct.className = 'fs-pct';
    entry.appendChild(pct);

    entry._icon = icon;
    entry._name = nameEl;
    entry._fill = fill;
    entry._pct = pct;
    container.appendChild(entry);
  }

  var item = selectedFiles.filter(function (f) { return f.id === id; })[0];
  if (item) {
    entry._icon.textContent = (item.file.type && item.file.type.indexOf('image/') === 0) ? '🖼' : '📄';
    entry._name.textContent = item.name;
  }

  entry.classList.remove('fs-uploading', 'fs-done', 'fs-error');
  if (status === 'uploading') entry.classList.add('fs-uploading');
  else if (status === 'done') entry.classList.add('fs-done');
  else if (status === 'error') entry.classList.add('fs-error');

  if (status === 'uploading') {
    entry._fill.style.width = progress + '%';
    entry._pct.textContent = progress + '%';
  } else if (status === 'done') {
    entry._fill.style.width = '100%';
    entry._pct.textContent = '\u2713';
  } else if (status === 'error') {
    entry._fill.style.width = '0%';
    entry._pct.textContent = '\u2717';
  }
}

function showToast(msg, type) {
  const c = document.getElementById('toastContainer');
  if (!c) return;
  const d = document.createElement('div');
  d.className = 'bu-toast bu-toast-' + (type || 'info');
  d.textContent = msg;
  c.appendChild(d);
  setTimeout(() => d.remove(), 4000);
}

// Map of in-flight AbortControllers for AI extraction per file ID
window._uploadAiControllers = window._uploadAiControllers || {};

async function processFileMetadataAutofill(newItem, file) {
  const form = document.getElementById(`meta-form-${newItem.id}`);
  if (!form) return;

  // Track user edits so AI never overwrites manually entered fields
  form.addEventListener('input', (e) => { e.target.dataset.userModified = 'true'; });
  form.addEventListener('change', (e) => { e.target.dataset.userModified = 'true'; });

  const showAiPill = (field) => {
    const pill = form.querySelector(`.field-ai-pill[data-field="${field}"]`);
    if (pill) pill.style.display = 'inline-flex';
  };

  const setStatusBadge = (show, text) => {
    const badge = form.querySelector('.meta-ai-status-badge');
    if (badge) {
      badge.style.display = show ? 'inline-flex' : 'none';
      if (text) badge.textContent = text;
    }
  };

  let known = { type: null, year: null, unit: null, subject_id: null, subject_name: null, qb_tags: null };

  // Step 1: Fast & Free Heuristic Pass
  try {
    const hRes = await fetch('/api/ai/predict-metadata', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name })
    }).then(r => r.json());

    if (hRes && hRes.success && hRes.prediction) {
      const p = hRes.prediction;
      if (p.type) known.type = p.type;
      if (p.year) known.year = p.year;
      if (p.unit) known.unit = p.unit;
      if (p.subject_id) known.subject_id = p.subject_id;

      if (known.type) {
        const typeEl = form.querySelector('.meta-type');
        if (typeEl && !typeEl.dataset.userModified && !typeEl.value) {
          typeEl.value = known.type;
          updateDynamicFieldsForForm(form);
        }
      }
      if (known.year) {
        const yearEl = form.querySelector('.meta-year');
        if (yearEl && !yearEl.dataset.userModified) yearEl.value = known.year;
      }
      if (known.unit) {
        const unitEl = form.querySelector('.meta-unit');
        if (unitEl && !unitEl.dataset.userModified && !unitEl.value) {
          unitEl.innerHTML = `<option value="${known.unit}" selected>${known.unit}</option>`;
          unitEl.value = known.unit;
        }
      }
      if (known.subject_id) {
        const subjEl = form.querySelector('.subject-select');
        if (subjEl && !subjEl.dataset.userModified) {
          const tsSubj = window.AbhiHubSelect?.instances[subjEl.id];
          if (tsSubj) {
            if (!tsSubj.options[known.subject_id]) tsSubj.addOption({ value: known.subject_id, text: p.subject || 'Loading...' });
            tsSubj.setValue(known.subject_id, true);
          } else {
            subjEl.value = known.subject_id;
          }
        }
      }
    }
  } catch (e) {
    console.warn("[Autofill] Heuristic predict error:", e);
  }

  // Step 2: Check if all key fields are resolved
  const isComplete = known.type && known.year && (known.type !== 'papers' || known.unit) && known.subject_id;
  if (isComplete) {
    return;
  }

  // Step 3: AI Document Extraction Pass (Async, Abortable)
  const controller = new AbortController();
  window._uploadAiControllers[newItem.id] = controller;
  setStatusBadge(true, '🤖 Analyzing document…');

  try {
    const branchEl = form.querySelector('.branch-select');
    const branch_id = branchEl
      ? (window.AbhiHubSelect?.instances[branchEl.id]?.getValue() || branchEl.value || window.userBranchId || '')
      : (window.userBranchId || '');

    const fd = new FormData();
    fd.append('upload_document', file);
    fd.append('filename', file.name);
    if (branch_id) fd.append('branch_id', branch_id);
    fd.append('known_fields', JSON.stringify(known));

    const aiRes = await fetch('/api/ai/extract-upload-metadata', {
      method: 'POST',
      body: fd,
      signal: controller.signal
    }).then(r => r.json());

    if (aiRes && aiRes.success && aiRes.metadata) {
      const m = aiRes.metadata;

      // 1. Category / Type
      if (m.type) {
        const typeEl = form.querySelector('.meta-type');
        if (typeEl && !typeEl.dataset.userModified) {
          typeEl.value = m.type;
          updateDynamicFieldsForForm(form);
          showAiPill('type');
        }
      }

      // 2. Year
      if (m.year) {
        const yearEl = form.querySelector('.meta-year');
        if (yearEl && !yearEl.dataset.userModified) {
          yearEl.value = m.year;
          showAiPill('year');
        }
      }

      // 3. Unit
      if (m.unit) {
        const unitEl = form.querySelector('.meta-unit');
        if (unitEl && !unitEl.dataset.userModified) {
          let opt = unitEl.querySelector(`option[value="${m.unit}"]`);
          if (!opt) {
            opt = document.createElement('option');
            opt.value = m.unit;
            opt.textContent = m.unit;
            unitEl.appendChild(opt);
          }
          unitEl.value = m.unit;
          showAiPill('unit');
        }
      }

      // 4. Subject
      const subjEl = form.querySelector('.subject-select');
      if (subjEl && !subjEl.dataset.userModified) {
        const tsSubj = window.AbhiHubSelect?.instances[subjEl.id];
        if (m.subject_id) {
          if (tsSubj) {
            if (!tsSubj.options[m.subject_id]) {
              tsSubj.addOption({ value: m.subject_id, text: m.subject_name || 'Loading...' });
            }
            tsSubj.setValue(m.subject_id, false);
          } else {
            subjEl.value = m.subject_id;
          }
          showAiPill('subject');
        } else if (m.subject_name) {
          // Pre-populate search query in TomSelect if subject_id wasn't resolved
          if (tsSubj && typeof tsSubj.setTextboxValue === 'function') {
            tsSubj.setTextboxValue(m.subject_name);
          }
        }
      }

      // 5. Question Bank Tags
      if (m.qb_tags) {
        const qbEl = form.querySelector('.qb-tags');
        if (qbEl && !qbEl.dataset.userModified && !qbEl.value) {
          qbEl.value = m.qb_tags;
        }
      }

      if (aiRes.source && aiRes.source.startsWith('ai_') && (aiRes.fields_filled || []).length > 0) {
        showToast('✨ AI auto-filled metadata for ' + newItem.name, 'info');
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.warn("[Autofill] AI extract failed (silent degradation):", err);
    }
  } finally {
    setStatusBadge(false);
    delete window._uploadAiControllers[newItem.id];
  }
}

/* ── File selection ── */
function handleFilesSelected(filesOrEvent) {
  const files = (filesOrEvent && filesOrEvent.type && filesOrEvent.type.startsWith('change') && filesOrEvent.target)
    ? filesOrEvent.target.files
    : filesOrEvent;
  const fromCamera = Array.from(files).some(f =>
    !f.lastModified || f.name.toLowerCase().startsWith('image') || f.name.toLowerCase() === 'blob'
  );
  if (fromCamera && typeof window.AbhiHubTracking !== 'undefined') {
    window.AbhiHubTracking.trackCameraUpload();
  }
  Array.from(files).forEach(file => {
    const activeForm = document.querySelector('.meta-form-wrap[style*="display: block"]');
    const typeEl = activeForm?.querySelector('.meta-type');
    const selType = typeEl ? typeEl.value : '';
    const imgOnly = ['papers', 'practical'].includes(selType.toLowerCase());
    if (imgOnly && !file.type.startsWith('image/')) {
      return showToast(file.name + ': images only for this type', 'error');
    }
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      return showToast(file.name + ': unsupported type', 'error');
    }
    if (file.size > 500 * 1024 * 1024) return showToast(file.name + ': exceeds 500 MB', 'error');

    const newItem = {
      id: uid(), file, blob: null, compressedBlob: null, name: file.name, cropped: false, status: 'pending', compressionStatus: 'compressing'
    };
    selectedFiles.push(newItem);
    startBackgroundCompression(newItem);

    // Update the drop-zone hint + accept attr based on this file's type
    updateDynamicFields();

    // Create DOM isolated form
    const template = document.getElementById('metaFormTemplate');
    const container = document.getElementById('metaFormsContainer');
    if (template && container) {
      const clone = template.content.cloneNode(true);
      const wrap = clone.querySelector('.meta-form-wrap');
      wrap.id = `meta-form-${newItem.id}`;
      wrap.style.display = 'none';

      // Ensure unique IDs for AbhiHubSelect initialization tracking
      wrap.querySelectorAll('.abhihub-select').forEach(sel => {
        sel.id = `abhiselect_${uid()}`;
      });

      container.appendChild(clone);

      // Initialize AbhiHubSelect on new elements FIRST so TomSelect instances exist
      if (window.AbhiHubSelect) window.AbhiHubSelect.init();

      // Pre-fill profile defaults via cascade-aware autofill
      const addedWrap = document.getElementById(`meta-form-${newItem.id}`);
      if (typeof autofillMetaForm === 'function') {
        autofillMetaForm(addedWrap);
      }

      // Wire dynamic fields for THIS file's category
      updateDynamicFieldsForForm(addedWrap);
    }

    // Trigger tiered metadata prediction & AI content extraction
    processFileMetadataAutofill(newItem, file);
  });

  if (selectedFiles.length > 0) {
    document.getElementById('uploadCarousel').style.display = 'flex';
    document.querySelector('.upload-defaults-toggle')?.remove();
    renderCarousel(selectedFiles.length - 1);
  }
}

function removeFile(id) {
  if (window._uploadAiControllers && window._uploadAiControllers[id]) {
    window._uploadAiControllers[id].abort();
    delete window._uploadAiControllers[id];
  }
  selectedFiles = selectedFiles.filter(f => f.id !== id);
  if (selectedFiles.length === 0) {
    document.getElementById('uploadCarousel').style.display = 'none';
    const strip = document.getElementById('uploadFilmstrip');
    if (strip) strip.style.display = 'none';
    resetUploadButton();
  } else {
    if (carouselIndex >= selectedFiles.length) carouselIndex = selectedFiles.length - 1;
    renderCarousel(carouselIndex);
  }
}

/* ── Carousel Logic ── */
let carouselIndex = 0;
let carouselRotation = 0;

function removeCarouselImage() {
  if (selectedFiles.length === 0) return;
  carouselIndex = Math.max(0, Math.min(carouselIndex, selectedFiles.length - 1));
  const item = selectedFiles[carouselIndex];
  if (!item) return;

  // Remove the isolated form
  const form = document.getElementById(`meta-form-${item.id}`);
  if (form) form.remove();

  removeFile(item.id);
}

function renderCarousel(index) {
  if (selectedFiles.length === 0) {
    const el = document.getElementById('uploadCarousel');
    if (el) el.style.display = 'none';
    return;
  }
  index = Math.max(0, Math.min(index, selectedFiles.length - 1));
  carouselIndex = index;
  const item = selectedFiles[index];
  if (!item) return;

  const fnEl = document.getElementById('carouselFilename');
  if (fnEl) fnEl.textContent = item.name + (item.cropped ? ' (Cropped)' : '');
  const cImg = document.getElementById('carouselImg');
  const metricEl = document.getElementById('carouselMetric');
  const isPdf = item.file && (item.file.type === 'application/pdf' || item.name.toLowerCase().endsWith('.pdf'));
  if (cImg) {
    if (isPdf) {
      cImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 24 24" fill="none" stroke="%23ef4444" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><text x="6" y="18" fill="%23ef4444" font-size="6" font-family="sans-serif" font-weight="bold">PDF FILE</text></svg>';
    } else {
      cImg.src = carouselImageSrc(item);
    }
    cImg.style.transform = `rotate(${item.rotation || 0}deg)`;
  }

  // Compression badge for the carousel
  if (metricEl && item.compression) {
    const label = item.compression.label;
    const cls = item.compression.cls || 'original';
    metricEl.innerHTML = `<span class="compression-badge ${cls}">${label}</span>`;
    metricEl.style.display = 'flex';
  } else if (metricEl) {
    metricEl.style.display = 'none';
  }

  // DOM Isolation: Toggle visibility of forms
  document.querySelectorAll('.meta-form-wrap').forEach(el => el.style.display = 'none');
  const activeForm = document.getElementById(`meta-form-${item.id}`);
  if (activeForm) activeForm.style.display = 'block';

  const cCounter = document.getElementById('cCounter');
  if (cCounter) cCounter.textContent = (index + 1) + ' / ' + selectedFiles.length;
  const cPrevBtn = document.getElementById('cPrevBtn');
  if (cPrevBtn) cPrevBtn.disabled = (index === 0);
  const cNextBtn = document.getElementById('cNextBtn');
  if (cNextBtn) cNextBtn.disabled = (index === selectedFiles.length - 1);

  renderFilmstrip();
}

function renderFilmstrip() {
  const strip = document.getElementById('uploadFilmstrip');
  const list = document.getElementById('filmstripList');
  const countEl = document.getElementById('filmstripCount');
  if (!strip || !list) return;

  if (selectedFiles.length === 0) {
    strip.style.display = 'none';
    return;
  }

  strip.style.display = 'block';
  if (countEl) countEl.textContent = selectedFiles.length;

  list.innerHTML = selectedFiles.map((item, idx) => {
    const isCur = idx === carouselIndex;
    const isPdf = item.file && (item.file.type === 'application/pdf' || item.name.toLowerCase().endsWith('.pdf'));
    const form = document.getElementById(`meta-form-${item.id}`);
    
    let isLabeled = false;
    if (form) {
      const col = form.querySelector('.college-select')?.value;
      const sub = form.querySelector('.subject-select')?.value;
      const title = form.querySelector('.meta-title')?.value;
      const type = form.querySelector('.meta-type')?.value;
      if (col && sub && type && title && title.length >= 3) {
        isLabeled = true;
      }
    }

    const thumbSrc = isPdf ? '' : carouselImageSrc(item);
    const thumbHtml = isPdf 
      ? '<span class="film-pdf-icon">📄 PDF</span>'
      : `<img src="${thumbSrc}" class="film-thumb-img" alt="thumb">`;

    return `
      <div class="filmstrip-card ${isCur ? 'active' : ''} ${isLabeled ? 'labeled' : 'unlabeled'}" onclick="renderCarousel(${idx})">
        <div class="filmstrip-thumb-wrap">
          ${thumbHtml}
          <button type="button" class="filmstrip-del-btn" onclick="event.stopPropagation(); removeFileById('${item.id}');" title="Remove file">✕</button>
        </div>
        <div class="filmstrip-info">
          <div class="filmstrip-name" title="${item.name}">${item.name}</div>
          <div class="filmstrip-badge ${isLabeled ? 'badge-ok' : 'badge-warn'}">
            ${isLabeled ? '✓ Ready' : '● Incomplete'}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function removeFileById(id) {
  const form = document.getElementById(`meta-form-${id}`);
  if (form) form.remove();
  removeFile(id);
}

function copyLabelsToAll() {
  if (selectedFiles.length <= 1) {
    showToast('Add more files first to copy details across files', 'info');
    return;
  }
  const curItem = selectedFiles[carouselIndex];
  if (!curItem) return;
  const sourceForm = document.getElementById(`meta-form-${curItem.id}`);
  if (!sourceForm) return;

  const colVal = sourceForm.querySelector('.college-select')?.value || '';
  const branchVal = sourceForm.querySelector('.branch-select')?.value || '';
  const progVal = sourceForm.querySelector('.program-select')?.value || '';
  const semVal = sourceForm.querySelector('.semester-select')?.value || '';
  const subVal = sourceForm.querySelector('.subject-select')?.value || '';
  const typeVal = sourceForm.querySelector('.meta-type')?.value || '';
  const yearVal = sourceForm.querySelector('.meta-year')?.value || '';
  const unitVal = sourceForm.querySelector('.meta-unit')?.value || '';

  let count = 0;
  selectedFiles.forEach(item => {
    if (item.id === curItem.id) return;
    const targetForm = document.getElementById(`meta-form-${item.id}`);
    if (!targetForm) return;

    const progEl = targetForm.querySelector('.program-select');
    if (progEl && progVal) progEl.value = progVal;

    const typeEl = targetForm.querySelector('.meta-type');
    if (typeEl && typeVal) {
      typeEl.value = typeVal;
      updateDynamicFieldsForForm(targetForm);
    }

    const yearEl = targetForm.querySelector('.meta-year');
    if (yearEl && yearVal) yearEl.value = yearVal;

    const unitEl = targetForm.querySelector('.meta-unit');
    if (unitEl && unitVal) unitEl.value = unitVal;

    const colEl = targetForm.querySelector('.college-select');
    if (colEl && colVal) {
      const tsCol = window.AbhiHubSelect?.instances[colEl.id];
      if (tsCol) tsCol.setValue(colVal, false);
      else { colEl.value = colVal; colEl.dispatchEvent(new Event('change')); }
    }

    const branchEl = targetForm.querySelector('.branch-select');
    if (branchEl && branchVal) {
      const tsBranch = window.AbhiHubSelect?.instances[branchEl.id];
      if (tsBranch) tsBranch.setValue(branchVal, false);
      else { branchEl.value = branchVal; branchEl.dispatchEvent(new Event('change')); }
    }

    const semEl = targetForm.querySelector('.semester-select');
    if (semEl && semVal) {
      const tsSem = window.AbhiHubSelect?.instances[semEl.id];
      if (tsSem) tsSem.setValue(semVal, false);
      else { semEl.value = semVal; semEl.dispatchEvent(new Event('change')); }
    }

    const subEl = targetForm.querySelector('.subject-select');
    if (subEl && subVal) {
      const tsSub = window.AbhiHubSelect?.instances[subEl.id];
      if (tsSub) tsSub.setValue(subVal, false);
      else { subEl.value = subVal; subEl.dispatchEvent(new Event('change')); }
    }

    count++;
  });

  showToast(`⚡ Copied labels to ${count} other file(s)!`, 'success');
  renderFilmstrip();
}

function openFullPreview() {
  if (selectedFiles.length === 0) return;
  const item = selectedFiles[carouselIndex];
  if (!item || !item.file) return;
  const fileUrl = URL.createObjectURL(item.file);
  window.open(fileUrl, '_blank');
}

async function analyzeCurrentFileWithAi() {
  if (selectedFiles.length === 0) {
    showToast('Select a file first to analyze with Tarika', 'info');
    return;
  }
  const curItem = selectedFiles[carouselIndex];
  if (!curItem || !curItem.file) return;

  const btn = document.getElementById('tarikaUploadAnalyzeBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳ Tarika Analyzing…</span>';
  }

  try {
    const res = await fetch('/api/ai/tool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name: 'suggest_upload_metadata',
        parameters: { filename: curItem.file.name }
      })
    }).then(r => r.json());

    if (res && res.success && res.result && res.result.data) {
      const d = res.result.data;
      const form = document.getElementById(`meta-form-${curItem.id}`);
      if (form) {
        if (d.title) {
          const tEl = form.querySelector('.meta-title');
          if (tEl && !tEl.dataset.userModified) {
            tEl.value = d.title;
            const p = form.querySelector('.field-ai-pill[data-field="title"]');
            if (p) p.style.display = 'inline-flex';
          }
        }
        if (d.document_type) {
          const catMap = { pyq: 'papers', notes: 'notes', practicals: 'practical', syllabus: 'syllabus' };
          const targetType = catMap[d.document_type] || d.document_type;
          const typeEl = form.querySelector('.meta-type');
          if (typeEl && !typeEl.dataset.userModified) {
            typeEl.value = targetType;
            if (typeof updateDynamicFieldsForForm === 'function') updateDynamicFieldsForForm(form);
            const p = form.querySelector('.field-ai-pill[data-field="type"]');
            if (p) p.style.display = 'inline-flex';
          }
        }
        if (d.year) {
          const yearEl = form.querySelector('.meta-year');
          if (yearEl && !yearEl.dataset.userModified) {
            yearEl.value = String(d.year);
            const p = form.querySelector('.field-ai-pill[data-field="year"]');
            if (p) p.style.display = 'inline-flex';
          }
        }
        if (d.semester) {
          const semEl = form.querySelector('.semester-select');
          if (semEl && !semEl.dataset.userModified) {
            const tsSem = window.AbhiHubSelect?.instances[semEl.id];
            if (tsSem) tsSem.setValue(String(d.semester), true);
            else { semEl.value = String(d.semester); semEl.dispatchEvent(new Event('change')); }
          }
        }
      }
      showToast('✨ Tarika generated metadata suggestions!', 'success');
    } else {
      await processFileMetadataAutofill(curItem, curItem.file);
    }
  } catch (e) {
    console.warn('[Tarika Upload Analysis]', e);
    await processFileMetadataAutofill(curItem, curItem.file);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span>✨ Analyze with Tarika</span>';
    }
  }
}

window.renderFilmstrip = renderFilmstrip;
window.removeFileById = removeFileById;
window.copyLabelsToAll = copyLabelsToAll;
window.openFullPreview = openFullPreview;
window.analyzeCurrentFileWithAi = analyzeCurrentFileWithAi;


/**
 * Carousel image source: prefer a client-side preview compression
 * (item.previewBlob, set in uploadOne) for smooth rendering, fall
 * back to the raw file. The upload FormData always sends the ORIGINAL
 * file so the server (cloudinary_upload.py) owns compression authoritatively.
 */
function carouselImageSrc(item) {
  if (item.previewBlob) return URL.createObjectURL(item.previewBlob);
  if (item.blob) return URL.createObjectURL(item.blob);
  return URL.createObjectURL(item.file);
}

/**
 * Per-file dynamic field wiring: show/hide unit + exam groups
 * based on the category selected in THIS form's .meta-type select.
 * Called after each meta-form clone is appended so every file
 * gets its own correct field visibility.
 */
function updateDynamicFieldsForForm(formWrap) {
  if (!formWrap) return;
  var typeEl = formWrap.querySelector('.meta-type');
  var unitG = formWrap.querySelector('.meta-unit-wrap');
  var pracG = formWrap.querySelector('.meta-practical-wrap');
  var unitSel = formWrap.querySelector('.meta-unit');
  var qbG = formWrap.querySelector('.qb-tags-wrap');

  if (!typeEl) return;
  var type = (typeEl.value || '').toLowerCase();

  if (unitG) unitG.style.display = 'none';
  if (pracG) pracG.style.display = 'none';
  if (qbG) qbG.style.display = 'none';

  if (type === 'notes') {
    if (unitG) unitG.style.display = 'block';
    if (unitSel) unitSel.innerHTML = '<option value="U1">Unit 1</option><option value="U2">Unit 2</option><option value="U3">Unit 3</option><option value="U4">Unit 4</option><option value="U5">Unit 5</option><option value="All">All Units</option>';
  } else if (type === 'papers') {
    if (unitG) unitG.style.display = 'block';
    if (unitSel) unitSel.innerHTML = '<option value="CAE1">CAE-1</option><option value="CAE2">CAE-2</option><option value="CAE3">CAE-3</option><option value="ESE">End Sem/Resit</option>';
  } else if (type === 'practical') {
    if (pracG) pracG.style.display = 'grid';
  } else if (type === 'question_bank') {
    if (qbG) qbG.style.display = 'block';
  }
}

function navigateCarousel(dir) {
  if (selectedFiles.length === 0) return;
  if (typeof dir !== 'number') {
    if (typeof dir === 'string') {
      dir = parseInt(dir, 10);
    } else if (dir && dir.currentTarget && dir.currentTarget.getAttribute) {
      dir = parseInt(dir.currentTarget.getAttribute('data-direction'), 10);
    } else if (dir && dir.target && dir.target.closest) {
      const btn = dir.target.closest('[data-direction]');
      dir = btn ? parseInt(btn.getAttribute('data-direction'), 10) : -1;
    } else {
      dir = -1;
    }
  }
  if (isNaN(dir)) dir = -1;
  let newIdx = carouselIndex + dir;
  newIdx = Math.max(0, Math.min(newIdx, selectedFiles.length - 1));
  renderCarousel(newIdx);
}

function rotateCarousel(deg) {
  if (typeof deg !== 'number') {
    if (typeof deg === 'string') {
      deg = parseInt(deg, 10);
    } else if (deg && deg.currentTarget && deg.currentTarget.getAttribute) {
      deg = parseInt(deg.currentTarget.getAttribute('data-direction'), 10);
    } else if (deg && deg.target && deg.target.closest) {
      const btn = deg.target.closest('[data-direction]');
      deg = btn ? parseInt(btn.getAttribute('data-direction'), 10) : 90;
    } else {
      deg = 90;
    }
  }
  if (isNaN(deg)) deg = 90;
  if (cropperInst) {
    cropperInst.rotate(deg);
  } else {
    const imgEl = document.getElementById('carouselImg');
    if (imgEl) {
      carouselRotation = (carouselRotation + deg) % 360;
      imgEl.style.transform = `rotate(${carouselRotation}deg)`;
    }
  }
}

function toggleCarouselCrop() {
  const img = document.getElementById('carouselImg');
  if (cropperInst) {
    // Apply crop
    cropperInst.getCroppedCanvas({ maxWidth: 2400, maxHeight: 2400, imageSmoothingQuality: 'high' })
      .toBlob(blob => {
        const item = selectedFiles[carouselIndex];
        item.blob = blob;
        item.cropped = true;
        cropperInst.destroy();
        cropperInst = null;
        img.src = URL.createObjectURL(blob);
        img.style.transform = `rotate(0deg)`;
        carouselRotation = 0;
      }, 'image/jpeg', 0.92);
  } else {
    // Start crop
    cropperInst = new Cropper(img, { viewMode: 1, movable: true, zoomable: true, rotatable: true });
  }
}

/* ── Upload & Compression ── */
async function startBackgroundCompression(item) {
  if (!item || !item.file) return;
  const rawFile = item.file;
  item.compressionStatus = 'compressing';
  item.compression = { label: '⚡ Compressing...', cls: 'compressing' };

  if (selectedFiles[carouselIndex] && selectedFiles[carouselIndex].id === item.id) {
    renderCarousel(carouselIndex);
  }

  try {
    let compressedBlob = null;
    if (rawFile.type.startsWith('image/')) {
      compressedBlob = await compressImage(rawFile, 0.82);
    } else if (rawFile.type === 'application/pdf') {
      compressedBlob = await compressPdfFile(rawFile);
    }

    if (compressedBlob && compressedBlob.size > 0 && compressedBlob.size < rawFile.size) {
      item.compressedBlob = compressedBlob;
      item.blob = compressedBlob;
      const savedPct = Math.round((1 - compressedBlob.size / rawFile.size) * 100);
      item.compressionStatus = 'done';
      item.compression = {
        label: `⚡ Ready (${fmtSize(rawFile.size)} ➔ ${fmtSize(compressedBlob.size)}, -${savedPct}%)`,
        cls: 'compressed'
      };
    } else {
      item.compressionStatus = 'done';
      item.compression = {
        label: `✓ Ready (${fmtSize(rawFile.size)})`,
        cls: 'original'
      };
    }
  } catch (err) {
    console.warn("Background compression warning:", err);
    item.compressionStatus = 'done';
    item.compression = { label: `✓ Ready (${fmtSize(rawFile.size)})`, cls: 'original' };
  }

  if (selectedFiles[carouselIndex] && selectedFiles[carouselIndex].id === item.id) {
    renderCarousel(carouselIndex);
  }
}

async function compressPdfFile(fileObj) {
  if (fileObj.size <= 1024 * 1024) return fileObj;
  return fileObj;
}

async function compressImage(fileObj, quality) {
  quality = quality || 0.75;
  return new Promise(function (resolve) {
    if (!fileObj.type || !fileObj.type.startsWith('image/')) return resolve(fileObj);
    var img = new Image();
    img.onload = function () {
      var MAX = 1600;
      var scaleW = img.width > MAX ? MAX / img.width : 1;
      var scaleH = img.height > MAX ? MAX / img.height : 1;
      var scale = Math.min(scaleW, scaleH, 1);
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      var ctx = canvas.getContext('2d');
      ctx.filter = 'grayscale(100%) contrast(110%)';
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      ctx.filter = 'none';

      // AbhiHub logo watermark on bottom right corner
      var fontSize = Math.max(14, Math.round(canvas.width * 0.025));
      var padding = Math.max(12, Math.round(canvas.width * 0.015));
      ctx.font = 'bold ' + fontSize + 'px system-ui, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
      ctx.shadowBlur = 4;
      ctx.shadowOffsetX = 1;
      ctx.shadowOffsetY = 1;
      ctx.fillStyle = '#ffffff';
      ctx.fillText('🚀 AbhiHub', canvas.width - padding, canvas.height - padding);

      canvas.toBlob(function (blob) { resolve(blob || fileObj); }, 'image/jpeg', quality);
    };
    img.onerror = function () { resolve(fileObj); };
    img.src = URL.createObjectURL(fileObj);
  });
}

function buildFormData(item) {
  const fd = new FormData();

  const form = document.getElementById(`meta-form-${item.id}`);
  let m = {};
  if (form) {
    const typeEl = form.querySelector('.meta-type');
    const yearEl = form.querySelector('.meta-year');
    const unitEl = form.querySelector('.meta-unit');
    const colEl = form.querySelector('.college-select');
    const branchEl = form.querySelector('.branch-select');
    const semEl = form.querySelector('.semester-select');
    const subjEl = form.querySelector('.subject-select');
    const progEl = form.querySelector('.program-select');

    const tsSubj = window.AbhiHubSelect?.instances[subjEl?.id];
    const subjId = tsSubj ? tsSubj.getValue() : (subjEl ? subjEl.value : '');
    const subjOpt = tsSubj ? tsSubj.options[subjId] : null;
    const subjText = subjOpt ? subjOpt.text : (subjEl && subjEl.selectedIndex >= 0 ? subjEl.options[subjEl.selectedIndex]?.text : '') || subjId || '';

    const titleEl = form.querySelector('.meta-title') || form.querySelector('[name="title"]');
    const descEl = form.querySelector('.meta-description') || form.querySelector('[name="description"]');

    m = {
      type: typeEl ? typeEl.value : '',
      year: yearEl ? yearEl.value : '2025',
      unit: unitEl ? unitEl.value : '',
      college_id: colEl ? colEl.value : '',
      branch_id: branchEl ? branchEl.value : '',
      semester: semEl ? semEl.value : '',
      subject_id: subjId,
      subject: subjText,
      program: progEl ? progEl.value : 'b.tech',
      title: titleEl ? titleEl.value.trim() : '',
      description: descEl ? descEl.value.trim() : ''
    };
  }
  if (item.meta) {
    m = Object.assign({}, item.meta, m);
  }

  fd.append('title', m.title || '');
  fd.append('description', m.description || '');
  fd.append('college_id', m.college_id || '');
  fd.append('branch_id', m.branch_id || '');
  fd.append('semester', m.semester || '');
  fd.append('subject', m.subject || '');
  fd.append('subject_id', m.subject_id || '');
  fd.append('year', m.year || '2025');
  fd.append('program', m.program || 'b.tech');
  fd.append('type', m.type || '');
  fd.append('document_type', m.type || '');
  fd.append('unit', m.unit || '');
  const _csrfEl = document.querySelector('input[name="csrf_token"]');
  if (_csrfEl) fd.append('csrf_token', _csrfEl.value);
  if (item.fileHash) fd.append('file_hash', item.fileHash);
  const _examEl = form ? form.querySelector('[name="exam_type"]') : null;
  if (_examEl && _examEl.value) fd.append('exam_type', _examEl.value);
  const _codeEl = form ? form.querySelector('[name="subject_code"]') : null;
  if (_codeEl && _codeEl.value) fd.append('subject_code', _codeEl.value);
  const _qbForm = form || document.querySelector('.meta-form-wrap');
  const _qbTags = _qbForm ? _qbForm.querySelector('.qb-tags') : null;
  if (_qbTags && _qbTags.value) fd.append('qb_tags', _qbTags.value.trim());
  const origName = item.name || (item.file && item.file.name) || `file_${Date.now()}`;
  const ext = origName.includes('.') ? origName.split('.').pop().toLowerCase() : 'jpg';
  const sanitize = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const code = sanitize(m.subject || '');
  const docType = sanitize(m.type || '');
  const year = sanitize(m.year || '2025');
  const unit = sanitize(m.unit || '');
  const randSuffix = Math.random().toString(36).slice(2, 7);
  const parts = [code, docType, year];
  if (unit) parts.push(unit);
  parts.push(randSuffix);
  const cleanName = parts.filter(Boolean).join('_') || `doc_${Date.now()}_${randSuffix}`;
  const finalName = `${cleanName}.${ext}`;

  let fileObj = item.compressedBlob || item.blob || item.file;
  if (!(fileObj instanceof File)) {
    fileObj = new File([fileObj], finalName, { type: fileObj.type || 'image/jpeg' });
  } else {
    fileObj = new File([fileObj], finalName, { type: fileObj.type });
  }
  fd.append('upload_document', fileObj, finalName);
  return fd;
}


function setUploadButtonState(state, info) {
  const btn = document.getElementById('submitBtn');
  const btnText = document.getElementById('submitBtnText');
  const spinner = document.getElementById('btnSpinner');
  if (!btn) return;

  info = info || {};
  btn.classList.remove('uploading', 'is-done', 'is-error');

  switch (state) {
    case 'validating':
      btn.disabled = true;
      if (spinner) spinner.style.display = 'inline-block';
      if (btnText) btnText.textContent = 'Checking files…';
      btn.classList.add('uploading');
      break;

    case 'uploading':
      btn.disabled = true;
      if (spinner) spinner.style.display = 'inline-block';
      const pct = typeof info.pct === 'number' ? `${info.pct}%` : '';
      const count = info.total ? ` (${info.current || 1}/${info.total})` : '';
      if (btnText) btnText.textContent = `Uploading ${pct}${count}…`;
      btn.classList.add('uploading');
      break;

    case 'processing':
      btn.disabled = true;
      if (spinner) spinner.style.display = 'inline-block';
      if (btnText) btnText.textContent = 'Processing & publishing…';
      btn.classList.add('uploading');
      break;

    case 'completed':
      btn.disabled = true;
      if (spinner) spinner.style.display = 'none';
      if (btnText) btnText.textContent = 'Contribution Published ✓';
      btn.classList.add('is-done');
      break;

    case 'failed':
      btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
      if (btnText) btnText.textContent = 'Retry Failed Uploads';
      btn.classList.add('is-error');
      break;

    case 'idle':
    default:
      btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
      if (btnText) btnText.textContent = 'Upload Files';
      break;
  }
}

function resetUploadButton() {
  setUploadButtonState('idle');
}

async function uploadOne(item, retries) {
  retries = (retries === undefined) ? 2 : retries;

  if (!item.meta || !item.meta.type || (item.meta.type.toLowerCase() !== 'question_bank' && !item.meta.subject)) {
    openStatusModal();
    setItemStatus(item.id, 'error', 0, 'Fill metadata first', true);
    showToast(item.name + ': fill metadata first', 'error');
    return { ok: false, msg: 'Missing metadata' };
  }

  // Duplicate guard — skip if already uploaded this session
  var fp = fileFingerprint(item);
  if (uploadedFingerprints.has(fp)) {
    openStatusModal();
    setItemStatus(item.id, 'skipped', 100, 'Already uploaded in this session');
    return { ok: true, xp: 0, score: 0, skipped: true };
  }

  openStatusModal();
  ensureStatusItem(item.id, item.name);
  setItemStatus(item.id, 'validating', 0, 'Checking file & integrity…');

  var rawFile = item.file;
  if (rawFile && rawFile.type && rawFile.type.startsWith('image/') && rawFile.size > 500 * 1024) {
    var preview = await compressImage(rawFile);
    if (preview && preview !== rawFile && preview.size > 0) {
      item.previewBlob = preview;
      item.compression = {
        label: `Preview ${((1 - preview.size / rawFile.size) * 100).toFixed(0)}%`,
        cls: 'compressed'
      };
    }
  }

  // Zero-byte guard
  if (!rawFile || rawFile.size === 0) {
    setFileStatus(item.id, 'error', 0, 'File is empty');
    setItemStatus(item.id, 'error', 0, 'File is empty, cannot upload', false);
    showToast((item.name || 'File') + ': empty file, cannot upload', 'error');
    return { ok: false, msg: 'Empty file' };
  }

  // Duplicate Detection
  setFloatStatus(true, `Checking duplicates for ${item.name}…`);
  item.fileHash = await computeFileHash(rawFile);
  try {
    const dupCheck = await fetch('/api/check-duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: item.fileHash })
    }).then(r => r.json());

    if (dupCheck.success && dupCheck.is_duplicate) {
      setItemStatus(item.id, 'duplicate', 0, 'Duplicate detected');
      const choice = await showDuplicatePrompt(item, dupCheck.existing_file);
      if (choice === 'skip') {
        setFloatStatus(false);
        setItemStatus(item.id, 'skipped', 100, 'Skipped by user');
        return { ok: true, xp: 0, score: 0, skipped: true };
      }
      if (choice === 'cancel') {
        setFloatStatus(false);
        setItemStatus(item.id, 'error', 0, 'Cancelled by user', true);
        return { ok: false, msg: 'Cancelled by user' };
      }
      setItemStatus(item.id, 'uploading', 0, 'Uploading anyway…');
    }
  } catch (e) {
    console.warn("Duplicate check error, proceeding with upload", e);
  } finally {
    setFloatStatus(false);
  }

  return new Promise(async function (resolve) {
    let sigRes = null;
    try {
      const res = await fetch('/api/get-upload-signature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: item.name })
      });
      sigRes = await res.json();
    } catch (e) {
      console.warn('Presigned URL fetch failed, routing via server', e);
    }

    var xhr = new XMLHttpRequest();
    var targetUrl = '/upload';
    xhr.open('POST', targetUrl, true);
    xhr.timeout = 180000;

    // Real upload progress (network transmission)
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        var pct = Math.round((e.loaded / e.total) * 100);
        if (pct < 100) {
          setItemStatus(item.id, 'uploading', pct, `Uploading ${pct}%`);
          setFileStatus(item.id, 'uploading', pct);
          setUploadButtonState('uploading', { pct: pct, current: _progDone + 1, total: _progTotal });
        } else {
          // Transmission reached 100%, now waiting for server processing
          setItemStatus(item.id, 'processing', 100, 'Upload received. Processing & publishing…');
          setFileStatus(item.id, 'uploading', 100);
          setUploadButtonState('processing');
        }
        if (_progCurrentFile !== item.name) {
          _progCurrentFile = item.name;
          _progCurrentPct = 0;
        }
        _progCurrentPct = pct;
        updateProgressUI();
      }
    };

    xhr.upload.onload = function () {
      setItemStatus(item.id, 'processing', 100, 'Processing & publishing contribution…');
      setUploadButtonState('processing');
    };

    xhr.onload = function () {
      try {
        var r = JSON.parse(xhr.responseText);
        if (xhr.status === 200 && (r.success || r.document || r.secure_url)) {
          _progCurrentFile = '';
          _progCurrentPct = 0;
          uploadedFingerprints.add(fp);
          setFileStatus(item.id, 'done', 100);
          setItemStatus(item.id, 'done', 100, 'Published');

          var docData = r.document || (r.data ? {
            id: r.data.resource_id || r.data.record_id,
            title: r.data.title || item.name,
            url: r.data.resource_url || r.data.url,
            subject: r.data.subject,
            semester: r.data.semester,
            document_type: r.data.document_type
          } : { id: null, title: item.name, url: null });

          var contribData = r.contribution || (r.data ? {
            xp_earned: r.data.xp_gained || 1,
            total_xp: r.data.new_score || 0,
            total_contributions: r.data.total_contributions || 1
          } : { xp_earned: 1, total_xp: 0, total_contributions: 1 });

          resolve({
            ok: true,
            item: item,
            document: docData,
            contribution: contribData,
            xp: contribData.xp_earned,
            score: contribData.total_xp
          });

          if (typeof window.AbhiHubInvitePrompt === 'function') {
            try { window.AbhiHubInvitePrompt(); } catch (e) { }
          }
        } else {
          _progCurrentFile = '';
          _progCurrentPct = 0;
          var errMsg = r.message || r.error || 'Upload failed';
          setFileStatus(item.id, 'error', 0, errMsg);
          setItemStatus(item.id, 'error', 0, errMsg, true);
          resolve({ ok: false, msg: errMsg, item: item });
        }
      } catch (e) {
        _progCurrentFile = '';
        _progCurrentPct = 0;
        setFileStatus(item.id, 'error', 0, 'Invalid server response');
        setItemStatus(item.id, 'error', 0, 'Invalid server response', true);
        resolve({ ok: false, msg: 'Invalid response', item: item });
      }
    };

    xhr.onerror = function () {
      _progCurrentFile = '';
      _progCurrentPct = 0;
      if (retries > 0) {
        showToast('Network issue — retrying…', 'error');
        setItemStatus(item.id, 'validating', 0, 'Network issue — retrying…');
        setTimeout(function () { uploadOne(item, retries - 1).then(resolve); }, 1500);
      } else {
        setFileStatus(item.id, 'error', 0, 'Network error');
        setItemStatus(item.id, 'error', 0, 'Network connection interrupted', true);
        resolve({ ok: false, msg: 'Network error', item: item });
      }
    };

    xhr.ontimeout = function () {
      if (retries > 0) {
        showToast('Upload timed out — retrying…', 'error');
        setItemStatus(item.id, 'validating', 0, 'Timeout — retrying…');
        setTimeout(function () { uploadOne(item, retries - 1).then(resolve); }, 2000);
      } else {
        setFileStatus(item.id, 'error', 0, 'Timed out');
        setItemStatus(item.id, 'error', 0, 'Upload timed out. Check your connection.', true);
        resolve({ ok: false, msg: 'Upload timed out', item: item });
      }
    };

    var fd = buildFormData(item);
    if (sigRes && sigRes.success) {
      fd.append('api_key', sigRes.api_key);
      fd.append('timestamp', sigRes.timestamp);
      fd.append('signature', sigRes.signature);
      fd.append('folder', sigRes.folder);
      fd.append('file', item.file);
    }
    xhr.send(fd);
  });
}

function handleBeforeUnload(e) {
  if (isUploading) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadAbandoned('uploading');
    e.preventDefault(); e.returnValue = 'Upload in progress.';
  } else if (selectedFiles.length > 0) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadAbandoned('metadata');
  }
}

async function startBulkUpload(event) {
  if (event) event.preventDefault();
  if (isUploading) return; // Immediate duplicate click prevention

  // Immediately lock submit button synchronously
  setUploadButtonState('validating');

  if (!selectedFiles.length) {
    resetUploadButton();
    return showToast('Select at least one file', 'error');
  }

  // Validate all files have required metadata
  const missing = selectedFiles.filter(f => {
    const form = document.getElementById(`meta-form-${f.id}`);
    if (!form) return true;
    const type = form.querySelector('.meta-type')?.value;
    const col = form.querySelector('.college-select')?.value;
    const branch = form.querySelector('.branch-select')?.value;

    const subjEl = form.querySelector('.subject-select');
    const tsSubj = window.AbhiHubSelect?.instances[subjEl?.id];
    const subj = tsSubj ? tsSubj.getValue() : (subjEl ? subjEl.value : '');

    const prog = form.querySelector('.program-select')?.value;
    return !type || !col || !branch || !subj || !prog;
  });

  if (missing.length) {
    resetUploadButton();
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed('missing_metadata', 'validation_error', 'file');
    showToast('Fill required metadata (College, Department, Category, Subject) first', 'error');
    return;
  }

  // Extract batch
  const uploadBatch = [...selectedFiles];

  // Reset upload status modal for a fresh batch
  const statusList = document.getElementById('uploadStatusList');
  if (statusList) statusList.innerHTML = '';
  if (typeof updateStatusSummary === 'function') updateStatusSummary();

  // Build meta object for each item before upload to prevent DOM lookup issues later
  uploadBatch.forEach(f => {
    const form = document.getElementById(`meta-form-${f.id}`);
    if (form) {
      const subjEl = form.querySelector('.subject-select');
      const tsSubj = window.AbhiHubSelect?.instances[subjEl?.id];
      const subjId = tsSubj ? tsSubj.getValue() : (subjEl ? subjEl.value : '');
      const subjOpt = tsSubj ? tsSubj.options[subjId] : null;
      const subjText = subjOpt ? subjOpt.text : (subjEl && subjEl.selectedIndex >= 0 ? subjEl.options[subjEl.selectedIndex]?.text : '') || subjId || '';

      f.meta = {
        type: form.querySelector('.meta-type')?.value,
        college_id: form.querySelector('.college-select')?.value,
        branch_id: form.querySelector('.branch-select')?.value,
        subject: subjText
      };
    } else {
      f.meta = { type: 'unknown', subject: 'unknown' };
    }
  });

  openStatusModal();
  await processUploadBatch(uploadBatch);
}

window.retrySingleUpload = async function(id) {
  const item = selectedFiles.find(f => f.id === id);
  if (!item) return showToast('File no longer in queue', 'error');

  setItemStatus(id, 'validating', 0, 'Retrying…');
  const res = await uploadOne(item);
  if (res && res.ok) {
    updateStatusSummary();
  }
};

let activeUploads = 0;

async function processUploadBatch(batch) {
  activeUploads++;
  isUploading = true;
  window.addEventListener('beforeunload', handleBeforeUnload);

  openStatusModal();
  const statusList = document.getElementById('uploadStatusList');
  if (statusList) statusList.innerHTML = '';
  batch.forEach(item => ensureStatusItem(item.id, item.name));
  updateStatusSummary();

  const _gaMethod = batch.some(f => !f.file.lastModified || f.file.name.toLowerCase().startsWith('image')) ? 'camera' : 'file';

  if (typeof window.AbhiHubTracking !== 'undefined') {
    const _category = batch[0].meta.type || 'unknown';
    window.AbhiHubTracking.trackUploadStarted(batch.length, _gaMethod, _category);
  }

  let done = 0, failed = 0;
  const results = [];
  _progTotal = batch.length;
  _progDone = 0;
  _progBar = document.getElementById('uploadProgressBar');
  _progFloat = document.getElementById('floatingProgress');
  _progText = document.getElementById('uploadProgressText');
  const pBar = _progBar;

  const CONCURRENCY = 2;
  const queue = [...batch];
  const running = new Set();

  function processNext() {
    if (queue.length === 0 && running.size === 0) return;
    while (running.size < CONCURRENCY && queue.length > 0) {
      const item = queue.shift();
      running.add(item.id);
      uploadOne(item).then(res => {
        results.push(res);
        if (res.skipped) {
          // Skipped item
        } else if (res.ok) {
          done++;
          _progDone++;
          if (window.AbhiHubTracking && typeof window.AbhiHubTracking.trackUpload === 'function') {
            window.AbhiHubTracking.trackUpload(item.name, item.file?.type || 'image/jpeg', Math.round(((item.blob || item.file)?.size || 0) / 1024));
          }
        } else {
          failed++;
          if (window.AbhiHubTracking && typeof window.AbhiHubTracking.trackUploadFailed === 'function') {
            window.AbhiHubTracking.trackUploadFailed(res.msg || 'network_error', 'system_error', _gaMethod);
          }
        }
        if (pBar) pBar.style.width = `${((done + failed) / batch.length) * 100}%`;
        running.delete(item.id);
        processNext();
      });
    }
  }

  processNext();

  // Wait for all in-flight uploads to settle
  await new Promise(resolve => {
    const check = () => { if (running.size === 0) resolve(); else setTimeout(check, 50); };
    check();
  });

  activeUploads--;
  isUploading = false;
  window.removeEventListener('beforeunload', handleBeforeUnload);

  if (failed === 0 && done > 0) {
    setUploadButtonState('completed');

    const firstCol = batch[0].meta.college_id;
    const firstBranch = batch[0].meta.branch_id;
    if (firstCol && firstBranch && firstCol !== '__other__' && firstBranch !== '__other__') {
      fetch('/api/profile/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ college_id: firstCol, department_id: firstBranch })
      }).catch(e => console.error(e));
    }

    const successfulResults = results.filter(r => r.ok && !r.skipped);
    const totalXp = successfulResults.reduce((sum, r) => sum + (r.xp || 0), 0);
    const lastScore = successfulResults.slice(-1)[0]?.score || 0;
    const successfulDocs = successfulResults.map(r => r.document || { name: r.item?.name, title: r.item?.name });

    if (window.AbhiHubTracking) {
      const types = Array.from(new Set(batch.map(f => f.file?.type || 'image/jpeg'))).join(',');
      const totalSizeKb = Math.round(batch.reduce((sum, f) => sum + ((f.blob || f.file)?.size || 0), 0) / 1024);
      if (typeof window.AbhiHubTracking.trackUploadCompleted === 'function') {
        window.AbhiHubTracking.trackUploadCompleted(done, _gaMethod, types, totalSizeKb);
      }
      if (totalXp > 0 && typeof window.AbhiHubTracking.trackXpEarned === 'function') {
        window.AbhiHubTracking.trackXpEarned(totalXp, lastScore, done);
      }
    }

    if (typeof window.markUserUploaded === 'function') window.markUserUploaded();
    closeStatusModal();
    if (typeof showXpModal === 'function') {
      showXpModal(totalXp, lastScore, done, successfulDocs);
    }

  } else if (done > 0) {
    setUploadButtonState('failed');
    showToast(`${done} published, ${failed} failed. Click retry on failed items.`, 'error');
  } else {
    setUploadButtonState('failed');
    showToast('Upload could not be completed. Please check errors and retry.', 'error');
  }
}

// Mario Mini-Game
let marioAnim;
function startMarioGame() {
  const canvas = document.getElementById('marioCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let mario = { x: 50, y: 100, width: 20, height: 20, dy: 0, jumpPower: -10, grounded: false };
  let obstacles = [];
  let frame = 0;
  let score = 0;
  let gravity = 0.6;
  let isGameOver = false;

  function jump() {
    if (mario.grounded) { mario.dy = mario.jumpPower; mario.grounded = false; }
    else if (isGameOver) reset();
  }

  const jumpHandler = (e) => { if (e.code === 'Space' || e.type === 'touchstart') jump(); };
  window.addEventListener('keydown', jumpHandler);
  canvas.addEventListener('touchstart', jumpHandler);

  function reset() {
    mario.y = 100; mario.dy = 0; obstacles = []; score = 0; frame = 0; isGameOver = false;
    loop();
  }

  function loop() {
    if (!document.getElementById('marioCanvas')) {
      window.removeEventListener('keydown', jumpHandler);
      return;
    }
    if (isGameOver) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Ground (Brick style)
    ctx.fillStyle = '#8B4513';
    ctx.fillRect(0, 120, canvas.width, 30);
    ctx.fillStyle = '#A0522D';
    for (let i = 0; i < canvas.width; i += 20) { ctx.strokeRect(i, 120, 20, 15); ctx.strokeRect(i - 10, 135, 20, 15); }

    // Mario physics
    mario.dy += gravity;
    mario.y += mario.dy;
    if (mario.y + mario.height >= 120) {
      mario.y = 120 - mario.height;
      mario.dy = 0;
      mario.grounded = true;
    }

    // Draw Mario (Red Block with blue pants)
    ctx.fillStyle = '#ef4444'; // Red shirt
    ctx.fillRect(mario.x, mario.y, mario.width, mario.height * 0.6);
    ctx.fillStyle = '#3b82f6'; // Blue pants
    ctx.fillRect(mario.x, mario.y + mario.height * 0.6, mario.width, mario.height * 0.4);

    // Obstacles (Green Pipes)
    if (frame % 90 === 0) {
      obstacles.push({ x: canvas.width, width: 24, height: 25 + Math.random() * 25 });
    }

    ctx.fillStyle = '#22c55e'; // Pipe Green
    for (let i = 0; i < obstacles.length; i++) {
      let obs = obstacles[i];
      obs.x -= 4.0;
      // Draw pipe body
      ctx.fillRect(obs.x + 2, 120 - obs.height + 10, obs.width - 4, obs.height - 10);
      // Draw pipe lip
      ctx.fillRect(obs.x, 120 - obs.height, obs.width, 10);

      // Collision
      if (mario.x < obs.x + obs.width && mario.x + mario.width > obs.x &&
        mario.y < 120 && mario.y + mario.height > 120 - obs.height) {
        isGameOver = true;
      }
    }

    obstacles = obstacles.filter(obs => obs.x + obs.width > 0);

    // Score
    score++;
    ctx.fillStyle = '#1e293b';
    ctx.font = 'bold 16px monospace';
    ctx.fillText(`SCORE: ${Math.floor(score / 10)}`, canvas.width - 120, 30);

    if (isGameOver) {
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = 'white';
      ctx.font = 'bold 20px sans-serif';
      ctx.fillText("MAMA MIA! Tap to restart.", 70, 80);
    }

    frame++;
    marioAnim = requestAnimationFrame(loop);
  }

  cancelAnimationFrame(marioAnim);
  reset();
}

function setFloatStatus(show, text) {
  const el = document.getElementById('uploadFloat');
  if (!el) return;
  el.style.display = show ? 'flex' : 'none';
  const t = document.getElementById('uploadFloatText');
  if (t && text) t.textContent = text;
}

/* ── Upload Status Modal ── */
function openStatusModal() {
  const overlay = document.getElementById('uploadStatusModal');
  if (!overlay) return;
  overlay.style.display = 'flex';
  _statusModalOpen = true;
}

function closeStatusModal() {
  const overlay = document.getElementById('uploadStatusModal');
  if (overlay) overlay.style.display = 'none';
  _statusModalOpen = false;
}

function ensureStatusItem(id, name) {
  const list = document.getElementById('uploadStatusList');
  if (!list) return null;
  let el = document.getElementById('us-' + id);
  if (el) return el;
  el = document.createElement('div');
  el.id = 'us-' + id;
  el.className = 'upload-status-item';
  el.innerHTML = `
    <div class="upload-status-row">
      <div class="upload-status-name" title="${(name||'').replace(/"/g,'&quot;')}">${name||'File'}</div>
      <span class="upload-status-pill pending" id="us-pill-${id}">Pending</span>
    </div>
    <div class="upload-status-meta" id="us-meta-${id}"></div>
    <div class="upload-status-progress"><div class="upload-status-progress-fill" id="us-fill-${id}"></div></div>
    <div class="upload-status-actions-row" id="us-actions-${id}" style="display:none;"></div>
  `;
  list.appendChild(el);
  return el;
}

function setItemStatus(id, status, progress, msg, allowRetry) {
  const item = (typeof selectedFiles !== 'undefined' ? selectedFiles : []).find(f => f.id === id);
  const name = item ? item.name : 'File';
  ensureStatusItem(id, name);

  const pill = document.getElementById('us-pill-' + id);
  const fill = document.getElementById('us-fill-' + id);
  const meta = document.getElementById('us-meta-' + id);
  const actions = document.getElementById('us-actions-' + id);
  const el = document.getElementById('us-' + id);
  if (!el) return;

  if (pill) {
    pill.className = 'upload-status-pill ' + (status || 'pending');
    const map = {
      pending: '○ Pending',
      validating: '🔍 Checking…',
      uploading: (typeof progress === 'number' && progress > 0 && progress < 100) ? `⟳ Uploading ${progress}%` : '⟳ Uploading',
      processing: '⚡ Processing & publishing…',
      done: '✓ Published',
      error: '❌ Failed',
      skipped: '⏭️ Skipped',
      duplicate: '⚠️ Duplicate'
    };
    pill.textContent = map[status] || status;
  }

  if (fill) {
    fill.style.width = (typeof progress === 'number' ? Math.max(0, Math.min(100, progress)) : 0) + '%';
  }

  if (meta && typeof msg === 'string') {
    if (status === 'error') {
      meta.innerHTML = `<span class="error-msg">${msg}</span>`;
    } else {
      meta.textContent = msg;
    }
  }

  if (actions) {
    if (status === 'error' && allowRetry) {
      actions.innerHTML = `
        <button type="button" class="btn-retry-upload" onclick="retrySingleUpload('${id}')">🔄 Retry</button>
      `;
      actions.style.display = 'flex';
    } else if (status !== 'duplicate') {
      actions.style.display = 'none';
    }
  }

  el.classList.remove('is-done', 'is-error', 'is-processing', 'duplicate-prompt');
  if (status === 'done') el.classList.add('is-done');
  else if (status === 'error') el.classList.add('is-error');
  else if (status === 'processing') el.classList.add('is-processing');
  else if (status === 'duplicate') el.classList.add('duplicate-prompt');

  updateStatusSummary();
}

function updateStatusSummary() {
  const list = document.getElementById('uploadStatusList');
  const summary = document.getElementById('usSummary');
  const title = document.getElementById('usTitle');
  const subtitle = document.getElementById('usSubtitle');
  const closeBtn = document.getElementById('usClose');
  if (!list || !summary) return;
  const entries = Array.from(list.querySelectorAll('.upload-status-item'));
  const total = entries.length;
  const done = entries.filter(x => x.classList.contains('is-done')).length;
  const error = entries.filter(x => x.classList.contains('is-error')).length;
  const skipped = entries.filter(x => querySelectorOne(x, '.upload-status-pill') && querySelectorOne(x, '.upload-status-pill').classList.contains('skipped')).length;
  const uploading = entries.filter(x => querySelectorOne(x, '.upload-status-pill') && querySelectorOne(x, '.upload-status-pill').classList.contains('uploading')).length;
  const processing = entries.filter(x => querySelectorOne(x, '.upload-status-pill') && querySelectorOne(x, '.upload-status-pill').classList.contains('processing')).length;

  const parts = [];
  if (uploading) parts.push(`Uploading ${uploading}`);
  if (processing) parts.push(`Processing ${processing}`);
  if (done) parts.push(`${done} Published`);
  if (error) parts.push(`${error} Need Attention`);
  if (skipped) parts.push(`${skipped} Skipped`);

  summary.textContent = parts.join(' · ') || 'Preparing resources…';

  if (title) {
    if (error > 0 && (done + error + skipped === total)) title.textContent = 'Upload Completed with Issues';
    else if (done === total && total > 0) title.textContent = 'All Resources Published! 🎉';
    else if (processing > 0) title.textContent = 'Processing Contributions…';
    else title.textContent = 'Uploading Resources…';
  }
  if (subtitle) {
    subtitle.textContent = total ? `${done + error + skipped} of ${total} resources processed` : 'Please keep this window open';
  }
  if (closeBtn) closeBtn.style.display = (done + error + skipped) >= total && total > 0 ? 'inline-flex' : 'none';
}

function querySelectorOne(el, sel) {
  try { return el.querySelector(sel); } catch (e) { return null; }
}

function showDuplicatePrompt(item, existing) {
  const id = item.id;
  ensureStatusItem(id, item.name);
  setItemStatus(id, 'duplicate', 0, 'Duplicate detected');
  const el = document.getElementById('us-' + id);
  const actions = el ? el.querySelector('.upload-status-actions-row') : null;
  if (!actions) return;

  actions.innerHTML = `
    <button id="dup-skip-${id}">Skip this file</button>
    <button id="dup-continue-${id}">Upload anyway</button>
    <button id="dup-cancel-${id}">Cancel upload</button>
  `;
  actions.style.display = 'flex';

  return new Promise(function (resolve) {
    const done = function (choice) {
      actions.style.display = 'none';
      resolve(choice);
    };
    document.getElementById('dup-skip-' + id)?.addEventListener('click', function () { done('skip'); });
    document.getElementById('dup-continue-' + id)?.addEventListener('click', function () { done('continue'); });
    document.getElementById('dup-cancel-' + id)?.addEventListener('click', function () { done('cancel'); });
  });
}

/* ── Drag & drop ── */
function initDragDrop() {
  const da = document.getElementById('dropArea');
  if (!da) return;
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(n =>
    da.addEventListener(n, e => { e.preventDefault(); e.stopPropagation(); })
  );
  da.addEventListener('dragover', () => da.classList.add('drag-over'));
  da.addEventListener('dragleave', () => da.classList.remove('drag-over'));
  da.addEventListener('drop', e => { da.classList.remove('drag-over'); handleFilesSelected(e.dataTransfer.files); });
}

document.addEventListener('DOMContentLoaded', function () {
  initDragDrop();

  const usClose = document.getElementById('usClose');
  const usMinimize = document.getElementById('usMinimize');
  const usOverlay = document.getElementById('uploadStatusModal');
  if (usClose) usClose.addEventListener('click', function () { closeStatusModal(); });
  if (usMinimize) usMinimize.addEventListener('click', function () { closeStatusModal(); });
  if (usOverlay) usOverlay.addEventListener('click', function (e) { if (e.target === usOverlay) closeStatusModal(); });
});

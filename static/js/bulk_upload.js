'use strict';

let selectedFiles        = [];
let isUploading          = false;
let cropperInst          = null;
let currentCropId        = null;
let currentMetaId        = null;
let uploadedFingerprints = new Set(); // duplicate guard (session-scoped)

function fileFingerprint(item) {
  var f = item.file;
  return [f.name, f.size, f.lastModified || 0].join('|');
}

function fmtSize(b) {
  if (b < 1024) return b + 'B';
  if (b < 1048576) return (b/1024).toFixed(1) + 'KB';
  return (b/1048576).toFixed(2) + 'MB';
}
function uid() {
  return 'f_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
}
function gv(id) { return (document.getElementById(id)||{}).value || ''; }

async function computeFileHash(file) {
  try {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  } catch(e) {
    console.error("Hashing failed", e);
    return fileFingerprint({file: file}); // Fallback
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

  var item = selectedFiles.filter(function(f) { return f.id === id; })[0];
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
  d.className = 'bu-toast bu-toast-' + (type||'info');
  d.textContent = msg;
  c.appendChild(d);
  setTimeout(() => d.remove(), 4000);
}

/* ── File selection ── */
function handleFilesSelected(filesOrEvent) {
  const files = (filesOrEvent && filesOrEvent.type && filesOrEvent.type.startsWith('change') && filesOrEvent.target)
    ? filesOrEvent.target.files
    : filesOrEvent;
  // Type is read from the most recent meta-form (per-file, not global)
  // Detect camera captures (no lastModified or name starts with 'image')
  const fromCamera = Array.from(files).some(f =>
    !f.lastModified || f.name.toLowerCase().startsWith('image') || f.name.toLowerCase() === 'blob'
  );
  if (fromCamera && typeof window.AbhiHubTracking !== 'undefined') {
    window.AbhiHubTracking.trackCameraUpload();
  }
  Array.from(files).forEach(file => {
    // Per-file type from the most recent meta-form (if any)
    const activeForm = document.querySelector('.meta-form-wrap[style*="display: block"]');
    const typeEl = activeForm?.querySelector('.meta-type');
    const selType = typeEl ? typeEl.value : '';
    const imgOnly = ['papers','practical'].includes(selType.toLowerCase());
    if (imgOnly && !file.type.startsWith('image/')) {
      return showToast(file.name + ': images only for this type', 'error');
    }
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      return showToast(file.name + ': unsupported type', 'error');
    }
    if (file.size > 50*1024*1024) return showToast(file.name + ': exceeds 50 MB', 'error');

    const newItem = {
      id: uid(), file, blob: null, name: file.name, cropped: false, status: 'pending'
    };
    selectedFiles.push(newItem);

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

        // Wire dynamic fields for THIS file's category (notes/papers/practical)
        updateDynamicFieldsForForm(addedWrap);
    }
    
    // Phase 5: AI Metadata Prediction (Async)
    fetch('/api/ai/predict-metadata', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name })
    }).then(r => r.json()).then(data => {
      if (data.success && data.prediction) {
        const p = data.prediction;
        const form = document.getElementById(`meta-form-${newItem.id}`);
        if (!form) return;
        
        if (p.type) {
            const typeEl = form.querySelector('.meta-type');
            if (typeEl && !typeEl.value) typeEl.value = p.type;
        }
        if (p.unit) {
            const unitEl = form.querySelector('.meta-unit');
            if (unitEl && !unitEl.value) {
                // simple assignment, may need updateMetaUnit call logic but skipping for brevity
                unitEl.innerHTML = `<option value="${p.unit}">${p.unit}</option>`;
                unitEl.value = p.unit;
            }
        }
        if (p.year) {
            const yearEl = form.querySelector('.meta-year');
            if (yearEl) yearEl.value = p.year;
        }
        if (p.subject_id) {
           const subjEl = form.querySelector('.subject-select');
           const tsSubj = window.AbhiHubSelect?.instances[subjEl?.id];
           if (tsSubj) {
               if (!tsSubj.options[p.subject_id]) tsSubj.addOption({value: p.subject_id, text: p.subject || 'Loading...'});
               tsSubj.setValue(p.subject_id, true); // silent set
           } else if (subjEl) {
               subjEl.value = p.subject_id;
           }
        }
        
        showToast('🤖 AI auto-filled metadata for ' + newItem.name, 'info');
      }
    }).catch(e => console.warn("AI predict error:", e));
  });

  if (selectedFiles.length > 0) {
    document.getElementById('uploadCarousel').style.display = 'flex';
    document.querySelector('.upload-defaults-toggle')?.remove();
    renderCarousel(selectedFiles.length - 1); // Go to the newest file
  }
}

function removeFile(id) {
  selectedFiles = selectedFiles.filter(f => f.id !== id);
  if (selectedFiles.length === 0) {
    document.getElementById('uploadCarousel').style.display = 'none';
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
  const item = selectedFiles[carouselIndex];
  
  // Remove the isolated form
  const form = document.getElementById(`meta-form-${item.id}`);
  if (form) form.remove();
  
  removeFile(item.id);
}

function renderCarousel(index) {
  if (selectedFiles.length === 0) {
    document.getElementById('uploadCarousel').style.display = 'none';
    return;
  }
  carouselIndex = index;
  const item = selectedFiles[index];
  
  document.getElementById('carouselFilename').textContent = item.name + (item.cropped ? ' (Cropped)' : '');
  const cImg = document.getElementById('carouselImg');
  const metricEl = document.getElementById('carouselMetric');
  cImg.src = carouselImageSrc(item);
  cImg.style.transform = `rotate(${item.rotation || 0}deg)`;

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

  document.getElementById('cCounter').textContent = (index + 1) + ' / ' + selectedFiles.length;
  document.getElementById('cPrevBtn').disabled = (index === 0);
  document.getElementById('cNextBtn').disabled = (index === selectedFiles.length - 1);
}

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
  var unitG  = formWrap.querySelector('.meta-unit-wrap');
  var pracG  = formWrap.querySelector('.meta-practical-wrap');
  var unitSel = formWrap.querySelector('.meta-unit');

  if (!typeEl) return;
  var type = (typeEl.value || '').toLowerCase();

  if (unitG) unitG.style.display = 'none';
  if (pracG) pracG.style.display = 'none';

  if (type === 'notes') {
    if (unitG) unitG.style.display = 'block';
    if (unitSel) unitSel.innerHTML = '<option value="U1">Unit 1</option><option value="U2">Unit 2</option><option value="U3">Unit 3</option><option value="U4">Unit 4</option><option value="U5">Unit 5</option><option value="All">All Units</option>';
  } else if (type === 'papers') {
    if (unitG) unitG.style.display = 'block';
    if (unitSel) unitSel.innerHTML = '<option value="CAE1">CAE-1</option><option value="CAE2">CAE-2</option><option value="CAE3">CAE-3</option><option value="ESE">End Sem/Resit</option>';
  } else if (type === 'practical') {
    if (pracG) pracG.style.display = 'grid';
  }
}

function navigateCarousel(dir) {
  let newIdx = carouselIndex + dir;
  if (newIdx < 0) newIdx = 0;
  if (newIdx >= selectedFiles.length) newIdx = selectedFiles.length - 1;
  renderCarousel(newIdx);
}

function rotateCarousel(deg) {
  if (cropperInst) {
    cropperInst.rotate(deg);
  } else {
    const imgEl = document.getElementById('carouselImg');
    carouselRotation = (carouselRotation + deg) % 360;
    imgEl.style.transform = `rotate(${carouselRotation}deg)`;
  }
}

function toggleCarouselCrop() {
  const img = document.getElementById('carouselImg');
  if (cropperInst) {
    // Apply crop
    cropperInst.getCroppedCanvas({ maxWidth:2400, maxHeight:2400, imageSmoothingQuality:'high' })
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
    cropperInst = new Cropper(img, { viewMode:1, movable:true, zoomable:true, rotatable:true });
  }
}

/* ── Upload ── */
/**
 * Client-side compression for the carousel preview only.
 * The server (cloudinary_upload.py) owns the authoritative
 * compression + EXIF strip, so we keep this light: just
 * downsample very large images for a smoother preview, never
 * re-encoding if the file is already small.
 */
async function compressImage(fileObj, quality) {
  quality = quality || 0.82;
  return new Promise(function(resolve) {
    if (!fileObj.type.startsWith('image/')) return resolve(fileObj);
    var img = new Image();
    img.onload = function() {
      var MAX = 1600;
      var scaleW = img.width > MAX ? MAX / img.width : 1;
      var scaleH = img.height > MAX ? MAX / img.height : 1;
      var scale  = Math.min(scaleW, scaleH, 1);
      if (scale >= 1) return resolve(fileObj); // already small enough
      var canvas = document.createElement('canvas');
      canvas.width  = Math.round(img.width  * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function(blob) { resolve(blob || fileObj); }, 'image/jpeg', quality);
    };
    img.onerror = function() { resolve(fileObj); };
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

      m = {
          type: typeEl ? typeEl.value : '',
          year: yearEl ? yearEl.value : '2025',
          unit: unitEl ? unitEl.value : '',
          college_id: colEl ? colEl.value : '',
          branch_id: branchEl ? branchEl.value : '',
          semester: semEl ? semEl.value : '',
          subject_id: subjId,
          subject: subjText,
          program: progEl ? progEl.value : 'b.tech'
      };
  }

  fd.append('college_id', m.college_id || '');
  fd.append('branch_id',  m.branch_id || '');
  fd.append('semester',   m.semester  || '');
  fd.append('subject',    m.subject   || '');
  fd.append('subject_id', m.subject_id || '');
  fd.append('year',       m.year      || '2025');
  fd.append('program',    m.program   || 'b.tech');
  fd.append('type',       m.type      || '');
  fd.append('document_type', m.type   || '');
  fd.append('unit',       m.unit      || '');
  // CSRF protection — the form's hidden input holds the token;
  // grab it from the DOM so the XHR is not rejected.
  const _csrfEl = document.querySelector('input[name="csrf_token"]');
  if (_csrfEl) fd.append('csrf_token', _csrfEl.value);
  // Optional metadata the duplicate-detection hash (if JS computed one)
  if (item.fileHash) fd.append('file_hash', item.fileHash);
  // Optional academic extras (exam_type, subject_code) — only if present
  const _examEl = form ? form.querySelector('[name="exam_type"]') : null;
  if (_examEl && _examEl.value) fd.append('exam_type', _examEl.value);
  const _codeEl = form ? form.querySelector('[name="subject_code"]') : null;
  if (_codeEl && _codeEl.value) fd.append('subject_code', _codeEl.value);
  const origName  = item.name || (item.file && item.file.name) || `file_${Date.now()}`;
  const ext       = origName.includes('.') ? origName.split('.').pop().toLowerCase() : 'jpg';
  const sanitize  = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const code      = sanitize(m.subject || '');
  const docType   = sanitize(m.type || '');
  const year      = sanitize(m.year || '2025');
  const unit      = sanitize(m.unit || '');
  const parts     = [code, docType, year];
  if (unit) parts.push(unit);
  const cleanName = parts.filter(Boolean).join('_') || sanitize(origName.replace(/\.[^.]+$/, ''));
  const finalName = `${cleanName}.${ext}`;

  let fileObj = item.blob || item.file;
  if (!(fileObj instanceof File)) {
    fileObj = new File([fileObj], finalName, { type: fileObj.type || 'image/jpeg' });
  } else {
    fileObj = new File([fileObj], finalName, { type: fileObj.type });
  }
  fd.append('upload_document', fileObj, finalName);
  return fd;
}


async function uploadOne(item, retries) {
  retries = (retries === undefined) ? 2 : retries;

  if (!item.meta || !item.meta.subject || !item.meta.type) {
    setFileStatus(item.id, 'error', 0, 'Fill metadata first');
    showToast(item.name + ': fill metadata (📝) first', 'error');
    return { ok: false, msg: 'Missing metadata' };
  }

  // Duplicate guard — skip if already uploaded this session
  var fp = fileFingerprint(item);
  if (uploadedFingerprints.has(fp)) {
    setFileStatus(item.id, 'done', 100);
    showToast((item.name || 'File') + ': already uploaded, skipping', 'info');
    return { ok: true, xp: 0, score: 0 };
  }

  // ── Client-side preview compression (carousels only) ───────────────
  // We NEVER modify item.file — that stays the original so the
  // server (cloudinary_upload.py) is the single authority on
  // compression + EXIF strip. We only produce a lighter preview
  // blob for the carousel so large photos don't choke the tab.
  var rawFile = item.file;
  if (rawFile && rawFile.type && rawFile.type.startsWith('image/') && rawFile.size > 500 * 1024) {
    var preview = await compressImage(rawFile);
    if (preview && preview !== rawFile && preview.size > 0) {
      item.previewBlob = preview;
      item.compression = {
        label: `Preview ${((1 - preview.size / rawFile.size) * 100).toFixed(0)}%`,
        cls: 'compressed'
      };
    } else if (preview && preview.size === 0) {
      console.warn('[upload] Preview compression returned empty blob, skipping.');
    }
  }

  // Zero-byte guard (on original, not preview)
  if (!rawFile || rawFile.size === 0) {
    setFileStatus(item.id, 'error', 0, 'File is empty');
    showToast((item.name || 'File') + ': empty file, cannot upload', 'error');
    return { ok: false, msg: 'Empty file' };
  }

  // Phase 8: Duplicate Detection — hash the ORIGINAL file
  setFloatStatus(true, `Checking duplicates for ${item.name}...`);
  item.fileHash = await computeFileHash(rawFile);
  try {
    const dupCheck = await fetch('/api/check-duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: item.fileHash })
    }).then(r => r.json());

    if (dupCheck.success && dupCheck.is_duplicate) {
       setFileStatus(item.id, 'error', 0, 'Duplicate File Found');
       showToast((item.name || 'File') + ': exact duplicate already exists!', 'error');
       return { ok: false, msg: 'Duplicate detected' };
    }
  } catch (e) {
    console.warn("Duplicate check failed, continuing upload", e);
  }

  return new Promise(function(resolve) {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload', true);
    xhr.timeout = 45000;
    xhr.upload.onprogress = function(e) {
      if (e.lengthComputable) {
        setFileStatus(item.id, 'uploading', Math.round(e.loaded / e.total * 100));
        if (_progCurrentFile !== item.name) {
          _progCurrentFile = item.name;
          _progCurrentPct = 0;
        }
        _progCurrentPct = Math.round(e.loaded / e.total * 100);
        updateProgressUI();
      }
    };
    xhr.onload = function() {
      try {
        var r = JSON.parse(xhr.responseText);
        if (xhr.status === 200 && r.success) {
          _progCurrentFile = '';
          _progCurrentPct = 0;
          uploadedFingerprints.add(fp);
          setFileStatus(item.id, 'done', 100);
          resolve({ ok: true, xp: (r.data && r.data.xp_gained) || 0, score: (r.data && r.data.new_score) || 0 });
          if (typeof window.AbhiHubInvitePrompt === 'function') {
            try { window.AbhiHubInvitePrompt(); } catch (e) {}
          }
        } else {
          _progCurrentFile = '';
          _progCurrentPct = 0;
          setFileStatus(item.id, 'error', 0, r.message || 'Failed');
          resolve({ ok: false, msg: r.message });
        }
      } catch(e) {
        _progCurrentFile = '';
        _progCurrentPct = 0;
        setFileStatus(item.id, 'error', 0, 'Invalid response');
        resolve({ ok: false, msg: 'Invalid response' });
      }
    };
    xhr.onerror = function() {
      _progCurrentFile = '';
      _progCurrentPct = 0;
      if (retries > 0) {
        showToast('Network error — retrying…', 'error');
        setTimeout(function() { uploadOne(item, retries - 1).then(resolve); }, 1500);
      } else {
        setFileStatus(item.id, 'error', 0, 'Network error');
        resolve({ ok: false });
      }
    };
    xhr.ontimeout = function() {
      if (retries > 0) {
        showToast('Upload timed out — retrying…', 'error');
        setTimeout(function() { uploadOne(item, retries - 1).then(resolve); }, 2000);
      } else {
        setFileStatus(item.id, 'error', 0, 'Timed out');
        resolve({ ok: false, msg: 'Upload timed out' });
      }
    };
    xhr.send(buildFormData(item));
  });
}

function handleBeforeUnload(e) {
  if (isUploading) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadAbandoned('uploading');
    e.preventDefault(); e.returnValue='Upload in progress.';
  } else if (selectedFiles.length > 0) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadAbandoned('metadata');
  }
}

async function startBulkUpload(event) {
    event.preventDefault();
    if (!selectedFiles.length) return showToast('Select at least one file', 'error');
  
    // Validate all have required metadata (including college and branch now)
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
      if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed('missing_metadata', 'validation_error', 'file');
      showToast('Fill metadata (College, Department, Category, Subject) for all image(s) first', 'error');
      return;
    }
  
  // Extract batch
  const uploadBatch = [...selectedFiles];
  
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

  // Show floating progress pill offering the game
  let overlay = document.getElementById('uploadOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'uploadOverlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(15,23,42,0.95);z-index:99999;display:none;flex-direction:column;align-items:center;justify-content:center;color:white;font-family:system-ui, sans-serif;';
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <button id="minimizeUploadBtn" data-action="minimizeUploadOverlay" class="upload-overlay-minimize-btn" aria-label="Minimize upload progress">&minus;</button>
    <h2 id="uploadProgressText" style="margin-bottom:10px; font-weight:700;">Uploading 0 / ${uploadBatch.length}</h2>
    <div style="width:300px;background:#334155;height:24px;border-radius:12px;overflow:hidden;margin-bottom:30px;box-shadow:inset 0 2px 4px rgba(0,0,0,0.5);">
        <div id="uploadProgressBar" style="width:0%;height:100%;background:linear-gradient(90deg, #ef4444, #f59e0b);transition:width 0.3s ease;"></div>
    </div>
    <div style="background:#1e293b; padding:20px; border-radius:16px; border:1px solid #334155; text-align:center;">
        <p style="margin-bottom:15px;color:#cbd5e1;font-weight:600;">Play Super Abhi Bros while you wait! (Tap/Space to jump)</p>
        <canvas id="marioCanvas" width="400" height="150" style="background:#87CEEB;border-radius:8px;box-shadow:0 10px 25px rgba(0,0,0,0.5);"></canvas>
    </div>
  `;
  
  let floatingProgress = document.getElementById('floatingProgress');
  if (!floatingProgress) {
      floatingProgress = document.createElement('div');
      floatingProgress.id = 'floatingProgress';
      floatingProgress.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#2563eb;color:white;padding:12px 20px;border-radius:30px;font-weight:bold;box-shadow:0 4px 15px rgba(0,0,0,0.3);z-index:99998;display:none;cursor:pointer;transition:transform 0.2s;';
      floatingProgress.onmouseover = () => floatingProgress.style.transform = 'scale(1.05)';
      floatingProgress.onmouseout = () => floatingProgress.style.transform = 'scale(1)';
      floatingProgress.onclick = () => { overlay.style.display = 'flex'; floatingProgress.style.display = 'none'; startMarioGame(); };
      document.body.appendChild(floatingProgress);
  }
  
  // Show the pill, keep the overlay hidden
  overlay.style.display = 'none';
  floatingProgress.style.display = 'block';
  floatingProgress.innerHTML = `Uploading 0 / ${uploadBatch.length} &mdash; Play Game 🎮`;
  
  await processUploadBatch(uploadBatch);
}

window.minimizeUploadOverlay = function() {
    document.getElementById('uploadOverlay').style.display = 'none';
    const floating = document.getElementById('floatingProgress');
    if (floating) floating.style.display = 'block';
};

let activeUploads = 0;

async function processUploadBatch(batch) {
  activeUploads++;
  isUploading = true;
  window.addEventListener('beforeunload', handleBeforeUnload);
  
  const _gaMethod = batch.some(f => !f.file.lastModified || f.file.name.toLowerCase().startsWith('image')) ? 'camera' : 'file';
  
  if (typeof window.AbhiHubTracking !== 'undefined') {
    const _category = batch[0].meta.type || 'unknown';
    window.AbhiHubTracking.trackUploadStarted(batch.length, _gaMethod, _category);
  }

  let done=0, failed=0;
  const results = [];
  const pText = document.getElementById('uploadProgressText');
  const pBar = document.getElementById('uploadProgressBar');
  const fProg = document.getElementById('floatingProgress');

  // Bounded concurrency — upload up to 2 files simultaneously so the
  // connection isn't saturated and each file still gets per-file progress.
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
        if (res.ok) { done++; if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUpload(item.name, item.file.type || 'image/jpeg', Math.round((item.blob || item.file).size / 1024)); }
        else { failed++; if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed(res.msg || 'network_error', 'system_error', _gaMethod); }
        if (pBar) pBar.style.width = `${((done+failed)/batch.length)*100}%`;
        running.delete(item.id);
        processNext();
      });
    }
  }

  for (const item of batch) {
    if (pText) pText.innerText = `Uploading 0 / ${batch.length}`;
    if (fProg) fProg.innerHTML = `Uploading 0 / ${batch.length} &mdash; Play Game 🎮`;
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

  // Hide progress elements
  if (fProg) fProg.style.display = 'none';
  const ov = document.getElementById('uploadOverlay');
  if (ov) ov.style.display = 'none';

  if (failed === 0 && done > 0) {
    const firstCol = batch[0].meta.college_id;
    const firstBranch = batch[0].meta.branch_id;
    if (firstCol && firstBranch && firstCol !== '__other__' && firstBranch !== '__other__') {
      fetch('/api/profile/update', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ college_id: firstCol, department_id: firstBranch })
      }).catch(e => console.error(e));
    }

    const totalXp = results.filter(r => r.ok).reduce((sum, r) => sum + (r.xp || 0), 0);
    const lastScore = results.filter(r => r.ok).slice(-1)[0]?.score || 0;
    
    if (typeof window.AbhiHubTracking !== 'undefined') {
      const types = Array.from(new Set(batch.map(f => f.file.type || 'image/jpeg'))).join(',');
      const totalSizeKb = Math.round(batch.reduce((sum, f) => sum + (f.blob || f.file).size, 0) / 1024);
      window.AbhiHubTracking.trackUploadCompleted(done, _gaMethod, types, totalSizeKb);
      if (totalXp > 0) window.AbhiHubTracking.trackXpEarned(totalXp, lastScore, done);
    }
    
    if (typeof window.markUserUploaded === 'function') window.markUserUploaded();
    if (typeof showXpModal === 'function') showXpModal(totalXp, lastScore, done);
    
    // Clear the UI cards after a slight delay so user sees the checkmarks
    setTimeout(() => {
        selectedFiles.length = 0; 
        document.getElementById('uploadCarousel').style.display = 'none';
    }, 2000);
    
  } else if (done > 0) {
    showToast(`${done} succeeded, ${failed} failed.`, 'error');
  } else {
    showToast('Upload failed. Please try again.', 'error');
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
    
    const jumpHandler = (e) => { if(e.code === 'Space' || e.type === 'touchstart') jump(); };
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
        for(let i=0; i<canvas.width; i+=20) { ctx.strokeRect(i, 120, 20, 15); ctx.strokeRect(i-10, 135, 20, 15); }

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
            obstacles.push({ x: canvas.width, width: 24, height: 25 + Math.random()*25 });
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
        ctx.fillText(`SCORE: ${Math.floor(score/10)}`, canvas.width - 120, 30);
        
        if (isGameOver) {
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(0,0,canvas.width, canvas.height);
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

/* ── Drag & drop ── */
function initDragDrop() {
  const da = document.getElementById('dropArea');
  if (!da) return;
  ['dragenter','dragover','dragleave','drop'].forEach(n =>
    da.addEventListener(n, e => { e.preventDefault(); e.stopPropagation(); })
  );
  da.addEventListener('dragover',  () => da.classList.add('drag-over'));
  da.addEventListener('dragleave', () => da.classList.remove('drag-over'));
  da.addEventListener('drop', e => { da.classList.remove('drag-over'); handleFilesSelected(e.dataTransfer.files); });
}

document.addEventListener('DOMContentLoaded', initDragDrop);

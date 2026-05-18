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
function handleFilesSelected(files) {
  const imgOnly = ['papers','practical'].includes(gv('type').toLowerCase());
  // Detect camera captures (no lastModified or name starts with 'image')
  const fromCamera = Array.from(files).some(f =>
    !f.lastModified || f.name.toLowerCase().startsWith('image') || f.name.toLowerCase() === 'blob'
  );
  if (fromCamera && typeof window.AbhiHubTracking !== 'undefined') {
    window.AbhiHubTracking.trackCameraUpload();
  }
  Array.from(files).forEach(file => {
    if (imgOnly && !file.type.startsWith('image/')) {
      return showToast(file.name + ': images only for this type', 'error');
    }
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      return showToast(file.name + ': unsupported type', 'error');
    }
    if (file.size > 50*1024*1024) return showToast(file.name + ': exceeds 50 MB', 'error');

    const newItem = {
      id: uid(), file, blob: null, name: file.name, cropped: false, status: 'pending',
      meta: { subject: gv('subject'), year: gv('Year')||'2025', type: gv('type'), unit: gv('unit') }
    };
    selectedFiles.push(newItem);

    // If meta is incomplete (camera or browse without defaults set), auto-open modal
    if (!newItem.meta.subject || !newItem.meta.type) {
      renderGrid();
      setTimeout(() => openMetaModal(newItem.id), 80);
    }
  });
  renderGrid();
}

function removeFile(id) {
  selectedFiles = selectedFiles.filter(f => f.id !== id);
  renderGrid();
}

/* ── Grid ── */
function renderGrid() {
  const grid = document.getElementById('fileGrid');
  if (!grid) return;
  if (!selectedFiles.length) { grid.style.display = 'none'; return; }
  grid.style.display = 'grid';

  grid.innerHTML = selectedFiles.map(item => {
    const src    = URL.createObjectURL(item.blob || item.file);
    const isImg  = item.file.type.startsWith('image/');
    const mFill  = item.meta && item.meta.subject && item.meta.type;
    const mLabel = mFill ? (item.meta.subject.slice(0,10) + (item.meta.unit ? ' / '+item.meta.unit : '')) : '⚠ Add info';
    return `
    <div class="bu-thumb ${item.status==='done'?'bu-done':''} ${item.status==='error'?'bu-error':''}" id="thumb_${item.id}">
      <div class="bu-thumb-img">
        ${isImg ? `<img src="${src}" alt="">` : '<div class="bu-pdf-icon">📄</div>'}
        ${item.cropped ? '<span class="bu-badge">✂</span>' : ''}
        <div class="bu-thumb-actions">
          ${isImg ? `<button type="button" onclick="openCrop('${item.id}')">✂</button>` : ''}
          <button type="button" onclick="openMetaModal('${item.id}')">📝</button>
          <button type="button" onclick="removeFile('${item.id}')">🗑</button>
        </div>
      </div>
      <div class="bu-meta-bar ${mFill?'meta-ok':'meta-warn'}" onclick="openMetaModal('${item.id}')">
        ${mFill ? '✅ ' : '⚠️ '}<span>${mLabel}</span>
      </div>
      <div class="bu-bar-wrap" id="bar_${item.id}" style="display:none">
        <div class="bu-bar-fill" id="fill_${item.id}"></div>
      </div>
      <div class="bu-status" id="st_${item.id}"></div>
    </div>`;
  }).join('');
}

function setFileStatus(id, status, pct, msg) {
  const bar  = document.getElementById('bar_'+id);
  const fill = document.getElementById('fill_'+id);
  const st   = document.getElementById('st_'+id);
  const thm  = document.getElementById('thumb_'+id);
  if (!bar) return;
  bar.style.display = 'block';
  if (status === 'uploading') { fill.style.width = pct+'%'; if(st) st.textContent = pct+'%'; }
  else if (status === 'done')  { fill.style.width='100%'; fill.style.background='#10b981'; if(st) st.textContent='✓'; if(thm) thm.classList.add('bu-done'); }
  else if (status === 'error') { fill.style.width='100%'; fill.style.background='#ef4444'; if(st) st.textContent=msg||'✗'; if(thm) thm.classList.add('bu-error'); }
}

/* ── Per-image metadata modal ── */
function openMetaModal(id) {
  currentMetaId = id;
  const item = selectedFiles.find(f => f.id === id);
  if (!item) return;
  const m = item.meta || {};
  const el = id => document.getElementById(id);
  el('metaModalTitle').textContent = '📝 ' + item.name;
  el('metaSubject').value = m.subject || gv('subject');
  el('metaYear').value    = m.year    || gv('Year') || '2025';
  el('metaType').value    = m.type    || gv('type') || '';
  updateMetaUnit();
  el('metaUnit').value    = m.unit    || gv('unit') || '';
  el('metaModal').style.display = 'flex';
}

function updateMetaUnit() {
  const type = gv('metaType');
  const wrap = document.getElementById('metaUnitWrap');
  const sel  = document.getElementById('metaUnit');
  if (type === 'notes') {
    wrap.style.display = 'block';
    sel.innerHTML = '<option value="U1">Unit 1</option><option value="U2">Unit 2</option><option value="U3">Unit 3</option><option value="U4">Unit 4</option><option value="U5">Unit 5</option><option value="All">All Units</option>';
  } else if (type === 'papers') {
    wrap.style.display = 'block';
    sel.innerHTML = '<option value="CAE1">CAE-1</option><option value="CAE2">CAE-2</option><option value="CAE3">CAE-3</option><option value="ESE">End Sem/Resit</option>';
  } else {
    wrap.style.display = 'none';
  }
}

function saveMetaModal() {
  if (!currentMetaId) return;
  const subj = (document.getElementById('metaSubject')||{}).value?.trim();
  const type = gv('metaType');
  if (!subj || !type) return showToast('Subject and Category are required', 'error');
  const idx = selectedFiles.findIndex(f => f.id === currentMetaId);
  if (idx !== -1) {
    selectedFiles[idx].meta = { subject: subj, year: gv('metaYear')||'2025', type, unit: gv('metaUnit') };
  }
  closeMetaModal();
  renderGrid();
}

function closeMetaModal() {
  document.getElementById('metaModal').style.display = 'none';
  currentMetaId = null;
}

/* ── Crop ── */
function openCrop(id) {
  currentCropId = id;
  const item = selectedFiles.find(f => f.id === id);
  if (!item) return;
  const img = document.getElementById('cropImg');
  img.src = URL.createObjectURL(item.blob || item.file);
  document.getElementById('cropModal').style.display = 'flex';
  setTimeout(() => {
    if (cropperInst) cropperInst.destroy();
    cropperInst = new Cropper(img, { viewMode:1, movable:true, zoomable:true, rotatable:true });
  }, 150);
}

function closeCropModal() {
  if (cropperInst) { cropperInst.destroy(); cropperInst = null; }
  document.getElementById('cropModal').style.display = 'none';
  currentCropId = null;
}

function rotateCrop(deg) { if (cropperInst) cropperInst.rotate(deg); }

function applyCrop() {
  if (!cropperInst || !currentCropId) return;
  cropperInst.getCroppedCanvas({ maxWidth:2400, maxHeight:2400, imageSmoothingQuality:'high' })
    .toBlob(blob => {
      const idx = selectedFiles.findIndex(f => f.id === currentCropId);
      if (idx !== -1) { selectedFiles[idx].blob = blob; selectedFiles[idx].cropped = true; }
      closeCropModal(); renderGrid();
    }, 'image/jpeg', 0.92);
}

/* ── Upload ── */
async function compressImage(fileObj, quality) {
  quality = quality || 0.72;
  return new Promise(function(resolve) {
    if (!fileObj.type.startsWith('image/')) return resolve(fileObj);
    var img = new Image();
    img.onload = function() {
      var MAX = 1280;
      var scale = img.width > MAX ? MAX / img.width : 1;
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
  fd.append('college_id', gv('college_id'));
  fd.append('branch_id',  gv('branch_id'));
  const m = item.meta || {};
  fd.append('subject',       m.subject || '');
  fd.append('Year',          m.year    || '2025');
  fd.append('type',          m.type    || '');
  fd.append('document_type', m.type    || '');
  fd.append('unit',          m.unit    || '');
  let fileObj = item.blob || item.file;
  const fileName = item.name || (fileObj && fileObj.name) || `camera_${Date.now()}.jpg`;
  if (!(fileObj instanceof File)) {
    fileObj = new File([fileObj], fileName, { type: fileObj.type || 'image/jpeg' });
  }
  fd.append('upload_document', fileObj, fileName);
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

  // Compress image before building FormData
  var rawFile = item.blob || item.file;
  if (rawFile && rawFile.type && rawFile.type.startsWith('image/') && rawFile.size > 500 * 1024) {
    var compressed = await compressImage(rawFile);
    if (compressed && compressed !== rawFile && compressed.size > 0) {
      item.blob = compressed;
    } else if (compressed && compressed.size === 0) {
      // Compression failed silently — keep original
      console.warn('[upload] Compression returned empty blob, using original.');
    }
  }

  // Zero-byte guard
  var finalFile = item.blob || item.file;
  if (!finalFile || finalFile.size === 0) {
    setFileStatus(item.id, 'error', 0, 'File is empty');
    showToast((item.name || 'File') + ': empty file, cannot upload', 'error');
    return { ok: false, msg: 'Empty file' };
  }

  return new Promise(function(resolve) {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload', true);
    xhr.timeout = 45000; // 45s — covers slow mobile 3G
    xhr.upload.onprogress = function(e) {
      if (e.lengthComputable) setFileStatus(item.id, 'uploading', Math.round(e.loaded / e.total * 100));
    };
    xhr.onload = function() {
      try {
        var r = JSON.parse(xhr.responseText);
        if (xhr.status === 200 && r.success) {
          uploadedFingerprints.add(fp); // mark as uploaded for this session
          setFileStatus(item.id, 'done', 100);
          resolve({ ok: true, xp: (r.data && r.data.xp_gained) || 0, score: (r.data && r.data.new_score) || 0 });
        } else {
          setFileStatus(item.id, 'error', 0, r.message || 'Failed');
          resolve({ ok: false, msg: r.message });
        }
      } catch(e) {
        setFileStatus(item.id, 'error', 0, 'Invalid response');
        resolve({ ok: false, msg: 'Invalid response' });
      }
    };
    xhr.onerror = function() {
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
  if (isUploading) return;
  if (!selectedFiles.length) return showToast('Select at least one file', 'error');

  // Validate all have metadata
  const missing = selectedFiles.filter(f => !f.meta || !f.meta.subject || !f.meta.type);
  if (missing.length) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed('missing_metadata', 'validation_error', 'file');
    showToast('Fill metadata (📝) for all ' + missing.length + ' image(s) first', 'error');
    // Highlight missing
    missing.forEach(f => { const t = document.getElementById('thumb_'+f.id); if(t) t.classList.add('bu-pulse'); });
    return;
  }
  if (!gv('college_id')) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed('missing_college', 'validation_error', 'file');
    return showToast('Select a college', 'error');
  }
  if (!gv('branch_id')) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed('missing_branch', 'validation_error', 'file');
    return showToast('Select a branch', 'error');
  }

  isUploading = true;
  const btn = document.getElementById('submitBtn');
  if (btn) { btn.disabled=true; btn.textContent='Uploading…'; }
  window.addEventListener('beforeunload', handleBeforeUnload);
  setFloatStatus(true, '0 / '+selectedFiles.length+' uploaded');

  // GA4 — upload funnel start
  const _gaMethod = selectedFiles.some(f =>
    !f.file.lastModified || f.file.name.toLowerCase().startsWith('image')
  ) ? 'camera' : 'file';
  if (typeof window.AbhiHubTracking !== 'undefined') {
    const _category = gv('type') || 'unknown';
    window.AbhiHubTracking.trackUploadStarted(selectedFiles.length, _gaMethod, _category);
  }

  let done=0, failed=0;
  const results = [];
  for (const item of selectedFiles) {
    setFloatStatus(true, done+' / '+selectedFiles.length+' uploading…');
    setFileStatus(item.id, 'uploading', 0);
    const res = await uploadOne(item);
    results.push(res);
    if (res.ok) {
      done++;
      // GA4 — per-file upload event
      if (typeof window.AbhiHubTracking !== 'undefined') {
        window.AbhiHubTracking.trackUpload(
          item.name,
          item.file.type || 'image/jpeg',
          Math.round((item.blob || item.file).size / 1024)
        );
      }
    } else {
      failed++;
      if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed(res.msg || 'network_error', 'system_error', _gaMethod);
    }
    setFloatStatus(true, done+' / '+selectedFiles.length+' done');
  }

  isUploading = false;
  window.removeEventListener('beforeunload', handleBeforeUnload);
  setFloatStatus(false);
  if (btn) { btn.disabled=false; btn.textContent='Upload Files'; }

  if (failed === 0) {
    // Collect XP data from successful uploads
    const totalXp = results.filter(r => r.ok).reduce((sum, r) => sum + (r.xp || 0), 0);
    const lastScore = results.filter(r => r.ok).slice(-1)[0]?.score || 0;
    showToast('All ' + done + ' files uploaded! 🎉', 'success');
    // GA4 — upload_completed + xp_earned
    if (typeof window.AbhiHubTracking !== 'undefined') {
      const types = Array.from(new Set(selectedFiles.map(f => f.file.type || 'image/jpeg'))).join(',');
      const totalSizeKb = Math.round(selectedFiles.reduce((sum, f) => sum + (f.blob || f.file).size, 0) / 1024);
      window.AbhiHubTracking.trackUploadCompleted(done, _gaMethod, types, totalSizeKb);
      if (totalXp > 0) window.AbhiHubTracking.trackXpEarned(totalXp, lastScore, done);
    }
    if (typeof window.markUserUploaded === 'function') window.markUserUploaded();
    if (typeof showXpModal === 'function') {
      showXpModal(totalXp, lastScore, done);
    } else {
      setTimeout(() => { window.location.href = '/premium'; }, 1500);
    }
  } else if (done > 0) {
    showToast(done + ' succeeded, ' + failed + ' failed.', 'error');
  } else {
    showToast('All uploads failed. Check metadata and try again.', 'error');
  }
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

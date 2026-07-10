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
      meta: { 
        college_id: gv('college_id'),
        branch_id: gv('branch_id'),
        subject: '', 
        subject_id: '', 
        semester: '',
        year: '2025', 
        type: '', 
        unit: '' 
      }
    };
    selectedFiles.push(newItem);
  });

  if (selectedFiles.length > 0) {
    document.getElementById('uploadCarousel').style.display = 'flex';
    document.querySelector('.upload-defaults-toggle')?.remove(); // Remove defaults UI since we now edit per-file immediately
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

function saveCurrentMeta() {
  if (selectedFiles.length === 0 || carouselIndex < 0 || carouselIndex >= selectedFiles.length) return;
  const item = selectedFiles[carouselIndex];
  
  const typeEl = document.getElementById('metaType');
  const yearEl = document.getElementById('metaYear');
  const unitEl = document.getElementById('metaUnit');
  const subjEl = document.getElementById('metaSubject');
  const semEl = document.getElementById('semester');
  const colEl = document.getElementById('college_id');
  const branchEl = document.getElementById('branch_id');
  
  // Save to item meta
  item.meta.type = typeEl.value;
  item.meta.year = yearEl.value;
  item.meta.unit = unitEl.value;
  item.meta.semester = semEl.value;
  item.meta.college_id = colEl.value;
  item.meta.branch_id = branchEl.value;
  item.meta.subject_id = subjEl.value;
  const selOpt = subjEl.options[subjEl.selectedIndex];
  if (selOpt && subjEl.value) {
    item.meta.subject = selOpt.text;
  }
}

function updateMetaUnit() {
  const typeEl = document.getElementById('metaType');
  const type = typeEl ? typeEl.value : '';
  const wrap = document.getElementById('metaUnitWrap');
  const sel  = document.getElementById('metaUnit');
  if (!wrap || !sel) return;
  
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

function renderCarousel(index) {
  if (selectedFiles.length === 0) return;
  carouselIndex = index;
  const item = selectedFiles[carouselIndex];
  
  document.getElementById('cCounter').textContent = (carouselIndex + 1) + ' / ' + selectedFiles.length;
  document.getElementById('cPrevBtn').disabled = (carouselIndex === 0);
  document.getElementById('cNextBtn').disabled = (carouselIndex === selectedFiles.length - 1);
  
  document.getElementById('carouselFilename').textContent = item.name;
  
  const imgEl = document.getElementById('carouselImg');
  imgEl.src = URL.createObjectURL(item.blob || item.file);
  carouselRotation = 0;
  imgEl.style.transform = `rotate(0deg)`;
  
  if (cropperInst) { cropperInst.destroy(); cropperInst = null; }
  
  // Populate form
  const m = item.meta || {};
  document.getElementById('metaType').value = m.type || '';
  document.getElementById('metaYear').value = m.year || '2025';
  updateMetaUnit();
  document.getElementById('metaUnit').value = m.unit || '';
  
  // College dropdown logic
  const colEl = document.getElementById('college_id');
  const tsCol = window.AbhiHubSelect?.instances['college_id'];
  if (m.college_id) {
    if (tsCol) setTimeout(() => tsCol.setValue(m.college_id), 10);
    else colEl.value = m.college_id;
  } else {
    if (tsCol) { tsCol.clear(); }
    else colEl.value = '';
  }

  // Branch dropdown logic
  const branchEl = document.getElementById('branch_id');
  const tsBranch = window.AbhiHubSelect?.instances['branch_id'];
  if (m.branch_id) {
    if (tsBranch) setTimeout(() => tsBranch.setValue(m.branch_id), 30);
    else branchEl.value = m.branch_id;
  } else {
    if (tsBranch) { tsBranch.clear(); }
    else branchEl.value = '';
  }

  // Semester dropdown logic
  const semEl = document.getElementById('semester');
  const tsSem = window.AbhiHubSelect?.instances['semester'];
  if (m.semester) {
    if (tsSem) {
        setTimeout(() => tsSem.setValue(m.semester), 50);
    } else {
        semEl.value = m.semester;
    }
  } else {
    if (tsSem) {
        tsSem.clear();
    } else {
        semEl.value = '';
    }
  }
  
  // Subject dropdown logic
  const subjEl = document.getElementById('metaSubject');
  const tsSubj = window.AbhiHubSelect?.instances['metaSubject'];
  if (m.subject_id) {
    if (tsSubj) {
        setTimeout(() => tsSubj.setValue(m.subject_id), 100);
    } else {
        subjEl.value = m.subject_id;
    }
  } else {
    if (tsSubj) {
        tsSubj.clear();
    } else {
        subjEl.value = '';
    }
  }
}

function removeCarouselImage() {
  if (selectedFiles.length === 0 || carouselIndex < 0 || carouselIndex >= selectedFiles.length) return;
  const item = selectedFiles[carouselIndex];
  removeFile(item.id);
}

function navigateCarousel(dir) {
  saveCurrentMeta();
  const newIdx = carouselIndex + dir;
  if (newIdx >= 0 && newIdx < selectedFiles.length) {
    renderCarousel(newIdx);
  }
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
  const m = item.meta || {};
  fd.append('college_id', m.college_id || gv('college_id'));
  fd.append('branch_id',  m.branch_id || gv('branch_id'));
  fd.append('semester',   m.semester   || '');
  fd.append('subject',    m.subject    || '');
  fd.append('subject_id',    m.subject_id || gv('subject') || '');
  fd.append('Year',          m.year       || '2025');
  fd.append('type',          m.type       || '');
  fd.append('document_type', m.type       || '');
  fd.append('unit',          m.unit       || '');

  // ── Build a clean filename ──────────────────────────────────────────
  const origName  = item.name || (item.file && item.file.name) || `file_${Date.now()}`;
  const ext       = origName.includes('.') ? origName.split('.').pop().toLowerCase() : 'jpg';
  const sanitize  = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  // Prefer subject_code from dropdown dataset, fallback to subject name
  const subjectEl = document.getElementById('metaSubject') || document.getElementById('subject');
  const selOpt    = subjectEl?.options[subjectEl?.selectedIndex];
  const code      = sanitize(selOpt?.dataset?.code || m.subject || '');
  const docType   = sanitize(m.type || '');
  const year      = sanitize(m.year || gv('Year') || '2025');
  const unit      = sanitize(m.unit || gv('unit') || '');
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
  if (!selectedFiles.length) return showToast('Select at least one file', 'error');

  saveCurrentMeta(); // Ensure the active slide's data is saved before uploading

  // Validate all have required metadata (including college and branch now)
  const missing = selectedFiles.filter(f => !f.meta || !f.meta.subject || !f.meta.type || !f.meta.college_id || !f.meta.branch_id);
  if (missing.length) {
    if (typeof window.AbhiHubTracking !== 'undefined') window.AbhiHubTracking.trackUploadFailed('missing_metadata', 'validation_error', 'file');
    showToast('Fill metadata (College, Department, Category, Subject) for all image(s) first', 'error');
    return;
  }
  
  // Request Notification permission if possible
  if (typeof Notification !== 'undefined' && Notification.permission !== "granted" && Notification.permission !== "denied") {
    Notification.requestPermission();
  }

  // Extract batch and reset UI to allow immediate re-use
  const uploadBatch = [...selectedFiles];
  selectedFiles.length = 0; 
  document.getElementById('uploadCarousel').style.display = 'none';
  
  showToast('Upload started in background! You can prepare more files now.', 'info');
  
  // Kick off background processing asynchronously
  processUploadBatch(uploadBatch);
}

let activeUploads = 0;

async function processUploadBatch(batch) {
  activeUploads++;
  isUploading = true;
  window.addEventListener('beforeunload', handleBeforeUnload);
  
  setFloatStatus(true, `Uploading ${batch.length} files in background...`);

  // GA4 — upload funnel start
  const _gaMethod = batch.some(f =>
    !f.file.lastModified || f.file.name.toLowerCase().startsWith('image')
  ) ? 'camera' : 'file';
  
  if (typeof window.AbhiHubTracking !== 'undefined') {
    const _category = batch[0].meta.type || 'unknown';
    window.AbhiHubTracking.trackUploadStarted(batch.length, _gaMethod, _category);
  }

  let done=0, failed=0;
  const results = [];
  
  for (const item of batch) {
    setFloatStatus(true, `Background Upload: ${done} / ${batch.length} ...`);
    const res = await uploadOne(item);
    results.push(res);
    if (res.ok) {
      done++;
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
  }

  activeUploads--;
  if (activeUploads === 0) {
    isUploading = false;
    window.removeEventListener('beforeunload', handleBeforeUnload);
    setFloatStatus(false);
  } else {
    setFloatStatus(true, `Remaining batches processing...`);
  }

  // Fire OS Notification if granted
  if (typeof Notification !== 'undefined' && Notification.permission === "granted") {
     new Notification("AbhiHub", { body: `Upload batch complete: ${done} files uploaded successfully.` });
  }

  if (failed === 0 && done > 0) {
    // Update user profile college_id and department_id in background using the first file's values
    const firstCol = batch[0].meta.college_id;
    const firstBranch = batch[0].meta.branch_id;
    if (firstCol && firstBranch && firstCol !== '__other__' && firstBranch !== '__other__') {
      fetch('/api/profile/update', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ college_id: firstCol, department_id: firstBranch })
      }).catch(err => console.error('Failed to update profile selection', err));
    }

    const totalXp = results.filter(r => r.ok).reduce((sum, r) => sum + (r.xp || 0), 0);
    const lastScore = results.filter(r => r.ok).slice(-1)[0]?.score || 0;
    
    // GA4 — upload_completed + xp_earned
    if (typeof window.AbhiHubTracking !== 'undefined') {
      const types = Array.from(new Set(batch.map(f => f.file.type || 'image/jpeg'))).join(',');
      const totalSizeKb = Math.round(batch.reduce((sum, f) => sum + (f.blob || f.file).size, 0) / 1024);
      window.AbhiHubTracking.trackUploadCompleted(done, _gaMethod, types, totalSizeKb);
      if (totalXp > 0) window.AbhiHubTracking.trackXpEarned(totalXp, lastScore, done);
    }
    
    if (typeof window.markUserUploaded === 'function') window.markUserUploaded();
    
    if (typeof showXpModal === 'function') {
      showXpModal(totalXp, lastScore, done);
    }
  } else if (done > 0) {
    showToast(`${done} succeeded, ${failed} failed in background.`, 'error');
  } else {
    showToast('Background uploads failed. Please try again.', 'error');
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

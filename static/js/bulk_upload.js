'use strict';

let selectedFiles = [];
let isUploading   = false;
let cropperInst   = null;
let currentCropId = null;
let currentMetaId = null;

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
  Array.from(files).forEach(file => {
    if (imgOnly && !file.type.startsWith('image/')) {
      return showToast(file.name + ': images only for this type', 'error');
    }
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      return showToast(file.name + ': unsupported type', 'error');
    }
    if (file.size > 50*1024*1024) return showToast(file.name + ': exceeds 50 MB', 'error');

    selectedFiles.push({
      id: uid(), file, blob: null, name: file.name, cropped: false, status: 'pending',
      meta: { subject: gv('subject'), year: gv('Year')||'2025', type: gv('type'), unit: gv('unit') }
    });
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
  fd.append('upload_document', item.blob || item.file, item.name);
  return fd;
}

async function uploadOne(item) {
  return new Promise(resolve => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload', true);
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) setFileStatus(item.id, 'uploading', Math.round(e.loaded/e.total*100));
    };
    xhr.onload = () => {
      try {
        const r = JSON.parse(xhr.responseText);
        if (xhr.status === 200 && r.success) { setFileStatus(item.id,'done',100); resolve({ok:true}); }
        else { setFileStatus(item.id,'error',0,r.message||'Failed'); resolve({ok:false,msg:r.message}); }
      } catch { setFileStatus(item.id,'done',100); resolve({ok:true}); }
    };
    xhr.onerror = () => { setFileStatus(item.id,'error',0,'Network error'); resolve({ok:false}); };
    xhr.send(buildFormData(item));
  });
}

function handleBeforeUnload(e) { e.preventDefault(); e.returnValue='Upload in progress.'; }

async function startBulkUpload(event) {
  event.preventDefault();
  if (isUploading) return;
  if (!selectedFiles.length) return showToast('Select at least one file', 'error');

  // Validate all have metadata
  const missing = selectedFiles.filter(f => !f.meta || !f.meta.subject || !f.meta.type);
  if (missing.length) {
    showToast('Fill metadata (📝) for all ' + missing.length + ' image(s) first', 'error');
    // Highlight missing
    missing.forEach(f => { const t = document.getElementById('thumb_'+f.id); if(t) t.classList.add('bu-pulse'); });
    return;
  }
  if (!gv('college_id')) return showToast('Select a college', 'error');
  if (!gv('branch_id'))  return showToast('Select a branch', 'error');

  isUploading = true;
  const btn = document.getElementById('submitBtn');
  if (btn) { btn.disabled=true; btn.textContent='Uploading…'; }
  window.addEventListener('beforeunload', handleBeforeUnload);
  setFloatStatus(true, '0 / '+selectedFiles.length+' uploaded');

  let done=0, failed=0;
  for (const item of selectedFiles) {
    setFloatStatus(true, done+' / '+selectedFiles.length+' uploading…');
    setFileStatus(item.id, 'uploading', 0);
    const res = await uploadOne(item);
    res.ok ? done++ : failed++;
    setFloatStatus(true, done+' / '+selectedFiles.length+' done');
  }

  isUploading = false;
  window.removeEventListener('beforeunload', handleBeforeUnload);
  setFloatStatus(false);
  if (btn) { btn.disabled=false; btn.textContent='Upload Files'; }

  if (failed === 0) {
    showToast('All '+done+' files uploaded! 🎉', 'success');
    if (typeof window.markUserUploaded === 'function') window.markUserUploaded();
    setTimeout(() => { window.location.href = '/premium'; }, 1500);
  } else {
    showToast(done+' succeeded, '+failed+' failed.', 'error');
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

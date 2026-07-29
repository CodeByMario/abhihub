/**
 * Store Room Manager
 * A modular, object-oriented rewrite of the Store Room Labeling Queue
 * Built to completely eliminate repetition and handle all regressions.
 */

class StoreRoomAPI {
    static async fetchFiles(params) {
        const urlParams = new URLSearchParams(params);
        const res = await fetch(`/store-room/api/unlabeled?${urlParams}`);
        return res.json();
    }
    
    static async fetchColleges() {
        const res = await fetch('/api/colleges');
        return res.json();
    }
    
    static async syncStorage() {
        const res = await fetch('/store-room/api/sync', { method: 'POST' });
        return { response: res, data: await res.json() };
    }
    
    static async submitLabel(payload) {
        const res = await fetch('/store-room/api/label', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return res.json();
    }
    
    static async renameFile(payload) {
        const res = await fetch('/store-room/api/rename-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return res.json();
    }
}

class StoreRoomState {
    constructor() {
        this.files = [];
        this.currentOffset = 0;
        this.itemsPerPage = 20;
        this.hasMore = true;
        this.activeFile = null;
        this.rememberLabels = localStorage.getItem('storeroom_remember_labels') === 'true';
        this.lastLabels = JSON.parse(localStorage.getItem('storeroom_last_labels') || '{}');
    }
    
    resetPagination() {
        this.currentOffset = 0;
        this.hasMore = true;
        this.files = [];
    }
}

class GestureManager {
    static initResizer(resizerEl, leftPanel, rightPanel) {
        if (!resizerEl || !leftPanel || !rightPanel) return;
        let isResizing = false;
        
        resizerEl.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const containerWidth = document.querySelector('.labeling-view').clientWidth;
            const minWidth = 300;
            const newWidth = containerWidth - e.clientX - 20;
            if (newWidth >= minWidth && newWidth <= containerWidth - 400) {
                rightPanel.style.flex = `0 0 ${newWidth}px`;
                rightPanel.style.width = `${newWidth}px`;
            }
        });
        
        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
            }
        });
    }

    static initMobileDrawer(handleEl, panelEl, closeCallback) {
        if (!handleEl || !panelEl) return;
        let startY = 0, currentY = 0, isDragging = false;
        
        const onStart = (e) => {
            isDragging = true;
            startY = e.touches ? e.touches[0].clientY : e.clientY;
            panelEl.style.transition = 'none';
        };
        
        const onMove = (e) => {
            if (!isDragging) return;
            currentY = e.touches ? e.touches[0].clientY : e.clientY;
            const diff = currentY - startY;
            if (diff > 0) panelEl.style.transform = `translateY(${diff}px)`;
        };
        
        const onEnd = () => {
            if (!isDragging) return;
            isDragging = false;
            panelEl.style.transition = 'transform 0.25s ease';
            const diff = currentY - startY;
            if (diff > 100) closeCallback();
            else panelEl.style.transform = 'translateY(0)';
        };
        
        handleEl.addEventListener('touchstart', onStart, { passive: true });
        handleEl.addEventListener('touchmove', onMove, { passive: true });
        handleEl.addEventListener('touchend', onEnd);
        handleEl.addEventListener('mousedown', onStart);
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onEnd);
    }

    static initImageViewer(imgEl, containerEl) {
        if (!imgEl || !containerEl) return null;
        let scale = 1, panX = 0, panY = 0;
        let isDragging = false, startX, startY;
        
        const updateTransform = () => {
            imgEl.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
        };
        
        containerEl.addEventListener('wheel', (e) => {
            e.preventDefault();
            scale += e.deltaY * -0.001;
            scale = Math.min(Math.max(0.5, scale), 5);
            updateTransform();
        });
        
        containerEl.addEventListener('mousedown', (e) => {
            if (scale <= 1) return;
            isDragging = true;
            startX = e.clientX - panX;
            startY = e.clientY - panY;
            imgEl.style.cursor = 'grabbing';
        });
        
        window.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            panX = e.clientX - startX;
            panY = e.clientY - startY;
            updateTransform();
        });
        
        window.addEventListener('mouseup', () => {
            isDragging = false;
            imgEl.style.cursor = scale > 1 ? 'grab' : 'default';
        });
        
        return {
            reset: () => { scale = 1; panX = 0; panY = 0; updateTransform(); },
            zoomIn: () => { scale = Math.min(scale + 0.25, 5); updateTransform(); },
            zoomOut: () => { scale = Math.max(scale - 0.25, 0.5); updateTransform(); }
        };
    }
}

class StoreRoomUI {
    constructor(state) {
        this.state = state;
        this.grid = document.getElementById('filesGrid');
        this.viewMoreContainer = document.getElementById('viewMoreContainer');
        this.searchTimer = null;
        this.viewerControls = null;
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.initGestures();
        this.loadMetadata();
        this.reloadFiles();
        
        // Remember Labels Toggle
        const toggle = document.getElementById('rememberToggle');
        if (toggle) {
            toggle.setAttribute('aria-checked', this.state.rememberLabels);
            toggle.addEventListener('click', () => {
                this.state.rememberLabels = !this.state.rememberLabels;
                toggle.setAttribute('aria-checked', this.state.rememberLabels);
                localStorage.setItem('storeroom_remember_labels', this.state.rememberLabels);
            });
        }
    }
    
    bindEvents() {
        // Sync Button
        document.getElementById('syncStorageBtn')?.addEventListener('click', () => this.handleSync());
        
        // Search & Filters
        document.getElementById('storeRoomSearchInput')?.addEventListener('input', () => {
            clearTimeout(this.searchTimer);
            this.searchTimer = setTimeout(() => this.reloadFiles(), 300);
        });
        ['sortSelect', 'formatFilter', 'verificationFilter'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => this.reloadFiles());
        });
        
        // Pagination
        document.getElementById('viewMoreBtn')?.addEventListener('click', () => {
            this.state.currentOffset += this.state.itemsPerPage;
            this.loadMoreFiles();
        });
        
        // Form Submit
        document.getElementById('labelForm')?.addEventListener('submit', (e) => this.handleFormSubmit(e));
        
        // Auto-fill Title
        document.getElementById('documentTitle')?.addEventListener('input', (e) => {
            const titleInput = document.getElementById('docTitle');
            if (titleInput && !titleInput.value) {
                titleInput.value = e.target.value.replace(/_/g, ' ').replace(/\.[^/.]+$/, '');
            }
        });
        
        // Auto-fill Subject Code
        document.getElementById('subjectName')?.addEventListener('change', (e) => {
            const tsSubj = window.AbhiHubSelect?.instances['subjectName'];
            const subjectCodeInput = document.getElementById('subjectCode');
            if (tsSubj && subjectCodeInput && e.target.value) {
                const opt = tsSubj.options[e.target.value];
                if (opt && opt.subject_code) {
                    subjectCodeInput.value = opt.subject_code;
                } else if (opt && opt.text) {
                    const match = opt.text.match(/^(.*?)(?:\s*\((.*?)\))?$/);
                    if (match && match[2]) subjectCodeInput.value = match[2].trim();
                }
            }
        });
        
        // Close Modal — also handled by inline onclick, this is a fallback
        document.getElementById('closeLabelingBtn')?.addEventListener('click', () => this.closeLabelingDrawer());
    }
    
    initGestures() {
        GestureManager.initResizer(
            document.querySelector('.drawer-toggle-btn'), 
            document.querySelector('.image-panel'), 
            document.querySelector('.form-panel')
        );
        GestureManager.initMobileDrawer(
            document.querySelector('.drawer-indicator'), 
            document.querySelector('.form-panel'), 
            () => this.closeLabelingDrawer()
        );
        this.viewerControls = GestureManager.initImageViewer(
            document.getElementById('previewImg'), 
            document.getElementById('imageContainer')
        );
    }
    
    async handleSync() {
        const btn = document.getElementById('syncStorageBtn');
        if (!btn || btn.disabled) return;
        
        const originalText = btn.innerHTML;
        btn.disabled = true;
        const setStatus = (text) => {
            btn.innerHTML = `<svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px; animation: spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg> ${text}`;
        };
        
        setStatus('Connecting...');
        const phases = [
            {time: 800, text: 'Fetching files...'},
            {time: 2000, text: 'Comparing metadata...'},
            {time: 3500, text: 'Updating queue...'}
        ];
        let timers = phases.map(p => setTimeout(() => setStatus(p.text), p.time));
        
        try {
            const { response, data } = await StoreRoomAPI.syncStorage();
            timers.forEach(t => clearTimeout(t));
            
            if (response.ok && data.success) {
                btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;"><polyline points="20 6 9 17 4 12"></polyline></svg> Sync Complete`;
                btn.style.cssText = 'background: var(--success-color, #10b981); border-color: var(--success-color, #10b981); color: white;';
                alert(`Sync Complete\n\nNew Pending Files: ${data.upserted || 0}`);
                setTimeout(() => location.reload(), 1000);
            } else {
                throw new Error(data.message || 'Sync failed');
            }
        } catch (e) {
            timers.forEach(t => clearTimeout(t));
            this.showToast(e.message, 'error');
            btn.innerHTML = originalText;
            btn.disabled = false;
            btn.style.cssText = '';
        }
    }
    
    async reloadFiles() {
        this.state.resetPagination();
        if (this.grid) this.grid.innerHTML = '';
        await this.loadMoreFiles();
    }
    
    async loadMoreFiles() {
        if (!this.grid) return;
        
        const params = {
            offset: this.state.currentOffset,
            limit: this.state.itemsPerPage,
            search: document.getElementById('storeRoomSearchInput')?.value || '',
            sort_by: document.getElementById('sortSelect')?.value || 'date',
            format: document.getElementById('formatFilter')?.value || '',
            verification: document.getElementById('verificationFilter')?.value || ''
        };
        
        try {
            const data = await StoreRoomAPI.fetchFiles(params);
            if (data.success) {
                const newFiles = data.files || [];
                this.state.files = this.state.currentOffset === 0 ? newFiles : [...this.state.files, ...newFiles];
                this.state.hasMore = data.pagination?.has_more || false;
                
                if (this.state.currentOffset === 0 && this.state.files.length === 0) {
                    this.grid.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-icon">📂</div>
                            <h3 class="empty-title">No Pending Files</h3>
                            <p class="empty-text">All storage files have been assigned metadata.</p>
                        </div>
                    `;
                } else {
                    newFiles.forEach(f => this.grid.appendChild(this.createFileCard(f)));
                }
                
                if (this.viewMoreContainer) {
                    this.viewMoreContainer.classList.toggle('hidden', !this.state.hasMore);
                }
                
                if (data.statistics) this.updateStats(data.statistics);
            }
        } catch (e) {
            console.error('Failed to load files', e);
            this.showToast('Failed to load files', 'error');
        }
    }
    
    createFileCard(file) {
        const card = document.createElement('div');
        card.className = 'file-card';
        const isPdf = file.format === 'pdf' || (file.filename && file.filename.toLowerCase().endsWith('.pdf'));
        const iconPath = isPdf ? '/static/premium/icon/pdf.png' : '/static/premium/icon/image.png';
        const dateStr = new Date(file.created_at).toLocaleDateString();
        
        card.innerHTML = `
            ${file.verification_status === 'pending' ? '<span class="label-badge" style="background:#fef3c7;color:#d97706;">Needs Verification</span>' : ''}
            <div class="file-icon-wrapper">
                <img src="${iconPath}" alt="icon" class="file-icon">
            </div>
            <div class="file-name" title="${file.filename}">${file.filename}</div>
            <div class="file-meta">
                <span>${(file.format || 'unknown').toUpperCase()}</span> • <span>${dateStr}</span>
            </div>
        `;
        card.addEventListener('click', () => this.openLabelingDrawer(file));
        return card;
    }
    
    async loadMetadata() {
        try {
            if (window.AbhiHubSelect) window.AbhiHubSelect.init();
            this.loadLastLabels();
        } catch (e) {
            console.error('Failed to load metadata', e);
        }
    }
    
    loadLastLabels() {
        if (!this.state.rememberLabels) return;
        
        // Simple non-dependent fields
        ['documentCategory', 'year', 'examType', 'difficulty'].forEach(id => {
            const val = this.state.lastLabels[id];
            if (val) {
                const ts = window.AbhiHubSelect && window.AbhiHubSelect.instances[id];
                if (ts) setTimeout(() => ts.setValue(val), 100);
                else {
                    const el = document.getElementById(id);
                    if (el) el.value = val;
                }
            }
        });

        // Cascade dependent fields sequentially
        const colVal = this.state.lastLabels['collegeName'];
        if (colVal) {
            const tsCol = window.AbhiHubSelect?.instances['collegeName'];
            if (tsCol) {
                setTimeout(() => {
                    tsCol.setValue(colVal);
                    // Wait for branches to load
                    setTimeout(() => {
                        const branchVal = this.state.lastLabels['branch'];
                        const tsBranch = window.AbhiHubSelect?.instances['branch'];
                        if (branchVal && tsBranch) {
                            tsBranch.setValue(branchVal);
                            // Wait for semesters to load
                            setTimeout(() => {
                                const semVal = this.state.lastLabels['semester'];
                                const tsSem = window.AbhiHubSelect?.instances['semester'];
                                if (semVal && tsSem) {
                                    tsSem.setValue(semVal);
                                    // Wait for subjects to load
                                    setTimeout(() => {
                                        const subVal = this.state.lastLabels['subjectName'];
                                        const tsSub = window.AbhiHubSelect?.instances['subjectName'];
                                        if (subVal && tsSub) tsSub.setValue(subVal);
                                    }, 800);
                                }
                            }, 800);
                        }
                    }, 800);
                }, 100);
            }
        }
    }
    
    saveLastLabels() {
        if (!this.state.rememberLabels) return;
        ['documentCategory', 'collegeName', 'branch', 'semester', 'subjectName', 'year', 'examType', 'difficulty'].forEach(id => {
            const el = document.getElementById(id);
            if (el && el.value) this.state.lastLabels[id] = el.value;
        });
        localStorage.setItem('storeroom_last_labels', JSON.stringify(this.state.lastLabels));
    }
    
    openLabelingDrawer(file) {
        this.state.activeFile = file;
        const view = document.getElementById('labelingView');
        const img = document.getElementById('previewImg');
        const frame = document.getElementById('previewFrame');
        
        const badge = document.getElementById('fileInfoBadge');
        const docTitleEl = document.getElementById('documentTitle');
        
        if (badge) badge.textContent = file.filename;
        if (docTitleEl && !docTitleEl.value) {
            docTitleEl.value = file.filename.replace(/_/g, ' ').replace(/\.[^/.]+$/, '');
        }
        
        const isPdf = file.format === 'pdf' || (file.filename && file.filename.toLowerCase().endsWith('.pdf'));
        if (isPdf) {
            if (img) img.classList.add('hidden');
            if (frame) {
                frame.classList.remove('hidden');
                frame.src = `/pdf-proxy/${encodeURIComponent(file.url || file.path)}#toolbar=0&navpanes=0&scrollbar=0`;
            }
            document.querySelector('.image-controls')?.classList.add('hidden');
        } else {
            if (frame) frame.classList.add('hidden');
            if (img) {
                img.classList.remove('hidden');
                img.src = file.url || file.path;
            }
            this.viewerControls?.reset();
            document.querySelector('.image-controls')?.classList.remove('hidden');
        }
        
        if (view) {
            view.classList.add('active');
            document.body.style.overflow = 'hidden';
            const idx = this.state.files.indexOf(file);
            this.updateNavCounter(idx);
        }
    }
    
    closeLabelingDrawer() {
        this.state.activeFile = null;
        const view = document.getElementById('labelingView');
        if (view) view.classList.remove('active');
        document.body.style.overflow = '';
        
        const frame = document.getElementById('previewFrame');
        if (frame) frame.src = 'about:blank';
        
        const formPanel = document.querySelector('.form-panel');
        if (formPanel) formPanel.style.transform = '';
    }
    
    async handleFormSubmit(e) {
        e.preventDefault();
        const btn = document.getElementById('saveBtn');
        if (!btn || btn.disabled) return;
        
        btn.disabled = true;
        const origText = btn.innerHTML;
        btn.innerHTML = `<svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg> Saving...`;
        
        try {
            const formData = new FormData(e.target);
            const payload = Object.fromEntries(formData.entries());
            
            // Map TomSelect values correctly (fallback to native select options)
            ['documentCategory', 'examType', 'difficulty'].forEach(id => {
                const el = document.getElementById(id);
                if (el && el.value) {
                    payload[id] = el.options[el.selectedIndex]?.text || el.value;
                }
            });
            
            payload.college_id = document.getElementById('collegeName')?.value;
            payload.branch_id = document.getElementById('branch')?.value;
            payload.subject_id = document.getElementById('subjectName')?.value;
            
            const subjSelect = document.getElementById('subjectName');
            if (subjSelect && subjSelect.selectedIndex >= 0) {
                const optText = subjSelect.options[subjSelect.selectedIndex]?.text || '';
                if (optText && optText !== 'Select…' && optText !== 'Select Subject') {
                    const match = optText.match(/^(.*?)(?:\s*\((.*?)\))?$/);
                    payload.subject_name = match ? match[1].trim() : optText;
                    payload.subject_code = match && match[2] ? match[2].trim() : '';
                }
            }
            
            if (this.state.activeFile) {
                if (this.state.activeFile.record_id) {
                    payload.record_id = this.state.activeFile.record_id;
                }
                payload.filename = this.state.activeFile.filename || this.state.activeFile.name || 'Unknown File';
                payload.url = this.state.activeFile.url || this.state.activeFile.path || '';
            }
            
            const data = await StoreRoomAPI.submitLabel(payload);
            if (data.success) {
                this.saveLastLabels();
                this.showToast('File successfully labeled! You can find it on the Home page.', 'success');
                
                // Optimistically remove the file from the grid and state BEFORE closing the drawer (which clears activeFile)
                if (this.state.activeFile) {
                    const filename = this.state.activeFile.filename || this.state.activeFile.name;
                    this.state.files = this.state.files.filter(f => (f.filename || f.name) !== filename);
                    
                    if (this.grid) {
                        Array.from(this.grid.children).forEach(card => {
                            const nameEl = card.querySelector('.file-name');
                            if (nameEl && nameEl.textContent.trim() === filename.trim()) {
                                card.style.transition = 'all 0.3s ease';
                                card.style.opacity = '0';
                                card.style.transform = 'scale(0.8)';
                                setTimeout(() => card.remove(), 300);
                            }
                        });
                        
                        // Show empty state if all files are processed
                        if (this.state.files.length === 0) {
                            setTimeout(() => {
                                this.grid.innerHTML = `
                                    <div class="empty-state">
                                        <div class="empty-icon">📂</div>
                                        <h3 class="empty-title">No Pending Files</h3>
                                        <p class="empty-text">All storage files have been assigned metadata.</p>
                                    </div>
                                `;
                            }, 300);
                        }
                    }
                }
                
                this.closeLabelingDrawer();
            } else {
                throw new Error(data.message || 'Failed to save');
            }
        } catch (err) {
            console.error(err);
            this.showToast(err.message, 'error');
        } finally {
            btn.innerHTML = origText;
            btn.disabled = false;
        }
    }

    handleSave() {
        const form = document.getElementById('labelForm');
        if (form) form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }

    navigateFile(dir) {
        const idx = this.state.files.indexOf(this.state.activeFile);
        if (idx === -1) return;
        const next = this.state.files[idx + dir];
        if (next) this.openLabelingDrawer(next);
        this.updateNavCounter(idx + dir);
    }

    updateNavCounter(idx) {
        const counter = document.getElementById('navCounter');
        if (counter) counter.textContent = `${idx + 1} / ${this.state.files.length}`;
        document.getElementById('prevBtn')?.toggleAttribute('disabled', idx <= 0);
        document.getElementById('nextBtn')?.toggleAttribute('disabled', idx >= this.state.files.length - 1);
    }

    rotateImage() {
        const img = document.getElementById('previewImg');
        if (!img) return;
        const current = parseInt(img.dataset.rotation || '0');
        const next = (current + 90) % 360;
        img.dataset.rotation = next;
        img.style.transform = `rotate(${next}deg)`;
    }

    toggleFullscreen() {
        const container = document.getElementById('imageContainer');
        if (!container) return;
        if (!document.fullscreenElement) {
            container.requestFullscreen?.();
        } else {
            document.exitFullscreen?.();
        }
    }

    async handleRename() {
        if (!this.state.activeFile) return;
        const newName = prompt("Enter new filename:", this.state.activeFile.filename);
        if (!newName || newName === this.state.activeFile.filename) return;
        
        try {
            const fileId = this.state.activeFile.id || this.state.activeFile.storage_id || this.state.activeFile.path;
            const data = await StoreRoomAPI.renameFile({ file_id: fileId, new_name: newName });
            if (data.success) {
                this.state.activeFile.filename = newName;
                const fnInput = document.getElementById('fileName');
                const titleInput = document.getElementById('docTitle');
                if (fnInput) fnInput.value = newName;
                if (titleInput) titleInput.value = newName.replace(/_/g, ' ').replace(/\.[^/.]+$/, '');
                
                this.showToast('Renamed successfully', 'success');
                this.reloadFiles();
            } else {
                throw new Error(data.message || 'Failed to rename');
            }
        } catch (e) {
            this.showToast(e.message, 'error');
        }
    }
    
    updateStats(stats) {
        const setVal = (selector, val) => {
            const el = document.querySelector(selector);
            if (el) el.textContent = val;
        };
        setVal('.stat-card.total .stat-number', stats.total);
        setVal('.stat-card.sorted .stat-number', stats.sorted);
        setVal('.stat-card.remaining .stat-number', stats.remaining);
    }
    
    showToast(message, type = 'info') {
        if (window.showToast) return window.showToast(message, type);
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    const state = new StoreRoomState();
    window.StoreRoom = new StoreRoomUI(state);
});

// Global shims for inline onclick handlers in HTML
function closeLabelingView()   { window.StoreRoom?.closeLabelingDrawer(); }
function handleSave()          { window.StoreRoom?.handleSave(); }
function loadMoreFiles()       { window.StoreRoom?.loadMoreFiles(); }
function syncStorage()         { window.StoreRoom?.handleSync(); }
function navigateFile(dir)     { window.StoreRoom?.navigateFile(dir); }
function resetView()           { window.StoreRoom?.viewerControls?.reset(); }
function zoomIn()              { window.StoreRoom?.viewerControls?.zoomIn(); }
function zoomOut()             { window.StoreRoom?.viewerControls?.zoomOut(); }
function rotateImage()         { window.StoreRoom?.rotateImage(); }
function toggleFullscreen()    { window.StoreRoom?.toggleFullscreen(); }

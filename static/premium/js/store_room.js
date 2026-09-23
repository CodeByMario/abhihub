/**
 * AbhiHub Store Room Studio Manager
 * High-speed data labeling studio connecting cloud database assets to academic hierarchy.
 */

class StoreRoomAPI {
    static async fetchFiles(params) {
        const urlParams = new URLSearchParams(params);
        const res = await fetch(`/store-room/api/unlabeled?${urlParams}`);
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

    static async extractAiSuggestions(filename) {
        const res = await fetch('/api/ai/tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: 'suggest_upload_metadata',
                parameters: { filename }
            })
        });
        return res.json();
    }
}

class StoreRoomState {
    constructor() {
        this.files = Array.isArray(window.INITIAL_STORE_ROOM_FILES) ? [...window.INITIAL_STORE_ROOM_FILES] : [];
        this.activeIndex = -1;
        this.totalCount = Number(window.INITIAL_TOTAL_PAPERS) || 0;
        this.sortedCount = Number(window.INITIAL_SORTED_PAPERS) || 0;
        this.remainingCount = Number(window.INITIAL_REMAINING_PAPERS) || this.files.length;
        this.currentOffset = this.files.length;
        this.itemsPerPage = 20;
        this.hasMore = this.remainingCount > this.files.length;
        this.rememberLabels = localStorage.getItem('storeroom_remember_labels') === 'true';
        this.lastLabels = JSON.parse(localStorage.getItem('storeroom_last_labels') || '{}');
    }

    get activeFile() {
        if (this.activeIndex >= 0 && this.activeIndex < this.files.length) {
            return this.files[this.activeIndex];
        }
        return null;
    }
}

class StudioImageViewer {
    constructor(imgEl, containerEl) {
        this.imgEl = imgEl;
        this.containerEl = containerEl;
        this.scale = 1;
        this.rotation = 0;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.startX = 0;
        this.startY = 0;
        this.bindEvents();
    }

    bindEvents() {
        if (!this.imgEl || !this.containerEl) return;

        this.containerEl.addEventListener('wheel', (e) => {
            e.preventDefault();
            this.scale += e.deltaY * -0.001;
            this.scale = Math.min(Math.max(0.5, this.scale), 5);
            this.update();
        }, { passive: false });

        this.containerEl.addEventListener('mousedown', (e) => {
            if (this.scale <= 1) return;
            this.isDragging = true;
            this.startX = e.clientX - this.panX;
            this.startY = e.clientY - this.panY;
            this.imgEl.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            this.panX = e.clientX - this.startX;
            this.panY = e.clientY - this.startY;
            this.update();
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            this.imgEl.style.cursor = this.scale > 1 ? 'grab' : 'default';
        });
    }

    update() {
        if (!this.imgEl) return;
        this.imgEl.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale}) rotate(${this.rotation}deg)`;
    }

    reset() {
        this.scale = 1;
        this.rotation = 0;
        this.panX = 0;
        this.panY = 0;
        this.update();
    }

    zoomIn() {
        this.scale = Math.min(this.scale + 0.25, 5);
        this.update();
    }

    zoomOut() {
        this.scale = Math.max(this.scale - 0.25, 0.5);
        this.update();
    }

    rotate() {
        this.rotation = (this.rotation + 90) % 360;
        this.update();
    }
}

class StoreRoomStudio {
    constructor() {
        this.state = new StoreRoomState();
        this.grid = document.getElementById('filesGrid');
        this.searchTimer = null;
        this.imageViewer = null;

        const imgEl = document.getElementById('previewImg');
        const containerEl = document.getElementById('imageContainer');
        if (imgEl && containerEl) {
            this.imageViewer = new StudioImageViewer(imgEl, containerEl);
        }

        this.init();
    }

    init() {
        this.bindEvents();
        this.initRememberToggle();
        this.initMobileTabs();
        this.initShortcuts();
        this.updateProgress();

        if (this.state.files.length > 0) {
            this.renderQueue();
            this.selectFileByIndex(0);
        } else {
            this.reloadFiles();
        }

        if (window.AbhiHubSelect) {
            window.AbhiHubSelect.init();
        }
    }

    bindEvents() {
        // Sync Cloud Storage
        document.getElementById('syncStorageBtn')?.addEventListener('click', () => this.handleSync());

        // Queue Search & Filters
        document.getElementById('storeRoomSearchInput')?.addEventListener('input', () => {
            clearTimeout(this.searchTimer);
            this.searchTimer = setTimeout(() => this.reloadFiles(), 300);
        });

        ['formatFilter', 'sortSelect'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => this.reloadFiles());
        });

        // Load More Queue
        document.getElementById('viewMoreBtn')?.addEventListener('click', () => this.loadMoreFiles());

        // Tarika AI Auto-Suggest Button
        document.getElementById('tarikaExtractBtn')?.addEventListener('click', () => this.handleTarikaAutoSuggest());

        // Document Viewer Controls
        document.querySelector('[data-action="resetView"]')?.addEventListener('click', () => this.imageViewer?.reset());
        document.querySelector('[data-action="zoomIn"]')?.addEventListener('click', () => this.imageViewer?.zoomIn());
        document.querySelector('[data-action="zoomOut"]')?.addEventListener('click', () => this.imageViewer?.zoomOut());
        document.querySelector('[data-action="rotateImage"]')?.addEventListener('click', () => this.imageViewer?.rotate());
        document.querySelector('[data-action="openFullNewTab"]')?.addEventListener('click', () => {
            const f = this.state.activeFile;
            if (f && (f.url || f.path)) window.open(f.url || f.path, '_blank');
        });

        // Navigation Prev/Next
        document.getElementById('prevBtn')?.addEventListener('click', () => this.navigate(-1));
        document.getElementById('nextBtn')?.addEventListener('click', () => this.navigate(1));

        // Form Submit & Save Button
        document.getElementById('labelForm')?.addEventListener('submit', (e) => this.handleFormSubmit(e));
        document.getElementById('saveBtn')?.addEventListener('click', () => this.triggerSave());

        // Subject change auto-populates code
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
    }

    initRememberToggle() {
        const toggle = document.getElementById('rememberToggle');
        if (!toggle) return;
        toggle.setAttribute('aria-checked', String(this.state.rememberLabels));
        toggle.addEventListener('click', () => {
            this.state.rememberLabels = !this.state.rememberLabels;
            toggle.setAttribute('aria-checked', String(this.state.rememberLabels));
            localStorage.setItem('storeroom_remember_labels', String(this.state.rememberLabels));
            this.showToast(this.state.rememberLabels ? 'Labels will be remembered for next files' : 'Remember labels disabled', 'info');
        });
    }

    initMobileTabs() {
        const tabs = document.querySelectorAll('.studio-tab-btn');
        const grid = document.getElementById('studioGrid');
        if (!grid || tabs.length === 0) return;

        grid.classList.add('show-queue');

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => {
                    t.classList.remove('active');
                    t.setAttribute('aria-selected', 'false');
                });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');

                const target = tab.dataset.tab;
                grid.classList.remove('show-queue', 'show-preview', 'show-form');
                grid.classList.add(`show-${target}`);
            });
        });
    }

    initShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Enter or Cmd+Enter to Save & Advance
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                this.triggerSave();
                return;
            }

            // Keyboard navigation if not inside an input/select
            const tag = document.activeElement?.tagName?.toLowerCase();
            if (['input', 'select', 'textarea'].includes(tag)) return;

            if (e.key === 'ArrowLeft' || e.key === '[') {
                e.preventDefault();
                this.navigate(-1);
            } else if (e.key === 'ArrowRight' || e.key === ']') {
                e.preventDefault();
                this.navigate(1);
            }
        });
    }

    updateProgress() {
        const total = this.state.totalCount || (this.state.sortedCount + this.state.remainingCount);
        const sorted = this.state.sortedCount;
        const percent = total > 0 ? Math.min(Math.round((sorted / total) * 100), 100) : 0;

        const fill = document.getElementById('progressBarFill');
        const label = document.getElementById('progressPercent');
        const countRem = document.getElementById('remainingCount');
        const countSort = document.getElementById('sortedCount');
        const countTot = document.getElementById('totalCount');
        const mobileQueueCount = document.getElementById('mobileQueueCount');

        if (fill) fill.style.width = `${percent}%`;
        if (label) label.textContent = `${percent}% Sorted (${sorted}/${total})`;
        if (countRem) countRem.textContent = this.state.remainingCount;
        if (countSort) countSort.textContent = this.state.sortedCount;
        if (countTot) countTot.textContent = total;
        if (mobileQueueCount) mobileQueueCount.textContent = this.state.remainingCount;
    }

    renderQueue() {
        if (!this.grid) return;
        this.grid.innerHTML = '';

        if (this.state.files.length === 0) {
            this.grid.innerHTML = `
                <div style="padding:2rem 1rem; text-align:center; color:#64748b;">
                    <div style="font-size:2rem; margin-bottom:0.5rem;">🎉</div>
                    <div style="font-weight:700; color:#0f172a; margin-bottom:0.25rem;">Queue is Empty!</div>
                    <div style="font-size:0.8rem;">All files in storage have been labeled.</div>
                </div>
            `;
            return;
        }

        this.state.files.forEach((file, idx) => {
            const card = document.createElement('div');
            card.className = `queue-card ${idx === this.state.activeIndex ? 'active' : ''}`;
            card.dataset.index = idx;

            const format = (file.format || file.filename?.split('.').pop() || 'file').toUpperCase();
            const dateStr = file.created_at ? new Date(file.created_at).toLocaleDateString() : 'Storage';

            card.innerHTML = `
                <div class="queue-card-top">
                    <span class="queue-badge">${format}</span>
                    <span class="queue-date">${dateStr}</span>
                </div>
                <div class="queue-card-name" title="${file.filename || file.name}">${file.filename || file.name}</div>
            `;

            card.addEventListener('click', () => {
                this.selectFileByIndex(idx);
                // On mobile, automatically show preview
                const previewTab = document.querySelector('.studio-tab-btn[data-tab="preview"]');
                if (window.innerWidth <= 900 && previewTab) previewTab.click();
            });

            this.grid.appendChild(card);
        });

        this.updateNavCounter();
    }

    selectFileByIndex(index) {
        if (index < 0 || index >= this.state.files.length) return;
        this.state.activeIndex = index;

        // Highlight active queue card
        const cards = this.grid?.querySelectorAll('.queue-card');
        cards?.forEach((c, i) => {
            c.classList.toggle('active', i === index);
            if (i === index) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });

        const file = this.state.activeFile;
        if (!file) return;

        // Update preview headers
        const badge = document.getElementById('previewBadge');
        const formatPill = document.getElementById('previewFormatPill');
        const format = (file.format || file.filename?.split('.').pop() || 'file').toUpperCase();

        if (badge) badge.textContent = file.filename || file.name;
        if (formatPill) formatPill.textContent = format;

        // Update Document Canvas
        const emptyPrompt = document.getElementById('emptyPreviewPrompt');
        const img = document.getElementById('previewImg');
        const frame = document.getElementById('previewFrame');
        const controls = document.getElementById('previewControls');

        if (emptyPrompt) emptyPrompt.classList.add('hidden');

        const isPdf = format === 'PDF' || (file.filename && file.filename.toLowerCase().endsWith('.pdf'));
        const fileUrl = file.url || file.path;

        if (isPdf) {
            if (img) img.classList.add('hidden');
            if (controls) controls.classList.add('hidden');
            if (frame) {
                frame.classList.remove('hidden');
                frame.src = `/pdf-proxy/${encodeURIComponent(fileUrl)}#toolbar=0&navpanes=0&scrollbar=0`;
            }
        } else {
            if (frame) frame.classList.add('hidden');
            if (img) {
                img.classList.remove('hidden');
                img.src = fileUrl;
            }
            if (controls) controls.classList.remove('hidden');
            this.imageViewer?.reset();
        }

        // Auto-generate title placeholder
        const docTitle = document.getElementById('docTitle');
        if (docTitle && !docTitle.dataset.modifiedByUser) {
            docTitle.value = (file.filename || file.name || '').replace(/_/g, ' ').replace(/\.[^/.]+$/, '');
        }

        // Apply remembered labels if active
        if (this.state.rememberLabels) {
            this.applyRememberedLabels();
        }

        this.updateNavCounter();
    }

    navigate(direction) {
        if (this.state.files.length === 0) return;
        let newIdx = this.state.activeIndex + direction;
        if (newIdx < 0) newIdx = this.state.files.length - 1;
        if (newIdx >= this.state.files.length) newIdx = 0;
        this.selectFileByIndex(newIdx);
    }

    updateNavCounter() {
        const counter = document.getElementById('navCounter');
        if (counter) {
            const current = this.state.files.length > 0 ? this.state.activeIndex + 1 : 0;
            counter.textContent = `${current} / ${this.state.files.length}`;
        }
    }

    async handleTarikaAutoSuggest() {
        const cur = this.state.activeFile;
        if (!cur) {
            this.showToast('Select a file from the queue first', 'info');
            return;
        }

        const btn = document.getElementById('tarikaExtractBtn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Tarika Analyzing…</span>';
        }

        try {
            const res = await StoreRoomAPI.extractAiSuggestions(cur.filename || cur.name);
            if (res && res.success && res.result && res.result.data) {
                const d = res.result.data;

                if (d.title) {
                    const t = document.getElementById('docTitle');
                    if (t) t.value = d.title;
                }
                if (d.year) {
                    const y = document.getElementById('year');
                    if (y) y.value = String(d.year);
                }
                if (d.semester) {
                    const s = document.getElementById('semester');
                    if (s) {
                        const tsSem = window.AbhiHubSelect?.instances['semester'];
                        if (tsSem) tsSem.setValue(String(d.semester));
                        else s.value = String(d.semester);
                    }
                }
                if (d.document_type) {
                    const catMap = { pyq: 'papers', notes: 'notes', practicals: 'practical', syllabus: 'syllabus' };
                    const targetType = catMap[d.document_type] || d.document_type;
                    const catEl = document.getElementById('documentCategory');
                    if (catEl) catEl.value = targetType;
                }
                this.showToast('Tarika auto-suggested metadata from filename!', 'success');
            } else {
                this.showToast('Could not extract details automatically. Please enter manually.', 'info');
            }
        } catch (e) {
            console.warn('Tarika suggestion failed', e);
            this.showToast('AI suggestion unavailable', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span>✨ Tarika Auto-Suggest</span>';
            }
        }
    }

    triggerSave() {
        const form = document.getElementById('labelForm');
        if (!form) return;
        if (form.reportValidity()) {
            form.dispatchEvent(new Event('submit', { cancelable: true }));
        }
    }

    async handleFormSubmit(e) {
        e.preventDefault();
        const cur = this.state.activeFile;
        if (!cur) {
            this.showToast('No active file selected', 'error');
            return;
        }

        const btn = document.getElementById('saveBtn');
        if (!btn || btn.disabled) return;

        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = `<span class="btn-text">⏳ Saving...</span>`;

        try {
            const formData = new FormData(e.target);
            const payload = Object.fromEntries(formData.entries());

            payload.filename = cur.filename || cur.name;
            payload.url = cur.url || cur.path;
            payload.college_id = document.getElementById('collegeName')?.value;
            payload.branch_id = document.getElementById('branch')?.value;
            payload.subject_id = document.getElementById('subjectName')?.value;

            const subjSelect = document.getElementById('subjectName');
            if (subjSelect && subjSelect.selectedIndex >= 0) {
                const optText = subjSelect.options[subjSelect.selectedIndex]?.text || '';
                if (optText && !optText.startsWith('Select')) {
                    const match = optText.match(/^(.*?)(?:\s*\((.*?)\))?$/);
                    payload.subject_name = match ? match[1].trim() : optText;
                    payload.subject_code = match && match[2] ? match[2].trim() : '';
                }
            }

            const data = await StoreRoomAPI.submitLabel(payload);
            if (data.success) {
                this.showToast('File labeled and published to academic library!', 'success');

                if (this.state.rememberLabels) {
                    this.saveRememberedLabels();
                }

                // Update state counts
                this.state.sortedCount++;
                this.state.remainingCount = Math.max(0, this.state.remainingCount - 1);
                this.updateProgress();

                // Remove from local files list
                const removedIdx = this.state.activeIndex;
                this.state.files.splice(removedIdx, 1);

                this.renderQueue();

                // Advance to next file or stay on same index
                if (this.state.files.length > 0) {
                    const nextIdx = Math.min(removedIdx, this.state.files.length - 1);
                    this.selectFileByIndex(nextIdx);
                } else {
                    this.state.activeIndex = -1;
                    document.getElementById('emptyPreviewPrompt')?.classList.remove('hidden');
                    document.getElementById('previewImg')?.classList.add('hidden');
                    document.getElementById('previewFrame')?.classList.add('hidden');
                    document.getElementById('previewBadge').textContent = 'Queue Finished!';
                }
            } else {
                this.showToast(data.message || 'Error saving file label', 'error');
            }
        } catch (err) {
            console.error('Save failed', err);
            this.showToast('Network error while saving label', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    }

    saveRememberedLabels() {
        ['collegeName', 'branch', 'semester', 'year', 'documentCategory', 'examType'].forEach(id => {
            const el = document.getElementById(id);
            if (el && el.value) this.state.lastLabels[id] = el.value;
        });
        localStorage.setItem('storeroom_last_labels', JSON.stringify(this.state.lastLabels));
    }

    applyRememberedLabels() {
        const labels = this.state.lastLabels;
        if (!labels) return;

        ['documentCategory', 'year', 'examType'].forEach(id => {
            if (labels[id]) {
                const el = document.getElementById(id);
                if (el) el.value = labels[id];
            }
        });

        // Cascading selects
        const colVal = labels['collegeName'];
        if (colVal) {
            const tsCol = window.AbhiHubSelect?.instances['collegeName'];
            if (tsCol) {
                tsCol.setValue(colVal);
                setTimeout(() => {
                    const brVal = labels['branch'];
                    const tsBr = window.AbhiHubSelect?.instances['branch'];
                    if (brVal && tsBr) {
                        tsBr.setValue(brVal);
                        setTimeout(() => {
                            const semVal = labels['semester'];
                            const tsSem = window.AbhiHubSelect?.instances['semester'];
                            if (semVal && tsSem) tsSem.setValue(semVal);
                        }, 400);
                    }
                }, 400);
            }
        }
    }

    async reloadFiles() {
        const search = document.getElementById('storeRoomSearchInput')?.value || '';
        const format = document.getElementById('formatFilter')?.value || '';
        const sort = document.getElementById('sortSelect')?.value || 'date';

        try {
            const res = await StoreRoomAPI.fetchFiles({
                search,
                format,
                sort_by: sort === 'name' ? 'filename' : 'created_at',
                order: sort === 'name' ? 'asc' : 'desc',
                offset: 0,
                limit: this.state.itemsPerPage
            });

            if (res.success) {
                this.state.files = res.files || [];
                if (res.statistics) {
                    this.state.totalCount = res.statistics.total;
                    this.state.sortedCount = res.statistics.sorted;
                    this.state.remainingCount = res.statistics.remaining;
                }
                this.state.currentOffset = this.state.files.length;
                this.updateProgress();
                this.renderQueue();

                if (this.state.files.length > 0) {
                    this.selectFileByIndex(0);
                }
            }
        } catch (e) {
            console.error('Failed to reload files', e);
        }
    }

    async loadMoreFiles() {
        const btn = document.getElementById('viewMoreBtn');
        if (btn) btn.textContent = 'Loading...';

        try {
            const res = await StoreRoomAPI.fetchFiles({
                offset: this.state.currentOffset,
                limit: this.state.itemsPerPage
            });

            if (res.success && res.files && res.files.length > 0) {
                this.state.files.push(...res.files);
                this.state.currentOffset += res.files.length;
                this.renderQueue();
            } else {
                if (btn) btn.textContent = 'All Files Loaded';
            }
        } catch (e) {
            console.error('Failed to load more files', e);
        } finally {
            if (btn && btn.textContent === 'Loading...') btn.textContent = 'Load More Queue Files';
        }
    }

    async handleSync() {
        const btn = document.getElementById('syncStorageBtn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Syncing...</span>';
        }

        try {
            const { data } = await StoreRoomAPI.syncStorage();
            if (data.success) {
                this.showToast(data.message || 'Storage synchronized successfully', 'success');
                await this.reloadFiles();
            } else {
                this.showToast(data.message || 'Sync failed', 'error');
            }
        } catch (e) {
            this.showToast('Storage sync request failed', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.23-9.57l5.71 5.71"></path>
                    </svg>
                    <span>Sync Cloud Storage</span>
                `;
            }
        }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `store-toast toast-${type}`;
        toast.style.cssText = `
            padding: 10px 16px;
            margin-bottom: 8px;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            color: #ffffff;
            background: ${type === 'success' ? '#16a34a' : type === 'error' ? '#dc2626' : '#2563eb'};
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transition: all 0.3s ease;
        `;
        toast.textContent = message;

        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.storeRoomStudio = new StoreRoomStudio();
});

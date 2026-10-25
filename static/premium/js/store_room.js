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
        const data = await res.json().catch(() => ({}));
        return { response: res, data };
    }

    static async updateLabel(payload) {
        const res = await fetch('/store-room/api/edit-label', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json().catch(() => ({}));
        return { response: res, data };
    }

    static async extractAiSuggestions(fileItem, knownFields = {}) {
        let filename = fileItem.filename || fileItem.name || '';
        const fileUrl = fileItem.url || fileItem.path || '';

        const branchEl = document.getElementById('branch');
        const branchId = window.AbhiHubSelect?.instances['branch']?.getValue() || branchEl?.value || '';

        // Attempt Vision / OCR extraction if file URL is accessible
        if (fileUrl) {
            try {
                const fd = new FormData();
                fd.append('file_url', fileUrl);
                fd.append('filename', filename);
                if (branchId) fd.append('branch_id', branchId);
                if (knownFields) fd.append('known_fields', JSON.stringify(knownFields));

                const blob = await fetch(fileUrl).then(r => r.ok ? r.blob() : null).catch(() => null);
                if (blob) {
                    let ext = (filename.includes('.') ? filename.split('.').pop() : '').toLowerCase();
                    if (!['pdf', 'jpg', 'jpeg', 'png', 'webp'].includes(ext)) {
                        ext = (blob.type === 'application/pdf') ? 'pdf' : (blob.type === 'image/png' ? 'png' : 'jpg');
                        filename = filename ? `${filename.replace(/\.[^/.]+$/, '')}.${ext}` : `document.${ext}`;
                    }
                    const fileObj = new File([blob], filename, { type: blob.type || (ext === 'pdf' ? 'application/pdf' : 'image/jpeg') });
                    fd.append('upload_document', fileObj, filename);
                }

                const res = await fetch('/api/ai/extract-upload-metadata', {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json().catch(() => null);
                if (data && data.success && data.metadata) {
                    return {
                        success: true,
                        source: data.source || 'ai_vision',
                        result: { data: data.metadata }
                    };
                }
            } catch (err) {
                console.warn('[StoreRoom] Vision extraction attempt failed, falling back to heuristic tools', err);
            }
        }

        // Fallback: heuristic filename parsing tool
        const res = await fetch('/api/ai/tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: 'suggest_upload_metadata',
                arguments: { filename }
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
        this.isEditMode = false;
        this.editingDoc = null;
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

        // Touch Pinch-to-Zoom & Drag for Mobile
        let initialDist = 0;
        let initialScale = 1;
        this.containerEl.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                initialDist = Math.hypot(
                    e.touches[0].clientX - e.touches[1].clientX,
                    e.touches[0].clientY - e.touches[1].clientY
                );
                initialScale = this.scale;
            } else if (e.touches.length === 1 && this.scale > 1) {
                this.isDragging = true;
                this.startX = e.touches[0].clientX - this.panX;
                this.startY = e.touches[0].clientY - this.panY;
            }
        }, { passive: true });

        this.containerEl.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2 && initialDist > 0) {
                const dist = Math.hypot(
                    e.touches[0].clientX - e.touches[1].clientX,
                    e.touches[0].clientY - e.touches[1].clientY
                );
                this.scale = Math.min(Math.max(0.5, initialScale * (dist / initialDist)), 5);
                this.update();
            } else if (e.touches.length === 1 && this.isDragging) {
                this.panX = e.touches[0].clientX - this.startX;
                this.panY = e.touches[0].clientY - this.startY;
                this.update();
            }
        }, { passive: true });

        this.containerEl.addEventListener('touchend', () => {
            this.isDragging = false;
            initialDist = 0;
        }, { passive: true });
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
        this.initHistoryTab();
        this.updateProgress();

        // Auto-apply redirected search query from dashboard
        const urlParams = new URLSearchParams(window.location.search);
        const redirectedQuery = urlParams.get('search') || urlParams.get('q');
        const searchInput = document.getElementById('storeRoomSearchInput');
        if (redirectedQuery && searchInput) {
            searchInput.value = redirectedQuery;
        }

        if (this.state.files.length > 0 && !redirectedQuery) {
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
        document.getElementById('cancelEditBtn')?.addEventListener('click', () => this.cancelEdit());

        // Quick Add Subject Button Trigger
        document.getElementById('triggerAddSubjectBtn')?.addEventListener('click', () => {
            const semVal = document.getElementById('semester')?.value || '';
            const deptVal = document.getElementById('branch')?.value || '';
            if (window.AbhiHubSelect?.showAddEntityModal) {
                window.AbhiHubSelect.showAddEntityModal('subject', 'subjectName', semVal, '');
            } else {
                const modal = document.getElementById('globalEntityModal');
                if (modal) {
                    modal.style.display = 'flex';
                    const semSelect = document.getElementById('entitySemester');
                    if (semSelect && semVal) semSelect.value = semVal;
                    document.getElementById('entityModalTitle').textContent = 'Add New Subject';
                    document.querySelectorAll('.entity-field-group').forEach(el => el.style.display = 'none');
                    document.getElementById('entityNameField').style.display = 'block';
                    document.getElementById('entityCodeField').style.display = 'block';
                    document.getElementById('entitySemesterField').style.display = 'block';
                    const form = document.getElementById('entityModalForm');
                    if (form) {
                        form.dataset.entity = 'subject';
                        form.dataset.targetId = 'subjectName';
                        form.dataset.parentVal = semVal;
                    }
                }
            }
        });

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
            this.updateAutoTitle();
        });

        // Track user manually modifying title
        const docTitleEl = document.getElementById('docTitle');
        if (docTitleEl) {
            docTitleEl.addEventListener('input', () => {
                docTitleEl.dataset.modifiedByUser = 'true';
            });
        }

        // Real-time title auto-update on academic & metadata changes
        ['collegeName', 'branch', 'semester', 'subjectCode', 'documentCategory', 'examType', 'year'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => this.updateAutoTitle());
            document.getElementById(id)?.addEventListener('input', () => this.updateAutoTitle());
        });
    }

    makeAcronym(str) {
        if (!str) return '';
        const parenMatch = str.match(/\(([^)]+)\)/);
        if (parenMatch) {
            const inside = parenMatch[1].trim();
            if (/^[a-zA-Z0-9&.\-_]{2,8}$/.test(inside)) {
                return inside.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
            }
        }
        const cleanStr = str.replace(/\([^)]*\)/g, '').trim();
        const stopWords = new Set(['and', 'of', 'the', 'in', 'for', 'to', 'with', 'on', 'at', '&']);
        const words = cleanStr.split(/[\s_\-]+/).filter(w => w && !stopWords.has(w.toLowerCase()));
        if (words.length === 1) {
            const clean = words[0].replace(/[^a-zA-Z0-9]/g, '');
            return clean.length <= 6 ? clean.toUpperCase() : clean.slice(0, 6).toUpperCase();
        }
        const acr = words.map(w => w.replace(/[^a-zA-Z0-9]/g, '')[0] || '').join('');
        return (acr.length >= 2 ? acr : cleanStr.replace(/[^a-zA-Z0-9]/g, '').slice(0, 6)).toUpperCase();
    }

    updateAutoTitle() {
        const titleEl = document.getElementById('docTitle');
        if (!titleEl || titleEl.dataset.modifiedByUser === 'true') return;

        const colSelect = document.getElementById('collegeName');
        const tsCol = window.AbhiHubSelect?.instances['collegeName'];
        const colId = tsCol ? tsCol.getValue() : (colSelect?.value || '');
        const colText = (tsCol && tsCol.options[colId]?.text) || (colSelect && colSelect.selectedIndex >= 0 ? colSelect.options[colSelect.selectedIndex]?.text : '') || '';
        let colAbbr = this.makeAcronym(colText);
        if (colAbbr === 'GHRCEG') colAbbr = 'GHRCE';

        const brSelect = document.getElementById('branch');
        const tsBr = window.AbhiHubSelect?.instances['branch'];
        const brId = tsBr ? tsBr.getValue() : (brSelect?.value || '');
        const brText = (tsBr && tsBr.options[brId]?.text) || (brSelect && brSelect.selectedIndex >= 0 ? brSelect.options[brSelect.selectedIndex]?.text : '') || '';
        let deptAbbr = this.makeAcronym(brText);

        const progSelect = document.getElementById('program');
        const progVal = (progSelect?.value || '').trim();
        if (progVal && progVal.toLowerCase() !== 'b.tech') {
            if (!deptAbbr || deptAbbr === 'ALL' || deptAbbr === 'ABA' || /^(all|general)/i.test(brText)) {
                deptAbbr = progVal.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
            }
        }
        if (deptAbbr === 'ABA') deptAbbr = 'MBA';

        const subjSelect = document.getElementById('subjectName');
        const tsSubj = window.AbhiHubSelect?.instances['subjectName'];
        const subjId = tsSubj ? tsSubj.getValue() : (subjSelect?.value || '');
        const rawSubj = (tsSubj && tsSubj.options[subjId]?.text) || (subjSelect && subjSelect.selectedIndex >= 0 ? subjSelect.options[subjSelect.selectedIndex]?.text : '') || '';

        let subjName = rawSubj;
        let subjCode = document.getElementById('subjectCode')?.value || '';
        const match = rawSubj.match(/^(.*?)(?:\s*\((.*?)\))?$/);
        if (match) {
            subjName = match[1].trim();
            if (!subjCode && match[2]) subjCode = match[2].trim();
        }
        const subjAbbr = this.makeAcronym(subjName);

        const prefixTags = [colAbbr, deptAbbr, subjAbbr].filter(Boolean);
        let header = prefixTags.join(' - ');
        if (subjCode && !header.includes(subjCode)) {
            header = header ? `${header} (${subjCode})` : subjCode;
        }

        const catEl = document.getElementById('documentCategory');
        const catTitle = catEl?.value ? (catEl.value.charAt(0).toUpperCase() + catEl.value.slice(1)) : 'Papers';
        const examEl = document.getElementById('examType');
        const examType = examEl?.value || '';
        const yearEl = document.getElementById('year');
        const year = yearEl?.value || '';

        const details = [examType, catTitle, year].filter(Boolean).join(' · ');
        if (header || details) {
            titleEl.value = header && details ? `${header} - ${details}` : (header || details);
        }
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

    initHistoryTab() {
        const btnQueue = document.getElementById('btnQueueMode');
        const btnHistory = document.getElementById('btnHistoryMode');
        const queueList = document.getElementById('filesGrid');
        const historyList = document.getElementById('historyList');
        const loadMore = document.getElementById('viewMoreContainer');
        const filters = document.querySelector('.queue-filters');

        if (!btnQueue || !btnHistory) return;

        btnQueue.addEventListener('click', () => {
            btnQueue.classList.add('active');
            btnHistory.classList.remove('active');
            queueList?.classList.remove('hidden');
            loadMore?.classList.remove('hidden');
            if (filters) filters.style.display = 'flex';
            historyList?.classList.add('hidden');
        });

        btnHistory.addEventListener('click', async () => {
            btnHistory.classList.add('active');
            btnQueue.classList.remove('active');
            queueList?.classList.add('hidden');
            loadMore?.classList.add('hidden');
            if (filters) filters.style.display = 'none';
            historyList?.classList.remove('hidden');

            await this.loadHistory(true);
        });

        // Pre-fetch count on initialization
        this.loadHistory(false);
    }

    async loadHistory(render = true) {
        try {
            const res = await fetch('/store-room/api/history');
            const data = await res.json();
            if (data.success && Array.isArray(data.data)) {
                this.state.historyList = data.data;
                const countBadge = document.getElementById('historyBadgeCount');
                if (countBadge) countBadge.textContent = data.data.length;

                if (render) {
                    this.renderHistory();
                }
            }
        } catch (e) {
            console.warn('Failed to fetch history', e);
        }
    }

    renderHistory() {
        const container = document.getElementById('historyList');
        if (!container) return;
        container.innerHTML = '';

        if (!this.state.historyList || this.state.historyList.length === 0) {
            container.innerHTML = `
                <div class="empty-preview-prompt" style="padding: 2.5rem 1rem;">
                    <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">🌱</div>
                    <p style="font-size: 0.82rem; color: var(--apple-secondary); margin: 0; line-height: 1.4;">
                        You have not cataloged any files yet. Label a file from the queue to start building your permanent curator archive!
                    </p>
                </div>
            `;
            return;
        }

        this.state.historyList.forEach((item) => {
            const card = document.createElement('div');
            card.className = 'history-item-card';
            const catMap = { papers: 'PYQ', notes: 'Notes', practical: 'Practical', syllabus: 'Syllabus' };
            const catLabel = catMap[item.category] || (item.category || 'Paper').toUpperCase();
            const statusClass = item.status === 'approved' ? 'status-approved' : 'status-pending';
            const statusText = item.status === 'approved' ? 'Live ✅' : 'Reviewing ⏳';

            card.innerHTML = `
                <div class="history-card-top">
                    <span class="history-cat-badge">${catLabel}</span>
                    <div style="display:flex; align-items:center; gap:0.4rem;">
                        <span class="history-status-pill ${statusClass}">${statusText}</span>
                        <button type="button" class="btn-text-action edit-label-btn" style="background:none; border:none; color:var(--apple-blue); font-size:0.75rem; font-weight:700; cursor:pointer;" title="Edit this label">✏️ Edit</button>
                    </div>
                </div>
                <div class="history-title" title="${item.title || 'Untitled Resource'}">${item.title || 'Untitled Resource'}</div>
                <div class="history-meta">
                    <span>${item.college || item.subject || 'Verified'}</span>
                    <span>👥 ${item.view_count || 0} views</span>
                </div>
            `;

            card.querySelector('.edit-label-btn')?.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.history-item-card').forEach(c => c.classList.remove('active-preview'));
                card.classList.add('active-preview');
                this.startEditHistoryFile(item);
            });

            card.addEventListener('click', () => {
                document.querySelectorAll('.history-item-card').forEach(c => c.classList.remove('active-preview'));
                card.classList.add('active-preview');
                this.previewHistoryFile(item);
            });

            container.appendChild(card);
        });
    }

    previewHistoryFile(item) {
        const badge = document.getElementById('previewBadge');
        if (badge) badge.textContent = item.title || 'Cataloged Document';
        const pill = document.getElementById('previewFormatPill');
        if (pill) pill.textContent = (item.category || 'Resource').toUpperCase();

        const img = document.getElementById('previewImg');
        const frame = document.getElementById('previewFrame');
        const prompt = document.getElementById('emptyPreviewPrompt');
        const controls = document.getElementById('previewControls');

        if (prompt) prompt.classList.add('hidden');

        const fileUrl = item.file_url;
        const isPdf = (fileUrl && fileUrl.toLowerCase().includes('.pdf')) || (item.title && item.title.toLowerCase().endsWith('.pdf'));

        if (isPdf) {
            if (img) img.classList.add('hidden');
            if (controls) controls.classList.add('hidden');
            if (frame) {
                frame.classList.remove('hidden');
                frame.src = fileUrl;
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
    }

    startEditHistoryFile(item) {
        this.state.isEditMode = true;
        this.state.editingDoc = item;

        this.previewHistoryFile(item);

        const headerTitle = document.getElementById('formHeaderTitle');
        if (headerTitle) headerTitle.textContent = '✏️ Edit Catalog Record';
        const navCounter = document.getElementById('navCounter');
        if (navCounter) navCounter.textContent = 'Editing';
        const cancelBtn = document.getElementById('cancelEditBtn');
        if (cancelBtn) cancelBtn.classList.remove('hidden');
        const saveBtn = document.getElementById('saveBtn');
        if (saveBtn) {
            const btnText = saveBtn.querySelector('.btn-text');
            if (btnText) btnText.textContent = 'Update Record ↵';
        }
        const rememberWrapper = document.getElementById('rememberToggleWrapper');
        if (rememberWrapper) rememberWrapper.style.display = 'none';

        if (item.category) {
            const catEl = document.getElementById('documentCategory');
            if (catEl) catEl.value = item.category;
        }
        if (item.year) {
            const yrEl = document.getElementById('year');
            if (yrEl) yrEl.value = String(item.year);
        }
        if (item.exam_type) {
            const examEl = document.getElementById('examType');
            if (examEl) examEl.value = item.exam_type;
        }
        if (item.subject_code) {
            const codeEl = document.getElementById('subjectCode');
            if (codeEl) codeEl.value = item.subject_code;
        }
        const titleEl = document.getElementById('docTitle');
        if (titleEl) {
            titleEl.value = item.title || '';
            titleEl.dataset.modifiedByUser = 'true';
        }

        if (item.college_id) {
            const tsCol = window.AbhiHubSelect?.instances['collegeName'];
            if (tsCol) tsCol.setValue(String(item.college_id));
            else {
                const colEl = document.getElementById('collegeName');
                if (colEl) colEl.value = String(item.college_id);
            }
        }
        if (item.branch_id) {
            setTimeout(() => {
                const tsBr = window.AbhiHubSelect?.instances['branch'];
                if (tsBr) tsBr.setValue(String(item.branch_id));
                else {
                    const brEl = document.getElementById('branch');
                    if (brEl) brEl.value = String(item.branch_id);
                }
                if (item.semester) {
                    setTimeout(() => {
                        const tsSem = window.AbhiHubSelect?.instances['semester'];
                        if (tsSem) tsSem.setValue(String(item.semester));
                        else {
                            const semEl = document.getElementById('semester');
                            if (semEl) semEl.value = String(item.semester);
                        }
                        if (item.subject_id) {
                            setTimeout(() => {
                                const tsSubj = window.AbhiHubSelect?.instances['subjectName'];
                                if (tsSubj) {
                                    if (!tsSubj.options[item.subject_id]) {
                                        tsSubj.addOption({ value: item.subject_id, text: item.subject || 'Subject' });
                                    }
                                    tsSubj.setValue(String(item.subject_id));
                                } else {
                                    const subjEl = document.getElementById('subjectName');
                                    if (subjEl) subjEl.value = String(item.subject_id);
                                }
                            }, 300);
                        }
                    }, 300);
                }
            }, 300);
        }

        this.showToast(`Editing label for "${item.title || 'document'}"`, 'info');

        const formTab = document.querySelector('.studio-tab-btn[data-tab="form"]');
        if (window.innerWidth <= 900 && formTab) formTab.click();
    }

    cancelEdit() {
        this.state.isEditMode = false;
        this.state.editingDoc = null;

        const headerTitle = document.getElementById('formHeaderTitle');
        if (headerTitle) headerTitle.textContent = 'Catalog Resource';
        const cancelBtn = document.getElementById('cancelEditBtn');
        if (cancelBtn) cancelBtn.classList.add('hidden');
        const saveBtn = document.getElementById('saveBtn');
        if (saveBtn) {
            const btnText = saveBtn.querySelector('.btn-text');
            if (btnText) btnText.textContent = 'Publish to Library (+XP) ↵';
        }
        const rememberWrapper = document.getElementById('rememberToggleWrapper');
        if (rememberWrapper) rememberWrapper.style.display = 'flex';

        if (this.state.files.length > 0 && this.state.activeIndex >= 0) {
            this.selectFileByIndex(this.state.activeIndex);
        } else {
            this.updateNavCounter();
        }
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

        // Gamified Points: Each labeled file gives potential 5 Points per unique viewer (₹0.05 / view)
        const pointsBadge = document.getElementById('rewardPointsCount');
        if (pointsBadge) {
            const earnedPoints = this.state.sortedCount * 5;
            pointsBadge.textContent = `${earnedPoints} Pts`;
        }
    }

    renderQueue() {
        if (!this.grid) return;
        this.grid.innerHTML = '';

        if (this.state.files.length === 0) {
            const hasFilter = document.getElementById('storeRoomSearchInput')?.value || document.getElementById('formatFilter')?.value;
            this.grid.innerHTML = `
                <div style="padding:2rem 1rem; text-align:center; color:#64748b;">
                    <div style="font-size:2rem; margin-bottom:0.5rem;">${hasFilter ? '🔍' : '🎉'}</div>
                    <div style="font-weight:700; color:#0f172a; margin-bottom:0.25rem;">${hasFilter ? 'No Matching Files' : 'Queue is Empty!'}</div>
                    <div style="font-size:0.8rem;">${hasFilter ? 'Try adjusting your search query or format filter.' : 'All files in storage have been labeled.'}</div>
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
            const sizeStr = file.size && file.size !== 'Unknown' ? ` · ${file.size}` : '';

            card.innerHTML = `
                <div class="queue-card-top">
                    <span class="queue-badge">${format}</span>
                    <span class="queue-date">${dateStr}${sizeStr}</span>
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
        if (formatPill) {
            const sizePart = file.size && file.size !== 'Unknown' ? ` (${file.size})` : '';
            formatPill.textContent = `${format}${sizePart}`;
        }

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

        // Auto-fill from local catalog match if not remembering previous labels
        if (this.state.rememberLabels) {
            this.applyRememberedLabels();
        } else {
            this.autoFillLocalMatch(file);
        }

        this.updateAutoTitle();
        this.updateNavCounter();
    }

    autoFillLocalMatch(file) {
        if (!file) return;
        const match = this.matchFileLocally(file);
        if (match) {
            this.applyLocalMatch(match);
        }
    }

    /**
     * Local Zero-Cost Metadata Matcher
     * Evaluates filename tokens against the cached college, department, and subject catalogs.
     */
    matchFileLocally(file) {
        if (!file) return null;
        const rawName = file.filename || file.name || '';
        if (!rawName) return null;

        // Clean name: remove UUID prefixes, hashes, timestamps, and extensions
        let clean = rawName
            .replace(/^[a-f0-9\-]{20,}_\d+_/i, '')
            .replace(/_[a-z0-9]{5,8}(\.[a-z0-9]+)?$/i, '')
            .replace(/\.[a-z0-9]+$/i, '')
            .replace(/[_\-]+/g, ' ')
            .trim();

        const lowerClean = clean.toLowerCase();
        const tokens = lowerClean.split(/\s+/).filter(Boolean);

        const result = {
            category: 'papers',
            year: null,
            examType: null,
            semester: null,
            subjectId: null,
            subjectName: null,
            subjectCode: null,
            branchId: null,
            collegeId: null,
            title: null,
            confidence: 0
        };

        // 1. Detect Category
        if (/paper|pyq|exam|term|mid|ese|cie|question/i.test(lowerClean)) {
            result.category = 'papers';
        } else if (/note|unit|module|chapter|lecture|handwritten/i.test(lowerClean)) {
            result.category = 'notes';
        } else if (/lab|practical|manual|experiment|viva/i.test(lowerClean)) {
            result.category = 'practical';
        } else if (/syllabus|curriculum|scheme/i.test(lowerClean)) {
            result.category = 'syllabus';
        } else if (/qb|question[\s_]*bank|imp/i.test(lowerClean)) {
            result.category = 'question_bank';
        } else if (/timetable|date[\s_]*sheet|schedule/i.test(lowerClean)) {
            result.category = 'timetable';
        }

        // 2. Detect Year (2018 - 2026)
        const yearMatch = lowerClean.match(/\b(201\d|202\d)\b/);
        result.year = yearMatch ? yearMatch[1] : String(new Date().getFullYear());

        // 3. Detect Exam Type
        if (/\b(cae[-_\s]?1|mt[-_\s]?1|ms[-_\s]?1|mid[-_\s]?1|test[-_\s]?1)\b/i.test(lowerClean)) {
            result.examType = 'CAE1';
        } else if (/\b(cae[-_\s]?2|mt[-_\s]?2|ms[-_\s]?2|mid[-_\s]?2|test[-_\s]?2)\b/i.test(lowerClean)) {
            result.examType = 'CAE2';
        } else if (/\b(cae[-_\s]?3|mt[-_\s]?3|ms[-_\s]?3|mid[-_\s]?3)\b/i.test(lowerClean)) {
            result.examType = 'CAE3';
        } else if (/\b(ese|end[\s_-]*sem|final|resit|regular)\b/i.test(lowerClean)) {
            result.examType = 'ESE';
        } else if (/\b(mid|mt|ms)\b/i.test(lowerClean)) {
            result.examType = 'CAE1';
        }

        // 4. Detect Semester (1 - 8)
        const semMatch = lowerClean.match(/\b(?:sem(?:ester)?[\s_-]*([1-8])|s([1-8])|([1-8])(?:st|nd|rd|th)?[\s_-]*sem)\b/i);
        if (semMatch) {
            result.semester = semMatch[1] || semMatch[2] || semMatch[3];
        }

        // 5. Subject Catalog Matching
        const subjectsCache = window.AbhiHubSelect?.apiCache?.['/api/subjects:all']?.subjects ||
                              window.AbhiHubSelect?.apiCache?.['/api/subjects']?.subjects || [];
        
        let bestSubject = null;
        let maxSubScore = 0;

        for (const s of subjectsCache) {
            const sName = (s.name || '').toLowerCase().trim();
            const sCode = (s.subject_code || '').toLowerCase().trim();
            if (!sName) continue;

            const sWords = sName.split(/\s+/).filter(w => w.length > 2 && !['and', 'for', 'the', 'with', 'intro', 'introduction', 'theory'].includes(w));
            let score = 0;

            // A. Exact subject name contained in filename
            if (sName.length > 3 && lowerClean.includes(sName)) {
                score = 150 + sName.length;
            }
            // B. Subject code match (e.g. UITL305, UCSL101, UDH, etc.)
            else if (sCode && sCode.length >= 2 && new RegExp(`\\b${sCode}\\b`, 'i').test(lowerClean)) {
                score = 120 + sCode.length;
            }
            // C. Multi-word overlap
            else if (sWords.length > 0) {
                let overlapCount = 0;
                for (const w of sWords) {
                    if (tokens.includes(w)) overlapCount++;
                }
                if (overlapCount === sWords.length) {
                    score = 100 + overlapCount * 10;
                } else if (overlapCount > 1) {
                    score = overlapCount * 25;
                }
            }

            // D. Acronym match (e.g. ML, NLP, DSA, DT, EM, AP)
            if (score === 0 && sWords.length >= 2) {
                const acronym = sWords.map(w => w[0]).join('');
                if (acronym.length >= 2 && new RegExp(`\\b${acronym}\\b`, 'i').test(lowerClean)) {
                    score = 80 + acronym.length * 5;
                }
            }

            if (score > maxSubScore) {
                maxSubScore = score;
                bestSubject = s;
            }
        }

        if (bestSubject && maxSubScore >= 20) {
            result.subjectId = bestSubject.id;
            result.subjectName = bestSubject.name;
            result.subjectCode = bestSubject.subject_code || '';
            result.branchId = bestSubject.department_id || null;
            if (bestSubject.semester && !result.semester) {
                result.semester = String(bestSubject.semester);
            }
            result.confidence = Math.min(100, Math.round((maxSubScore / 160) * 100));
        }

        // 6. Branch / Department fallback
        if (!result.branchId) {
            const deptsCache = window.AbhiHubSelect?.apiCache?.['/api/departments']?.departments || [];
            for (const d of deptsCache) {
                const dName = (d.name || '').toLowerCase();
                const dAbbr = (d.abbreviation || d.short_name || '').toLowerCase();
                if (dAbbr && new RegExp(`\\b${dAbbr}\\b`, 'i').test(lowerClean)) {
                    result.branchId = d.id;
                    break;
                } else if (dName && lowerClean.includes(dName)) {
                    result.branchId = d.id;
                    break;
                }
            }
        }

        // 7. College detection
        const collegesCache = window.AbhiHubSelect?.apiCache?.['/api/colleges']?.colleges || [];
        for (const c of collegesCache) {
            const cAbbr = (c.abbreviation || c.short_name || '').toLowerCase();
            const cName = (c.name || '').toLowerCase();
            if (cAbbr && new RegExp(`\\b${cAbbr}\\b`, 'i').test(lowerClean)) {
                result.collegeId = c.id;
                break;
            } else if (cName && lowerClean.includes(cName)) {
                result.collegeId = c.id;
                break;
            }
        }

        // 8. Clean Human Title
        if (result.subjectName) {
            const parts = [result.subjectName];
            if (result.examType) parts.push(result.examType);
            if (result.year) parts.push(result.year);
            result.title = parts.join(' ');
        } else {
            result.title = clean.replace(/\b\w/g, l => l.toUpperCase());
        }

        return result;
    }

    applyLocalMatch(match) {
        if (!match) return;

        // 1. Category
        if (match.category) {
            const catEl = document.getElementById('documentCategory');
            if (catEl) catEl.value = match.category;
        }

        // 2. Year
        if (match.year) {
            const yearEl = document.getElementById('year');
            if (yearEl) yearEl.value = String(match.year);
        }

        // 3. Exam Type
        if (match.examType) {
            const examEl = document.getElementById('examType');
            if (examEl) examEl.value = match.examType;
        }

        // 4. College
        if (match.collegeId) {
            const tsCol = window.AbhiHubSelect?.instances['collegeName'];
            if (tsCol) tsCol.setValue(String(match.collegeId), true);
            else {
                const el = document.getElementById('collegeName');
                if (el) el.value = String(match.collegeId);
            }
        }

        // 5. Branch
        if (match.branchId) {
            const tsBr = window.AbhiHubSelect?.instances['branch'];
            if (tsBr) tsBr.setValue(String(match.branchId), true);
            else {
                const el = document.getElementById('branch');
                if (el) el.value = String(match.branchId);
            }
        }

        // 6. Semester
        if (match.semester) {
            const tsSem = window.AbhiHubSelect?.instances['semester'];
            if (tsSem) tsSem.setValue(String(match.semester), true);
            else {
                const el = document.getElementById('semester');
                if (el) el.value = String(match.semester);
            }
        }

        // 7. Subject
        if (match.subjectId) {
            const tsSubj = window.AbhiHubSelect?.instances['subjectName'];
            if (tsSubj) {
                if (!tsSubj.options[match.subjectId]) {
                    tsSubj.addOption({ value: match.subjectId, text: match.subjectName });
                }
                tsSubj.setValue(match.subjectId, true);
            } else {
                const el = document.getElementById('subjectName');
                if (el) el.value = match.subjectId;
            }
        }

        // 8. Subject Code
        if (match.subjectCode) {
            const codeEl = document.getElementById('subjectCode');
            if (codeEl) codeEl.value = match.subjectCode;
        }

        // 9. Document Title with standard abbreviations
        this.updateAutoTitle();
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

    findSubjectInCatalog(text, code) {
        if (!text && !code) return null;
        const subjectsCache = window.AbhiHubSelect?.apiCache?.['/api/subjects:all']?.subjects ||
                              window.AbhiHubSelect?.apiCache?.['/api/subjects']?.subjects || [];
        const cleanT = (text || '').toLowerCase().trim();
        const cleanC = (code || '').toLowerCase().trim();

        for (const s of subjectsCache) {
            const sName = (s.name || '').toLowerCase().trim();
            const sCode = (s.subject_code || '').toLowerCase().trim();

            if (cleanC && sCode && (cleanC === sCode || cleanC.includes(sCode) || sCode.includes(cleanC))) {
                return s;
            }
            if (cleanT && sName && (cleanT === sName || cleanT.includes(sName) || sName.includes(cleanT))) {
                return s;
            }
        }

        if (cleanT.length > 3) {
            for (const s of subjectsCache) {
                const sName = (s.name || '').toLowerCase().trim();
                const words = cleanT.split(/\s+/).filter(w => w.length > 2);
                const sWords = sName.split(/\s+/).filter(w => w.length > 2);
                const overlap = words.filter(w => sWords.includes(w));
                if (overlap.length >= 2 && overlap.length >= sWords.length * 0.6) {
                    return s;
                }
            }
        }
        return null;
    }

    findCollegeInCatalog(text) {
        if (!text) return null;
        const collegesCache = window.AbhiHubSelect?.apiCache?.['/api/colleges']?.colleges || [];
        const cleanT = text.toLowerCase().trim();

        for (const c of collegesCache) {
            const cAbbr = (c.abbreviation || c.short_name || '').toLowerCase().trim();
            const cName = (c.name || '').toLowerCase().trim();

            if (cAbbr && (cleanT.includes(cAbbr) || cAbbr.includes(cleanT))) return c.id;
            if (cName && (cleanT.includes(cName) || cName.includes(cleanT))) return c.id;
        }
        return null;
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
            btn.innerHTML = '<span>⏳ Scanning File & Document Image…</span>';
        }

        // 1. Extract metadata from filename
        const fileMatch = this.matchFileLocally(cur) || {};

        try {
            // 2. Extract text & visual metadata from document image
            const res = await StoreRoomAPI.extractAiSuggestions(cur, fileMatch);
            const imgData = (res && res.success && res.result && res.result.data) ? res.result.data : {};

            const sources = [];

            // 3. Smart Fusion across all form boxes

            // Category
            const catMap = { pyq: 'papers', notes: 'notes', practicals: 'practical', syllabus: 'syllabus', question_bank: 'question_bank', timetable: 'timetable' };
            const resolvedCategory = (imgData.document_type || imgData.type) ? (catMap[imgData.document_type || imgData.type] || imgData.document_type || imgData.type) : fileMatch.category;
            if (resolvedCategory) {
                const catEl = document.getElementById('documentCategory');
                if (catEl) catEl.value = resolvedCategory;
                sources.push(imgData.type ? 'Category (image)' : 'Category (filename)');
            }

            // Year
            const resolvedYear = imgData.year || fileMatch.year;
            if (resolvedYear) {
                const yearEl = document.getElementById('year');
                if (yearEl) yearEl.value = String(resolvedYear);
                sources.push(imgData.year ? 'Year (image)' : 'Year (filename)');
            }

            // Exam Type / Unit
            const resolvedExam = imgData.unit || fileMatch.examType;
            if (resolvedExam) {
                const examEl = document.getElementById('examType');
                if (examEl) examEl.value = resolvedExam;
                sources.push(imgData.unit ? 'Exam (image)' : 'Exam (filename)');
            }

            // Subject & Subject Code
            let matchedSubject = null;
            if (imgData.subject_id) {
                matchedSubject = { id: imgData.subject_id, name: imgData.subject_name || imgData.subject };
            } else if (imgData.subject_name || imgData.subject_match || imgData.subject_code) {
                matchedSubject = this.findSubjectInCatalog(imgData.subject_name || imgData.subject_match, imgData.subject_code);
            }
            if (!matchedSubject && fileMatch.subjectId) {
                matchedSubject = { id: fileMatch.subjectId, name: fileMatch.subjectName, subject_code: fileMatch.subjectCode, department_id: fileMatch.branchId };
            }

            if (matchedSubject) {
                const tsSubj = window.AbhiHubSelect?.instances['subjectName'];
                if (tsSubj) {
                    if (!tsSubj.options[matchedSubject.id]) {
                        tsSubj.addOption({ value: matchedSubject.id, text: matchedSubject.name || 'Subject' });
                    }
                    tsSubj.setValue(matchedSubject.id, true);
                } else {
                    const subjEl = document.getElementById('subjectName');
                    if (subjEl) subjEl.value = matchedSubject.id;
                }

                // Code
                const sCode = matchedSubject.subject_code || imgData.subject_code || fileMatch.subjectCode;
                if (sCode) {
                    const codeEl = document.getElementById('subjectCode');
                    if (codeEl) codeEl.value = sCode;
                }

                sources.push(imgData.subject_name || imgData.subject_match ? 'Subject (image)' : 'Subject (filename)');
            }

            // Department / Branch
            const resolvedBranchId = (matchedSubject && matchedSubject.department_id) || imgData.branch_id || fileMatch.branchId;
            if (resolvedBranchId) {
                const tsBr = window.AbhiHubSelect?.instances['branch'];
                if (tsBr) tsBr.setValue(String(resolvedBranchId), true);
                else {
                    const brEl = document.getElementById('branch');
                    if (brEl) brEl.value = String(resolvedBranchId);
                }
            }

            // Semester
            const resolvedSem = imgData.semester || fileMatch.semester;
            if (resolvedSem) {
                const tsSem = window.AbhiHubSelect?.instances['semester'];
                if (tsSem) tsSem.setValue(String(resolvedSem), true);
                else {
                    const semEl = document.getElementById('semester');
                    if (semEl) semEl.value = String(resolvedSem);
                }
                sources.push(imgData.semester ? 'Semester (image)' : 'Semester (filename)');
            }

            // College
            const collegeFromImage = imgData.college ? this.findCollegeInCatalog(imgData.college) : null;
            const resolvedCollegeId = collegeFromImage || fileMatch.collegeId;
            if (resolvedCollegeId) {
                const tsCol = window.AbhiHubSelect?.instances['collegeName'];
                if (tsCol) tsCol.setValue(String(resolvedCollegeId), true);
                else {
                    const colEl = document.getElementById('collegeName');
                    if (colEl) colEl.value = String(resolvedCollegeId);
                }
                if (collegeFromImage) sources.push('College (image)');
            }

            // Title
            const cleanTitle = (matchedSubject ? matchedSubject.name : (imgData.title || fileMatch.title || '')) + (resolvedExam ? ` ${resolvedExam}` : '') + (resolvedYear ? ` ${resolvedYear}` : '');
            const titleEl = document.getElementById('docTitle');
            if (titleEl && cleanTitle) {
                titleEl.value = cleanTitle.trim();
            }

            this.showToast(`✨ Smart Fill: Merged filename & image analysis (${sources.slice(0, 4).join(', ')})`, 'success');

        } catch (e) {
            console.warn('Smart Fill error', e);
            if (fileMatch) {
                this.applyLocalMatch(fileMatch);
                this.showToast(`⚡ Filled from filename (${fileMatch.title})`, 'info');
            } else {
                this.showToast('Could not extract details. Please enter manually.', 'error');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span>⚡ Smart Auto-Fill (Image + Filename)</span>';
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
        const cur = this.state.isEditMode ? this.state.editingDoc : this.state.activeFile;
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
            payload.storage_provider = cur.storage_provider || 'cloudinary';
            payload.provider_public_id = cur.storage_id || '';
            payload.college_id = document.getElementById('collegeName')?.value;
            payload.branch_id = document.getElementById('branch')?.value;

            const tsSubj = window.AbhiHubSelect?.instances['subjectName'];
            const subjId = tsSubj ? tsSubj.getValue() : (document.getElementById('subjectName')?.value || '');
            payload.subject_id = subjId;

            if (tsSubj && tsSubj.options[subjId]) {
                const optText = tsSubj.options[subjId].text || '';
                const match = optText.match(/^(.*?)(?:\s*\((.*?)\))?$/);
                payload.subject_name = match ? match[1].trim() : optText;
                payload.subject_code = match && match[2] ? match[2].trim() : '';
            } else {
                const subjSelect = document.getElementById('subjectName');
                if (subjSelect && subjSelect.selectedIndex >= 0) {
                    const optText = subjSelect.options[subjSelect.selectedIndex]?.text || '';
                    if (optText && !optText.startsWith('Select')) {
                        const match = optText.match(/^(.*?)(?:\s*\((.*?)\))?$/);
                        payload.subject_name = match ? match[1].trim() : optText;
                        payload.subject_code = match && match[2] ? match[2].trim() : '';
                    }
                }
            }

            const colSelect = document.getElementById('collegeName');
            const tsCol = window.AbhiHubSelect?.instances['collegeName'];
            const colId = tsCol ? tsCol.getValue() : (colSelect?.value || '');
            const colText = (tsCol && tsCol.options[colId]?.text) || (colSelect && colSelect.selectedIndex >= 0 ? colSelect.options[colSelect.selectedIndex]?.text : '') || '';
            let colAbbr = this.makeAcronym(colText);
            if (colAbbr === 'GHRCEG') colAbbr = 'GHRCE';
            payload.college_abbr = colAbbr;

            const brSelect = document.getElementById('branch');
            const tsBr = window.AbhiHubSelect?.instances['branch'];
            const brId = tsBr ? tsBr.getValue() : (brSelect?.value || '');
            const brText = (tsBr && tsBr.options[brId]?.text) || (brSelect && brSelect.selectedIndex >= 0 ? brSelect.options[brSelect.selectedIndex]?.text : '') || '';
            let deptAbbr = this.makeAcronym(brText);
            const progSelect = document.getElementById('program');
            const progVal = (progSelect?.value || '').trim();
            if (progVal && progVal.toLowerCase() !== 'b.tech') {
                if (!deptAbbr || deptAbbr === 'ALL' || deptAbbr === 'ABA' || /^(all|general)/i.test(brText)) {
                    deptAbbr = progVal.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
                }
            }
            if (deptAbbr === 'ABA') deptAbbr = 'MBA';
            payload.branch_abbr = deptAbbr;

            payload.subject_abbr = this.makeAcronym(payload.subject_name);

            if (this.state.isEditMode && this.state.editingDoc) {
                payload.document_id = this.state.editingDoc.id;
                const res = await StoreRoomAPI.updateLabel(payload);
                const data = res.data;
                if (res.response && res.response.ok && data && data.success) {
                    this.showToast('✅ Label updated successfully!', 'success');
                    Object.assign(this.state.editingDoc, {
                        title: data.data?.title || payload.title,
                        category: data.data?.document_category || payload.document_category,
                        college_id: payload.college_id,
                        branch_id: payload.branch_id,
                        subject_id: payload.subject_id,
                        subject: payload.subject_name,
                        subject_code: payload.subject_code,
                        semester: payload.semester,
                        year: payload.year,
                        exam_type: payload.exam_type
                    });
                    this.renderHistory();
                    this.cancelEdit();
                } else {
                    this.showToast((data && data.message) ? data.message : 'Failed to update label', 'error');
                }
                return;
            }

            const res = await StoreRoomAPI.submitLabel(payload);
            const data = res.data;
            if (res.response && res.response.ok && data && data.success) {
                this.triggerGamifiedRewardPop(btn);
                this.showToast('🎉 +10 XP & 5 Royalty Points unlocked! Document published to academic library.', 'success');

                // Update live session gamification stats
                window.sessionCuratorCount = (window.sessionCuratorCount || 0) + 1;
                window.sessionStreak = (window.sessionStreak || 0) + 1;
                const streakEl = document.getElementById('curatorStreakVal');
                if (streakEl) streakEl.textContent = `${window.sessionStreak}x Streak 🔥`;
                const questFill = document.getElementById('curatorQuestFill');
                const questLabel = document.getElementById('curatorQuestLabel');
                if (questFill) {
                    const pct = Math.min(100, Math.round((window.sessionCuratorCount / 3) * 100));
                    questFill.style.width = Math.max(15, pct) + '%';
                    if (questLabel) {
                        questLabel.textContent = window.sessionCuratorCount >= 3 
                            ? `🎉 Quest Achieved! ${window.sessionCuratorCount} papers cataloged. You unlocked +50 Bonus XP!` 
                            : `${window.sessionCuratorCount}/3 Complete · Catalog ${3 - window.sessionCuratorCount} more for +50 XP bonus!`;
                    }
                }

                if (this.state.rememberLabels) {
                    this.saveRememberedLabels();
                }

                // Update state counts
                this.state.sortedCount++;
                this.state.remainingCount = Math.max(0, this.state.remainingCount - 1);
                this.updateProgress();

                // Prepend to history list in memory
                if (!this.state.historyList) this.state.historyList = [];
                const colSelect = document.getElementById('collegeName');
                const colText = colSelect ? (colSelect.options[colSelect.selectedIndex]?.text || '') : '';
                this.state.historyList.unshift({
                    id: data.data?.id || String(Date.now()),
                    title: data.data?.title || payload.title || payload.subject_name || cur.filename,
                    category: data.data?.document_category || payload.document_category || 'papers',
                    college: colText,
                    subject: payload.subject_name || '',
                    file_url: data.data?.file_url || cur.url || cur.path,
                    view_count: 0,
                    status: data.data?.status || 'pending',
                    labeled_at: data.data?.created_at || new Date().toISOString()
                });
                const countBadge = document.getElementById('historyBadgeCount');
                if (countBadge) countBadge.textContent = this.state.historyList.length;

                const historyListEl = document.getElementById('historyList');
                if (historyListEl && !historyListEl.classList.contains('hidden')) {
                    this.renderHistory();
                }

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
                const errMsg = (data && data.message) ? data.message : `Failed to save label (${res.response ? res.response.status : 'Unknown error'})`;
                this.showToast(errMsg, 'error');
            }
        } catch (err) {
            console.error('Save failed', err);
            this.showToast('Network error while saving label: ' + (err.message || 'Check connection'), 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    }

    triggerGamifiedRewardPop(anchorEl) {
        try {
            const rect = anchorEl ? anchorEl.getBoundingClientRect() : { left: window.innerWidth / 2, top: window.innerHeight / 2 };
            const pop = document.createElement('div');
            pop.className = 'point-pop-badge';
            pop.innerHTML = '✨ +5 Points Earned! (₹0.05/view)';
            pop.style.left = `${Math.max(16, rect.left - 40)}px`;
            pop.style.top = `${Math.max(16, rect.top - 20)}px`;
            document.body.appendChild(pop);
            setTimeout(() => pop.remove(), 1500);
        } catch (e) {
            console.warn('Pop animation error', e);
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

                const queueBadge = document.getElementById('queueBadgeCount');
                if (queueBadge) {
                    queueBadge.textContent = (search || format) ? (res.pagination?.total ?? this.state.files.length) : this.state.remainingCount;
                }

                this.renderQueue();

                if (this.state.files.length > 0) {
                    this.selectFileByIndex(0);
                } else {
                    this.state.activeIndex = -1;
                    document.getElementById('emptyPreviewPrompt')?.classList.remove('hidden');
                    document.getElementById('previewImg')?.classList.add('hidden');
                    document.getElementById('previewFrame')?.classList.add('hidden');
                    document.getElementById('previewControls')?.classList.add('hidden');
                    const badge = document.getElementById('previewBadge');
                    if (badge) badge.textContent = search ? 'No Matching Files' : 'Queue Empty';
                    const pill = document.getElementById('previewFormatPill');
                    if (pill) pill.textContent = 'NONE';
                    const navCounter = document.getElementById('navCounter');
                    if (navCounter) navCounter.textContent = '0 / 0';
                }

                const loadMoreBtn = document.getElementById('viewMoreBtn');
                if (loadMoreBtn) {
                    loadMoreBtn.style.display = res.pagination?.has_more ? 'block' : 'none';
                    loadMoreBtn.textContent = 'Load More Queue Files';
                }
            }
        } catch (e) {
            console.error('Failed to reload files', e);
        }
    }

    async loadMoreFiles() {
        const btn = document.getElementById('viewMoreBtn');
        if (btn) btn.textContent = 'Loading...';

        const search = document.getElementById('storeRoomSearchInput')?.value || '';
        const format = document.getElementById('formatFilter')?.value || '';
        const sort = document.getElementById('sortSelect')?.value || 'date';

        try {
            const res = await StoreRoomAPI.fetchFiles({
                search,
                format,
                sort_by: sort === 'name' ? 'filename' : 'created_at',
                order: sort === 'name' ? 'asc' : 'desc',
                offset: this.state.currentOffset,
                limit: this.state.itemsPerPage
            });

            if (res.success && res.files && res.files.length > 0) {
                this.state.files.push(...res.files);
                this.state.currentOffset += res.files.length;
                this.renderQueue();
            }
            if (btn) {
                if (!res.pagination?.has_more) {
                    btn.textContent = 'All Files Loaded';
                    btn.style.display = 'none';
                } else {
                    btn.textContent = 'Load More Queue Files';
                    btn.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('Failed to load more files', e);
            if (btn) btn.textContent = 'Load More Queue Files';
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

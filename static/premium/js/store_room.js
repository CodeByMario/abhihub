/**
 * Store Room JavaScript - Enhanced Adaptive Version
 * Features:
 * - Adaptive layout (split-screen desktop / drawer mobile)
 * - Gesture-based image viewing (pinch zoom, pan, rotate)
 * - Smart form suggestions from localStorage
 * - Save button with states (idle, saving, saved, error)
 * - Unsaved changes protection
 * - Accessibility support
 */

// ==========================================
// File Navigation
// ==========================================
let currentFileIndex = -1;

function getCurrentFileIndex() {
    if (!currentFileData) return -1;
    return currentFiles.findIndex(f => f.filename === currentFileData.filename);
}

function navigateToPreviousFile() {
    const currentIndex = getCurrentFileIndex();
    if (currentIndex <= 0) return; // Can't go before first file

    if (isFormDirty) {
        // Save current file first
        pendingCloseAction = () => openLabelingView(currentFiles[currentIndex - 1]);
        showConfirmDialog();
    } else {
        openLabelingView(currentFiles[currentIndex - 1]);
    }
}

function navigateToNextFile() {
    const currentIndex = getCurrentFileIndex();
    if (currentIndex >= currentFiles.length - 1) return; // Can't go after last file

    if (isFormDirty) {
        // Save current file first
        pendingCloseAction = () => openLabelingView(currentFiles[currentIndex + 1]);
        showConfirmDialog();
    } else {
        openLabelingView(currentFiles[currentIndex + 1]);
    }
}

function updateNavigationButtons() {
    const currentIndex = getCurrentFileIndex();
    const totalFiles = currentFiles.length;

    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const navCounter = document.getElementById('navCounter');

    if (!prevBtn || !nextBtn || !navCounter) return;

    // Update counter
    navCounter.textContent = `${currentIndex + 1} / ${totalFiles}`;

    // Update button states
    prevBtn.disabled = currentIndex <= 0;
    nextBtn.disabled = currentIndex >= totalFiles - 1;
}

// ==========================================
// File Navigation
let currentFiles = [];
let currentFileData = null;
let searchHistory = [];
let formSuggestions = {};
let isFormDirty = false;
let pendingCloseAction = null;

// Pagination state
let currentOffset = 20; // We start with 20 files already loaded
let itemsPerPage = 20;
let hasMore = true;
let isLoadingMore = false;
let totalFiles = 0;

// Image viewer state
let currentZoom = 1;
let currentRotation = 0;
let panX = 0;
let panY = 0;
let isPanning = false;
let lastPanPoint = { x: 0, y: 0 };

// Drawer state (mobile)
let drawerState = 'collapsed'; // 'collapsed', 'half', 'full'
let drawerStartY = 0;
let drawerCurrentY = 0;

// Panel resize state (desktop)
let isResizing = false;
let panelWidth = localStorage.getItem('storeroom_panel_width') || 420;

// Remember last labels toggle
let rememberLabels = localStorage.getItem('storeroom_remember_labels') === 'true';

// ==========================================
// Initialization
// ==========================================
document.addEventListener('DOMContentLoaded', function () {
    initializeStoreRoom();
    loadSearchHistory();
    loadFormSuggestions();
    fetchMetadata(); // Fetch college and branch data
    initializeGestures();
    initializeDrawer();
    initializePanelResizer();
    initializeRememberToggle();
    initializeFormTracking();
});

function initializeStoreRoom() {
    // Get initial files from the page
    const fileCards = document.querySelectorAll('.file-card');
    currentFiles = Array.from(fileCards).map(card => {
        try {
            return JSON.parse(card.getAttribute('data-file'));
        } catch (e) {
            console.error('Error parsing file data:', e);
            return null;
        }
    }).filter(f => f !== null);

    console.log(`Initialized with ${currentFiles.length} files`);

    // Get total files from stats (if available)
    const totalCountEl = document.getElementById('totalCount');
    if (totalCountEl) {
        totalFiles = parseInt(totalCountEl.textContent) || currentFiles.length;
    }

    // Check if we need to show "View More" button
    const viewMoreContainer = document.getElementById('viewMoreContainer');
    if (viewMoreContainer) {
        // Hide if we've loaded all files or if there are fewer than initial batch size
        if (currentFiles.length >= totalFiles || currentFiles.length < itemsPerPage) {
            viewMoreContainer.classList.add('hidden');
            hasMore = false;
        }
    }

    // Attach event listeners
    attachFileCardListeners();
    attachControlListeners();
    attachKeyboardListeners();
    attachNavigationListeners();

    // Handle window resize
    window.addEventListener('resize', () => {
        const formPanel = document.getElementById('formPanel');
        const labelingView = document.getElementById('labelingView');

        if (window.innerWidth > 768) {
            // Desktop: Clear mobile drawer styles
            if (formPanel) {
                formPanel.style.height = '';
                formPanel.classList.remove('half', 'full', 'collapsed');
            }
            if (labelingView) {
                labelingView.style.removeProperty('--drawer-height');
            }
            applyPanelWidth();
        } else {
            // Mobile: If open, ensure drawer state
            if (labelingView && labelingView.classList.contains('active')) {
                // If not already set, default to half
                if (!formPanel.style.height) {
                    setDrawerState('half');
                }
            }
        }
    });
}

function attachNavigationListeners() {
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');

    if (prevBtn) {
        prevBtn.addEventListener('click', navigateToPreviousFile);
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', navigateToNextFile);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (!document.getElementById('labelingView').classList.contains('active')) return;

        // Prevent navigation if typing in an input
        if (
            e.target.tagName === 'INPUT' ||
            e.target.tagName === 'TEXTAREA' ||
            e.target.tagName === 'SELECT'
        ) return;

        if (e.key === 'ArrowLeft' && !e.ctrlKey && !e.altKey) {
            navigateToPreviousFile();
        } else if (e.key === 'ArrowRight' && !e.ctrlKey && !e.altKey) {
            navigateToNextFile();
        }
    });
}

function attachFileCardListeners() {
    const fileCards = document.querySelectorAll('.file-card');
    fileCards.forEach(card => {
        card.addEventListener('click', function () {
            const fileData = JSON.parse(this.getAttribute('data-file'));
            openLabelingView(fileData);
        });
    });
}

function attachControlListeners() {
    // Search input
    const searchInput = document.getElementById('storeRoomSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', handleSearch);
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter' && e.target.value.trim()) {
                saveSearchHistory(e.target.value.trim());
            }
        });
    }

    // Sort select
    const sortSelect = document.getElementById('sortSelect');
    if (sortSelect) {
        sortSelect.addEventListener('change', handleSort);
    }

    // Format filter
    const formatFilter = document.getElementById('formatFilter');
    if (formatFilter) {
        formatFilter.addEventListener('change', handleFilter);
    }

    // Verification filter
    const verificationFilter = document.getElementById('verificationFilter');
    if (verificationFilter) {
        verificationFilter.addEventListener('change', handleFilter);
    }
}

// ==========================================
// Search, Sort, and Filter Handlers
// ==========================================
let searchDebounceTimer = null;

async function handleSearch(e) {
    // Track search query
    const searchQuery = e?.target?.value || '';

    // Debounce search input
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(async () => {
        // Track the search action
        if (searchQuery && window.AbhiHubTracking && window.AbhiHubTracking.trackSearch) {
            try {
                const resultCount = currentFiles.length; // Will be updated after reload
                window.AbhiHubTracking.trackSearch(searchQuery, resultCount, 'storeroom');
            } catch (error) {
                console.error('Error tracking search:', error);
            }
        }
        await reloadFiles();
    }, 300);
}

async function handleSort(e) {
    // Track sort action
    const sortValue = e?.target?.value || '';
    if (sortValue && window.AbhiHubTracking && window.AbhiHubTracking.trackFilterAction) {
        try {
            window.AbhiHubTracking.trackFilterAction('sort', sortValue, currentFiles.length);
        } catch (error) {
            console.error('Error tracking sort:', error);
        }
    }
    await reloadFiles();
}

async function handleFilter(e) {
    // Track filter action
    const filterType = e?.target?.id || 'unknown';
    const filterValue = e?.target?.value || '';
    if (filterValue && window.AbhiHubTracking && window.AbhiHubTracking.trackFilterAction) {
        try {
            window.AbhiHubTracking.trackFilterAction(filterType, filterValue, currentFiles.length);
        } catch (error) {
            console.error('Error tracking filter:', error);
        }
    }
    await reloadFiles();
}

// Reload files with current filters
async function reloadFiles() {
    const filesGrid = document.getElementById('filesGrid');
    const viewMoreContainer = document.getElementById('viewMoreContainer');

    if (!filesGrid) return;

    try {
        // Reset pagination
        currentOffset = 0;
        hasMore = true;

        // Get filter values
        const searchInput = document.getElementById('storeRoomSearchInput');
        const sortSelect = document.getElementById('sortSelect');
        const formatFilter = document.getElementById('formatFilter');
        const verificationFilter = document.getElementById('verificationFilter');

        const params = new URLSearchParams({
            offset: 0,
            limit: itemsPerPage,
            search: searchInput?.value || '',
            sort_by: sortSelect?.value || 'date',
            format: formatFilter?.value || '',
            verification: verificationFilter?.value || ''
        });

        const response = await fetch(`/store-room/api/files?${params}`);
        const data = await response.json();

        if (data.success) {
            // Clear current files
            currentFiles = data.files || [];

            // Clear grid
            filesGrid.innerHTML = '';

            // Check if we have any files
            if (currentFiles.length === 0) {
                // Show empty state
                filesGrid.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">📂</div>
                        <h3 class="empty-title">No Files Found</h3>
                        <p class="empty-text">Try adjusting your search or filters</p>
                    </div>
                `;
                if (viewMoreContainer) {
                    viewMoreContainer.classList.add('hidden');
                }
            } else {
                // Add files to grid
                currentFiles.forEach(file => {
                    const card = createFileCard(file);
                    filesGrid.appendChild(card);
                });

                // Re-attach listeners
                attachFileCardListeners();

                // Update pagination state
                currentOffset = currentFiles.length;
                hasMore = data.pagination?.has_more || false;

                // Show/hide "View More" button
                if (viewMoreContainer) {
                    if (hasMore) {
                        viewMoreContainer.classList.remove('hidden');
                    } else {
                        viewMoreContainer.classList.add('hidden');
                    }
                }
            }

            // Update stats
            if (data.statistics) {
                updateStats(data.statistics);
            }
        }
    } catch (error) {
        console.error('Error reloading files:', error);
        showToast('Failed to load files', 'error');
    }
}

function attachKeyboardListeners() {
    document.addEventListener('keydown', function (event) {
        const labelingView = document.getElementById('labelingView');
        if (!labelingView?.classList.contains('active')) return;

        switch (event.key) {
            case 'Escape':
                closeLabelingView();
                break;
            case '+':
            case '=':
                zoomIn();
                break;
            case '-':
                zoomOut();
                break;
            case 'r':
            case 'R':
                rotateImage();
                break;
        }
    });
}

// ==========================================
// Pagination - Load More Files
// ==========================================
async function loadMoreFiles() {
    if (isLoadingMore || !hasMore) return;

    isLoadingMore = true;
    const viewMoreBtn = document.getElementById('viewMoreBtn');
    const filesGrid = document.getElementById('filesGrid');

    // Update button state to loading
    if (viewMoreBtn) {
        viewMoreBtn.classList.add('loading');
        viewMoreBtn.disabled = true;
    }

    try {
        // Get current filter/search/sort settings
        const searchInput = document.getElementById('storeRoomSearchInput');
        const sortSelect = document.getElementById('sortSelect');
        const formatFilter = document.getElementById('formatFilter');
        const verificationFilter = document.getElementById('verificationFilter');

        const params = new URLSearchParams({
            offset: currentOffset,
            limit: itemsPerPage,
            search: searchInput?.value || '',
            sort_by: sortSelect?.value || 'date',
            format: formatFilter?.value || '',
            verification: verificationFilter?.value || ''
        });

        const response = await fetch(`/store-room/api/files?${params}`);
        const data = await response.json();

        if (data.success && data.files && data.files.length > 0) {
            // Add new files to current files array
            currentFiles.push(...data.files);

            // Create and append new file cards
            data.files.forEach(file => {
                const card = createFileCard(file);
                filesGrid.appendChild(card);
            });

            // Re-attach listeners to new cards
            attachFileCardListeners();

            // Update pagination state
            currentOffset += data.files.length;
            hasMore = data.pagination?.has_more || false;

            // Update stats if available
            if (data.statistics) {
                updateStats(data.statistics);
            }

            // Hide button if no more files
            if (!hasMore) {
                const viewMoreContainer = document.getElementById('viewMoreContainer');
                if (viewMoreContainer) {
                    viewMoreContainer.classList.add('hidden');
                }
            }

            console.log(`Loaded ${data.files.length} more files. Total: ${currentFiles.length}`);
        } else {
            // No more files available
            hasMore = false;
            const viewMoreContainer = document.getElementById('viewMoreContainer');
            if (viewMoreContainer) {
                viewMoreContainer.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Error loading more files:', error);
        showToast('Failed to load more files', 'error');
    } finally {
        isLoadingMore = false;
        if (viewMoreBtn) {
            viewMoreBtn.classList.remove('loading');
            viewMoreBtn.disabled = false;
        }
    }
}

// Helper function to create file card element
function createFileCard(file) {
    const card = document.createElement('div');
    card.className = 'file-card fade-in';
    card.setAttribute('data-file', JSON.stringify(file));

    // Verified Badge
    if (file.verified) {
        const badge = document.createElement('div');
        badge.className = 'label-badge';
        badge.textContent = 'Verified';
        card.appendChild(badge);
    }

    // Pending Verification style
    if (file.verification_status === 'pending') {
        card.classList.add('pending-verification');
    } else if (file.verified) {
        card.classList.add('verified');
    }

    // Icon Wrapper
    const iconWrapper = document.createElement('div');
    iconWrapper.className = 'file-icon-wrapper';

    const icon = document.createElement('img');
    icon.className = 'file-icon';
    // Determine icon based on file type/name
    if (file.format === 'pdf' || (file.filename && file.filename.toLowerCase().endsWith('.pdf'))) {
        icon.src = '/static/premium/icon/notes.gif';
        icon.alt = 'PDF';
    } else {
        icon.src = '/static/premium/icon/practicals.gif';
        icon.alt = 'Image';
    }
    iconWrapper.appendChild(icon);
    card.appendChild(iconWrapper);

    // File Name
    const fileName = document.createElement('div');
    fileName.className = 'file-name';
    fileName.title = file.filename;
    fileName.textContent = file.filename;
    card.appendChild(fileName);

    // Meta (Format • Size)
    const fileMeta = document.createElement('div');
    fileMeta.className = 'file-meta';

    // Create spans for meta info
    const formatSpan = document.createElement('span');
    formatSpan.textContent = (file.format || 'UNK').toUpperCase();

    const separator = document.createElement('span');
    separator.textContent = ' • ';

    const sizeSpan = document.createElement('span');
    sizeSpan.textContent = file.size || '0 B';

    fileMeta.appendChild(formatSpan);
    fileMeta.appendChild(separator);
    fileMeta.appendChild(sizeSpan);
    card.appendChild(fileMeta);

    // Date
    const fileDate = document.createElement('div');
    fileDate.className = 'file-meta';
    fileDate.style.marginTop = '4px';
    fileDate.style.fontSize = '0.7rem';
    fileDate.textContent = file.created_at ? file.created_at.substring(0, 10) : 'Recent';
    card.appendChild(fileDate);

    // Footer for engagement
    if (file.record_id) {
        const footer = document.createElement('div');
        footer.className = 'file-card-footer';
        footer.classList.add('flex');
        footer.style.justifyContent = 'space-around';
        footer.style.paddingTop = '10px';
        footer.style.marginTop = '10px';
        footer.style.borderTop = '1px solid #eee';
        footer.onclick = (e) => e.stopPropagation();

        // Like button
        const likeBtn = document.createElement('button');
        likeBtn.className = `action-btn like-btn ${file.is_liked ? 'liked' : ''}`;
        likeBtn.style.border = 'none';
        likeBtn.style.background = 'none';
        likeBtn.style.cursor = 'pointer';
        likeBtn.innerHTML = `
            <i class="fas fa-heart" style="color: ${file.is_liked ? '#ef4444' : '#94a3b8'}"></i>
            <span class="like-count" style="font-size: 0.8rem; margin-left: 4px;">${file.like_count || ''}</span>
        `;
        likeBtn.onclick = (e) => toggleLike(e, file.record_id);
        footer.appendChild(likeBtn);

        // Comment button
        const commentBtn = document.createElement('button');
        commentBtn.className = 'action-btn comment-btn';
        commentBtn.style.border = 'none';
        commentBtn.style.background = 'none';
        commentBtn.style.cursor = 'pointer';
        commentBtn.innerHTML = `
            <i class="fas fa-comment" style="color: #94a3b8"></i>
            <span class="comment-count" style="font-size: 0.8rem; margin-left: 4px;">${file.comment_count || ''}</span>
        `;
        commentBtn.onclick = (e) => openComments(e, file.record_id);
        footer.appendChild(commentBtn);

        // Bookmark button
        const bookmarkBtn = document.createElement('button');
        bookmarkBtn.className = `action-btn bookmark-btn ${file.is_bookmarked ? 'bookmarked' : ''}`;
        bookmarkBtn.style.border = 'none';
        bookmarkBtn.style.background = 'none';
        bookmarkBtn.style.cursor = 'pointer';
        bookmarkBtn.innerHTML = `
            <i class="fas fa-bookmark" style="color: ${file.is_bookmarked ? '#3b82f6' : '#94a3b8'}"></i>
        `;
        bookmarkBtn.onclick = (e) => toggleBookmark(e, file.record_id);
        footer.appendChild(bookmarkBtn);

        card.appendChild(footer);
    }

    // Verify Action (if pending)
    if (file.verification_status === 'pending') {
        const verifyBtn = document.createElement('button');
        verifyBtn.className = 'verify-action-btn';
        verifyBtn.innerHTML = 'Verify This';
        verifyBtn.title = 'Verify this label';
        verifyBtn.onclick = (e) => {
            e.stopPropagation(); // Prevent opening labeling view
            if (typeof openVerificationModal === 'function') {
                openVerificationModal(file);
            } else {
                console.error('openVerificationModal not found');
            }
        };
        card.appendChild(verifyBtn);
    }

    // Interaction Bar
    const interactionBar = document.createElement('div');
    interactionBar.className = 'interaction-bar';
    interactionBar.onclick = (e) => { e.preventDefault(); e.stopPropagation(); };

    interactionBar.innerHTML = `
        <button class="interaction-btn like-btn ${file.is_liked ? 'liked' : ''}" onclick="window.toggleLike(event, '${file.record_id || file.id}')" title="Like">
            <svg viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
            <span class="like-count">${file.like_count || 0}</span>
        </button>
        <button class="interaction-btn comment-btn" onclick="window.openComments(event, '${file.record_id || file.id}')" title="Comment">
            <svg viewBox="0 0 24 24"><path d="M21.99 4c0-1.1-.89-2-1.99-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4-.01-18zM18 14H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg>
            <span class="comment-count">${file.comment_count || 0}</span>
        </button>
        <button class="interaction-btn bookmark-btn ${file.is_bookmarked ? 'bookmarked' : ''}" onclick="window.toggleBookmark(event, '${file.record_id || file.id}')" title="Bookmark">
            <svg viewBox="0 0 24 24"><path d="M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>
        </button>
    `;

    card.appendChild(interactionBar);

    return card;
}

// Helper function to update statistics
function updateStats(stats) {
    const totalCountEl = document.getElementById('totalCount');
    const sortedCountEl = document.getElementById('sortedCount');
    const remainingCountEl = document.getElementById('remainingCount');

    if (totalCountEl) totalCountEl.textContent = stats.total || 0;
    if (sortedCountEl) sortedCountEl.textContent = stats.sorted || 0;
    if (remainingCountEl) remainingCountEl.textContent = stats.remaining || 0;
}

// ==========================================
// Labeling View (Adaptive Layout)
// ==========================================
function openLabelingView(fileData) {
    currentFileData = fileData;
    isFormDirty = false;

    // Track file view with analytics
    if (window.AbhiHubTracking && window.AbhiHubTracking.trackFileView) {
        try {
            // Calculate file size in KB
            const fileSizeKB = fileData.bytes ? Math.round(fileData.bytes / 1024) : 0;

            // Track the file view with detailed information
            window.AbhiHubTracking.trackFileView(
                fileData.filename || 'unknown',
                fileData.format || 'unknown',
                fileData.folder || 'unsorted',
                fileSizeKB
            );

            // Also track as content impression for recommendation analysis
            if (window.AbhiHubTracking.trackContentImpression) {
                window.AbhiHubTracking.trackContentImpression(
                    fileData.filename || 'unknown',
                    'storeroom_file',
                    fileData.public_id || fileData.filename
                );
            }
        } catch (error) {
            console.error('Error tracking file view:', error);
        }
    }

    // Track file access history
    if (window.trackFileAccess) {
        try {
            window.trackFileAccess(
                fileData.filename || 'unknown',
                'image',  // Store room files are images
                fileData.path || '',
                fileData.url || ''
            );
        } catch (error) {
            console.error('Error tracking file access history:', error);
        }
    }

    // Update image/iframe
    const previewImg = document.getElementById('previewImg');
    const previewFrame = document.getElementById('previewFrame');
    const fileInfoBadge = document.getElementById('fileInfoBadge');

    fileInfoBadge.textContent = fileData.filename;

    const isPdf = fileData.format === 'pdf' || (fileData.filename && fileData.filename.toLowerCase().endsWith('.pdf'));

    if (isPdf) {
        if (previewImg) {
            previewImg.classList.add('hidden');
        }
        if (previewFrame) {
            previewFrame.classList.remove('hidden');
            previewFrame.src = fileData.url;
            // PDF needs height to scroll
            previewFrame.style.width = '100%';
            previewFrame.style.height = '100%';
        }
    } else {
        if (previewFrame) {
            previewFrame.classList.add('hidden');
            previewFrame.src = '';
        }
        if (previewImg) {
            previewImg.classList.remove('hidden');
            previewImg.src = fileData.url;
        }
    }

    // Reset image transforms (only for images)
    currentZoom = 1;
    currentRotation = 0;
    panX = 0;
    panY = 0;
    updateImageTransform();

    // Reset form
    resetForm();

    // Fill default title from filename (remove extension)
    const docTitleInput = document.getElementById('documentTitle');
    if (docTitleInput) {
        const parts = fileData.filename.split('.');
        const nameWithoutExt = parts.length > 1 ? parts.slice(0, -1).join('.') : fileData.filename;
        docTitleInput.value = nameWithoutExt.replace(/[_-]/g, ' ');
    }

    // Auto-fill year from filename
    autoFillYear(fileData.filename);

    // Load last labels if remember is enabled
    if (rememberLabels) {
        loadLastLabels();
    }

    // Populate suggestions
    populateSuggestions();

    // Update navigation buttons
    updateNavigationButtons();

    // Autofocus first empty required field
    setTimeout(() => autofocusFirstEmpty(), 100);

    // Show labeling view
    const labelingView = document.getElementById('labelingView');
    labelingView.classList.add('active');

    // Prevent body scroll
    document.body.style.overflow = 'hidden';

    // Set drawer to half state on mobile (so both image and form are visible)
    if (window.innerWidth <= 768) {
        setDrawerState('half');
        // Scroll form to top
        setTimeout(() => {
            const drawerContent = document.querySelector('.drawer-content');
            if (drawerContent) {
                drawerContent.scrollTop = 0;
            }
        }, 100);
    }

    // Apply saved panel width on desktop
    if (window.innerWidth > 768) {
        applyPanelWidth();
    }
}

function closeLabelingView() {
    if (isFormDirty) {
        showConfirmDialog();
        return;
    }

    forceCloseLabelingView();
}

function forceCloseLabelingView() {
    const labelingView = document.getElementById('labelingView');
    labelingView.classList.remove('active');
    labelingView.setAttribute('data-dirty', 'false');

    // Restore body scroll
    document.body.style.overflow = '';

    // Reset state
    currentFileData = null;
    isFormDirty = false;

    // Reset drawer state
    drawerState = 'collapsed';
    const formPanel = document.getElementById('formPanel');
    if (formPanel) {
        formPanel.classList.remove('half', 'full');
    }
}

// ==========================================
// Confirmation Dialog
// ==========================================
function showConfirmDialog() {
    const dialog = document.getElementById('confirmDialog');
    dialog.classList.add('active');
}

function cancelClose() {
    const dialog = document.getElementById('confirmDialog');
    dialog.classList.remove('active');
}

function confirmClose() {
    const dialog = document.getElementById('confirmDialog');
    dialog.classList.remove('active');
    forceCloseLabelingView();
}

// ==========================================
// Image Viewer Controls
// ==========================================
function zoomIn() {
    currentZoom = Math.min(currentZoom + 0.25, 4);
    updateImageTransform();
    triggerHaptic();
}

function zoomOut() {
    currentZoom = Math.max(currentZoom - 0.25, 0.5);
    updateImageTransform();
    triggerHaptic();
}

function rotateImage() {
    currentRotation = (currentRotation + 90) % 360;
    updateImageTransform();
    triggerHaptic();
}

function updateImageTransform() {
    const previewImg = document.getElementById('previewImg');
    // Only apply transform if image is visible
    if (previewImg && !previewImg.classList.contains('hidden')) {
        previewImg.style.transform = `translate(${panX}px, ${panY}px) scale(${currentZoom}) rotate(${currentRotation}deg)`;
    }
}

function downloadImage() {
    if (!currentFileData) return;

    const link = document.createElement('a');
    link.href = currentFileData.url;
    link.download = currentFileData.filename || 'download';
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast('Download started', 'success');
}

// ==========================================
// Gesture & Mouse Handling
// ==========================================
function initializeGestures() {
    const imageContainer = document.getElementById('imageContainer');
    if (!imageContainer) return;

    let pointers = [];

    // Pointer events for touch and mouse drag
    imageContainer.addEventListener('pointerdown', (e) => {
        // Ignore if clicking a button inside (though controls are outside container usually)
        if (e.target.closest('button')) return;

        pointers.push({ id: e.pointerId, x: e.clientX, y: e.clientY });
        imageContainer.setPointerCapture(e.pointerId);

        if (pointers.length === 1) {
            isPanning = true;
            lastPanPoint = { x: e.clientX, y: e.clientY };
            imageContainer.style.cursor = 'grabbing';
        }
    });

    imageContainer.addEventListener('pointermove', (e) => {
        const idx = pointers.findIndex(p => p.id === e.pointerId);
        if (idx === -1) return;

        pointers[idx] = { id: e.pointerId, x: e.clientX, y: e.clientY };

        if (pointers.length === 2) {
            // Pinch zoom
            const dist = getPointerDistance(pointers[0], pointers[1]);
            if (pointers[0].lastDist) {
                const delta = dist - pointers[0].lastDist;
                currentZoom = Math.max(0.5, Math.min(8, currentZoom + delta * 0.005));
                updateImageTransform();
            }
            pointers[0].lastDist = dist;
        } else if (isPanning) {
            // Pan (allow panning even at zoom 1 for better UX)
            const dx = e.clientX - lastPanPoint.x;
            const dy = e.clientY - lastPanPoint.y;
            panX += dx;
            panY += dy;
            lastPanPoint = { x: e.clientX, y: e.clientY };
            updateImageTransform();
        }
    });

    imageContainer.addEventListener('pointerup', (e) => {
        pointers = pointers.filter(p => p.id !== e.pointerId);
        if (pointers.length === 0) {
            isPanning = false;
            imageContainer.style.cursor = 'grab';
        }
    });

    imageContainer.addEventListener('pointercancel', (e) => {
        pointers = pointers.filter(p => p.id !== e.pointerId);
        if (pointers.length === 0) {
            isPanning = false;
            imageContainer.style.cursor = 'grab';
        }
    });

    // Mouse Wheel Zoom
    imageContainer.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        currentZoom = Math.max(0.5, Math.min(8, currentZoom + delta));
        updateImageTransform();
    }, { passive: false });

    // Double-tap/click to reset or zoom in
    let lastTap = 0;
    imageContainer.addEventListener('click', (e) => {
        // Ignore if panning occurred
        if (isPanning) return;

        // Auto-collapse drawer on image click (Mobile)
        if (window.innerWidth <= 768) {
            setDrawerState('collapsed');
        }

        const now = Date.now();
        if (now - lastTap < 300) {
            if (currentZoom > 1 || panX !== 0 || panY !== 0) {
                resetView();
            } else {
                currentZoom = 2; // Quick zoom
                updateImageTransform();
            }
        }
        lastTap = now;
    });
}

function resetView() {
    currentZoom = 1;
    currentRotation = 0;
    panX = 0;
    panY = 0;
    updateImageTransform();
    triggerHaptic();
}

function toggleFullscreen() {
    const imagePanel = document.querySelector('.image-panel');
    const btn = document.getElementById('fullscreenBtn');

    if (!imagePanel) return;

    imagePanel.classList.toggle('fullscreen');
    const isFullscreen = imagePanel.classList.contains('fullscreen');

    // Update button icon
    if (btn) {
        if (isFullscreen) {
            // Exit Fullscreen Icon
            btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
            </svg>`;
            btn.title = "Exit Fullscreen";
        } else {
            // Enter Fullscreen Icon
            btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
            </svg>`;
            btn.title = "Fullscreen";
        }
    }

    // Adjust image frame logic for fullscreen if needed
    triggerHaptic();
}

function getPointerDistance(p1, p2) {
    return Math.hypot(p2.x - p1.x, p2.y - p1.y);
}

// ==========================================
// Drawer Management (Mobile)
// ==========================================
function initializeDrawer() {
    const drawerHandle = document.getElementById('drawerHandle');
    const formPanel = document.getElementById('formPanel');
    const labelingView = document.getElementById('labelingView');

    if (!drawerHandle || !formPanel) return;

    let isDragging = false;
    let startY = 0;
    let startHeight = 0;

    drawerHandle.addEventListener('touchstart', (e) => {
        isDragging = true;
        startY = e.touches[0].clientY;
        startHeight = formPanel.offsetHeight;
        formPanel.style.transition = 'none';
        document.body.style.overflow = 'hidden';

        // Hide controls while dragging
        document.querySelector('.image-controls')?.classList.add('hidden-controls');
    }, { passive: true });

    drawerHandle.addEventListener('touchmove', (e) => {
        if (!isDragging) return;

        const currentY = e.touches[0].clientY;
        const deltaY = startY - currentY; // Negative = drag up, Positive = drag down
        const newHeight = startHeight + deltaY;

        // Constrain height between min and max
        const minHeight = window.innerHeight * 0.10; // 10vh minimum
        const maxHeight = window.innerHeight * 0.92; // 92vh maximum
        const constrainedHeight = Math.max(minHeight, Math.min(newHeight, maxHeight));

        // Update drawer height directly
        updateDrawerHeight(constrainedHeight);
    }, { passive: true });

    drawerHandle.addEventListener('touchend', (e) => {
        if (!isDragging) return;
        isDragging = false;
        formPanel.style.transition = '';
        snapDrawer();
    });

    drawerHandle.addEventListener('mousedown', (e) => {
        if (window.innerWidth > 768) return; // Only on mobile
        isDragging = true;
        startY = e.clientY;
        startHeight = formPanel.offsetHeight;
        formPanel.style.transition = 'none';
        document.body.style.overflow = 'hidden';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging || window.innerWidth > 768) return;

        const currentY = e.clientY;
        const deltaY = startY - currentY;
        const newHeight = startHeight + deltaY;

        const minHeight = window.innerHeight * 0.10;
        const maxHeight = window.innerHeight * 0.92;
        const constrainedHeight = Math.max(minHeight, Math.min(newHeight, maxHeight));

        updateDrawerHeight(constrainedHeight);
    });

    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        formPanel.style.transition = '';
        document.body.style.overflow = 'hidden';
        document.body.style.userSelect = '';
        snapDrawer();
    });
}

function updateDrawerHeight(height) {
    const formPanel = document.getElementById('formPanel');
    const labelingView = document.getElementById('labelingView');

    if (!formPanel || !labelingView) return;

    // Ensure minimum height is 10% of viewport
    const minHeight = window.innerHeight * 0.10;
    const constrainedHeight = Math.max(minHeight, height);

    // Update CSS variable
    labelingView.style.setProperty('--drawer-height', `${constrainedHeight}px`);

    // Apply height directly
    formPanel.style.height = `${constrainedHeight}px`;

    // Auto-adjust controls visibility based on height
    const viewHeight = window.innerHeight;
    const percentage = (constrainedHeight / viewHeight) * 100;
    const controls = document.querySelector('.image-controls');
    if (controls) {
        if (percentage > 20) {
            controls.classList.add('hidden-controls');
        } else {
            controls.classList.remove('hidden-controls');
        }
    }
}

function setDrawerState(state) {
    drawerState = state;
    const formPanel = document.getElementById('formPanel');
    const labelingView = document.getElementById('labelingView');

    if (!formPanel || !labelingView) return;

    formPanel.classList.remove('half', 'full', 'collapsed');

    let targetHeight;
    const viewHeight = window.innerHeight;

    switch (state) {
        case 'collapsed':
            targetHeight = viewHeight * 0.10;
            formPanel.classList.add('collapsed');
            break;
        case 'half':
            targetHeight = viewHeight * 0.55;
            formPanel.classList.add('half');
            break;
        case 'full':
            targetHeight = viewHeight * 0.92;
            formPanel.classList.add('full');
            break;
        default:
            targetHeight = viewHeight * 0.60;
    }

    formPanel.style.transition = 'height 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
    updateDrawerHeight(targetHeight);

    // Toggle image controls visibility on mobile
    if (window.innerWidth <= 768) {
        const controls = document.querySelector('.image-controls');
        if (controls) {
            if (state === 'collapsed') {
                controls.classList.remove('hidden-controls');
            } else {
                controls.classList.add('hidden-controls');
            }
        }
    }
}

function snapDrawer() {
    const formPanel = document.getElementById('formPanel');
    if (!formPanel) return;

    const currentHeight = formPanel.offsetHeight;
    const viewHeight = window.innerHeight;
    const percentage = (currentHeight / viewHeight) * 100;

    // Snap to nearest state - adjusted for 10% collapsed height
    if (percentage > 75) {
        setDrawerState('full');
    } else if (percentage > 30) {
        setDrawerState('half');
    } else {
        setDrawerState('collapsed');
    }
}

// ==========================================
// Mobile Drawer Toggle
// ==========================================
function toggleDrawer() {
    // Only logic for mobile
    if (window.innerWidth > 768) return;

    const formPanel = document.getElementById('formPanel');
    if (!formPanel) return;

    // Check current state
    const currentHeight = formPanel.offsetHeight;
    const viewHeight = window.innerHeight;
    const percentage = (currentHeight / viewHeight) * 100;

    if (percentage > 20) {
        // Collapse
        setDrawerState('collapsed');
        // Update arrow icon
        const btn = document.querySelector('.drawer-toggle-btn svg');
        if (btn) btn.innerHTML = '<polyline points="6 9 12 15 18 9"></polyline>';
    } else {
        // Expand
        setDrawerState('half');
        // Update arrow icon
        const btn = document.querySelector('.drawer-toggle-btn svg');
        if (btn) btn.innerHTML = '<polyline points="18 15 12 9 6 15"></polyline>';
    }
}

// ==========================================
// Panel Resizer (Desktop)
// ==========================================
function initializePanelResizer() {
    const resizer = document.getElementById('panelResizer');
    if (!resizer) return;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        // Disable iframe interactions
        const iframe = document.getElementById('previewFrame');
        if (iframe) iframe.style.pointerEvents = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;

        const labelingView = document.getElementById('labelingView');
        const viewWidth = labelingView.offsetWidth;
        const newWidth = viewWidth - e.clientX;
        const clampedWidth = Math.max(320, Math.min(newWidth, viewWidth * 0.5));

        panelWidth = clampedWidth;
        applyPanelWidth();
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            const resizer = document.getElementById('panelResizer');
            resizer?.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('storeroom_panel_width', panelWidth);

            // Re-enable iframe interactions
            const iframe = document.getElementById('previewFrame');
            if (iframe) iframe.style.pointerEvents = '';
        }
    });

    // Double-click to reset
    resizer.addEventListener('dblclick', () => {
        panelWidth = 420;
        applyPanelWidth();
        localStorage.setItem('storeroom_panel_width', panelWidth);
    });
}

function applyPanelWidth() {
    const formPanel = document.getElementById('formPanel');
    if (formPanel && window.innerWidth > 768) {
        formPanel.style.width = `${panelWidth}px`;
    }
}

// ==========================================
// Form Handling
// ==========================================
function resetForm() {
    const form = document.getElementById('labelForm');
    if (form) {
        form.reset();
    }

    // Reset save button
    updateSaveButton('idle');
}

function initializeFormTracking() {
    const form = document.getElementById('labelForm');
    if (!form) return;

    // Track all input changes
    form.addEventListener('input', () => {
        isFormDirty = true;
        document.getElementById('labelingView')?.setAttribute('data-dirty', 'true');
    });

    form.addEventListener('change', () => {
        isFormDirty = true;
        document.getElementById('labelingView')?.setAttribute('data-dirty', 'true');
    });
}

function autofocusFirstEmpty() {
    const requiredFields = ['collegeName', 'subjectName', 'year', 'branch'];

    for (const fieldId of requiredFields) {
        const field = document.getElementById(fieldId);
        if (field && !field.value.trim()) {
            field.focus();
            return;
        }
    }
}

function autoFillYear(filename) {
    if (!filename) return;

    // Try to extract year from filename
    const yearMatch = filename.match(/(20[0-9]{2})/);
    if (yearMatch) {
        const yearField = document.getElementById('year');
        if (yearField) {
            yearField.value = yearMatch[1];
        }
    }
}

function scrollToFieldError(fieldId) {
    const field = document.getElementById(fieldId);
    if (field) {
        field.scrollIntoView({ behavior: 'smooth', block: 'center' });
        field.classList.add('error');
        field.focus();
        setTimeout(() => field.classList.remove('error'), 400);
    }
}

// ==========================================
// Form Suggestions
// ==========================================
function loadFormSuggestions() {
    try {
        const stored = localStorage.getItem('storeroom_form_suggestions');
        if (stored) {
            formSuggestions = JSON.parse(stored);
        }
    } catch (e) {
        console.error('Error loading form suggestions:', e);
        formSuggestions = {};
    }
}

function saveFormSuggestions() {
    try {
        localStorage.setItem('storeroom_form_suggestions', JSON.stringify(formSuggestions));
    } catch (e) {
        console.error('Error saving form suggestions:', e);
    }
}

function addSuggestion(field, value) {
    if (!value || value.length < 2) return;

    if (!formSuggestions[field]) {
        formSuggestions[field] = [];
    }

    // Remove duplicates and add to front
    formSuggestions[field] = formSuggestions[field].filter(v => v !== value);
    formSuggestions[field].unshift(value);

    // Keep only last 10
    formSuggestions[field] = formSuggestions[field].slice(0, 10);
    saveFormSuggestions();
}

function populateSuggestions() {
    // Dropdowns are now handled by fetchMetadata, but we still need to set form values from last labels
    loadLastLabels();
}

async function fetchMetadata() {
    try {
        const [collegesRes, branchesRes] = await Promise.all([
            fetch('/api/colleges'),
            fetch('/api/branches')
        ]);

        const collegesData = await collegesRes.json();
        const branchesData = await branchesRes.json();

        if (collegesData.success) {
            const collegeSelect = document.getElementById('collegeName');
            if (collegeSelect) {
                // Keep the first "Select College..." option
                collegeSelect.innerHTML = '<option value="">Select College...</option>';
                collegesData.colleges.forEach(college => {
                    const option = document.createElement('option');
                    option.value = college.name;
                    option.textContent = college.name;
                    collegeSelect.appendChild(option);
                });
            }
        }

        if (branchesData.success) {
            const branchSelect = document.getElementById('branch');
            if (branchSelect) {
                // Keep the first "Select Branch..." option
                branchSelect.innerHTML = '<option value="">Select Branch...</option>';
                branchesData.branches.forEach(branch => {
                    const option = document.createElement('option');
                    option.value = branch.name;
                    option.textContent = branch.name;
                    branchSelect.appendChild(option);
                });
            }
        }

        // After populating, try to load last used labels
        loadLastLabels();
    } catch (e) {
        console.error('Error fetching metadata:', e);
    }
}

// ==========================================
// Remember Labels
// ==========================================
function initializeRememberToggle() {
    const toggle = document.getElementById('rememberToggle');
    if (!toggle) return;

    // Set initial state
    if (rememberLabels) {
        toggle.classList.add('active');
        toggle.setAttribute('aria-checked', 'true');
    }

    toggle.addEventListener('click', () => {
        rememberLabels = !rememberLabels;
        toggle.classList.toggle('active');
        toggle.setAttribute('aria-checked', rememberLabels.toString());
        localStorage.setItem('storeroom_remember_labels', rememberLabels.toString());
        triggerHaptic();
    });

    toggle.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle.click();
        }
    });
}

function saveLastLabels() {
    const labels = {
        collegeName: document.getElementById('collegeName')?.value,
        branch: document.getElementById('branch')?.value,
        documentCategory: document.querySelector('input[name="documentCategory"]:checked')?.value,
        examType: document.getElementById('examType')?.value,
        semesters: Array.from(document.querySelectorAll('input[name="semester"]:checked')).map(cb => cb.value)
    };

    localStorage.setItem('storeroom_last_labels', JSON.stringify(labels));
}

function loadLastLabels() {
    try {
        const stored = localStorage.getItem('storeroom_last_labels');
        if (!stored) return;

        const labels = JSON.parse(stored);

        // Set college and branch
        if (labels.collegeName) document.getElementById('collegeName').value = labels.collegeName;
        if (labels.branch) document.getElementById('branch').value = labels.branch;

        // Set document category
        if (labels.documentCategory) {
            const radio = document.querySelector(`input[name="documentCategory"][value="${labels.documentCategory}"]`);
            if (radio) radio.checked = true;
        }

        // Set exam type
        if (labels.examType) {
            const select = document.getElementById('examType');
            if (select) select.value = labels.examType;
        }

        // Set semesters
        if (labels.semesters) {
            labels.semesters.forEach(sem => {
                const checkbox = document.querySelector(`input[name="semester"][value="${sem}"]`);
                if (checkbox) checkbox.checked = true;
            });
        }
    } catch (e) {
        console.error('Error loading last labels:', e);
    }
}

// ==========================================
// Save Button & Submission
// ==========================================
function updateSaveButton(state, message = '') {
    const saveBtn = document.getElementById('saveBtn');
    if (!saveBtn) return;
    // Ensure consistent internal structure for the button
    let spinnerHtml = '<div class="spinner" aria-hidden="true"></div>';
    let checkmarkHtml = `<svg class="checkmark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>`;

    switch (state) {
        case 'idle':
            saveBtn.className = 'save-btn idle';
            saveBtn.innerHTML = `<span class="btn-text">Save Label</span>`;
            saveBtn.disabled = false;
            break;
        case 'saving':
            saveBtn.className = 'save-btn saving';
            saveBtn.innerHTML = `${spinnerHtml}<span class="btn-text">Saving...</span>`;
            saveBtn.disabled = true;
            break;
        case 'saved':
            saveBtn.className = 'save-btn saved';
            saveBtn.innerHTML = `${checkmarkHtml}<span class="btn-text">Saved!</span>`;
            saveBtn.disabled = true;
            setTimeout(() => updateSaveButton('idle'), 2000);
            break;
        case 'error':
            saveBtn.className = 'save-btn error';
            saveBtn.innerHTML = `<span class="btn-text">${message || 'Error - Retry'}</span>`;
            saveBtn.disabled = false;
            break;
        default:
            saveBtn.className = `save-btn ${state}`;
            if (!saveBtn.querySelector('.btn-text')) saveBtn.innerHTML = `<span class="btn-text">${message || 'Save'}</span>`;
    }
}

async function handleSave() {
    if (!currentFileData) {
        showToast('Error: No file selected', 'error');
        return;
    }

    // Validate form
    const validation = validateForm();
    if (!validation.valid) {
        scrollToFieldError(validation.field);
        showToast(validation.message, 'error');
        return;
    }

    // Get form data
    const labelData = getFormData();

    // Update button state
    updateSaveButton('saving');

    try {
        // First, save to database
        const response = await fetch('/store-room/api/label', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(labelData)
        });

        const result = await response.json();

        if (result.success) {
            // Save suggestions
            addSuggestion('collegeName', labelData.college_name);
            addSuggestion('subjectName', labelData.subject_name);
            addSuggestion('subjectCode', labelData.subject_code);
            addSuggestion('branch', labelData.branch);

            // Save last labels if enabled
            if (rememberLabels) {
                saveLastLabels();
            }

            // Now rename the file with metadata
            const renameResponse = await fetch('/store-room/api/rename-file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: currentFileData.filename,
                    college_name: labelData.college_name,
                    subject_name: labelData.subject_name,
                    subject_code: labelData.subject_code,
                    exam_type: labelData.exam_type,
                    year: labelData.year,
                    branch: labelData.branch,
                    semesters: labelData.semesters
                })
            });

            const renameResult = await renameResponse.json();

            updateSaveButton('saved');
            showToast('Paper labeled and filed successfully!', 'success');
            triggerHaptic();

            // Mark form as clean
            isFormDirty = false;

            // Update statistics
            updateStatistics();

            // Show verification notice
            showToast('Paper sent for verification. It will move to verified section after 7 user verifications.', 'info');

            // Update file card to show verification status
            const fileCard = document.querySelector(`[data-file*='"filename":"${currentFileData.filename}"']`);
            if (fileCard) {
                fileCard.classList.add('pending-verification');
                const labelBadge = fileCard.querySelector('.label-badge') || document.createElement('div');
                if (!fileCard.querySelector('.label-badge')) {
                    labelBadge.className = 'label-badge';
                    labelBadge.textContent = '⏳ Pending Verification';
                    fileCard.appendChild(labelBadge);
                }
            }

            // Close after delay
            setTimeout(() => {
                forceCloseLabelingView();
            }, 1500);
        } else {
            updateSaveButton('error', 'Failed - Retry');
            showToast(result.message || 'Failed to save label', 'error');
        }
    } catch (error) {
        console.error('Save error:', error);
        updateSaveButton('error', 'Error - Retry');
        showToast('An error occurred while saving', 'error');
    }
}

function validateForm() {
    const collegeName = document.getElementById('collegeName')?.value.trim();
    if (!collegeName) return { valid: false, field: 'collegeName', message: 'College Name is required' };

    const subjectName = document.getElementById('subjectName')?.value.trim();
    if (!subjectName) return { valid: false, field: 'subjectName', message: 'Subject Name is required' };

    const yearRaw = document.getElementById('year')?.value;
    if (!yearRaw) return { valid: false, field: 'year', message: 'Year is required' };
    const year = parseInt(yearRaw, 10);
    const thisYear = new Date().getFullYear();
    if (isNaN(year) || year < 1900 || year > thisYear + 1) return { valid: false, field: 'year', message: 'Please enter a valid year' };

    const branch = document.getElementById('branch')?.value.trim();
    if (!branch) return { valid: false, field: 'branch', message: 'Branch is required' };

    const category = document.querySelector('input[name="documentCategory"]:checked');
    if (!category) return { valid: false, field: 'documentCategory', message: 'Please select a Category' };

    return { valid: true };
}

function getFormData() {
    return {
        filename: currentFileData.filename,
        url: currentFileData.url,
        title: document.getElementById('documentTitle')?.value.trim(),
        document_category: document.querySelector('input[name="documentCategory"]:checked')?.value,
        college_name: document.getElementById('collegeName')?.value.trim(),
        subject_name: document.getElementById('subjectName')?.value.trim(),
        subject_code: document.getElementById('subjectCode')?.value.trim(),
        exam_type: document.getElementById('examType')?.value,
        year: parseInt(document.getElementById('year')?.value),
        branch: document.getElementById('branch')?.value.trim(),
        semesters: Array.from(document.querySelectorAll('input[name="semester"]:checked')).map(cb => cb.value),
        description: document.getElementById('description')?.value.trim()
    };
}

// ==========================================
// Toast Notifications
// ==========================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
        // Fallback to old notification style
        showNotification(message, type);
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${getToastIcon(type)}</span>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    // Remove after 4 seconds
    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function getToastIcon(type) {
    switch (type) {
        case 'success': return '✅';
        case 'error': return '❌';
        case 'warning': return '⚠️';
        default: return 'ℹ️';
    }
}

// Legacy notification function
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        z-index: 10000;
        font-size: 1rem;
        font-weight: 600;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ==========================================
// Haptic Feedback
// ==========================================
function triggerHaptic() {
    if ('vibrate' in navigator && window.matchMedia('(max-width: 768px)').matches) {
        navigator.vibrate(10);
    }
}

// ==========================================
// Toast Notifications
// ==========================================
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        console.log(`Toast (${type}): ${message}`);
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    toastContainer.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==========================================
// Search History
// ==========================================
function loadSearchHistory() {
    try {
        const stored = localStorage.getItem('storeroom_search_history');
        if (stored) {
            searchHistory = JSON.parse(stored);
        }
    } catch (e) {
        console.error('Error loading search history:', e);
    }
}

function saveSearchHistory(query) {
    if (!query || query.length < 2) return;

    searchHistory = searchHistory.filter(q => q !== query);
    searchHistory.unshift(query);
    searchHistory = searchHistory.slice(0, 10);

    try {
        localStorage.setItem('storeroom_search_history', JSON.stringify(searchHistory));
    } catch (e) {
        console.error('Error saving search history:', e);
    }
}

// ==========================================
// Statistics Update
// ==========================================
async function updateStatistics() {
    try {
        const response = await fetch('/store-room/api/files');
        const result = await response.json();

        if (result.success && result.statistics) {
            document.getElementById('totalCount').textContent = result.statistics.total;
            document.getElementById('sortedCount').textContent = result.statistics.sorted;
            document.getElementById('remainingCount').textContent = result.statistics.remaining;
        }
    } catch (error) {
        console.error('Error updating statistics:', error);
    }
}

// ==========================================
// File Card Management
// ==========================================
function removeFileCard(filename) {
    const fileCards = document.querySelectorAll('.file-card');
    fileCards.forEach(card => {
        const fileData = JSON.parse(card.getAttribute('data-file'));
        if (fileData.filename === filename) {
            card.style.opacity = '0';
            card.style.transform = 'scale(0.8)';
            setTimeout(() => card.remove(), 300);
        }
    });
}

function updateEmptyState(visibleCount, searchQuery = '') {
    const filesGrid = document.getElementById('filesGrid');
    let emptyState = filesGrid.querySelector('.empty-state');

    if (visibleCount === 0) {
        if (!emptyState) {
            emptyState = document.createElement('div');
            emptyState.className = 'empty-state';
            filesGrid.appendChild(emptyState);
        }

        if (searchQuery) {
            emptyState.innerHTML = `
                <div class="empty-icon">🔍</div>
                <h3 class="empty-title">No Results Found</h3>
                <p class="empty-text">Try adjusting your search or filters</p>
                <a href="#" class="upload-btn" onclick="document.getElementById('storeRoomSearchInput').value=''; handleSearch({target: document.getElementById('storeRoomSearchInput')}); return false;">
                    <span>🔄</span>
                    <span>Clear Search</span>
                </a>
            `;
        } else {
            emptyState.innerHTML = `
                <div class="empty-icon">📂</div>
                <h3 class="empty-title">No Files Found</h3>
                <p class="empty-text">Upload files to Cloudinary to get started</p>
                <a href="/upload" class="upload-btn">
                    <span>➕</span>
                    <span>Upload Files</span>
                </a>
            `;
        }
    } else {
        if (emptyState) {
            emptyState.remove();
        }
    }
}

// ==========================================
// CSS Animations (added dynamically)
// ==========================================
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ==========================================
// Backward Compatibility (legacy functions)
// ==========================================
function openLabelModal(fileData) {
    openLabelingView(fileData);
}

function closeModal() {
    closeLabelingView();
}

function openImageViewer() {
    // Image is already visible in the new layout
    // This is kept for backward compatibility
}

function closeImageViewer() {
    // Not needed in new layout
}

// ==========================================
// Interaction Methods (Likes & Bookmarks)
// ==========================================
window.toggleLike = async function (event, docId) {
    if (!docId) return;
    const btn = event.currentTarget;
    try {
        const res = await fetch('/api/interactions/like', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ document_id: docId })
        });
        const data = await res.json();
        if (data.success) {
            btn.classList.toggle('liked', data.is_liked);
            const countSpan = btn.querySelector('.like-count');
            if (countSpan) countSpan.textContent = data.like_count;
        } else {
            console.error(data.message);
        }
    } catch (e) { console.error('Error toggling like', e); }
};

window.toggleBookmark = async function (event, docId) {
    if (!docId) return;
    const btn = event.currentTarget;
    try {
        const res = await fetch('/api/interactions/bookmark', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ document_id: docId })
        });
        const data = await res.json();
        if (data.success) {
            btn.classList.toggle('bookmarked', data.is_bookmarked);
        } else {
            console.error(data.message);
        }
    } catch (e) { console.error('Error toggling bookmark', e); }
};

window.openComments = function (event, docId) {
    // We will render a modal dynamically.
    if (typeof renderCommentModal === 'function') {
        renderCommentModal(docId);
    } else {
        console.error("renderCommentModal is not defined.");
    }
};

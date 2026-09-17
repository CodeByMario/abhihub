console.log('[script.js] Loading started...');
// Slider functionality
let currentSlide = 0;

function showSlide(index) {
    const slides = document.querySelectorAll('.slides .notice-board');
    if (index >= slides.length) {
        currentSlide = 0;
    } else if (index < 0) {
        currentSlide = slides.length - 1;
    } else {
        currentSlide = index;
    }

    // Hide all slides and show the current one
    slides.forEach((slide, i) => {
        slide.style.display = i === currentSlide ? 'block' : 'none';
        slide.style.opacity = i === currentSlide ? '1' : '0';
    });
}

function changeSlide(direction) {
    clearInterval(autoSlideInterval); // Reset auto-slide timer on manual change
    showSlide(currentSlide + direction);
    autoSlideInterval = setInterval(() => {
        changeSlide(1);
    }, 5000); // Restart auto-slide timer
}

// Auto-slide functionality with reset on manual change
let autoSlideInterval = setInterval(() => {
    changeSlide(1);
}, 5000); // Change slide every 5 seconds

// Initialize the slider
document.addEventListener('DOMContentLoaded', () => {
    showSlide(currentSlide);
});

// Enhanced search functionality
const navbarSearchIcon = document.getElementById('navbarSearchIcon');
const topSearchForm = document.getElementById('navSearchOverlay');
const closeTopSearch = document.getElementById('navSearchClose');
const searchInput = topSearchForm?.querySelector('.nav-search-field');

if (navbarSearchIcon && topSearchForm && closeTopSearch && searchInput) {
    // Show search form when navbar search icon is clicked
    navbarSearchIcon.addEventListener('click', function (e) {
        e.preventDefault();
        topSearchForm.style.display = 'block';
        // Add entrance animation
        topSearchForm.style.animation = 'slideDown 0.3s ease-out';
        // Small delay to ensure form is visible before focusing
        setTimeout(() => {
            searchInput.focus();
        }, 150);
    });

    // Close search form with animation
    function closeSearchForm() {
        // Add exit animation
        topSearchForm.style.animation = 'slideUp 0.25s ease-in';
        setTimeout(() => {
            topSearchForm.style.display = 'none';
            searchInput.value = ''; // Clear input when closing
        }, 250);
    }

    closeTopSearch.addEventListener('click', closeSearchForm);

    // Close search form with Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && topSearchForm.style.display === 'block') {
            closeSearchForm();
        }
    });

    // Prevent form submission if search input is empty
    topSearchForm.addEventListener('submit', function (e) {
        const searchValue = searchInput.value.trim();
        if (!searchValue) {
            e.preventDefault();
            searchInput.focus();
            // Add a subtle shake animation for empty search
            searchInput.style.animation = 'shake 0.4s ease-in-out';
            setTimeout(() => {
                searchInput.style.animation = '';
            }, 400);
        }
    });

    // Close search form when clicking outside
    document.addEventListener('click', function (e) {
        if (topSearchForm.style.display === 'block' &&
            !topSearchForm.contains(e.target) &&
            !navbarSearchIcon.contains(e.target)) {
            closeSearchForm();
        }
    });
}

// Red dot notification for Account
function updateAccountRedDot() {
    const redDot = document.getElementById('accountRedDot');
    if (!redDot) return; // Element may not exist on all pages
    if (!localStorage.getItem('accountVisited')) {
        redDot.style.display = 'block';
    } else {
        redDot.style.display = 'none';
    }
}
updateAccountRedDot();
const accountNavItem = document.getElementById('accountNavItem');
if (accountNavItem) {
    accountNavItem.addEventListener('click', function () {
        localStorage.setItem('accountVisited', '1');
        updateAccountRedDot();
    });
}

// Hide navbar on scroll down, show on scroll up (improved)
(function () {
    let lastScrollY = window.scrollY;
    let ticking = false;
    const navbar = document.querySelector('.navbar');
    const topSearchForm = document.getElementById('navSearchOverlay');

    function onScroll() {
        if (!navbar) return;

        // Don't hide navbar if search form is open
        if (topSearchForm && topSearchForm.style.display === 'block') {
            return;
        }

        const currentScrollY = window.scrollY;
        if (currentScrollY > lastScrollY && currentScrollY > 50) {
            // Scrolling down
            navbar.classList.add('hide-navbar');
        } else {
            // Scrolling up
            navbar.classList.remove('hide-navbar');
        }
        lastScrollY = currentScrollY;
        ticking = false;
    }

    window.addEventListener('scroll', function () {
        if (!ticking) {
            window.requestAnimationFrame(onScroll);
            ticking = true;
        }
    }, { passive: true });
})();

// Search Manager
const SearchManager = {
    cache: null,
    searchDebounceTimer: null,
    searchHistory: [],
    MAX_HISTORY: 5,
    baseLimit: 12,
    displayLimit: 12,
    currentResults: [],

    elements: {
        fileName: () => document.getElementById("searchFileName"),
        author: () => document.getElementById("searchAuthor"),
        college: () => document.getElementById("searchCollege"),
        type: () => document.getElementById("searchType"),
        subject: () => document.getElementById("searchSubject"),
        year: () => document.getElementById("searchYear"),
        sort: () => document.getElementById("searchSort"),
        results: () => document.getElementById("searchResults"),
        noResults: () => document.getElementById("noResults"),
        loader: () => document.getElementById("loader"),
        error: () => document.getElementById("error"),
        history: () => document.getElementById("searchHistory")
    },

    async init() {
        console.log('[SearchManager] Initializing...');
        this.loadSearchHistory();
        this.setupEventListeners();
        await this.preloadData();
        await this.performSearch();
        console.log('[SearchManager] Init complete. Cache size:', this.cache?.length);
    },

    loadSearchHistory() {
        try {
            const saved = localStorage.getItem('searchHistory');
            if (saved) {
                this.searchHistory = JSON.parse(saved);
                this.updateSearchHistoryUI();
            }
        } catch (error) {
            console.error('Failed to load search history:', error);
        }
    },

    saveSearchHistory() {
        try {
            localStorage.setItem('searchHistory', JSON.stringify(this.searchHistory));
        } catch (error) {
            console.error('Failed to save search history:', error);
        }
    },

    addToSearchHistory(query) {
        if (!query) return;
        this.searchHistory = this.searchHistory.filter(item => item !== query);
        this.searchHistory.unshift(query);
        if (this.searchHistory.length > this.MAX_HISTORY) {
            this.searchHistory.pop();
        }
        this.saveSearchHistory();
        this.updateSearchHistoryUI();
    },

    updateSearchHistoryUI() {
        const container = this.elements.history();
        if (!container) return;
        container.innerHTML = '';
        this.searchHistory.forEach(query => {
            const tag = document.createElement('button');
            tag.className = 'ss-tag';
            tag.textContent = query;
            tag.addEventListener('click', () => {
                const fileNameInput = this.elements.fileName();
                if (fileNameInput) {
                    fileNameInput.value = query;
                    this.performSearch();
                }
            });
            container.appendChild(tag);
        });
    },

    setupEventListeners() {
        // hidden btn still works for hero search form compatibility
        document.getElementById("searchBtn")?.addEventListener("click", () => this.performSearch());

        // Clear button
        const clearBtn = document.getElementById('searchClearBtn');
        const fileInput = this.elements.fileName();
        if (fileInput && clearBtn) {
            fileInput.addEventListener('input', () => {
                clearBtn.style.display = fileInput.value ? 'block' : 'none';
                this.debounceSearch();
            });
            fileInput.addEventListener('keypress', e => {
                if (e.key === 'Enter') this.performSearch();
            });
            clearBtn.addEventListener('click', () => {
                fileInput.value = '';
                clearBtn.style.display = 'none';
                fileInput.focus();
                this.performSearch();
            });
        }

        // Selects — instant search on change
        ['searchCollege','searchType','searchSubject','searchYear','searchSort'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', (e) => {
                e.target.classList.toggle('active', !!e.target.value);
                this.performSearch();
            });
        });
    },

    async preloadData() {
        const loader = this.elements.loader();
        const error = this.elements.error();

        try {
            if (loader) loader.style.display = 'block';
            if (error) error.style.display = 'none';

            console.log('[SearchManager] Fetching files from API...');
            const [filesRes] = await Promise.all([
                fetch("/api/files/all"),
                this.loadColleges()
            ]);
            console.log('[SearchManager] Fetch response:', filesRes.status, filesRes.ok);
            if (!filesRes.ok) throw new Error("Failed to load data");
            const result = await filesRes.json();
            const data = result.data || [];  // Extract data array from API response
            this.cache = data;
            console.log(`[SearchManager] Loaded ${data.length} files from API (includes data.json + file_records)`);
            this.populateDropdowns(this.cache);
        } catch (err) {
            console.error("Data preload failed:", err);
            if (error) {
                error.textContent = 'Failed to load file data. Please try again later.';
                error.style.display = 'block';
            }
            this.cache = [];
        } finally {
            if (loader) loader.style.display = 'none';
        }
    },

    populateDropdowns(data) {
        console.log('[SearchManager] Populating dropdowns...');
        const cache = {};
        ['type', 'subject', 'year'].forEach(field => {
            cache[field] = [...new Set(data.map(f => f[field]))].filter(v => v).sort();
        });

        Object.entries(cache).forEach(([field, values]) => {
            this.fillDropdown(`search${field.charAt(0).toUpperCase() + field.slice(1)}`, values);
        });
    },

    async loadColleges() {
        try {
            const res = await fetch('/api/colleges');
            const data = await res.json();
            if (!data.success) return;

            const collegeSelect = document.getElementById('searchCollege');
            if (!collegeSelect) return;

            collegeSelect.innerHTML = '<option value="">🏫 All Colleges</option>';
            data.colleges.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.name;
                opt.textContent = c.name;
                collegeSelect.appendChild(opt);
            });

            // Auto-select user's college
            const userCollege = window.ABHIHUB_USER_COLLEGE;
            if (userCollege) {
                const lc = userCollege.toLowerCase();
                const options = Array.from(collegeSelect.options);
                // Exact match first
                let match = options.find(o => o.value.toLowerCase() === lc);
                // Partial match fallback
                if (!match) match = options.find(o => o.value && lc.includes(o.value.toLowerCase()));
                if (match) {
                    collegeSelect.value = match.value;
                    console.log('[SearchManager] Auto-selected college:', match.value);
                }
            }
        } catch (e) {
            console.warn('[SearchManager] Could not load colleges from API:', e);
        }
    },

    fillDropdown(id, values) {
        const dropdown = document.getElementById(id);
        if (!dropdown) return;

        // Keep the first option (placeholder)
        const firstOption = dropdown.firstElementChild;
        dropdown.innerHTML = '';
        if (firstOption) dropdown.appendChild(firstOption);

        const fragment = document.createDocumentFragment();
        values.forEach(val => {
            const opt = document.createElement("option");
            opt.value = val;
            opt.textContent = val;
            fragment.appendChild(opt);
        });
        dropdown.appendChild(fragment);
    },

    debounceSearch() {
        clearTimeout(this.searchDebounceTimer);
        this.searchDebounceTimer = setTimeout(() => this.performSearch(), 300);
    },

    async performSearch() {
        if (!this.cache) await this.preloadData();

        const fileName = this.elements.fileName()?.value.trim();
        const author = this.elements.author()?.value.trim();
        const college = this.elements.college()?.value;
        const type = this.elements.type()?.value;
        const subject = this.elements.subject()?.value;
        const year = this.elements.year()?.value;
        const sort = this.elements.sort()?.value;

        const searchTerms = {
            fileName: fileName?.toLowerCase(),
            author: author?.toLowerCase(),
            college: college,
            type: type,
            subject: subject,
            year: year,
            sort: sort
        };

        if (fileName) {
            this.addToSearchHistory(fileName);
        }

        const loader = this.elements.loader();
        const noResults = this.elements.noResults();
        const resultsContainer = this.elements.results();

        if (loader) loader.style.display = 'block';
        if (noResults) noResults.style.display = 'none';
        if (resultsContainer) resultsContainer.innerHTML = '';

        try {
            let filtered = [];
            
            // If we have a specific keyword, use the fast V2 Search API
            if (fileName && fileName.length > 0) {
                try {
                    const res = await fetch(`/api/v2/search?q=${encodeURIComponent(fileName)}&college_id=${encodeURIComponent(college || 'ALL')}`);
                    const data = await res.json();
                    let serverResults = data.results || [];
                    
                    // Apply the dropdown filters to the server results locally
                    filtered = serverResults.filter(file => {
                        const matchesType = !type || file.type === type;
                        const matchesSubject = !subject || file.subject === subject;
                        const matchesYear = !year || file.year === year;
                        const matchesCollege = !college || college === 'ALL' || file.college === college;
                        // Author filter is legacy but keep for compatibility
                        const matchesAuthor = !author || (file.author && file.author.toLowerCase().includes(author));
                        return matchesType && matchesSubject && matchesYear && matchesCollege && matchesAuthor;
                    });
                } catch(e) {
                    console.error("V2 search API error, falling back to local cache", e);
                    filtered = this.filterResults(searchTerms);
                }
            } else {
                // If no keyword, just use local cache filtering
                if (window.Worker) {
                    const worker = new Worker('/static/premium/js/search-worker.js');
                    filtered = await new Promise((resolve) => {
                        worker.postMessage({ fileData: this.cache, filters: searchTerms });
                        worker.onmessage = (e) => {
                            worker.terminate();
                            resolve(e.data);
                        };
                    });
                } else {
                    filtered = this.filterResults(searchTerms);
                }
            }

            this.displayLimit = this.baseLimit;
            this.currentResults = filtered;
            this.displayResults(this.currentResults);
            
            // Phase 4 Analytics Tracking: Log search query if provided
            if (fileName && fileName.length > 2) {
                fetch('/api/v2/search/analytics', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: fileName,
                        results_count: filtered.length
                    })
                }).catch(e => console.warn('Analytics logging failed', e));
            }
        } catch (error) {
            console.error('Search error:', error);
        } finally {
            if (loader) loader.style.display = 'none';
        }
    },

    filterResults(terms) {
        // Helper function to sanitize strings for matching
        const sanitize = (str) => {
            if (!str) return '';
            return str.toString().toLowerCase().replace(/[^a-z0-9]/g, '');
        };

        const cleanFileName = sanitize(terms.fileName);
        const cleanAuthor = sanitize(terms.author);

        const results = this.cache.filter(file => {
            // File name matching (matches against file name, subject, and subject code)
            const matchesFileName = !cleanFileName ||
                sanitize(file["file-name"]).includes(cleanFileName) ||
                sanitize(file.subject).includes(cleanFileName) ||
                sanitize(file.subject_code).includes(cleanFileName);

            // Author matching
            const matchesAuthor = !cleanAuthor ||
                sanitize(file.author).includes(cleanAuthor);

            // Exact matches for dropdowns
            const matchesType = !terms.type || file.type === terms.type;
            const matchesSubject = !terms.subject || file.subject === terms.subject;
            const matchesYear = !terms.year || file.year === terms.year;
            const matchesCollege = !terms.college || file.college === terms.college;

            return matchesFileName && matchesAuthor && matchesType && matchesSubject && matchesYear && matchesCollege;
        });

        if (terms.sort) {
            if (terms.sort === 'views_desc') {
                results.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
            } else if (terms.sort === 'likes_desc') {
                results.sort((a, b) => (b.like_count || 0) - (a.like_count || 0));
            } else if (terms.sort === 'bookmarks_desc') {
                results.sort((a, b) => (b.bookmark_count || 0) - (a.bookmark_count || 0));
            } else if (terms.sort === 'date_desc') {
                results.sort((a, b) => {
                    const dA = a.date ? new Date(a.date) : new Date(0);
                    const dB = b.date ? new Date(b.date) : new Date(0);
                    return dB - dA;
                });
            }
        }
        return results;
    },

    displayResults(results) {
        const container = this.elements.results();
        const noResults = this.elements.noResults();
        const header = document.getElementById('searchResultsHeader');
        const countEl = document.getElementById('searchResultCount');

        if (!container || !noResults) return;

        container.innerHTML = '';
        noResults.style.display = results.length ? 'none' : 'block';

        if (header) header.style.display = 'flex';
        if (countEl) countEl.textContent = `${results.length} result${results.length !== 1 ? 's' : ''}`;

        const loadMoreContainer = document.getElementById('loadMoreContainer');

        if (results.length) {
            const fragment = document.createDocumentFragment();
            const visibleResults = results.slice(0, this.displayLimit);
            visibleResults.forEach(file => {
                const card = this.createResultCard(file);
                fragment.appendChild(card);
            });
            container.appendChild(fragment);

            if (loadMoreContainer) {
                loadMoreContainer.style.display = results.length > this.displayLimit ? 'block' : 'none';
            }
        } else if (loadMoreContainer) {
            loadMoreContainer.style.display = 'none';
        }
    },

    loadMore() {
        this.displayLimit += this.baseLimit;
        this.displayResults(this.currentResults);
    },

    createResultCard(file) {
        const card = document.createElement('a');
        const typeClass = (file.type || 'default').toLowerCase();
        card.className = 'ss-card ' + typeClass;
        card.href = this.getFileUrl(file);

        const s = str => str ? str.toString()
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;') : '';

        const recordId = s(file.record_id || '');
        const isLiked = file.is_liked ? 'active' : '';
        const isBookmarked = file.is_bookmarked ? 'active' : '';
        const likeFill = file.is_liked ? 'currentColor' : 'none';
        const bookmarkFill = file.is_bookmarked ? 'currentColor' : 'none';

        card.innerHTML = `
          <div class="ss-card-top">
            <span class="ss-badge ${typeClass}">${s(file.type || 'File')}</span>
            <span style="font-size:0.72rem;color:#94a3b8;">${s(file.year || '')}</span>
          </div>
          <div class="ss-title">${s(file.subject)}</div>
          <div class="ss-meta">${s(file['file-name'])}</div>
          <div class="ss-footer">
            <span>👤 ${s(file.author)}</span>
            <span class="ss-stats">
              <span>👁 ${file.view_count || 0}</span>
              <span>❤ ${file.like_count || 0}</span>
            </span>
          </div>
          <div class="ss-actions" onclick="event.preventDefault();event.stopPropagation();">
            <button class="ss-btn view-btn" data-id="${recordId}" onclick="window.location.href='${this.getFileUrl(file)}'">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <span class="count">${file.view_count > 0 ? file.view_count : ''}</span>
            </button>
            <button class="ss-btn like-btn ${isLiked}" data-id="${recordId}" onclick="window.toggleFileAction(this,'like')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="${likeFill}" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
              <span class="count">${file.like_count > 0 ? file.like_count : ''}</span>
            </button>
            <button class="ss-btn comment-btn" data-id="${recordId}" onclick="window.openComments(event,'${recordId}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span class="count">${file.comment_count > 0 ? file.comment_count : ''}</span>
            </button>
            <button class="ss-btn bookmark-btn ${isBookmarked}" data-id="${recordId}" onclick="window.toggleFileAction(this,'bookmark')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="${bookmarkFill}" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
              <span class="count">${file.bookmark_count > 0 ? file.bookmark_count : ''}</span>
            </button>
          </div>
        `;
        return card;
    },

    resetFilters() {
        ['searchCollege','searchType','searchSubject','searchYear'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.value = ''; el.classList.remove('active'); }
        });
        const sort = document.getElementById('searchSort');
        if (sort) sort.value = 'date_desc';
        const input = this.elements.fileName();
        if (input) { input.value = ''; document.getElementById('searchClearBtn').style.display = 'none'; }
        this.performSearch();
    },





    getFileUrl(file) {
        // Route ALL documents through the SEO landing page (/resource/<uuid>).
        // The resource page proxies the actual file via /api/view-doc — one
        // consistent viewer path for PDFs, images, Firebase and Cloudinary alike.
        const recordId = file.record_id || file.id || '';
        if (recordId) {
            return `/resource/${encodeURIComponent(recordId)}`;
        }
        // Legacy fallback: no record id → old direct-viewer URLs
        const path = encodeURIComponent(file["file-path"] || '');
        const source = file.source ? `&source=${encodeURIComponent(file.source)}` : '';

        const formatStr = (file["file-type"] || file.format || '').toLowerCase();
        const fallbackIsPdf = typeof file["file-path"] === 'string' && file["file-path"].toLowerCase().endsWith('.pdf');
        const isPdf = formatStr === 'pdf' || (!formatStr && fallbackIsPdf);

        if (isPdf) {
            return `/view_pdf?pdf_name=${path}`;
        } else {
            return `/preview?file_path=${path}${source}`;
        }
    }
};

// Initialize Search Manager
console.log('[script.js] Setting up DOMContentLoaded for SearchManager...');
document.addEventListener('DOMContentLoaded', () => {
    console.log('[script.js] DOMContentLoaded fired, calling SearchManager.init()');
    SearchManager.init();
});

// Show More functionality for file sections
function showMore(section) {
    const hidden = document.querySelectorAll('.' + section + '-file-card.hidden');
    for (let i = 0; i < 20 && i < hidden.length; i++) {
        hidden[i].classList.remove('hidden');
    }
    if (document.querySelectorAll('.' + section + '-file-card.hidden').length === 0) {
        const btn = document.getElementById(section + '-show-more');
        if (btn) btn.style.display = 'none';
    }
}
// Expose to window for onclick attributes
window.showMore = showMore;

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

window.openComments = function (eventOrId, docIdStr) {
    if (typeof renderCommentModal === 'function') {
        renderCommentModal(docIdStr || eventOrId);
    } else {
        console.error("renderCommentModal is not defined.");
    }
};

window.renderCommentModal = async function (docId) {
    // 1. Check if modal exists, if not create it
    let modal = document.getElementById('comments-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'comments-modal';
        modal.className = 'comments-modal-overlay';
        modal.innerHTML = `
            <div class="comments-modal-content">
                <div class="comments-header" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #eee; padding-bottom:10px; margin-bottom:15px;">
                    <h3 style="margin:0; font-size:18px;">Comments</h3>
                    <button class="close-comments-btn" onclick="document.getElementById('comments-modal').classList.remove('active')" style="background:transparent;border:none;font-size:24px;cursor:pointer;">&times;</button>
                </div>
                <div class="comments-list" id="comments-list" style="max-height:300px; overflow-y:auto; padding-right:10px;">
                    <div class="loader-spinner"></div>
                </div>
                <div class="comments-input-area" style="display:flex; gap:10px; margin-top:15px; border-top:1px solid #eee; padding-top:15px;">
                    <input type="text" id="comment-input" placeholder="Add a comment..." style="flex:1; padding:8px 12px; border:1px solid #ccc; border-radius:4px; font-size:14px;" onkeypress="if(event.key === 'Enter') window.submitComment('${docId}')">
                    <button onclick="window.submitComment('${docId}')" style="background:#2563eb; color:white; border:none; padding:8px 16px; border-radius:4px; cursor:pointer;">Post</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Modal Overlay Styles
        const modalStyles = document.createElement('style');
        modalStyles.textContent = `
            .comments-modal-overlay {
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0,0,0,0.5); z-index: 9999;
                display: flex; justify-content: center; align-items: center;
                opacity: 0; pointer-events: none; transition: opacity 0.3s ease;
                backdrop-filter: blur(3px);
            }
            .comments-modal-overlay.active {
                opacity: 1; pointer-events: all;
            }
            .comments-modal-content {
                background: white; border-radius: 12px; width: 90%; max-width: 500px;
                padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                transform: translateY(20px); transition: transform 0.3s ease;
                color: #333;
            }
            .comments-modal-overlay.active .comments-modal-content {
                transform: translateY(0);
            }
            .comment-item { display:flex; gap:12px; margin-bottom:15px; }
            .comment-avatar { 
                width:36px; height:36px; border-radius:50%; background:#e0e7ff; 
                display:flex; align-items:center; justify-content:center;
                color:#4338ca; font-weight:bold; flex-shrink:0;
            }
            .comment-content { flex:1; background:#f9fafb; padding:10px 14px; border-radius:8px;}
            .comment-meta { display:flex; justify-content:space-between; margin-bottom:5px; font-size:12px;}
            .comment-author { font-weight:600; color:#111827; }
            .comment-author small { color:#6b7280; font-weight:normal; }
            .comment-date { color:#9ca3af; }
            .comment-text { font-size:14px; line-height:1.4; color:#374151; word-break:break-word;}
        `;
        document.head.appendChild(modalStyles);

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    }

    // Update input handlers with current docId
    const inputField = document.getElementById('comment-input');
    const submitBtn = modal.querySelector('.comments-input-area button');

    // Clear old event listeners by cloning
    const newInput = inputField.cloneNode(true);
    const newBtn = submitBtn.cloneNode(true);

    inputField.parentNode.replaceChild(newInput, inputField);
    submitBtn.parentNode.replaceChild(newBtn, submitBtn);

    newInput.onkeypress = (e) => { if (e.key === 'Enter') window.submitComment(docId); };
    newBtn.onclick = () => window.submitComment(docId);

    // 2. Open modal & fetch data
    modal.classList.add('active');
    const commentsList = document.getElementById('comments-list');
    commentsList.innerHTML = '<div style="margin:20px auto;border:3px solid #f3f3f3;border-top:3px solid #2563eb;border-radius:50%;width:24px;height:24px;animation:spin 1s linear infinite;"></div>';

    try {
        const res = await fetch(`/api/interactions/comments/${docId}`);
        const data = await res.json();

        commentsList.innerHTML = '';
        if (data.success && data.data.length > 0) {
            data.data.forEach(c => {
                const name = c.profiles?.full_name || 'Anonymous';
                const role = c.profiles?.role || 'student';
                const date = new Date(c.created_at).toLocaleDateString();
                commentsList.innerHTML += `
                    <div class="comment-item">
                        <div class="comment-avatar">${name.charAt(0).toUpperCase()}</div>
                        <div class="comment-content">
                            <div class="comment-meta">
                                <span class="comment-author">${name} <small>(${role})</small></span>
                                <span class="comment-date">${date}</span>
                            </div>
                            <div class="comment-text">${c.content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>
                        </div>
                    </div>
                `;
            });
            // scroll to bottom
            commentsList.scrollTop = commentsList.scrollHeight;
        } else {
            commentsList.innerHTML = '<p style="text-align:center; color:#6b7280; margin-top: 20px;">No comments yet. Be the first!</p>';
        }
    } catch (e) {
        console.error("Failed to load comments", e);
        commentsList.innerHTML = '<p style="text-align:center; color:#ef4444; margin-top: 20px;">Failed to load comments.</p>';
    }
};

window.submitComment = async function (docId) {
    const input = document.getElementById('comment-input');
    const content = input.value.trim();
    if (!content) return;

    try {
        const res = await fetch(`/api/interactions/comments/${docId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        const data = await res.json();

        if (data.success) {
            input.value = '';
            // Refresh comments immediately
            window.renderCommentModal(docId);

            // Increment the counter on the UI card
            const cards = document.querySelectorAll('.interaction-bar');
            cards.forEach(bar => {
                const btn = bar.querySelector(`.comment-btn[onclick*="${docId}"]`);
                if (btn) {
                    const cntSpan = btn.querySelector('.comment-count');
                    if (cntSpan) cntSpan.textContent = parseInt(cntSpan.textContent || "0") + 1;
                }
            });
        } else {
            alert(data.message || "Failed to post comment. Ensure you are logged in.");
        }
    } catch (e) {
        console.error("Failed to post comment", e);
        alert("An error occurred while posting.");
    }
};

// Carousel Logic
document.addEventListener('DOMContentLoaded', () => {
    const slides = [
        `Be a part of our community! Join our WhatsApp Channel, Group, and Telegram for latest updates.`,
        `Join us on
            < a href = "https://whatsapp.com/channel/0029VbAixWgLCoWwQwX1D91I" target = "_blank" class="text-green-600 font-semibold hover:underline" > WhatsApp Channel</a >,
                <a href="https://chat.whatsapp.com/F1tnqrY0CUC8diuNiJjExz?mode=ems_copy_t" target="_blank" class="text-green-600 font-semibold hover:underline">WhatsApp Group</a>,
                and
                < a href = "https://t.me/abhi_hub" target = "_blank" class="text-blue-600 font-semibold hover:underline" > Telegram</a > 
      for latest updates!`,
        `New Elite version is here! Be the first to explore new features and improvements.
      < a href = "https://abhi-hub-v02-e1ae04210f71.herokuapp.com/dashboard/" target = "_blank" class="text-blue-600 font-semibold hover:underline" > Get Elite Now!</a > `,
        `Latest Update: If you wish to enjoy the service for free, please share AbhiHub with others.`
    ];

    let current = 0;
    const textDiv = document.getElementById("carousel-text");
    const prevBtn = document.getElementById("prev-btn");
    const nextBtn = document.getElementById("next-btn");

    if (textDiv && prevBtn && nextBtn) {
        function showSlide(idx) {
            textDiv.classList.add('opacity-0'); // fade out
            setTimeout(() => {
                textDiv.innerHTML = slides[idx];
                textDiv.classList.remove('opacity-0'); // fade in
            }, 300);
        }

        function nextSlide() {
            current = (current + 1) % slides.length;
            showSlide(current);
        }

        function prevSlide() {
            current = (current - 1 + slides.length) % slides.length;
            showSlide(current);
        }

        prevBtn.onclick = prevSlide;
        nextBtn.onclick = nextSlide;

        // Initialize carousel
        showSlide(current);
    }
});

// Note: Feature Tour Logic is defined in p_struct.html inline script
// Do not duplicate it here to avoid 'Identifier already declared' errors

// Popup and Hamburger Logic
document.addEventListener('DOMContentLoaded', () => {
    const popupImg = document.getElementById('popupImg');
    const popup = document.getElementById('popup');
    const close = document.getElementById('close');

    // Initialize popup image listeners for elements with 'updates' class
    function initializeImagePopups() {
        const updateImages = document.querySelectorAll('.updates img');
        updateImages.forEach(img => {
            img.addEventListener('click', function () {
                if (popup && popupImg) {
                    popup.style.display = 'flex';
                    popupImg.src = this.src;
                }
            });
        });
    }

    initializeImagePopups();

    // Close popup
    if (close) {
        close.addEventListener('click', () => {
            if (popup) popup.style.display = 'none';
        });
    }

    // Close popup when clicking outside the image
    if (popup) {
        popup.addEventListener('click', (e) => {
            if (e.target === popup) {
                popup.style.display = 'none';
            }
        });
    }

    // Hamburger menu functionality
    const hamburger = document.getElementById('hamburger');
    const menuItems = document.getElementById('menuItems');

    if (hamburger && menuItems) {
        hamburger.addEventListener('click', () => {
            menuItems.classList.toggle('active');
            hamburger.classList.toggle('open');
        });
    }
});

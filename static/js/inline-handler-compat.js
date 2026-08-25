    /**
     * inline-handler-compat.js
 * inline-handler-compat.js
 * ========================
 * Replaces inline onclick="" handlers with delegated event listeners.
 *
 * Usage:  Replace onclick="myFunction()" with data-action="myFunction"
 *         The script auto-attaches a click listener from window scope.
 *
 * This is a progressive migration path: templates can be converted one at
 * a time while the script maintains backward compatibility with any
 * remaining inline handlers.
 *
 * Loaded in p_struct.html on all pages.
 */

(function () {
    'use strict';

    // Resolve a function name (supports dotted paths like "PWAManager.close")
    function resolveAction(fnName) {
        if (typeof window[fnName] === 'function') return window[fnName];
        if (typeof globalThis[fnName] === 'function') return globalThis[fnName];
        var parts = fnName.split('.');
        var obj = window;
        for (var i = 0; i < parts.length; i++) {
            if (obj == null || typeof obj[parts[i]] === 'undefined') return null;
            obj = obj[parts[i]];
        }
        return typeof obj === 'function' ? obj : null;
    }

    // Built-in action handlers — read args from data-* attributes
    var builtInActions = {
        dismissIfClicked: function (e, el) {
            if (e.target === el) {
                el.style.display = 'none';
                el.classList.remove('show');
                var id = el.id;
                if (id) {
                    var fnName = 'dismiss' + id.charAt(0).toUpperCase() + id.slice(1);
                    if (typeof window[fnName] === 'function') window[fnName]();
                }
            }
        },
        closeEntityModal: function (e, el) {
            var modal = document.getElementById('globalEntityModal');
            if (modal) { modal.classList.remove('show'); }
        },
        openFileInput: function (e, el) {
            var input = document.getElementById('fileInput');
            if (input) input.click();
        },
        openCameraInput: function (e, el) {
            var input = document.getElementById('cameraInput');
            if (input) input.click();
        },
        rotateCarousel: function (e, el) {
            var dir = el.getAttribute('data-direction');
            if (dir && typeof window.rotateCarousel === 'function') window.rotateCarousel(parseInt(dir, 10));
        },
        toggleCarouselCrop: function (e, el) {
            if (typeof window.toggleCarouselCrop === 'function') window.toggleCarouselCrop();
        },
        removeCarouselImage: function (e, el) {
            if (typeof window.removeCarouselImage === 'function') window.removeCarouselImage();
        },
        navigateCarousel: function (e, el) {
            var dir = el.getAttribute('data-direction');
            if (dir && typeof window.navigateCarousel === 'function') window.navigateCarousel(parseInt(dir, 10));
        },
        trackUploadStart: function (e, el) {
            try {
                if (window.gtag) window.gtag('event', 'upload_funnel', { 'funnel_step': '3_upload_started' });
            } catch (err) { /* non-critical */ }
        },
        toggleRequestsPanel: function (e, el) {
            if (typeof window.toggleRequestsPanel === 'function') {
                window.toggleRequestsPanel();
            } else {
                var p = document.getElementById('materialRequestsPanel');
                if (p) {
                    if (p.style.display === 'none') { p.style.display = 'block'; if (window.fetchMaterialRequests) window.fetchMaterialRequests(); }
                    else { p.style.display = 'none'; }
                }
            }
        },
        hideRequestsPanel: function (e, el) {
            var p = document.getElementById('materialRequestsPanel');
            if (p) p.style.display = 'none';
        },
        closeXpModal: function (e, el) {
            var overlay = document.getElementById('popupModal');
            var card = document.getElementById('xpCard');
            if (overlay) overlay.style.display = 'none';
            if (card) card.style.transform = 'scale(.85)';
            var xp = document.getElementById('popupXp');
            if (xp) xp.style.display = 'none';
            setTimeout(function () {
                var form = document.getElementById('uploadForm');
                if (form) form.reset();
                if (typeof selectedFiles !== 'undefined') { selectedFiles.length = 0; }
            }, 250);
        },
        minimizeUploadOverlay: function (e, el) {
            if (typeof window.minimizeUploadOverlay === 'function') window.minimizeUploadOverlay();
        },
        dismissPromoStrip: function (e, el) {
            if (typeof window.dismissPromoStrip === 'function') {
                window.dismissPromoStrip();
            } else {
                var strip = document.getElementById('promoStrip');
                if (strip) { strip.classList.add('hidden'); strip.style.display = 'none'; }
                document.documentElement.style.setProperty('--strip-h', '0px');
            }
        },
        closePromoCard: function (e, el) {
            if (typeof window.closePromoCard === 'function') {
                window.closePromoCard();
            } else {
                var overlay = document.getElementById('promoCardOverlay');
                if (overlay) overlay.classList.remove('show');
            }
        },
        goToPage: function (e, el) {
            var page = el.getAttribute('data-page');
            if (page) { window.location.href = page; }
        },
        dismissStudyPass: function (e, el) {
            if (el.parentElement) el.parentElement.remove();
            if (window.AbhiHubTracking) window.AbhiHubTracking.trackStudyPassDismiss();
        },
        switchTab: function (e, el) {
            var tabName = el.getAttribute('data-tab');
            if (!tabName) return;
            var panels = document.querySelectorAll('.tab-panel');
            panels.forEach(function (p) { p.classList.remove('active'); p.style.display = 'none'; });
            var btns = el.closest('.tab-bar') ? el.closest('.tab-bar').querySelectorAll('.tab-btn') : document.querySelectorAll('.tab-btn');
            btns.forEach(function (b) { b.classList.remove('active'); });
            var target = document.getElementById(tabName);
            if (target) { target.classList.add('active'); target.style.display = 'block'; }
            el.classList.add('active');
        },
        switchPeerTab: function (e, el) {
            var tabName = el.getAttribute('data-tab');
            if (!tabName) return;
            var contents = document.querySelectorAll('.peer-tab-content');
            contents.forEach(function (c) { c.classList.remove('active'); });
            var btns = el.closest('.peer-tabs') ? el.closest('.peer-tabs').querySelectorAll('.peer-tab-btn') : document.querySelectorAll('.peer-tab-btn');
            btns.forEach(function (b) { b.classList.remove('active'); });
            var target = document.getElementById('peer-tab-' + tabName);
            if (target) { target.classList.add('active'); }
            el.classList.add('active');
        },
        switchAdminTab: function (e, el) {
            var tabName = el.getAttribute('data-tab');
            if (!tabName) return;
            var contents = document.querySelectorAll('.tab-content');
            contents.forEach(function (c) { c.classList.remove('active'); c.style.display = 'none'; });
            var btns = el.closest('.tab-bar') ? el.closest('.tab-bar').querySelectorAll('.tab-btn') : document.querySelectorAll('.tab-btn');
            btns.forEach(function (b) { b.classList.remove('active'); });
            var target = document.getElementById(tabName);
            if (target) { target.classList.add('active'); target.style.display = 'block'; }
            el.classList.add('active');
        },
        openPeerSearchModal: function (e, el) {
            if (typeof window.openPeerSearchModal === 'function') window.openPeerSearchModal();
        },
        viewPeerDetail: function (e, el) {
            var userId = el.getAttribute('data-user-id');
            if (userId) { window.location.href = '/u/' + userId; }
        },
        toggleLike: function (e, el) {
            e.stopPropagation();
            var recordId = el.getAttribute('data-record-id');
            if (typeof window.toggleLike === 'function') window.toggleLike(e, recordId);
        },
        toggleBookmark: function (e, el) {
            e.stopPropagation();
            var recordId = el.getAttribute('data-record-id');
            if (typeof window.toggleBookmark === 'function') window.toggleBookmark(e, recordId);
        },
        openComments: function (e, el) {
            e.stopPropagation();
            var recordId = el.getAttribute('data-record-id');
            if (typeof window.openComments === 'function') window.openComments(e, recordId);
        },
        openFile: function (e, el) {
            e.stopPropagation();
            var filename = el.getAttribute('data-filename');
            if (filename && typeof window.openFile === 'function') window.openFile(filename);
        },
        toggleLikeCard: function (e, el) {
            e.stopPropagation();
            var recordId = el.getAttribute('data-record-id');
            if (typeof window.toggleLike === 'function') window.toggleLike(e, recordId);
        },
        toggleBookmarkCard: function (e, el) {
            e.stopPropagation();
            var recordId = el.getAttribute('data-record-id');
            if (typeof window.toggleBookmark === 'function') window.toggleBookmark(e, recordId);
        },
        openCommentsCard: function (e, el) {
            e.stopPropagation();
            var recordId = el.getAttribute('data-record-id');
            if (recordId && typeof window.openComments === 'function') window.openComments(e, recordId);
        },
        shareApp: function (e, el) {
            var platform = el.getAttribute('data-platform');
            if (platform && typeof window.shareApp === 'function') window.shareApp(platform);
        },
        copyLink: function (e, el) {
            if (typeof window.copyLink === 'function') window.copyLink();
        },
        // Page-specific built-ins
        navigateFile: function (e, el) {
            var dir = el.getAttribute('data-direction');
            if (dir !== null && typeof window.navigateFile === 'function') window.navigateFile(parseInt(dir, 10));
        },
        fillPdfQuestion: function (e, el) {
            var q = el.getAttribute('data-question');
            if (q && typeof window.fillPdfQuestion === 'function') window.fillPdfQuestion(q);
        },
        sendPersonaPrompt: function (e, el) {
            var persona = el.getAttribute('data-persona');
            if (persona && typeof window.sendPersonaPrompt === 'function') window.sendPersonaPrompt(persona, el);
        },
        suggestQ: function (e, el) {
            var q = el.getAttribute('data-question');
            if (q && typeof window.suggestQ === 'function') window.suggestQ(q);
        },
        viewFile: function (e, el) {
            var file = el.getAttribute('data-file');
            if (file && typeof window.viewFile === 'function') window.viewFile(file);
        },
        verifyFile: function (e, el) {
            var file = el.getAttribute('data-file');
            if (file && typeof window.verifyFile === 'function') window.verifyFile(file);
        },
        saveChanges: function (e, el) {
            if (typeof window.saveChanges === 'function') { window.saveChanges(el); return; }
            if (typeof window.handleSave === 'function') { window.handleSave(); return; }
        },
        cancelChanges: function (e, el) {
            if (typeof window.cancelChanges === 'function') window.cancelChanges(el);
        },
        closeAiChatPanel: function (e, el) {
            var p = document.getElementById('aiChatPanel');
            if (p) p.setAttribute('data-open', 'false');
        },
        closeOnBackdrop: function (e, el) {
            if (e.target === el && typeof window.closeAIModal === 'function') window.closeAIModal();
        },
        closeAIModalOnBackdrop: function (e, el) {
            if (e.target === el && typeof window.closeAIModal === 'function') window.closeAIModal();
        },
        closeInfoOnBackdrop: function (e, el) {
            if (e.target === el && typeof window.closeInfo === 'function') window.closeInfo();
        },
        reloadPage: function (e, el) {
            window.location.reload();
        },
        removeParentElement: function (e, el) {
            if (el && el.parentElement) el.parentElement.remove();
        },
        moderateApproveDocument: function (e, el) {
            var docId = el.getAttribute('data-doc-id');
            if (docId && typeof window.moderateApproveDocument === 'function') window.moderateApproveDocument(docId);
        },
        moderateRejectDocument: function (e, el) {
            var docId = el.getAttribute('data-doc-id');
            if (docId && typeof window.moderateRejectDocument === 'function') window.moderateRejectDocument(docId);
        },
        selectAdminUser: function (e, el) {
            var userId = el.getAttribute('data-user-id');
            var fullName = el.getAttribute('data-full-name') || '';
            var email = el.getAttribute('data-email') || '';
            var score = el.getAttribute('data-score') || '0';
            if (typeof window.selectAdminUser === 'function') window.selectAdminUser(userId, fullName, email, score);
        },
        clearPushForm: function (e, el) {
            if (typeof window.clearPushForm === 'function') window.clearPushForm();
        },
        showMore: function (e, el) {
            var category = el.getAttribute('data-category');
            if (category && typeof window.showMore === 'function') window.showMore(category);
        },
        closeNotification: function (e, el) {
            if (typeof window.closeNotification === 'function') window.closeNotification();
        },
        toggleShareOptions: function (e, el) {
            if (typeof window.toggleShareOptions === 'function') window.toggleShareOptions();
        },
        retryConnection: function (e, el) {
            if (typeof window.retryConnection === 'function') window.retryConnection();
        },
        showCachedContent: function (e, el) {
            if (typeof window.showCachedContent === 'function') window.showCachedContent();
        },
        handleNotificationToggle: function (e, el) {
            if (typeof window.handleNotificationToggle === 'function') window.handleNotificationToggle();
        },
        goBack: function (e, el) {
            e.preventDefault();
            window.history.back();
        },
        goBackSimple: function (e, el) {
            window.history.back();
        },
        openAIModal: function (e, el) {
            if (typeof window.openAIModal === 'function') window.openAIModal();
        },
        openInfo: function (e, el) {
            if (typeof window.openInfo === 'function') window.openInfo();
        },
        closeInfo: function (e, el) {
            if (typeof window.closeInfo === 'function') window.closeInfo();
        },
        closeAIModal: function (e, el) {
            if (typeof window.closeAIModal === 'function') window.closeAIModal();
        },
        askAI: function (e, el) {
            if (typeof window.askAI === 'function') window.askAI();
        },
        askAIOnEnter: function (e, el) {
            if (e.key === 'Enter' && typeof window.askAI === 'function') window.askAI();
        },
        askPdfAIOnEnter: function (e, el) {
            if (e.key === 'Enter' && typeof window.askPdfAI === 'function') window.askPdfAI();
        },
        askPdfAI: function (e, el) {
            if (typeof window.askPdfAI === 'function') window.askPdfAI();
        },
        syncStorage: function (e, el) {
            if (typeof window.syncStorage === 'function') window.syncStorage();
        },
        loadMoreFiles: function (e, el) {
            if (typeof window.loadMoreFiles === 'function') window.loadMoreFiles();
        },
        loadMore: function (e, el) {
            if (window.SearchManager && typeof SearchManager.loadMore === 'function') SearchManager.loadMore();
        },
        resetFilters: function (e, el) {
            if (window.SearchManager && typeof SearchManager.resetFilters === 'function') SearchManager.resetFilters();
        },
        clearFilters: function (e, el) {
            if (typeof window.clearFilters === 'function') window.clearFilters();
        },
        removeParentElement: function (e, el) {
            if (el.parentElement) el.parentElement.remove();
        },
        printPage: function (e, el) {
            window.print();
        },
        stopPropagation: function (e, el) {
            e.stopPropagation();
        },
        closeLabelingView: function (e, el) {
            if (typeof window.closeLabelingView === 'function') window.closeLabelingView();
        },
        resetView: function (e, el) {
            if (typeof window.resetView === 'function') window.resetView();
        },
        zoomIn: function (e, el) {
            if (typeof window.zoomIn === 'function') window.zoomIn();
            else if (typeof window.zoomInImage === 'function') window.zoomInImage();
        },
        zoomInImage: function (e, el) {
            if (typeof window.zoomInImage === 'function') window.zoomInImage();
            else if (typeof window.zoomIn === 'function') window.zoomIn();
        },
        zoomOut: function (e, el) {
            if (typeof window.zoomOut === 'function') window.zoomOut();
            else if (typeof window.zoomOutImage === 'function') window.zoomOutImage();
        },
        zoomOutImage: function (e, el) {
            if (typeof window.zoomOutImage === 'function') window.zoomOutImage();
            else if (typeof window.zoomOut === 'function') window.zoomOut();
        },
        resetImageZoom: function (e, el) {
            if (typeof window.resetImageZoom === 'function') window.resetImageZoom();
        },
        toggleImageFullscreen: function (e, el) {
            if (typeof window.toggleImageFullscreen === 'function') window.toggleImageFullscreen();
        },
        rotateImage: function (e, el) {
            if (typeof window.rotateImage === 'function') window.rotateImage();
        },
        toggleFullscreen: function (e, el) {
            if (typeof window.toggleFullscreen === 'function') window.toggleFullscreen();
        },
        handleSave: function (e, el) {
            if (typeof window.handleSave === 'function') window.handleSave();
        },
        hideStudyPassChip: function (e, el) {
            if (typeof window.hideStudyPassChip === 'function') window.hideStudyPassChip();
            else { var c = document.getElementById('studyPassChip'); if (c) c.style.display = 'none'; }
        },
        showStudyPassChip: function (e, el) {
            if (typeof window.showStudyPassChip === 'function') window.showStudyPassChip();
            else { var c = document.getElementById('studyPassChipMini'); if (c) c.style.display = 'block'; }
        },
        handleGateUpload: function (e, el) {
            window.gateActionTaken = true;
            if (window.AbhiHubTracking) window.AbhiHubTracking.trackStudyPassUploadClick();
            if (typeof window.handleGateUpload === 'function') window.handleGateUpload();
        },
        trackStoreRoomClick: function (e, el) {
            window.gateActionTaken = true;
            if (window.AbhiHubTracking) window.AbhiHubTracking.trackStudyPassStoreRoomClick();
        },
        shareChatWhatsApp: function (e, el) {
            if (typeof window.shareChatWhatsApp === 'function') window.shareChatWhatsApp();
        },
        exportChatPDF: function (e, el) {
            if (typeof window.exportChatPDF === 'function') window.exportChatPDF();
        },
        toggleChatFullscreen: function (e, el) {
            if (typeof window.toggleChatFullscreen === 'function') window.toggleChatFullscreen();
        },
        sendPersonaPrompt: function (e, el) {
            var model = el.getAttribute('data-model');
            if (model && typeof window.sendPersonaPrompt === 'function') window.sendPersonaPrompt(model, el);
        },
        suggestQ: function (e, el) {
            var prompt = el.getAttribute('data-question');
            if (prompt && typeof window.suggestQ === 'function') window.suggestQ(prompt);
        },
        fillPdfQuestion: function (e, el) {
            var prompt = el.getAttribute('data-question');
            if (prompt && typeof window.fillPdfQuestion === 'function') window.fillPdfQuestion(prompt);
        },
        navigateFile: function (e, el) {
            var dir = el.getAttribute('data-direction');
            if (dir !== null && typeof window.navigateFile === 'function') window.navigateFile(parseInt(dir, 10));
        },
        toggleLike: function (e, el) {
            var docId = el.getAttribute('data-doc-id');
            if (docId !== null && typeof window.toggleLike === 'function') window.toggleLike(e, docId);
        },
        toggleBookmark: function (e, el) {
            var docId = el.getAttribute('data-doc-id');
            if (docId !== null && typeof window.toggleBookmark === 'function') window.toggleBookmark(e, docId);
        },
        selectAdminUser: function (e, el) {
            var userId = el.getAttribute('data-user-id');
            if (userId && typeof window.selectAdminUser === 'function') window.selectAdminUser(el, userId);
        },
        selectFile: function (e, el) {
            var fileId = el.getAttribute('data-file-id');
            if (fileId && typeof window.selectFile === 'function') window.selectFile(fileId);
        },
        copyLink: function (e, el) {
            if (typeof window.copyLink === 'function') window.copyLink();
        },
        openSupportModal: function (e, el) {
            if (typeof window.openSupportModal === 'function') window.openSupportModal();
        },
        selectPeer: function (e, el) {
            var peerId = el.getAttribute('data-peer-id');
            if (peerId && typeof window.selectPeer === 'function') window.selectPeer(peerId);
        },
        shareHistory: function (e, el) {
            var requesterId = el.getAttribute('data-requester-id');
            if (requesterId && typeof window.shareHistory === 'function') window.shareHistory(requesterId);
        },
        requestHistory: function (e, el) {
            if (typeof window.requestHistory === 'function') window.requestHistory();
        },
        sendMessage: function (e, el) {
            if (typeof window.sendMessage === 'function') window.sendMessage();
        },
        pay: function (e, el) {
            var amount = el.getAttribute('data-amount');
            if (amount && typeof window.pay === 'function') window.pay(amount);
        },
        customPay: function (e, el) {
            if (typeof window.customPay === 'function') window.customPay();
        },
        openPrivacySettings: function (e, el) {
            if (window.AbhiHubConsent && typeof window.AbhiHubConsent.setConsent === 'function') window.AbhiHubConsent.setConsent(false);
        },
        copyUPI: function (e, el) {
            if (typeof window.copyUPI === 'function') window.copyUPI();
        },
        // Chat-specific actions
        startChatWith: function (e, el) {
            var peerId = el.getAttribute('data-peer-id');
            if (peerId && typeof window.startChatWith === 'function') window.startChatWith(peerId);
        },
        togglePeerMaterials: function (e, el) {
            e.stopPropagation();
            if (typeof window.togglePeerMaterials === 'function') window.togglePeerMaterials();
        },
        viewPeerMaterialsModal: function (e, el) {
            e.stopPropagation();
            var peerId = el.getAttribute('data-peer-id');
            if (peerId && typeof window.viewPeerMaterialsModal === 'function') window.viewPeerMaterialsModal(peerId);
        },
        showFileInfo: function (e, el) {
            e.stopPropagation();
            e.preventDefault();  // prevent anchor navigation when icon is inside <a>
            if (typeof window.showFileInfo === 'function') window.showFileInfo(e, el);
        },
        closeFileInfo: function (e, el) {
            if (typeof window.closeFileInfo === 'function') window.closeFileInfo();
        }
    };

    // Attach a data-action handler to an element
    function attachDataAction(el) {
        var action = el.getAttribute('data-action');
        if (!action) return;
        if (el.hasAttribute('data-listener-attached')) return;
        var fn = resolveAction(action) || builtInActions[action];
        if (!fn) return;
        el.addEventListener('click', function (e) {
            if (el.tagName === 'A' && el.getAttribute('href') === '#') e.preventDefault();
            try {
                var result = fn.call(el, e, el);
                if (result && typeof result.then === 'function') {
                    result.catch(function (err) { console.error('Error in data-action handler:', action, err); });
                }
            } catch (err) {
                console.error('Error in data-action handler:', action, err);
            }
        });
        el.setAttribute('data-listener-attached', 'true');
    }

    // Attach to all elements with data-action
    function attachAll() {
        var elements = document.querySelectorAll('[data-action]');
        elements.forEach(attachDataAction);
        // Also attach data-event-* listeners (file inputs, forms, etc.)
        var eventEls = document.querySelectorAll('[data-event-change], [data-event-click], [data-event-submit]');
        eventEls.forEach(function (el) {
            ['change', 'click', 'submit'].forEach(function (ev) {
                if (el.hasAttribute('data-event-' + ev)) {
                    attachEventAction(el, ev);
                }
            });
        });
    }

    // Attach for event-based actions (data-event-click, data-event-change, etc.)
    function attachEventAction(el, eventName) {
        var action = el.getAttribute('data-event-' + eventName);
        if (!action) return;
        var key = 'data-listener-' + eventName;
        if (el.hasAttribute(key)) return;
        el.setAttribute(key, 'true');
        var fn = resolveAction(action);
        if (!fn) return;
        el.addEventListener(eventName, function (e) {
            try {
                var result = fn.call(el, e, el);
                if (result && typeof result.then === 'function') {
                    result.catch(function (err) { console.error('Error in event handler:', action, err); });
                }
            } catch (err) {
                console.error('Error in event handler:', action, err);
            }
        });
    }

    window.attachAll = attachAll;
    // Initial attachment
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachAll);
    } else {
        attachAll();
    }
    setTimeout(attachAll, 500);

    // Safety net: auto-convert remaining inline event handlers
    var inlineEventAttrs = ['onclick', 'onchange', 'onkeyup', 'onkeydown', 'onmouseover', 'onmouseout', 'onsubmit'];
    var observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
            m.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;

                // Check this node
                inlineEventAttrs.forEach(function (attr) {
                    var handler = node.getAttribute && node.getAttribute(attr);
                    if (handler && !node.hasAttribute('data-listener-' + attr)) {
                        // Only convert simple handler calls without parameters (empty or no parentheses)
                        // so that handlers passing arguments are executed natively by the browser.
                        var match = handler.match(/^\s*([^(]+)\s*\(\s*\)/);
                        if (match) {
                            var eventName = attr.substring(2);
                            node.setAttribute('data-event-' + eventName, match[1].trim());
                            node.setAttribute('data-listener-' + attr, 'true');
                            node.removeAttribute(attr);
                            attachEventAction(node, eventName);
                        }
                    }
                });

                // Check children
                var children = node.querySelectorAll && node.querySelectorAll(
                    '[' + inlineEventAttrs.join('],[') + ']'
                );
                if (children && children.length) {
                    children.forEach(function (child) {
                        inlineEventAttrs.forEach(function (attr) {
                            var handler = child.getAttribute(attr);
                            if (handler && !child.hasAttribute('data-listener-' + attr)) {
                                // Only convert simple handler calls without parameters (empty or no parentheses)
                                // so that handlers passing arguments are executed natively by the browser.
                                var match = handler.match(/^\s*([^(]+)\s*\(\s*\)/);
                                if (match) {
                                    var eventName = attr.substring(2);
                                    child.setAttribute('data-event-' + eventName, match[1].trim());
                                    child.setAttribute('data-listener-' + attr, 'true');
                                    child.removeAttribute(attr);
                                    attachEventAction(child, eventName);
                                }
                            }
                        });
                    });
                }
                // Also attach listeners to any new data-action elements
                var newActions = node.querySelectorAll && node.querySelectorAll('[data-action]:not([data-listener-attached])');
                if (newActions && newActions.length) {
                    newActions.forEach(attachDataAction);
                }
            });
        });
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            observer.observe(document.body, { childList: true, subtree: true });
        });
    } else {
        observer.observe(document.body, { childList: true, subtree: true });
    }

})();

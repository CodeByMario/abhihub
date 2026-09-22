/**
 * AbhiHub AI In-App Floating Assistant Widget
 * v3 — Live user personalization, deep PDF/file extraction, external AI providers.
 */

import {
    streamExternalResponse,
    getActiveProvider, saveActiveProvider,
    getKey, getModel, hasKey,
    PROVIDERS
} from "/static/js/ai/external-provider.js";
import { buildAbhiHubSystemPrompt } from "/static/js/ai/webllm-core.js";

(function () {
    if (window.__ABHIHUB_AI_INITIALIZED__) return;
    window.__ABHIHUB_AI_INITIALIZED__ = true;

    const CANONICAL_BASE = "https://www.abhihub.edu.eu.org";
    const AI_HUB_ORIGIN = (window.location.hostname.includes("abhihub.edu.eu.org")) 
        ? "https://ai.abhihub.edu.eu.org" 
        : window.location.origin;

    // Helper to convert relative URLs to canonical AbhiHub URLs
    function toCanonicalUrl(url) {
        if (!url) return "";
        if (url.startsWith("http://") || url.startsWith("https://")) {
            return url;
        }
        const cleaned = url.startsWith("/") ? url : "/" + url;
        return `${CANONICAL_BASE}${cleaned}`;
    }

    // Lightweight Safe Markdown Formatter
    function formatMarkdown(text) {
        if (!text) return "";
        let escaped = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Code Blocks ```lang ... ```
        escaped = escaped.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<div class="ai-code-block">
                <div class="ai-code-header">
                    <span class="ai-code-lang">${lang || "code"}</span>
                    <button type="button" class="ai-copy-btn" data-action="copyCode">Copy</button>
                </div>
                <pre><code>${code.trim()}</code></pre>
            </div>`;
        });

        // Inline code `code`
        escaped = escaped.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');

        // Markdown Links [title](url)
        escaped = escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]+)\)/g, (match, label, href) => {
            const fullUrl = toCanonicalUrl(href);
            return `<a href="${fullUrl}" target="_blank" rel="noopener noreferrer" class="ai-link">🔗 ${label}</a>`;
        });

        // Bold **text**
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic *text*
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Linebreaks & paragraphs
        return escaped.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>');
    }

    class AbhiHubAIAssistant {
        constructor() {
            this.isOpen = false;
            this.iframeLoaded = false;
            this.pendingRequests = new Map();
            this.reqIdCounter = 0;
            this.messages = [];
            this.isModelLoaded = false;
            this.isModelLoading = false;
            this.isGenerating = false;
            this.currentProgress = 0;
            this.queuedMessage = null;
            this.activeProvider = getActiveProvider(); // "webllm" | "gemini" | "groq" | ...

            this.selectedModel = localStorage.getItem("abhihub_ai_model") || null;

            this.initDOM();
            this.initIframeBridge();
            this.bindEvents();
            this.bindViewportEvents();
        }

        initDOM() {
            const widget = document.createElement("div");
            widget.id = "abhihubAiWidget";
            widget.className = "abhihub-ai-widget";

            const profile = this.getUserProfile();
            const greetingName = profile.name && profile.name !== "Student" ? `, ${profile.name}` : "";
            const contextHint = profile.branch ? `${profile.branch} student` : "student";

            widget.innerHTML = `
                <button id="aiFabBtn" class="ai-fab-btn" aria-label="Open AbhiHub AI Assistant" title="AbhiHub AI Assistant (Ctrl+K)">
                    <span class="ai-fab-icon">⚡</span>
                    <span class="ai-fab-label">AI Assistant</span>
                    <span id="aiFabProgressBadge" class="ai-fab-badge" style="display: none;">0%</span>
                </button>

                <div id="aiDrawer" class="ai-drawer" aria-hidden="true">
                    <div class="ai-drawer-header">
                        <div class="ai-drawer-title">
                            <span class="ai-sparkle">✨</span>
                            <strong>AbhiHub AI</strong>
                            <span class="ai-context-badge" id="aiPageBadge">General</span>
                        </div>
                        <div class="ai-drawer-controls">
                            <button id="aiModelStatusBtn" class="ai-status-pill" title="Model Status">Ready</button>
                            <button id="aiCloseBtn" class="ai-icon-btn" aria-label="Close">✕</button>
                        </div>
                    </div>

                    <div id="aiDownloadBanner" class="ai-download-banner" style="display: none;">
                        <div class="ai-banner-row">
                            <span id="aiBannerText">Loading in background (you can continue browsing)...</span>
                            <span id="aiBannerPct">0%</span>
                        </div>
                        <div class="ai-mini-progress">
                            <div id="aiMiniBar" class="ai-mini-fill"></div>
                        </div>
                    </div>

                    <div class="ai-drawer-body">
                        <div class="ai-messages" id="aiWidgetMessages">
                            <div class="ai-msg bot">
                                <div class="ai-msg-content">
                                    <p>👋 Hi${greetingName}! I'm your personalized AbhiHub study partner. How can I help with your studies today?</p>
                                    <div class="ai-quick-actions" id="aiQuickActions">
                                        <button class="ai-action-chip" data-action="explain_page">📄 Explain This Page</button>
                                        <button class="ai-action-chip" data-action="get_file_links">🔗 List Download Links</button>
                                        <button class="ai-action-chip" data-action="summarize_pdf">📝 Summarize Active Document</button>
                                        <button class="ai-action-chip" data-action="pyq_help">🎯 PYQ Exam Tips</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <form class="ai-drawer-footer" id="aiChatForm">
                        <div class="ai-provider-row" id="aiProviderRow"></div>
                        <div class="ai-input-row">
                            <input type="text" id="aiChatInput" placeholder="Ask AI anything about your studies..." autocomplete="off">
                            <button type="submit" id="aiChatSend" class="ai-send-btn" aria-label="Send Message" title="Send (Enter)">
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                                </svg>
                            </button>
                            <button type="button" id="aiChatStop" class="ai-stop-btn" aria-label="Stop Generation" title="Stop Generation" style="display: none;">
                                <span class="ai-stop-icon">■</span>
                            </button>
                        </div>
                    </form>
                </div>

                <iframe id="aiWorkerFrame" src="${AI_HUB_ORIGIN}/ai/embed" style="display:none;" title="AbhiHub AI Runtime"></iframe>
            `;

            document.body.appendChild(widget);

            this.fabBtn = document.getElementById("aiFabBtn");
            this.fabBadge = document.getElementById("aiFabProgressBadge");
            this.drawer = document.getElementById("aiDrawer");
            this.closeBtn = document.getElementById("aiCloseBtn");
            this.statusBtn = document.getElementById("aiModelStatusBtn");
            this.messagesContainer = document.getElementById("aiWidgetMessages");
            this.chatForm = document.getElementById("aiChatForm");
            this.chatInput = document.getElementById("aiChatInput");
            this.sendBtn = document.getElementById("aiChatSend");
            this.stopBtn = document.getElementById("aiChatStop");
            this.banner = document.getElementById("aiDownloadBanner");
            this.bannerText = document.getElementById("aiBannerText");
            this.bannerPct = document.getElementById("aiBannerPct");
            this.miniBar = document.getElementById("aiMiniBar");
            this.iframe = document.getElementById("aiWorkerFrame");
            this.pageBadge = document.getElementById("aiPageBadge");
            this.providerRow = document.getElementById("aiProviderRow");

            this.updateContextBadge();
            this.renderProviderPills();
        }

        updateContextBadge() {
            const path = window.location.pathname;
            let label = "General";
            if (path.includes("/resource")) label = "Notes & Resources";
            else if (path.includes("/pyq")) label = "PYQ Papers";
            else if (path.includes("/subject")) label = "Subject Guide";
            else if (path.includes("/dashboard")) label = "Dashboard";
            else if (path.includes("/account")) label = "Account";
            if (this.pageBadge) this.pageBadge.textContent = label;
        }

        /** Read user profile fresh from window.__CURRENT_USER__ each call */
        getUserProfile() {
            const u = window.__CURRENT_USER__ || {};
            return {
                name:    u.name    || u.display_name || "",
                college: u.college || u.college_id   || "",
                branch:  u.branch  || u.branch_name  || "",
                degree:  u.degree  || "",
                year:    u.year    || u.pursuing_year || "",
                role:    u.role    || u.user_role     || ""
            };
        }

        getUserProfileContext() {
            const p = this.getUserProfile();
            const parts = [];
            if (p.name)    parts.push(`Student Name: ${p.name}`);
            if (p.college) parts.push(`College: ${p.college}`);
            if (p.branch)  parts.push(`Branch: ${p.branch}`);
            if (p.degree)  parts.push(`Degree: ${p.degree}`);
            if (p.year)    parts.push(`Year: Year ${p.year}`);
            if (p.role)    parts.push(`Role: ${p.role}`);
            return parts.length > 0 ? `STUDENT PROFILE METADATA:\n${parts.join("\n")}\n` : "";
        }

        getPageContext() {
            const path  = window.location.pathname;
            const title = document.title || "";
            const h1    = document.querySelector("h1")?.innerText?.trim() || "";

            // ── File links ───────────────────────────────────────────────
            const seenUrls = new Set();
            const fileLinks = [];
            const FILE_SELECTORS = [
                'a[href*=".pdf"]', 'a[href*="/view"]', 'a[href*="/preview"]',
                'a[href*="/download"]', 'a[data-file-url]', 'button[data-file-url]'
            ];
            document.querySelectorAll(FILE_SELECTORS.join(",")).forEach((el) => {
                const href = el.getAttribute("href") || el.getAttribute("data-file-url") || "";
                const text = el.innerText?.trim() || el.getAttribute("title") || el.getAttribute("aria-label") || "Document";
                if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
                    const canonical = toCanonicalUrl(href);
                    if (!seenUrls.has(canonical)) {
                        seenUrls.add(canonical);
                        fileLinks.push({ name: text.replace(/\s+/g, " ").slice(0, 80), url: canonical });
                    }
                }
            });

            // ── Deep PDF text extraction ────────────────────────────────────────
            let pdfText = "";
            // 1. In-page PDF viewer layer (pdf.js rendered)
            const pdfLayer = document.querySelector(".textLayer, #viewer, .pdfViewer, .reader-root, .pdf-content");
            if (pdfLayer) pdfText = pdfLayer.innerText?.trim().slice(0, 4000) || "";
            // 2. Embedded PDF <object> or <embed>
            if (!pdfText) {
                const embed = document.querySelector('embed[type*="pdf"], object[type*="pdf"]');
                if (embed) pdfText = `[Embedded PDF: ${toCanonicalUrl(embed.getAttribute("src") || "")}]`;
            }
            // 3. PDF <iframe src>
            if (!pdfText) {
                const pdfIframe = document.querySelector('iframe[src*=".pdf"], iframe[src*="/view"]');
                if (pdfIframe) pdfText = `[PDF Viewer: ${toCanonicalUrl(pdfIframe.getAttribute("src") || "")}]`;
            }

            // ── Images ─────────────────────────────────────────────────────
            const pageImages = [];
            document.querySelectorAll("img[src]").forEach((img) => {
                const src = img.getAttribute("src") || "";
                const alt = img.getAttribute("alt") || img.getAttribute("title") || "";
                const w   = img.naturalWidth  || img.width  || 0;
                const h   = img.naturalHeight || img.height || 0;
                if (src && (w > 80 || h > 80 || alt) &&
                    !src.includes("google") && !src.includes("analytics") &&
                    !src.includes("avatar") && !src.includes("icon")) {
                    pageImages.push({ alt: alt || "Diagram / Image", url: toCanonicalUrl(src) });
                }
            });

            // ── Selected text ──────────────────────────────────────────────────
            let selectedText = "";
            try { selectedText = window.getSelection()?.toString()?.trim() || ""; } catch (_) {}

            return {
                url: window.location.href, path, title, heading: h1,
                fileLinks:  fileLinks.slice(0, 20),
                pageImages: pageImages.slice(0, 10),
                pdfText,
                selectedText
            };
        }

        async updateCacheSizeTooltip() {
            try {
                let totalBytes = 0;
                if ('caches' in window) {
                    const cacheNames = ['abhihub-ai-models-v1', 'webllm/model'];
                    for (const name of cacheNames) {
                        try {
                            const cache = await caches.open(name);
                            const keys = await cache.keys();
                            for (const req of keys) {
                                const res = await cache.match(req);
                                if (res) {
                                    const blob = await res.blob().catch(() => null);
                                    if (blob) totalBytes += blob.size;
                                }
                            }
                        } catch (e) {}
                    }
                }
                const mb = (totalBytes / (1024 * 1024)).toFixed(1);
                if (totalBytes > 0 && this.statusBtn) {
                    this.statusBtn.title = `AbhiHub AI (On-Device • ${mb} MB Cached)`;
                }
            } catch (e) {}
        }

        initIframeBridge() {
            // 1. Listen for background download updates from Service Worker
            if (navigator.serviceWorker) {
                navigator.serviceWorker.addEventListener("message", (event) => {
                    const { type, payload } = event.data || {};
                    if (type === "AI_MODEL_PRECACHE_PROGRESS" && payload) {
                        const { progress, text, status } = payload;
                        if (typeof progress === "number") {
                            this.currentProgress = progress;
                            this.bannerPct.textContent = `${progress}%`;
                            this.fabBadge.textContent = `${progress}%`;
                            this.miniBar.style.width = `${progress}%`;
                        }
                        if (text) {
                            this.bannerText.innerHTML = `⚡ <strong>Step 2/3:</strong> ${text}`;
                        }
                        if (status === "ready") {
                            this.isModelLoaded = true;
                            this.isModelLoading = false;
                            localStorage.setItem("abhihub_ai_model_cached", "true");
                            this.banner.style.display = "none";
                            this.fabBadge.style.display = "none";
                            this.statusBtn.textContent = "⚡ Online";
                            this.statusBtn.classList.add("ready");
                            this.updateCacheSizeTooltip();
                        }
                    }
                });

                // Query existing background cache status on page mount
                if (navigator.serviceWorker.controller) {
                    navigator.serviceWorker.controller.postMessage({ type: "GET_AI_MODEL_CACHE_STATUS" });
                }
            }

            this.updateCacheSizeTooltip();

            // 2. PostMessage RPC Bridge
            window.addEventListener("message", (event) => {
                const { id, type, success, data, error } = event.data || {};
                if (!id) return;

                if (type && type.endsWith("_CHUNK")) {
                    const req = this.pendingRequests.get(id);
                    if (req && req.onChunk) {
                        req.onChunk(data);
                    }
                    return;
                }

                const resolver = this.pendingRequests.get(id);
                if (resolver) {
                    if (resolver.timeoutId) clearTimeout(resolver.timeoutId);
                    this.pendingRequests.delete(id);
                    if (success) resolver.resolve(data);
                    else resolver.reject(new Error(error || "RPC Failed"));
                }
            });

            this.iframe.onload = async () => {
                this.iframeLoaded = true;
                try {
                    const info = await this.rpcCall("GET_DEVICE_INFO", {}, null, 15000);
                    window.__ABHIHUB_AI_DEVICE_INFO__ = info;
                    window.dispatchEvent(new CustomEvent("abhihub_ai_ready", { detail: info }));

                    if (info && info.webgpu?.supported) {
                        this.statusBtn.textContent = "⚡ WebGPU Ready";
                        this.statusBtn.classList.add("ready");
                    } else {
                        this.statusBtn.textContent = "⚠️ CPU Fallback";
                    }

                    // Silently prefetch recommended model if not yet cached
                    if (info?.cacheStatus) {
                        const recId = info.deviceInfo?.recommendedModelId;
                        if (recId && !info.cacheStatus[recId]?.cached) {
                            this.rpcCall("PREFETCH_MODEL", { modelId: recId }, null, 0).catch(() => {});
                        }
                    }

                    if (localStorage.getItem("abhihub_ai_model_cached") === "true") {
                        this.ensureModelLoaded(false, true).catch(() => {});
                    }
                } catch (e) {
                    this.statusBtn.textContent = "Offline";
                }
            };
        }

        rpcCall(type, payload = {}, onChunk = null, timeoutMs = 60000) {
            return new Promise((resolve, reject) => {
                const id = "req_" + (++this.reqIdCounter) + "_" + Date.now();
                
                let timeoutId = null;
                if (timeoutMs > 0) {
                    timeoutId = setTimeout(() => {
                        if (this.pendingRequests.has(id)) {
                            this.pendingRequests.delete(id);
                            reject(new Error(`RPC request timeout (${type})`));
                        }
                    }, timeoutMs);
                }

                this.pendingRequests.set(id, { resolve, reject, onChunk, timeoutId });

                const targetOrigin = AI_HUB_ORIGIN.startsWith("http") ? AI_HUB_ORIGIN : "*";
                if (this.iframe && this.iframe.contentWindow) {
                    this.iframe.contentWindow.postMessage({ id, type, payload }, targetOrigin);
                } else {
                    if (timeoutId) clearTimeout(timeoutId);
                    this.pendingRequests.delete(id);
                    reject(new Error("AI Worker iframe not ready"));
                }
            });
        }

        async ensureModelLoaded(forceReload = false, isSilentPrewarm = false) {
            if (this.isModelLoaded && !forceReload) return;
            if (this.isModelLoading && !forceReload) return;

            this.isModelLoading = true;
            if (!isSilentPrewarm) {
                this.banner.style.display = "block";
                this.fabBadge.style.display = "inline-block";
                this.statusBtn.textContent = "Caching...";
            }

            const modelId = localStorage.getItem("abhihub_ai_model") || "Qwen2.5-0.5B-Instruct-q4f16_1-MLC";
            const baseUrl = `https://huggingface.co/mlc-ai/${modelId}/resolve/main`;

            // 1. Trigger background download in Service Worker so tab switch / page navigation never resets it
            if (navigator.serviceWorker && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({
                    type: "START_AI_MODEL_PRECACHE",
                    payload: { modelId, baseUrl }
                });
            }

            try {
                // 2. Initialize WebLLM engine (timeout 0 to allow tab switching without abort)
                await this.rpcCall("INIT_MODEL", { modelId }, (chunk) => {
                    const report = chunk.report;
                    if (report) {
                        if (report.text && !isSilentPrewarm) this.bannerText.textContent = report.text;
                        if (typeof report.progress === "number") {
                            const pct = Math.round(report.progress * 100);
                            this.currentProgress = pct;
                            if (!isSilentPrewarm) {
                                this.bannerPct.textContent = `${pct}%`;
                                this.fabBadge.textContent = `${pct}%`;
                                this.miniBar.style.width = `${pct}%`;
                            }
                        }
                        // Fast-cache banner feedback
                        if (report.fromCache && !isSilentPrewarm) {
                            this.bannerText.textContent = "⚡ Loading from cache (instant)...";
                        }
                    }
                }, 0);

                this.isModelLoaded = true;
                this.isModelLoading = false;
                localStorage.setItem("abhihub_ai_model_cached", "true");
                this.banner.style.display = "none";
                this.fabBadge.style.display = "none";
                this.statusBtn.textContent = "Online";
                this.statusBtn.classList.add("ready");

                if (this.queuedMessage) {
                    const q = this.queuedMessage;
                    this.queuedMessage = null;
                    await this.processMessage(q.text, q.botBubble);
                }
            } catch (err) {
                this.isModelLoading = false;
                this.fabBadge.style.display = "none";
                if (!document.hidden) {
                    this.banner.style.display = "block";
                    this.bannerPct.textContent = "";
                    this.miniBar.style.width = "0%";
                    const msg = String(err.message || err || "");
                    if (msg.includes("NS_BINDING_FAILED") || msg.includes("0x804b0001")) {
                        this.bannerText.innerHTML = `🦊 <strong>Firefox WebGPU Setup:</strong> Visit <code>about:config</code>, search <code>dom.webgpu.enabled</code> and toggle to <strong>true</strong>, or open in Chrome/Edge.`;
                        this.statusBtn.textContent = "Config Needed";
                    } else if (msg.includes("WebGPU")) {
                        this.bannerText.innerHTML = `⚠️ <strong>GPU Acceleration Disabled:</strong> Turn on <em>"Use graphics acceleration"</em> in browser settings (<code>chrome://settings/system</code>).`;
                        this.statusBtn.textContent = "GPU Off";
                    } else {
                        this.bannerText.textContent = `Notice: ${msg}`;
                        this.statusBtn.textContent = "Ready";
                    }
                }
            }
        }

        bindEvents() {
            this.fabBtn.addEventListener("click", () => this.toggleDrawer());
            this.closeBtn.addEventListener("click", () => this.toggleDrawer(false));

            window.addEventListener("keydown", (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
                    e.preventDefault();
                    this.toggleDrawer();
                }
            });

            // Stop / Interrupt Button Handler
            this.stopBtn.addEventListener("click", () => {
                if (this.isGenerating) {
                    this.rpcCall("INTERRUPT").catch(() => {});
                    this.setGeneratingState(false);
                }
            });

            document.addEventListener("click", (e) => {
                const chip = e.target.closest(".ai-action-chip");
                if (chip) {
                    const action = chip.getAttribute("data-action");
                    this.handleQuickAction(action);
                    return;
                }

                const copyBtn = e.target.closest(".ai-copy-btn");
                if (copyBtn) {
                    const block = copyBtn.closest(".ai-code-block");
                    const code = block?.querySelector("code")?.innerText || "";
                    if (code) {
                        navigator.clipboard.writeText(code).then(() => {
                            copyBtn.textContent = "Copied! ✓";
                            setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
                        });
                    }
                }
            });

            this.chatForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const text = this.chatInput.value.trim();
                if (!text) return;
                this.sendMessage(text);
                this.chatInput.value = "";
            });

            window.addEventListener("abhihub_ai_config_change", async (e) => {
                const newModelId = e.detail?.modelId;
                if (newModelId) {
                    localStorage.setItem("abhihub_ai_model", newModelId);
                    this.isModelLoaded = false;
                    await this.ensureModelLoaded(true);
                }
            });
        }

        bindViewportEvents() {
            if (window.visualViewport) {
                window.visualViewport.addEventListener("resize", () => {
                    if (this.isOpen && window.innerWidth <= 768) {
                        this.drawer.style.height = `${window.visualViewport.height * 0.75}px`;
                    }
                });
            }
        }

        toggleDrawer(forceState) {
            this.isOpen = typeof forceState === "boolean" ? forceState : !this.isOpen;
            if (this.isOpen) {
                this.drawer.classList.add("active");
                this.drawer.setAttribute("aria-hidden", "false");
                this.chatInput.focus();
                this.ensureModelLoaded().catch(() => {});
            } else {
                this.drawer.classList.remove("active");
                this.drawer.setAttribute("aria-hidden", "true");
            }
        }

        setGeneratingState(generating) {
            this.isGenerating = generating;
            if (generating) {
                this.sendBtn.style.display = "none";
                this.stopBtn.style.display = "flex";
            } else {
                this.sendBtn.style.display = "flex";
                this.stopBtn.style.display = "none";
                this.sendBtn.disabled = false;
            }
        }

        handleQuickAction(action) {
            const ctx = this.getPageContext();
            let prompt = "";

            if (action === "explain_page") {
                prompt = `Explain the key concepts on this page (${ctx.title || ctx.heading || ctx.path}) and summarize what students must prepare for exams.`;
            } else if (action === "get_file_links") {
                prompt = `List all study documents and PDF download links available on this page with direct clickable links.`;
            } else if (action === "summarize_pdf") {
                prompt = `Summarize the active document and provide key takeaways, definitions, and important exam questions.`;
            } else if (action === "pyq_help") {
                prompt = `What are the most repeated PYQ patterns, scoring topics, and exam tips for ${ctx.title || "this course"}?`;
            }

            if (prompt) {
                this.sendMessage(prompt);
            }
        }

        async sendMessage(text) {
            this.appendMessage("user", text);
            this.messages.push({ role: "user", content: text });

            if (!this.isModelLoaded) {
                const botBubble = this.appendMessage("bot", `⏳ Model is downloading in the background (${this.currentProgress}%). You can keep browsing; your answer will stream automatically when ready!`);
                this.queuedMessage = { text, botBubble };
                this.ensureModelLoaded().catch(() => {});
                return;
            }

            const botBubble = this.appendMessage("bot", "Thinking...");
            await this.processMessage(text, botBubble);
        }

        async processMessage(text, botBubble) {
            this.setGeneratingState(true);
            try {
                const ctx     = this.getPageContext();
                const profile = this.getUserProfile();

                // Build unified system prompt via webllm-core export
                const systemPrompt = buildAbhiHubSystemPrompt(profile, {
                    title:       ctx.title,
                    url:         ctx.url,
                    heading:     ctx.heading,
                    fileLinks:   ctx.fileLinks,
                    pageImages:  ctx.pageImages,
                    pdfText:     ctx.pdfText,
                    selectedText: ctx.selectedText
                });

                let fullResponse = "";
                let responseCards = [];

                const isActionIntent = /\b(find|search|show|get|open|pyq|notes|question paper|syllabus|study material|exam|bookmark|save)\b/i.test(text);

                // ── Server-side / Native Tool route for search & actions ─────────────
                if (isActionIntent || (this.activeProvider === "server")) {
                    try {
                        const srvResp = await fetch('/api/ai/assistant', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                message: text,
                                doc_id: ctx.docId || null,
                                doc_title: ctx.title || null
                            })
                        });
                        const srvData = await srvResp.json();
                        if (srvData.success) {
                            fullResponse = srvData.reply || "Here is what I found:";
                            responseCards = srvData.cards || [];
                            botBubble.innerHTML = `<p>${formatMarkdown(fullResponse)}</p>`;
                            if (responseCards.length > 0) {
                                this.appendMessage("bot", "", responseCards);
                            }
                            this.messages.push({ role: "assistant", content: fullResponse });
                            return;
                        }
                    } catch (srvErr) {
                        console.warn("[AbhiHub AI] Server assistant fallback:", srvErr);
                    }
                }

                // ── External provider route ──────────────────────────────────────
                if (this.activeProvider && this.activeProvider !== "webllm") {
                    const apiKey = getKey(this.activeProvider);
                    const model  = getModel(this.activeProvider);
                    if (!apiKey) throw new Error(`No API key for ${PROVIDERS[this.activeProvider]?.name || this.activeProvider}. Tap "🔑 Add Key" below.`);

                    const allMessages = [
                        { role: "system", content: systemPrompt },
                        ...this.messages
                    ];

                    fullResponse = await streamExternalResponse(
                        this.activeProvider, apiKey, model, allMessages,
                        (delta, currentFull) => {
                            if (this.isGenerating) {
                                fullResponse = currentFull;
                                botBubble.innerHTML = `<p>${formatMarkdown(currentFull)}</p>`;
                                this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
                            }
                        }
                    );

                } else {
                    // ── On-device WebLLM route ────────────────────────────────────
                    await this.rpcCall("GENERATE_STREAM", {
                        messages: this.messages,
                        options:  { systemPrompt }
                    }, (chunk) => {
                        if (chunk.currentFull && this.isGenerating) {
                            fullResponse = chunk.currentFull;
                            botBubble.innerHTML = `<p>${formatMarkdown(fullResponse)}</p>`;
                            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
                        }
                    });
                }

                this.messages.push({ role: "assistant", content: fullResponse });
            } catch (err) {
                botBubble.innerHTML = `<p>⚠️ ${err.message || "Failed to generate response."}</p>`;
            } finally {
                this.setGeneratingState(false);
            }
        }

        appendMessage(role, text, cards = []) {
            const msgDiv = document.createElement("div");
            msgDiv.className = `ai-msg ${role}`;
            
            const contentDiv = document.createElement("div");
            contentDiv.className = "ai-msg-content";
            contentDiv.innerHTML = `<p>${formatMarkdown(text)}</p>`;

            if (cards && cards.length > 0) {
                const cardsContainer = document.createElement("div");
                cardsContainer.className = "ai-cards-container";
                
                cards.forEach(card => {
                    if (card.type === "resource_cards" && Array.isArray(card.items)) {
                        card.items.forEach(item => {
                            const cardEl = document.createElement("div");
                            cardEl.className = "ai-resource-card";
                            const badgeClass = (item.document_type || "").toLowerCase() === "pyq" ? "ai-badge-pyq" : "ai-badge-notes";
                            cardEl.innerHTML = `
                                <div class="ai-card-header">
                                    <span class="ai-badge ${badgeClass}">${item.document_type || "DOCUMENT"}</span>
                                </div>
                                <a href="${item.url || '#'}" class="ai-card-title">${item.title || "Academic Resource"}</a>
                                <div class="ai-card-actions">
                                    <a href="${item.url || '#'}" class="ai-card-btn primary">Open ↗</a>
                                    <button type="button" class="ai-card-btn ai-bookmark-btn" data-doc-id="${item.id}">⭐ Save</button>
                                </div>
                            `;
                            cardsContainer.appendChild(cardEl);
                        });
                    } else if (card.type === "action_confirmation") {
                        const confEl = document.createElement("div");
                        confEl.className = "ai-confirmation-card";
                        confEl.innerHTML = `<span>✓</span> <span>${card.message || "Action completed."}</span>`;
                        cardsContainer.appendChild(confEl);
                    }
                });
                contentDiv.appendChild(cardsContainer);
            }

            msgDiv.appendChild(contentDiv);
            this.messagesContainer.appendChild(msgDiv);
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

            // Bind bookmark action buttons
            contentDiv.querySelectorAll(".ai-bookmark-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const docId = btn.getAttribute("data-doc-id");
                    if (!docId) return;
                    btn.disabled = true;
                    btn.textContent = "Saving...";
                    try {
                        const resp = await fetch("/api/ai/tool", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                tool_name: "bookmark_resource",
                                arguments: { resource_id: docId }
                            })
                        });
                        const res = await resp.json();
                        if (res.success) {
                            btn.textContent = "Saved ✓";
                            btn.style.color = "#16a34a";
                        } else {
                            btn.textContent = "Failed";
                            btn.disabled = false;
                        }
                    } catch (e) {
                        btn.textContent = "Failed";
                        btn.disabled = false;
                    }
                });
            });

            return contentDiv;
        }

        /** Render provider pill row in widget footer */
        renderProviderPills() {
            if (!this.providerRow) return;
            this.providerRow.innerHTML = "";

            // On-device pill
            const onDevicePill = document.createElement("button");
            onDevicePill.className = `ai-provider-pill${this.activeProvider === "webllm" ? " active" : ""}`;
            onDevicePill.dataset.provider = "webllm";
            onDevicePill.innerHTML = `🧠 On-Device`;
            onDevicePill.title = "Use WebGPU on-device AI (private, no API key needed)";
            this.providerRow.appendChild(onDevicePill);

            // External provider pills (only if key is saved)
            for (const [id, p] of Object.entries(PROVIDERS)) {
                if (!hasKey(id)) continue;
                const pill = document.createElement("button");
                pill.className = `ai-provider-pill${this.activeProvider === id ? " active" : ""}`;
                pill.dataset.provider = id;
                pill.innerHTML = `${p.icon} ${p.name}`;
                pill.title = `Use ${p.name} (${p.badge})`;
                this.providerRow.appendChild(pill);
            }

            // Add key pill
            const addPill = document.createElement("button");
            addPill.className = "ai-provider-pill add-key-pill";
            addPill.innerHTML = `🔑 Add Key`;
            addPill.title = "Add an external AI API key";
            addPill.addEventListener("click", () => {
                window.open("/ai?tab=external", "_blank");
            });
            this.providerRow.appendChild(addPill);

            // Bind pill clicks
            this.providerRow.querySelectorAll(".ai-provider-pill[data-provider]").forEach(pill => {
                pill.addEventListener("click", () => {
                    this.activeProvider = pill.dataset.provider;
                    saveActiveProvider(this.activeProvider);
                    this.renderProviderPills();
                    const providerLabel = this.activeProvider === "webllm"
                        ? "On-Device AI"
                        : PROVIDERS[this.activeProvider]?.name || this.activeProvider;
                    this.statusBtn.textContent = `✓ ${providerLabel}`;
                });
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => new AbhiHubAIAssistant());
    } else {
        new AbhiHubAIAssistant();
    }
})();

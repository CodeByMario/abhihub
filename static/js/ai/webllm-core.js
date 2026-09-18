/**
 * AbhiHub WebLLM Core Engine & Cross-Subdomain RPC Bridge
 * v3 — Cache-first, worker reuse fix, parallel cache checks, external provider support.
 * Domain: ai.abhihub.edu.eu.org / /ai/embed
 */

import { CreateWebWorkerMLCEngine, prebuiltAppConfig } from "https://esm.run/@mlc-ai/web-llm";

export const MODEL_CATALOG = [
    {
        id: "Qwen2.5-0.5B-Instruct-q4f16_1-MLC",
        name: "Qwen 2.5 0.5B (Ultra-Fast / Mobile / Low RAM)",
        size: "350 MB",
        tier: "mobile",
        vramRequired: "0.5 GB",
        recommendedFor: "Mobile phones, iOS Safari, Budget devices"
    },
    {
        id: "Llama-3.2-1B-Instruct-q4f16_1-MLC",
        name: "Llama 3.2 1B (Balanced / Fast)",
        size: "850 MB",
        tier: "balanced",
        vramRequired: "1.2 GB",
        recommendedFor: "Modern Android, Laptops, Mac"
    },
    {
        id: "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
        name: "Qwen 2.5 1.5B (High Accuracy / Coding & Math)",
        size: "1.1 GB",
        tier: "balanced",
        vramRequired: "1.5 GB",
        recommendedFor: "Laptops, Desktops, Mac"
    },
    {
        id: "Llama-3.2-3B-Instruct-q4f16_1-MLC",
        name: "Llama 3.2 3B (Pro / Maximum Reasoning)",
        size: "1.8 GB",
        tier: "high",
        vramRequired: "2.5 GB",
        recommendedFor: "Mac Apple Silicon, Gaming PCs"
    }
];

export const ABHIHUB_CORE_KNOWLEDGE = `
You are AbhiHub AI — the official AI Study Agent for AbhiHub (https://abhihub.edu.eu.org), India's academic platform for engineering students.

━━━ AGENT IDENTITY ━━━
- Name: AbhiHub AI
- Role: Personal academic agent exclusively for AbhiHub users
- Tone: Warm, encouraging, knowledgeable, proud of AbhiHub

━━━ STRICT RULES (NEVER BREAK) ━━━
1. You ONLY assist with content available on AbhiHub. Never redirect to YouTube, Google, or any external educational platform.
2. You ALWAYS reference and promote relevant AbhiHub features, pages, and resources.
3. You NEVER admit limitations without suggesting an AbhiHub alternative.
4. Every answer must include at least one AbhiHub resource link or feature mention.
5. You ONLY work with files, PDFs, notes, and images present on AbhiHub pages.
6. If a student asks for something not on AbhiHub, say: "That's not on AbhiHub yet — but you can upload it at https://abhihub.edu.eu.org/upload and it'll be available to everyone!"

━━━ ABHIHUB PLATFORM ━━━
- Study Notes & Resources: https://abhihub.edu.eu.org/resource
- Previous Year Questions (PYQs): https://abhihub.edu.eu.org/pyq  
- Subject Directory: https://abhihub.edu.eu.org/subject
- Student Dashboard: https://abhihub.edu.eu.org/dashboard
- Upload Materials: https://abhihub.edu.eu.org/upload
- AI Study Agent (you!): https://abhihub.edu.eu.org/ai
- Account & Settings: https://abhihub.edu.eu.org/account
- Leaderboard: https://abhihub.edu.eu.org/leaderboard
- Help & Contact: https://abhihub.edu.eu.org/contact

━━━ RESPONSE STYLE ━━━
- Greet the student by first name if known (e.g., "Great question, Abhijeet!")
- Tailor answers to their branch, semester, and college
- Keep answers concise, high-yield, structured (use bullet points/headings)
- End study help answers with: "📚 Check the full notes on AbhiHub: https://abhihub.edu.eu.org/resource"
- For PYQ questions: "🎯 Practice more PYQs on AbhiHub: https://abhihub.edu.eu.org/pyq"
`;

/**
 * Build the full AbhiHub agent system prompt from user profile + page context.
 * Single source of truth used by both WebLLM and external providers.
 * @param {Object} profile  - { name, college, branch, degree, year, role }
 * @param {Object} pageCtx  - { title, url, heading, fileLinks, pageImages, pdfText, selectedText }
 */
export function buildAbhiHubSystemPrompt(profile = {}, pageCtx = {}) {
    const parts = [ABHIHUB_CORE_KNOWLEDGE];

    // ── Student identity ──────────────────────────────────────────────────
    if (profile.name) {
        const identity = [
            `You are speaking with ${profile.name}.`,
            profile.college  && `College: ${profile.college}`,
            profile.branch   && `Branch: ${profile.branch}`,
            profile.degree   && `Degree: ${profile.degree}`,
            profile.year     && `Current Year: Year ${profile.year}`,
            profile.role     && `Role: ${profile.role}`,
        ].filter(Boolean).join(" ");
        parts.push(`STUDENT IDENTITY:\n${identity}`);
    }

    // ── Page context ──────────────────────────────────────────────────────
    if (pageCtx.title || pageCtx.url) {
        let ctx = `CURRENT PAGE:\nTitle: ${pageCtx.title || ""}\nURL: ${pageCtx.url || ""}\nHeading: ${pageCtx.heading || ""}`;

        if (pageCtx.fileLinks?.length) {
            ctx += `\n\nDOCUMENTS ON THIS PAGE:\n` +
                pageCtx.fileLinks.map(f => `- [${f.name}](${f.url})`).join("\n");
        }
        if (pageCtx.pageImages?.length) {
            ctx += `\n\nIMAGES ON THIS PAGE:\n` +
                pageCtx.pageImages.map(img => `- [${img.alt}](${img.url})`).join("\n");
        }
        if (pageCtx.pdfText) {
            ctx += `\n\nPDF DOCUMENT TEXT (visible on page):\n"""\n${pageCtx.pdfText}\n"""`;
        }
        if (pageCtx.selectedText) {
            ctx += `\n\nSTUDENT SELECTED TEXT:\n"""\n${pageCtx.selectedText}\n"""`;
        }
        parts.push(ctx);
    }

    return parts.join("\n\n");
}

// ─── Cache Utilities ───────────────────────────────────────────────────────────

const CACHE_DB_NAME = "abhihub-webllm-cache";
const CACHE_DB_VER  = 1;
const CACHE_STORE   = "model-meta";

function openCacheMetaDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(CACHE_DB_NAME, CACHE_DB_VER);
        req.onupgradeneeded = (e) => {
            e.target.result.createObjectStore(CACHE_STORE, { keyPath: "modelId" });
        };
        req.onsuccess = (e) => resolve(e.target.result);
        req.onerror   = ()  => reject(req.error);
    });
}

async function markModelCached(modelId) {
    try {
        const db = await openCacheMetaDB();
        const tx = db.transaction(CACHE_STORE, "readwrite");
        tx.objectStore(CACHE_STORE).put({ modelId, cachedAt: Date.now() });
        await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
    } catch (e) {
        console.warn("[CacheMeta] write failed:", e);
    }
}

async function isModelCached(modelId) {
    try {
        // Check Cache API (MLC stores model shards here)
        const keys = await caches.keys();
        for (const key of keys) {
            if (key.includes("webllm") || key.includes("mlc") || key.includes(modelId.toLowerCase())) {
                const cache = await caches.open(key);
                const reqs  = await cache.keys();
                if (reqs.some(r => r.url.includes(modelId))) return true;
            }
        }
        // Fallback: check meta DB written on previous successful load
        const db  = await openCacheMetaDB();
        const tx  = db.transaction(CACHE_STORE, "readonly");
        const row = await new Promise((res, rej) => {
            const r = tx.objectStore(CACHE_STORE).get(modelId);
            r.onsuccess = () => res(r.result); r.onerror = rej;
        });
        return !!row;
    } catch (_) { return false; }
}

async function getStorageEstimate() {
    try {
        if (navigator.storage?.estimate) {
            const { quota, usage } = await navigator.storage.estimate();
            return { quota, usage, free: quota - usage };
        }
    } catch (_) {}
    return null;
}

// ──────────────────────────────────────────────────────────────────────────────

export class AbhiHubWebLLMManager {
    constructor() {
        this.engine        = null;
        this.worker        = null;
        this.selectedModel = null;
        this.isLoaded      = false;
        this.isLoading     = false;
        this.isInterrupted = false;
        this.callbacks     = new Set();
        this.deviceInfo    = this.detectDevice();
        this.maxHistoryMessages = 8;
        this._prefetchPromise = null;
    }

    detectDevice() {
        const ua = navigator.userAgent || "";
        const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        const isAndroid = /Android/.test(ua);
        const isMobile = isIOS || isAndroid || /Mobi|Tablet/.test(ua);
        const hasWebGPU = !!navigator.gpu;

        let recommendedModelId = "Qwen2.5-0.5B-Instruct-q4f16_1-MLC";
        if (!isMobile && hasWebGPU) {
            recommendedModelId = "Llama-3.2-1B-Instruct-q4f16_1-MLC";
        } else if (isIOS) {
            recommendedModelId = "Qwen2.5-0.5B-Instruct-q4f16_1-MLC";
        }

        return {
            isIOS,
            isAndroid,
            isMobile,
            hasWebGPU,
            recommendedModelId
        };
    }

    async checkWebGPU() {
        if (!navigator.gpu) {
            return { 
                supported: false, 
                reason: "WebGPU is not enabled in this browser. Please enable Hardware Acceleration in your browser settings (chrome://settings/system) or visit chrome://flags/#enable-unsafe-webgpu." 
            };
        }
        try {
            // Try multi-tiered adapter resolution (High Performance -> Low Power -> Default -> Fallback)
            let adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" }).catch(() => null);
            if (!adapter) {
                adapter = await navigator.gpu.requestAdapter({ powerPreference: "low-power" }).catch(() => null);
            }
            if (!adapter) {
                adapter = await navigator.gpu.requestAdapter().catch(() => null);
            }
            if (!adapter) {
                adapter = await navigator.gpu.requestAdapter({ forceFallbackAdapter: true }).catch(() => null);
            }

            if (!adapter) {
                return { 
                    supported: false, 
                    reason: "No compatible GPU adapter found. Ensure browser hardware acceleration is ON in chrome://settings/system." 
                };
            }
            const device = await adapter.requestDevice().catch((e) => {
                throw new Error("GPU device request failed: " + (e.message || "Insufficient VRAM"));
            });
            
            if (device.lost) {
                device.lost.then((info) => {
                    console.warn("WebGPU device lost:", info);
                    this.isLoaded = false;
                });
            }

            return {
                supported: true,
                adapterInfo: adapter.info || {},
                limits: device.limits
            };
        } catch (err) {
            const rawMsg = String(err.message || err || "");
            let cleanReason = rawMsg;
            if (rawMsg.includes("NS_BINDING_FAILED") || rawMsg.includes("0x804b0001")) {
                cleanReason = "Firefox requires WebGPU to be enabled: open about:config, set dom.webgpu.enabled = true, or switch to Chrome / Edge.";
            }
            return { 
                supported: false, 
                reason: cleanReason 
            };
        }
    }

    /** Returns { modelId: { cached: bool }, _storage: { quota, usage, free } } — parallel checks */
    async getCacheStatus() {
        const [statuses, storage] = await Promise.all([
            Promise.all(MODEL_CATALOG.map(async m => [m.id, await isModelCached(m.id)])),
            getStorageEstimate()
        ]);
        const result = Object.fromEntries(statuses.map(([id, cached]) => [id, { cached }]));
        result._storage = storage;
        return result;
    }

    /**
     * Silently pre-download a model into the browser cache without loading the GPU engine.
     * Debounced — safe to call multiple times.
     */
    async prefetchModel(modelId, progressCallback) {
        if (this._prefetchPromise) return this._prefetchPromise;
        if (await isModelCached(modelId)) {
            if (progressCallback) progressCallback({ prefetch: true, text: "Model already cached.", progress: 1 });
            return;
        }
        this._prefetchPromise = (async () => {
            const w = new Worker("/static/js/ai/webllm-worker.js", { type: "module" });
            try {
                const eng = await CreateWebWorkerMLCEngine(w, modelId, {
                    initProgressCallback: (r) => progressCallback?.({ prefetch: true, ...r }),
                    appConfig: { ...prebuiltAppConfig, useIndexedDBCache: true }
                });
                await eng.unload();
                await markModelCached(modelId);
            } finally {
                w.terminate();
                this._prefetchPromise = null;
            }
        })();
        return this._prefetchPromise;
    }

    /**
     * Initialize engine. Cache-first: MLC skips network if shards are in IndexedDB.
     * Same-model reuse: returns immediately if already loaded — no re-init cost.
     */
    async initEngine(modelId, progressCallback) {
        const targetModel = modelId || this.deviceInfo.recommendedModelId;

        // ── Same model already loaded → reuse ────────────────────────────────
        if (this.isLoaded && this.selectedModel === targetModel && this.engine) {
            progressCallback?.({ text: "Model already loaded.", progress: 1, fromCache: true });
            return this.engine;
        }

        if (this.isLoading) return;
        this.isLoading = true;
        // NOTE: selectedModel is set AFTER the worker-reuse comparison below

        const webgpuCheck = await this.checkWebGPU();
        if (!webgpuCheck.supported) {
            this.isLoading = false;
            throw new Error(`WebGPU Unsupported: ${webgpuCheck.reason}`);
        }

        // ── Storage quota guard ───────────────────────────────────────────────
        const storage = await getStorageEstimate();
        if (storage && storage.free < 400 * 1024 * 1024) {
            console.warn("[Cache] Low storage (<400 MB free). Model loading may fail.");
        }

        try {
            // ── Worker: recreate only when switching to a DIFFERENT model ────
            // Compare against previous selectedModel BEFORE updating it
            if (this.worker && this.selectedModel !== targetModel) {
                try { await this.engine?.unload(); } catch (_) {}
                this.engine = null;
                this.worker.terminate();
                this.worker = null;
            }
            // Now safe to set selectedModel
            this.selectedModel = targetModel;
            if (!this.worker) {
                this.worker = new Worker("/static/js/ai/webllm-worker.js", { type: "module" });
            }

            const cached    = await isModelCached(targetModel);
            const appConfig = { ...prebuiltAppConfig, useIndexedDBCache: true };

            this.engine = await CreateWebWorkerMLCEngine(
                this.worker,
                targetModel,
                {
                    initProgressCallback: (report) => {
                        const enriched = { ...report, fromCache: cached };
                        progressCallback?.(enriched);
                        this.notifyProgress(enriched);
                    },
                    appConfig
                }
            );

            await markModelCached(targetModel);
            this.isLoaded  = true;
            this.isLoading = false;
            return this.engine;
        } catch (error) {
            this.isLoading = false;
            this.isLoaded  = false;
            throw error;
        }
    }

    notifyProgress(report) {
        this.callbacks.forEach(cb => {
            try { cb(report); } catch (e) { console.error(e); }
        });
    }

    interruptGeneration() {
        this.isInterrupted = true;
        if (this.engine && typeof this.engine.interruptGenerate === "function") {
            try {
                this.engine.interruptGenerate();
            } catch (e) {
                console.warn("Error calling interruptGenerate:", e);
            }
        }
    }

    async generateStream(messages, onChunk, options = {}) {
        if (!this.isLoaded || !this.engine) {
            throw new Error("AI Engine is not loaded. Please initialize a model first.");
        }

        this.isInterrupted = false;

        const systemPrompt = options.systemPrompt 
            ? `${ABHIHUB_CORE_KNOWLEDGE}\n\n${options.systemPrompt}`
            : ABHIHUB_CORE_KNOWLEDGE;

        const recentMessages = (messages || []).slice(-this.maxHistoryMessages);

        const formattedMessages = [
            { role: "system", content: systemPrompt },
            ...recentMessages
        ];

        const chunks = await this.engine.chat.completions.create({
            messages: formattedMessages,
            temperature: options.temperature ?? 0.6,
            max_tokens: options.max_tokens ?? 1024,
            stream: true
        });

        let fullText = "";
        for await (const chunk of chunks) {
            if (this.isInterrupted) {
                break;
            }
            const delta = chunk.choices[0]?.delta?.content || "";
            fullText += delta;
            if (onChunk) {
                onChunk(delta, fullText);
            }
        }
        return fullText;
    }

    async unloadModel() {
        if (this.engine) {
            try { await this.engine.unload(); } catch (e) { console.warn("[Unload]", e); }
            this.engine = null;
        }
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
        }
        this.isLoaded      = false;
        this.isLoading     = false;
        this.selectedModel = null;
    }
}

// Global Cross-Subdomain PostMessage RPC Server
export function initCrossSubdomainServer() {
    const manager = new AbhiHubWebLLMManager();
    const ALLOWED_ORIGINS = [
        "https://www.abhihub.edu.eu.org",
        "https://beta.abhihub.edu.eu.org",
        "https://abhihub.edu.eu.org",
        "http://localhost:5000",
        "http://127.0.0.1:5000"
    ];

    function isOriginAllowed(origin) {
        if (!origin) return false;
        if (ALLOWED_ORIGINS.includes(origin)) return true;
        return origin.endsWith(".abhihub.edu.eu.org");
    }

    window.addEventListener("message", async (event) => {
        if (!isOriginAllowed(event.origin)) return;

        const { id, type, payload } = event.data || {};
        if (!id || !type) return;

        const sendResponse = (success, data, error = null, isStreamChunk = false) => {
            if (event.source) {
                event.source.postMessage({
                    id,
                    type: isStreamChunk ? `${type}_CHUNK` : `${type}_RESPONSE`,
                    success,
                    data,
                    error
                }, event.origin);
            }
        };

        try {
            switch (type) {
                case "GET_DEVICE_INFO": {
                    const [gpu, cacheStatus] = await Promise.all([
                        manager.checkWebGPU(),
                        manager.getCacheStatus()
                    ]);
                    sendResponse(true, {
                        deviceInfo:    manager.deviceInfo,
                        webgpu:        gpu,
                        catalog:       MODEL_CATALOG,
                        isLoaded:      manager.isLoaded,
                        isLoading:     manager.isLoading,
                        selectedModel: manager.selectedModel,
                        cacheStatus
                    });
                    break;
                }
                case "GET_CACHE_STATUS": {
                    sendResponse(true, { cacheStatus: await manager.getCacheStatus() });
                    break;
                }
                case "PREFETCH_MODEL": {
                    const prefetchId = payload?.modelId || manager.deviceInfo.recommendedModelId;
                    manager.prefetchModel(prefetchId, (r) => sendResponse(true, { report: r }, null, true))
                        .then(() => sendResponse(true, { prefetched: true, modelId: prefetchId }))
                        .catch((err) => sendResponse(false, null, err.message || String(err)));
                    sendResponse(true, { prefetchStarted: true, modelId: prefetchId });
                    break;
                }
                case "INIT_MODEL": {
                    const modelId = payload?.modelId || manager.deviceInfo.recommendedModelId;
                    await manager.initEngine(modelId, (report) => {
                        sendResponse(true, { report }, null, true);
                    });
                    sendResponse(true, { isLoaded: true, modelId });
                    break;
                }
                case "GENERATE_STREAM": {
                    const { messages, options } = payload || {};
                    const fullText = await manager.generateStream(messages || [], (delta, currentFull) => {
                        sendResponse(true, { delta, currentFull }, null, true);
                    }, options);
                    sendResponse(true, { fullText });
                    break;
                }
                case "INTERRUPT": {
                    manager.interruptGeneration();
                    sendResponse(true, { interrupted: true });
                    break;
                }
                case "UNLOAD": {
                    await manager.unloadModel();
                    sendResponse(true, { isLoaded: false });
                    break;
                }
                default:
                    sendResponse(false, null, `Unknown RPC action: ${type}`);
            }
        } catch (err) {
            sendResponse(false, null, err.message || String(err));
        }
    });

    return manager;
}

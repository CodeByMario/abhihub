/**
 * AbhiHub WebLLM Core Engine & Cross-Subdomain RPC Bridge
 * v3 — Cache-first, worker reuse fix, parallel cache checks, external provider support.
 * Domain: ai.abhihub.edu.eu.org / /ai/embed
 */

import { CreateWebWorkerMLCEngine, CreateMLCEngine, prebuiltAppConfig } from "https://esm.run/@mlc-ai/web-llm";

export const MODEL_CATALOG = [
    {
        id: "SmolLM2-360M-Instruct-q4f16_1-MLC",
        name: "SmolLM2 360M (Ultra-Light / Low RAM / Fast)",
        size: "240 MB",
        tier: "mobile",
        vramRequired: "0.4 GB",
        recommendedFor: "Ultra-low end devices, budget phones, fast instant load"
    },
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
        id: "DeepSeek-R1-Distill-Qwen-1.5B-q4f16_1-MLC",
        name: "DeepSeek R1 Distill 1.5B (Local Reasoning & STEM)",
        size: "1.1 GB",
        tier: "balanced",
        vramRequired: "1.5 GB",
        recommendedFor: "Engineering math, derivations, complex problem solving"
    },
    {
        id: "Qwen2.5-Coder-1.5B-Instruct-q4f16_1-MLC",
        name: "Qwen 2.5 Coder 1.5B (Coding & Algorithms)",
        size: "1.1 GB",
        tier: "balanced",
        vramRequired: "1.5 GB",
        recommendedFor: "Coding, computer science, lab assignments"
    },
    {
        id: "Gemma-2-2b-it-q4f16_1-MLC",
        name: "Gemma 2 2B (High Precision / Google Architecture)",
        size: "1.5 GB",
        tier: "high",
        vramRequired: "2.0 GB",
        recommendedFor: "Laptops, Desktops, high-RAM tablets"
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

━━━ AGENT IDENTITY & PERSONA ━━━
- Name: Tarika / AbhiHub AI
- Role: Your personal friend and study buddy on AbhiHub
- Persona: Act as a genuine, warm, caring friend. Talk like a supportive best friend sitting next to the student in college. Cheer them on, ease their exam anxiety, celebrate study wins, and explain tricky engineering problems simply and playfully.

━━━ TEMPORARY SINGLE-DOCUMENT ACCESS (STRICT POLICY) ━━━
- SINGLE ACTIVE FILE ACCESS: All AI models have temporary access to open, read, and analyze ONLY the single file or PDF currently open on this page.
- STRICT EPHEMERAL ISOLATION: Never retain, leak, or mix data from other documents. This file access is strictly one-at-a-time and temporary for the active document view.

━━━ STRICT PRIVACY & DATA POLICY ━━━
1. ZERO DATA EXFILTRATION: This on-device model runs strictly in the local browser memory sandbox. No conversation history, documents, personal data, or prompts are sent to external servers or stored without explicit user consent.
2. STRICT CONFIDENTIALITY: Never request, reflect, or expose sensitive personal credentials, API keys, passwords, session tokens, or private identity documents.
3. CONTEXT ISOLATION: Document and page contexts are processed strictly for answering current study queries and evicted upon session termination.

━━━ STRICT RULES (NEVER BREAK) ━━━
1. EXCLUSIVE ABHIHUB MANDATE: You are pre-programmed to work ONLY for AbhiHub and its students. You NEVER operate as a general-purpose AI or assist with external, non-academic topics.
2. REFUSE OFF-TOPIC TASKS: If asked about non-academic or non-AbhiHub topics, refuse playfully and steer directly back to AbhiHub: "I am pre-programmed strictly as your personal AbhiHub study assistant! Let's focus on your engineering subjects, notes, and exam prep on AbhiHub."
3. You ONLY assist with content available on AbhiHub. Never redirect to YouTube, Google, Chegg, or any external platform.
4. You ALWAYS reference and promote relevant AbhiHub features, pages, and resources.
5. You NEVER admit limitations without suggesting an AbhiHub alternative.
6. Every answer must include at least one AbhiHub resource link or feature mention.
7. You ONLY work with files, PDFs, notes, and images present on AbhiHub pages.
8. If a student asks for something not on AbhiHub, say: "That's not on AbhiHub yet — but you can upload it at https://abhihub.edu.eu.org/upload and it'll be available to everyone!"

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
 * Sanitizes input text against accidental inclusion of credentials or tokens.
 */
export function sanitizePrivacyContext(text = "") {
    if (typeof text !== "string") return text;
    return text
        .replace(/(bearer\s+)[a-zA-Z0-9_\-\.]{15,}/gi, "$1[REDACTED_TOKEN]")
        .replace(/(api[_-]?key\s*[:=]\s*)[a-zA-Z0-9_\-]{15,}/gi, "$1[REDACTED_KEY]")
        .replace(/(password\s*[:=]\s*)[^\s,;\n]+/gi, "$1[REDACTED_PASSWORD]")
        .replace(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g, (match) => {
            // Keep domain generic for privacy
            const [user, domain] = match.split("@");
            return user.slice(0, 2) + "***@" + domain;
        });
}

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
            `You are speaking with ${sanitizePrivacyContext(profile.name)}.`,
            profile.college  && `College: ${sanitizePrivacyContext(profile.college)}`,
            profile.branch   && `Branch: ${sanitizePrivacyContext(profile.branch)}`,
            profile.degree   && `Degree: ${sanitizePrivacyContext(profile.degree)}`,
            profile.year     && `Current Year: Year ${profile.year}`,
            profile.role     && `Role: ${profile.role}`,
        ].filter(Boolean).join(" ");
        parts.push(`STUDENT IDENTITY:\n${identity}`);
    }

    // ── Page context ──────────────────────────────────────────────────────
    if (pageCtx.title || pageCtx.url) {
        let ctx = `CURRENT PAGE:\nTitle: ${sanitizePrivacyContext(pageCtx.title || "")}\nURL: ${pageCtx.url || ""}\nHeading: ${sanitizePrivacyContext(pageCtx.heading || "")}`;

        if (pageCtx.fileLinks?.length) {
            ctx += `\n\nDOCUMENTS ON THIS PAGE:\n` +
                pageCtx.fileLinks.map(f => `- [${sanitizePrivacyContext(f.name)}](${f.url})`).join("\n");
        }
        if (pageCtx.pageImages?.length) {
            ctx += `\n\nIMAGES ON THIS PAGE:\n` +
                pageCtx.pageImages.map(img => `- [${sanitizePrivacyContext(img.alt)}](${img.url})`).join("\n");
        }
        if (pageCtx.pdfText) {
            ctx += `\n\nPDF DOCUMENT TEXT (visible on page):\n"""\n${sanitizePrivacyContext(pageCtx.pdfText)}\n"""`;
        }
        if (pageCtx.selectedText) {
            ctx += `\n\nSTUDENT SELECTED TEXT:\n"""\n${sanitizePrivacyContext(pageCtx.selectedText)}\n"""`;
        }
        parts.push(ctx);
    }

    return parts.join("\n\n");
}

// ─── Cache Utilities ───────────────────────────────────────────────────────────

const CACHE_DB_NAME = "abhihub-webllm-cache";
const CACHE_DB_VER  = 1;
const CACHE_STORE   = "model-meta";

export async function ensurePersistentStorage() {
    try {
        if (navigator.storage && navigator.storage.persist) {
            const isPersisted = await navigator.storage.persisted();
            if (!isPersisted) {
                const granted = await navigator.storage.persist();
                console.info("[WebLLM] Persistent storage granted:", granted);
            }
        }
    } catch (e) {
        console.warn("[WebLLM] Persistent storage request error:", e);
    }
}

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

export async function markModelCached(modelId) {
    try {
        await ensurePersistentStorage();
        localStorage.setItem(`webllm_installed_${modelId}`, "true");
        localStorage.setItem("webllm_last_cached", modelId);
        const db = await openCacheMetaDB();
        const tx = db.transaction(CACHE_STORE, "readwrite");
        tx.objectStore(CACHE_STORE).put({ modelId, cachedAt: Date.now() });
        await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
    } catch (e) {
        console.warn("[CacheMeta] write failed:", e);
    }
}

export async function isModelCached(modelId) {
    try {
        if (localStorage.getItem(`webllm_installed_${modelId}`) === "true") {
            return true;
        }
        // Check Cache API (MLC stores model shards here)
        if ("caches" in window) {
            const keys = await caches.keys();
            for (const key of keys) {
                if (key.includes("webllm") || key.includes("mlc") || key.includes("abhihub-ai") || key.includes(modelId.toLowerCase())) {
                    const cache = await caches.open(key);
                    const reqs  = await cache.keys();
                    if (reqs.some(r => r.url.includes(modelId))) {
                        localStorage.setItem(`webllm_installed_${modelId}`, "true");
                        return true;
                    }
                }
            }
        }
        // Fallback: check meta DB written on previous successful load
        const db  = await openCacheMetaDB();
        const tx  = db.transaction(CACHE_STORE, "readonly");
        const row = await new Promise((res, rej) => {
            const r = tx.objectStore(CACHE_STORE).get(modelId);
            r.onsuccess = () => res(r.result); r.onerror = rej;
        });
        if (row) {
            localStorage.setItem(`webllm_installed_${modelId}`, "true");
            return true;
        }
        return false;
    } catch (_) { return false; }
}

export async function deleteModelFromStorage(modelId) {
    try {
        localStorage.removeItem(`webllm_installed_${modelId}`);
        if (localStorage.getItem("webllm_last_cached") === modelId) {
            localStorage.removeItem("webllm_last_cached");
        }
        try {
            const db = await openCacheMetaDB();
            const tx = db.transaction(CACHE_STORE, "readwrite");
            tx.objectStore(CACHE_STORE).delete(modelId);
        } catch (_) {}

        if ("caches" in window) {
            const keys = await caches.keys();
            for (const key of keys) {
                if (key.includes("webllm") || key.includes("mlc") || key.includes("abhihub-ai")) {
                    const cache = await caches.open(key);
                    const reqs  = await cache.keys();
                    for (const req of reqs) {
                        if (req.url.includes(modelId)) {
                            await cache.delete(req);
                        }
                    }
                }
            }
        }
        return true;
    } catch (e) {
        console.warn("[WebLLM] Delete model failed:", e);
        return false;
    }
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
            // Priority 1: Default adapter (matches standard browser WebGPU driver)
            let adapter = await navigator.gpu.requestAdapter().catch(() => null);
            if (!adapter) {
                adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" }).catch(() => null);
            }
            if (!adapter) {
                adapter = await navigator.gpu.requestAdapter({ powerPreference: "low-power" }).catch(() => null);
            }

            if (!adapter) {
                return { 
                    supported: false, 
                    reason: "No compatible GPU adapter found. Chrome/Edge may have blocklisted your graphics driver. Fix: Open chrome://flags/#enable-unsafe-webgpu, set to 'Enabled', ensure hardware acceleration is ON in chrome://settings/system, then click 'Relaunch'." 
                };
            }

            // Return success without acquiring an exclusive device (leave device creation to WebWorker)
            return {
                supported: true,
                adapterInfo: adapter.info || {}
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

    /**
     * Inspects real issues when WebLLM fails to run or load on the device.
     * Evaluates WebGPU, hardware drivers, storage quota, VRAM, and network issues.
     */
    async diagnoseIssue(error, targetModel = null) {
        const raw = String(error?.message || error || "");

        // 1. Insecure Context Guard (WebGPU strictly requires HTTPS or localhost)
        if (typeof window !== "undefined" && !window.isSecureContext && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
            return {
                issueType: "insecure_context",
                title: "Insecure Connection (HTTPS Required)",
                detail: "WebGPU security policy requires a secure HTTPS connection or localhost.",
                actionable: "Access AbhiHub over HTTPS (https://abhihub.edu.eu.org)."
            };
        }

        // 2. Hardware & Browser WebGPU Support Check
        const gpuCheck = await this.checkWebGPU();
        if (!gpuCheck.supported) {
            return {
                issueType: "webgpu_unsupported",
                title: "WebGPU Unsupported / Disabled",
                detail: gpuCheck.reason,
                actionable: "Enable Hardware Acceleration in browser settings or use Chrome/Edge 113+."
            };
        }

        // 3. VRAM / Out of Memory / Device Lost
        if (/out of memory|buffer allocation|allocation failed|device lost|vram|out-of-memory/i.test(raw)) {
            return {
                issueType: "out_of_vram",
                title: "GPU Memory Exhausted (VRAM Full)",
                detail: `Your device GPU does not have enough free VRAM to allocate weights for ${targetModel || "the model"}.`,
                actionable: "Switch to the ultra-lightweight SmolLM2 360M (240MB) or Qwen 0.5B (350MB) model.",
                fallbackModel: "SmolLM2-360M-Instruct-q4f16_1-MLC"
            };
        }

        // 4. Browser Storage Quota Exceeded
        if (/quota|storage|quotaexceeded|insufficient space/i.test(raw)) {
            const storage = await getStorageEstimate();
            const freeMb = storage ? Math.round(storage.free / (1024 * 1024)) : "unknown";
            return {
                issueType: "storage_quota",
                title: "Browser Storage Full",
                detail: `Browser disk quota exceeded (~${freeMb} MB free space). WebLLM could not store model shards.`,
                actionable: "Clear browser cache or delete older cached models in Settings."
            };
        }

        // 5. CDN / Network Weight Download Failure
        if (/failed to fetch|networkerror|load failed|aborted|404|cdn|offline/i.test(raw)) {
            return {
                issueType: "network_cdn_failure",
                title: "Model Download Interrupted",
                detail: "Could not download model weight shards from the MLC CDN or Hugging Face repository.",
                actionable: "Check your internet connection or verify adblocker / firewall isn't blocking esm.run."
            };
        }

        // 6. General WebWorker / MLC Runtime Issue
        return {
            issueType: "engine_runtime_error",
            title: "WebLLM Runtime Error",
            detail: raw || "Unknown initialization failure in MLC WebGPU engine.",
            actionable: "Refresh the browser page or try an alternative model."
        };
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

        if (!navigator.gpu) {
            this.isLoading = false;
            throw new Error("WebGPU is not enabled in this browser. Please enable Hardware Acceleration in chrome://settings/system or visit chrome://flags/#enable-unsafe-webgpu.");
        }

        // ── Storage quota guard ───────────────────────────────────────────────
        const storage = await getStorageEstimate();
        if (storage && storage.free < 400 * 1024 * 1024) {
            console.warn("[Cache] Low storage (<400 MB free). Model loading may fail.");
        }

        try {
            // Always spawn a fresh worker for engine initialization to prevent "Object has already been disposed"
            if (this.worker) {
                try { await this.engine?.unload(); } catch (_) {}
                this.engine = null;
                try { this.worker.terminate(); } catch (_) {}
                this.worker = null;
            }

            const cached    = await isModelCached(targetModel);
            const appConfig = { ...prebuiltAppConfig, useIndexedDBCache: true };

            try {
                this.worker = new Worker("/static/js/ai/webllm-worker.js", { type: "module" });
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
            } catch (workerErr) {
                console.warn("[WebLLM] WebWorker engine failed, attempting main-thread fallback:", workerErr);
                if (this.worker) {
                    try { this.worker.terminate(); } catch (_) {}
                    this.worker = null;
                }
                this.engine = await CreateMLCEngine(
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
            }

            await markModelCached(targetModel);
            this.selectedModel = targetModel;
            this.isLoaded  = true;
            this.isLoading = false;
            return this.engine;
        } catch (error) {
            this.isLoading = false;
            this.isLoaded  = false;
            this.selectedModel = null;
            if (this.worker) {
                try { this.worker.terminate(); } catch (_) {}
                this.worker = null;
            }
            this.engine = null;
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

        // Ensure no redundant or out-of-order system messages in conversation history
        const nonSystemMessages = (messages || [])
            .filter(m => m && m.role && String(m.role).toLowerCase() !== "system" && m.content)
            .slice(-this.maxHistoryMessages);

        const formattedMessages = [
            { role: "system", content: systemPrompt },
            ...nonSystemMessages
        ];

        try {
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
        } catch (err) {
            const msg = String(err?.message || err || "");
            if ((msg.includes("disposed") || msg.includes("lost") || msg.includes("terminated")) && !options._retried) {
                console.warn("[WebLLM] Recovering from disposed engine/worker...", err);
                this.isLoaded = false;
                if (this.worker) {
                    try { this.worker.terminate(); } catch (_) {}
                    this.worker = null;
                }
                this.engine = null;
                await this.initEngine(this.selectedModel);
                return this.generateStream(messages, onChunk, { ...options, _retried: true });
            }
            throw err;
        }
    }

    async unloadModel() {
        if (this.engine) {
            try { await this.engine.unload(); } catch (e) { console.warn("[Unload]", e); }
            this.engine = null;
        }
        if (this.worker) {
            try { this.worker.terminate(); } catch (_) {}
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
                case "DELETE_MODEL": {
                    const targetId = payload?.modelId;
                    const success = await deleteModelFromStorage(targetId);
                    sendResponse(success, { deleted: success, modelId: targetId });
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

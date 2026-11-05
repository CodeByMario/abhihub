/**
 * AbhiHub External AI Provider Client — v2
 * Harness-style: single provider, simple config, AbhiHub-exclusive agent.
 *
 * Model status (verified Sept 2026):
 *  - Groq: free, llama-3.1-8b-instant, llama-3.3-70b-versatile, gemma2-9b-it, qwen3-32b
 *  - Gemini: free tier, gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3-flash
 *  - OpenAI: paid, gpt-4o-mini, gpt-4o
 *  - Anthropic: paid, claude-3-haiku, claude-3-5-sonnet
 *
 * Keys stored in localStorage ONLY — never sent to AbhiHub servers.
 */

// ─── Provider Catalog ──────────────────────────────────────────────────────────
export const PROVIDERS = {
    groq: {
        id: "groq",
        name: "Groq",
        tagline: "100% Free · Ultra-Fast",
        free: true,
        icon: "⚡",
        color: "#f55036",
        keyLabel: "Groq API Key",
        keyPlaceholder: "gsk_...",
        keyUrl: "https://console.groq.com/keys",
        keyGuide: "Free — sign up at console.groq.com, click Create API Key",
        models: [
            { id: "llama-3.1-8b-instant",    name: "Llama 3.1 8B Instant",    free: true,  recommended: true,  note: "Best speed · Free" },
            { id: "llama-3.3-70b-versatile",  name: "Llama 3.3 70B Versatile", free: true,  recommended: false, note: "Highest quality · Free" },
            { id: "gemma2-9b-it",             name: "Gemma 2 9B (Google)",      free: true,  recommended: false, note: "Balanced · Free" },
            { id: "qwen3-32b",                name: "Qwen 3 32B",               free: true,  recommended: false, note: "Great for math/code · Free" },
        ],
        defaultModel: "llama-3.1-8b-instant",
        rateLimit: "30 RPM · 500K tokens/day (free)"
    },
    gemini: {
        id: "gemini",
        name: "Google Gemini",
        tagline: "Free Tier Available",
        free: true,
        icon: "✨",
        color: "#4285f4",
        keyLabel: "Gemini API Key",
        keyPlaceholder: "AIza...",
        keyUrl: "https://aistudio.google.com/app/apikey",
        keyGuide: "Free — sign in at Google AI Studio, click Get API Key",
        models: [
            { id: "gemini-2.5-flash",      name: "Gemini 2.5 Flash",      free: true,  recommended: true,  note: "Latest · Best balance · Free" },
            { id: "gemini-2.5-flash-lite", name: "Gemini 2.5 Flash Lite",  free: true,  recommended: false, note: "Fastest · Free" },
            { id: "gemini-3-flash",        name: "Gemini 3 Flash",         free: true,  recommended: false, note: "Newest (may require upgrade)" },
        ],
        defaultModel: "gemini-2.5-flash",
        rateLimit: "15 RPM · 1M tokens/day (free)"
    },
    openai: {
        id: "openai",
        name: "OpenAI",
        tagline: "Paid",
        free: false,
        icon: "💼",
        color: "#10a37f",
        keyLabel: "OpenAI API Key",
        keyPlaceholder: "sk-...",
        keyUrl: "https://platform.openai.com/api-keys",
        keyGuide: "Paid — requires billing at platform.openai.com",
        models: [
            { id: "gpt-4o-mini", name: "GPT-4o Mini", free: false, recommended: true,  note: "Best value · Paid" },
            { id: "gpt-4o",      name: "GPT-4o",       free: false, recommended: false, note: "Highest quality · Paid" },
        ],
        defaultModel: "gpt-4o-mini",
        rateLimit: "Based on your usage tier"
    },
    anthropic: {
        id: "anthropic",
        name: "Claude (Anthropic)",
        tagline: "Paid",
        free: false,
        icon: "🧠",
        color: "#d97757",
        keyLabel: "Anthropic API Key",
        keyPlaceholder: "sk-ant-...",
        keyUrl: "https://console.anthropic.com/settings/keys",
        keyGuide: "Paid — requires billing at console.anthropic.com",
        models: [
            { id: "claude-3-haiku-20240307",   name: "Claude 3 Haiku",      free: false, recommended: true,  note: "Fastest · Most affordable · Paid" },
            { id: "claude-3-5-sonnet-20241022", name: "Claude 3.5 Sonnet",   free: false, recommended: false, note: "Best quality · Paid" },
        ],
        defaultModel: "claude-3-haiku-20240307",
        rateLimit: "Based on your usage tier"
    }
};

// ─── Recommended order for UI display ─────────────────────────────────────────
export const PROVIDER_ORDER = ["groq", "gemini", "openai", "anthropic"];

// ─── localStorage helpers ──────────────────────────────────────────────────────
const LS = (k) => `abhihub_ai_${k}`;

export const saveKey   = (pid, v)  => v ? localStorage.setItem(LS(`key_${pid}`), v)   : localStorage.removeItem(LS(`key_${pid}`));
export const getKey    = (pid)     => localStorage.getItem(LS(`key_${pid}`)) || "";
export const saveModel = (pid, v)  => localStorage.setItem(LS(`model_${pid}`), v);
export const getModel  = (pid)     => localStorage.getItem(LS(`model_${pid}`)) || PROVIDERS[pid]?.defaultModel || "";
export const saveActiveProvider = (pid) => localStorage.setItem(LS("provider"), pid);
export const getActiveProvider  = ()    => localStorage.getItem(LS("provider")) || "webllm";
export const hasKey    = (pid)     => !!getKey(pid);

// ─── SSE stream reader ─────────────────────────────────────────────────────────
async function* readSSE(response) {
    const reader = response.body.getReader();
    const dec    = new TextDecoder();
    let buf      = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();
        for (const line of lines) { if (line.trim()) yield line.trim(); }
    }
    if (buf.trim()) yield buf.trim();
}

// ─── Provider Implementations ──────────────────────────────────────────────────

async function streamGroq(apiKey, model, messages, onChunk) {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
        body: JSON.stringify({ model, messages, stream: true, temperature: 0.5, max_tokens: 2048 })
    });
    if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e?.error?.message || `Groq ${res.status}: ${res.statusText}`);
    }
    return streamOpenAICompat(res, onChunk);
}

async function streamGemini(apiKey, model, messages, onChunk) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?alt=sse&key=${apiKey}`;
    const sysMsg  = messages.find(m => m.role === "system")?.content || "";
    const contents = messages
        .filter(m => m.role !== "system")
        .map(m => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] }));

    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            contents,
            systemInstruction: sysMsg ? { parts: [{ text: sysMsg }] } : undefined,
            generationConfig: { temperature: 0.5, maxOutputTokens: 2048 }
        })
    });
    if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e?.error?.message || `Gemini ${res.status}: ${res.statusText}`);
    }
    let full = "";
    for await (const line of readSSE(res)) {
        if (!line.startsWith("data:")) continue;
        try {
            const d = JSON.parse(line.slice(5).trim());
            const t = d?.candidates?.[0]?.content?.parts?.[0]?.text || "";
            if (t) { full += t; onChunk(t, full); }
        } catch (_) {}
    }
    return full;
}

async function streamOpenAI(apiKey, model, messages, onChunk) {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
        body: JSON.stringify({ model, messages, stream: true, temperature: 0.5, max_tokens: 2048 })
    });
    if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e?.error?.message || `OpenAI ${res.status}: ${res.statusText}`);
    }
    return streamOpenAICompat(res, onChunk);
}

async function streamAnthropic(apiKey, model, messages, onChunk) {
    const sysMsg  = messages.find(m => m.role === "system")?.content || "";
    const chatMsg = messages.filter(m => m.role !== "system");
    const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "x-api-key": apiKey,
            "anthropic-version": "2023-06-01"
        },
        body: JSON.stringify({ model, system: sysMsg, messages: chatMsg, stream: true, max_tokens: 2048 })
    });
    if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e?.error?.message || `Anthropic ${res.status}: ${res.statusText}`);
    }
    let full = "";
    for await (const line of readSSE(res)) {
        if (!line.startsWith("data:")) continue;
        try {
            const d = JSON.parse(line.slice(5).trim());
            const t = d?.delta?.text || "";
            if (t) { full += t; onChunk(t, full); }
        } catch (_) {}
    }
    return full;
}

async function streamOpenAICompat(response, onChunk) {
    let full = "";
    for await (const line of readSSE(response)) {
        if (!line.startsWith("data:")) continue;
        const json = line.slice(5).trim();
        if (json === "[DONE]") break;
        try {
            const d = JSON.parse(json);
            const t = d?.choices?.[0]?.delta?.content || "";
            if (t) { full += t; onChunk(t, full); }
        } catch (_) {}
    }
    return full;
}

// ─── Public API ────────────────────────────────────────────────────────────────

/**
 * Stream a response from any external provider.
 * All models behave as AbhiHub-exclusive agents (system prompt injected by caller).
 */
export async function streamExternalResponse(providerId, apiKey, model, messages, onChunk) {
    if (!apiKey?.trim()) throw new Error(`API key missing for ${PROVIDERS[providerId]?.name || providerId}.`);
    switch (providerId) {
        case "groq":      return streamGroq(apiKey, model, messages, onChunk);
        case "gemini":    return streamGemini(apiKey, model, messages, onChunk);
        case "openai":    return streamOpenAI(apiKey, model, messages, onChunk);
        case "anthropic": return streamAnthropic(apiKey, model, messages, onChunk);
        default: throw new Error(`Unknown provider: ${providerId}`);
    }
}

/**
 * Quick connection test — verifies key is valid and model responds.
 */
export async function testConnection(providerId, apiKey, model) {
    try {
        let reply = "";
        await streamExternalResponse(
            providerId, apiKey, model,
            [
                { role: "system", content: "You are AbhiHub AI. Reply in exactly one sentence." },
                { role: "user",   content: "Say hello and confirm you are ready as AbhiHub AI." }
            ],
            (d) => { reply += d; }
        );
        return { ok: true, preview: reply.trim().slice(0, 120) };
    } catch (err) {
        return { ok: false, error: err.message || String(err) };
    }
}

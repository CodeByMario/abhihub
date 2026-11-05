# Tarika Baseline & Verification Notes (Phase 0)

## 0.2 Conversation Routes in app.py
- `/api/ai/conversations` [GET, POST]: **Exists** at line 9696.
- `/api/ai/conversations/<convo_id>` [GET, PATCH, DELETE]: **Exists** at line 9728.

## 0.3 Route Line Numbers (app.py)
- `/api/ai/assistant` [POST]: Line 7724.
- `/api/ask-paper` [POST]: Line 8260.
- `/api/ai/conversations` [GET, POST]: Line 9696.
- `/api/ai/conversations/<convo_id>` [GET, PATCH, DELETE]: Line 9728.

## 0.4 Template & Asset Audit
- `resource_v2.html`: **In use dynamically** via `app.py:5255` (`template_name = 'resource_v2.html' if use_v2 else 'resource.html'`). Do NOT delete until unified with `resource.html`.
- `static/js/ai/abhihub-ai-assistant.js`: **Unreferenced** in all templates. Standalone drawer lives in `templates/includes/ai_assistant.html`.
- `static/css/ai/abhihub-ai-assistant.css`: **Unreferenced** in all templates.

## 0.6 Supported Platform & Engine Matrix
- **Server Cloud (Groq/Gemini/OpenAI/OpenRouter)**: Chrome, Edge, Safari, Firefox, iOS, Android (all supported browsers).
- **WebLLM (On-Device)**: Requires WebGPU (`navigator.gpu`). Supported on Chrome 113+, Edge 113+, Safari 18+ (macOS/iOS), Firefox (flagged). Disabled gracefully on devices lacking WebGPU or storage.
- **Ollama (Local)**: Desktop/localhost only (`http://127.0.0.1:11434` with `OLLAMA_ORIGINS`). Handled client-side.

## 7.4 Tarika Configuration & Troubleshooting Guide

### Engine Setup
1. **Cloud & BYOK (Bring Your Own Key)**:
   - Navigate to `/settings` -> AI Settings.
   - Enter your OpenRouter / Groq / OpenAI API key.
   - Keys are encrypted using Fernet (`MultiFernet` rotation support) and decrypted only in ephemeral request scope.

2. **On-Device (WebLLM / WebGPU)**:
   - Requires WebGPU (`navigator.gpu`).
   - Storage requirements: ~850MB for `Qwen2.5-0.5B`, ~2.5GB for `Llama-3.2-1B` and `Qwen2.5-1.5B`.
   - Weights are cached inside IndexedDB/CacheStorage for instant offline reuse.

3. **Local Developer (Ollama)**:
   - Run Ollama locally: `ollama run llama3.2`
   - Set environment variable for CORS access:
     - Windows PowerShell: `$env:OLLAMA_ORIGINS="*"; ollama serve`
     - Linux/macOS: `OLLAMA_ORIGINS="*" ollama serve`

### Troubleshooting Table

| Issue / Error | Cause | Recommended Action |
| :--- | :--- | :--- |
| **HTTP 401 Unauthorized** | Expired session or guest mode | Log in via `/login`. Input text is cached and preserved. |
| **HTTP 429 Rate Limited** | Request limit reached (25/min auth, 6/min guest) | Wait `retry_after` seconds, switch to BYOK, or use on-device WebLLM. |
| **WebGPU Unavailable** | Device or browser lacks WebGPU | Option is auto-disabled. Use cloud engine or modern Chrome/Edge. |
| **Ollama CORS Blocked** | Browser blocks cross-origin requests to 11434 | Set `OLLAMA_ORIGINS="*"` before starting `ollama serve`. |
| **Storage Quota Exceeded** | Insufficient disk space for WebLLM weights | Clear browser cache or switch to cloud model. |
| **Network Interrupted** | Stream interrupted mid-generation | Click the in-line "Retry" button. Completed generation is preserved. |


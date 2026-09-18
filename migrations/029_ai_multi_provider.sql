-- ============================================================
-- AbhiHub Migration 029: Multi-Provider AI Support (BYOK)
-- Expands ai_provider constraint to support Claude, Gemini, NVIDIA, OpenAI, Groq
-- Adds preferred ai_model column
-- ============================================================

ALTER TABLE abhihub.profiles
  DROP CONSTRAINT IF EXISTS profiles_ai_provider_check;

ALTER TABLE abhihub.profiles
  ADD CONSTRAINT profiles_ai_provider_check
  CHECK (ai_provider IN ('openrouter', 'anthropic', 'gemini', 'openai', 'nvidia', 'groq'));

ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS ai_model TEXT;

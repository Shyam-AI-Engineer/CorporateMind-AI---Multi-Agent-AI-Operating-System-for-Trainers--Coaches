# Multi-Language Rules

CorporateMind AI's primary content surface is **outreach copy** — emails, WhatsApp messages, Telegram posts, IG/FB captions — in the trainer's chosen language(s). India-first means Hindi, Hinglish, and regional languages are not afterthoughts.

## Supported languages (Phase 1)
- English (primary)
- Hindi
- Hinglish (Hindi + English code-switch)
- Tamil, Bengali, Marathi, Telugu, Kannada, Gujarati (regional)

## Where language is set
- Per `workspace`: `default_language` and `secondary_languages` (list).
- Per `hr_contact`: optional `preferred_language` (inferred from company HQ region if not set).
- Per `campaign`: explicit `language` override.

## Generation
- Prompts include the target language as a structured input — never hardcoded in the prompt body.
- For Hinglish, instruct the model explicitly: "code-switch naturally; do not translate; use Devanagari and Latin mixed as a native speaker would."
- Output validators check that the generated copy matches the requested language (langdetect or fastText classifier on output).

## Ingestion
- OCR pipeline handles multilingual posters (Hindi/regional scripts) via Tesseract + language packs, with Google Vision as fallback.
- Audio/video transcription via Whisper-large-v3 (native multilingual) — no separate translation step.

## Storage
- Postgres columns store native script (UTF-8). Never transliterate at storage layer.
- Full-text search via Meilisearch (handles Indic scripts natively).

## UI
- Frontend strings use i18next; locale switcher in user settings.
- LTR only in Phase 1 (no Arabic/Urdu support yet).

## Compliance
- WhatsApp templates must be approved per-language by Meta. Template registry stores `(template_name, language) → approval_status`.
- Unsubscribe flow text and physical-address footer translated per locale.

## Forbidden
- Hardcoding English-only assumptions (e.g., regex `[a-z]+` for names).
- Translating a stored canonical record — store native, translate at render time.
- Using LLM as a translator without explicit instruction + output validation.

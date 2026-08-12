# Kol Torah — data pipelines

This repo is the data ingestion/processing pipeline and lab described in
`documents/design.md`. Read that document for architecture, schema, and rationale before
making non-trivial changes — this file is conventions and navigation, not a substitute.

## Repo layout

This repo lives alongside sibling repos under `~/src/kol-torah`: `data-pipelines` (here),
`web`, `shared`, `documentation`, joined by `kol-torah.code-workspace`. The public web
tier's design (React Router SSR + Django/django-ninja + django-allauth OIDC) lives in
`../documentation/design/web-architecture.md`, not in this repo.

## Typing and data structures

Prefer typed structures — Pydantic models, or `dataclasses` where a full Pydantic model
is more than the case needs — over naked dicts. `dict[str, Any]` is not a default; it's
allowed only for a specific, documented reason (e.g. a genuinely dynamic provider payload
being passed through unmodified), and that reason should be a comment at the point of use,
not left implicit.

This applies throughout: config, function signatures, LLM structured output, stage
inputs/outputs — not just the config layer. The instinct should be "what shape is this
data, and where's the type that says so," not "what's in this dict."

Config specifically: secrets (DB password, API keys) come from the gitignored `.env`;
non-secret values (model names, params) come from the committed `config.toml`. Both are
loaded into one typed `Settings` object — see `src/data_pipelines/config.py`. Don't read
`os.environ` directly elsewhere in the codebase.

**Same rule on the frontend** (`frontend/`, see `documents/admin-lab.md`): TypeScript's
`any` is not a default either. It's allowed only for a specific, documented reason (a
comment at the point of use), same bar as `dict[str, Any]` above — prefer a real
interface/type. Where a type mirrors a backend Pydantic model (e.g. `TranscriptionResult`
in `documents/admin-lab.md` §4.2), generating it from the API's OpenAPI schema rather
than hand-duplicating it is worth doing once there's a schema to generate from — one
source of truth for the shape, not two definitions that can drift.

## LLM calls

All LLM calls go through LiteLLM (design.md §4) — don't hand-roll per-provider HTTP
clients. No stage may assume a specific vendor; the pipeline is provider-neutral by
design, and OpenAI-specific assumptions (tokenizers, usage-field shapes) will silently
break on other providers.

Token usage accounting needs care regardless of LiteLLM: providers disagree about what
"input tokens" means (OpenAI and Gemini include cached tokens in the count; Anthropic's
`input_tokens` is the uncached remainder only), and LiteLLM normalizes into OpenAI's shape
without resolving that disagreement. Verify the mapping per provider against a recorded
real response before trusting it, persist the raw provider payload alongside normalized
fields, and freeze the resolved cost onto the row at write time. Full detail in
design.md §4.1.

# Repository instructions

This repo's full conventions live in `CLAUDE.md` at the repo root — read it before
making non-trivial changes. The sections below are a condensed copy of the load-bearing
parts, kept here so they reach you even if you don't independently open `CLAUDE.md`. If
the two ever disagree, `CLAUDE.md` is authoritative — fix this file to match it, not the
other way around.

## Typing and data structures

Prefer typed structures — Pydantic models, or `dataclasses` where a full Pydantic model
is more than the case needs — over naked dicts. `dict[str, Any]` is not a default; it's
allowed only for a specific, documented reason (e.g. a genuinely dynamic provider payload
passed through unmodified), and that reason should be a comment at the point of use, not
left implicit.

This applies to every function signature, not just data models — including a helper
whose parameter is a value from a library (e.g. a Streamlit widget's return value, a
SQLAlchemy row). An untyped parameter is exactly the case where a type checker can't
catch a mismatch between how you're using a value and what it actually is — annotate
against the library's real return type rather than leaving it implicit, and run the
project's type checker (`pyright`) before considering a change finished.

Config specifically: secrets (DB password, API keys) come from the gitignored `.env`;
non-secret values (model names, params) come from the committed `config.toml`. Both are
loaded into one typed `Settings` object — see `src/data_pipelines/config.py`. Don't read
`os.environ` directly elsewhere in the codebase.

## LLM calls

All LLM calls go through LiteLLM — don't hand-roll per-provider HTTP clients. No stage
may assume a specific vendor; the pipeline is provider-neutral by design, and
OpenAI-specific assumptions (tokenizers, usage-field shapes) will silently break on other
providers.

Token usage accounting needs care regardless of LiteLLM: providers disagree about what
"input tokens" means (OpenAI and Gemini include cached tokens in the count; Anthropic's
`input_tokens` is the uncached remainder only), and LiteLLM normalizes into OpenAI's shape
without resolving that disagreement. Verify the mapping per provider against a recorded
real response before trusting it, persist the raw provider payload alongside normalized
fields, and freeze the resolved cost onto the row at write time.

## Repo layout

This repo (`data-pipelines`) lives alongside sibling repos under `~/src/kol-torah`:
`web`, `shared`, `documentation`, joined by `kol-torah.code-workspace`. The public web
tier's design (React Router SSR + Django/django-ninja + django-allauth OIDC) lives in
`../documentation/design/web-architecture.md`, not in this repo — don't confuse that
"admin panel" (the public site's staff CMS, a different stack) with this repo's own
Streamlit admin tool (`src/data_pipelines/admin_app.py`), which is a separate, internal
tool with its own doc at `documents/admin.md`.

## Before reporting a task finished

- Run `pyright` (or this project's configured type checker) over anything you changed.
- If the task came with a written plan that includes a manual-validation or testing
  section, actually run the app and carry out those steps yourself before reporting the
  task complete — don't infer that a change works from how it reads in a diff. A row
  click, button, or navigation flow described as working needs to have actually been
  clicked, not just written.

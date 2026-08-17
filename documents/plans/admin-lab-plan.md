# Plan: admin-lab — combined catalogue admin, experimentation lab, UI prototyping

**Status:** Planned — not yet implemented.
**Code to touch:** new `frontend/` (React), new `src/data_pipelines/lab/`, new
`src/data_pipelines/admin_lab_api/`; retires `src/data_pipelines/admin_app.py`; touches
`src/data_pipelines/config.py`, `alembic/`, `pyproject.toml`.

This is the concrete build plan for `documents/admin-lab.md`, which is the durable
reference for *why* each piece exists and stays up to date as the code evolves. This
document is a snapshot of *how* to build it, sequenced into four phases, and is expected
to go stale once implemented — same convention as
`documents/plans/implemented/adapters-plan.md`. Section numbers below reference
`admin-lab.md` (`AL §n`) and `design.md` (`DES §n`) rather than repeating their
reasoning. Visual design is sourced from
`../documentation/design/ui/` (a sibling-repo design handoff bundle, not part of
`admin-lab.md`) — see §0.1.

---

## 0. Decisions made for this plan

`admin-lab.md` deliberately leaves some implementation choices open (or doesn't address
them at all, being an architecture document rather than a build plan). Settled for this
plan, in conversation with the user:

| Question | Decision |
| --- | --- |
| Build sequencing | Four phases — infra, catalogue admin, jobs, results view (§1 below). Each is independently shippable and reviewable. |
| Visual design | **Not invented here — ported from `../documentation/design/ui/`** (direction 6b, "green ink, champagne, ruled ground"), a completed design bundle handed off after this plan's first draft. See §0.1. |
| Frontend styling | **Tailwind CSS v4** (`@tailwindcss/vite` plugin) for layout/spacing utilities only. Color, type, and every named component (buttons, cards, list rows, player) come from the vendored `tokens.css`/`base.css`, not from Tailwind's own palette — see §0.1. |
| Component behavior | **Tailwind + Headless UI** (`@headlessui/react`) for the handful of interactive widgets worth not hand-rolling (confirm dialogs, and any future combobox/multiselect), even though v1's actual widget list (§4 below) is coverable with native `<dialog>`/`<details>`/`<select>` alone — added now so it's already wired up when a real need shows up. Headless UI supplies behavior only; visual treatment is still the vendored `kt-*` classes/tokens, per §0.1. |
| List virtualization | **`@tanstack/react-virtual`** (AL §4.8 named this or `react-window`; picked for active maintenance and the existing TanStack affinity — `react-query` is a natural fit for the API layer too, see §2.4). |
| Package manager | **pnpm**. Not installed on the dev machine yet — `corepack enable && corepack prepare pnpm@latest --activate`, or `npm i -g pnpm`. |
| Text direction | **RTL-first.** The app is mainly Hebrew; English fields (`name_en`, `title_en`, slugs, adapter keys) stay LTR inline. Concrete rules in §0.1/§2.2 — now sourced from the design bundle's explicit RTL requirements rather than invented for this plan. |

**Superseded by §0.1:** this plan's original assumption that UI chrome would be
"Hebrew throughout, decided by convention" is now a settled fact of the design bundle
(README: "Hebrew is the primary language; English is a secondary locale, not a
fallback"), not an assumption to flag on review.

---

## 0.1 Visual design system — `../documentation/design/ui/`

A complete design handoff bundle landed in the sibling `documentation` repo after this
plan's first draft, produced by a design exploration and locked to one direction. It
replaces every color/typography/RTL decision this plan previously made up, and directly
supplies component patterns for two things Phase 4 was otherwise going to invent from
scratch: the audio player and the synced segment/turn lists. Read
`../documentation/design/ui/README.md` before touching any frontend styling code — it
is short and self-sufficient; this section only extracts what's load-bearing for the
plan below.

**What it is:** tokens (`tokens.css`) plus a reference component implementation
(`base.css`) plus a plain-HTML page showing them applied (`example-page.html`) plus
final logo assets (`logo/`). It's built for the **public site**, but the README is
explicit that this tool inherits it too: *"the first site to be built with it is an
internal admin/experimentation tool, which does not need careful visual design — for
that, take the tokens, the type pairing, and the component patterns, and don't spend
time on the signature graphics."*

**What this app takes from it:**

- **Every color, type size/weight, spacing, and radius token** in `tokens.css` — used
  as-is, not reinterpreted. No app-specific palette.
- **Component patterns that map directly onto planned screens:**
  - `.kt-list` / `.kt-row` / `.kt-row-time` / `.kt-row-title` / `.kt-row-summary`,
    with the active row signaled by `aria-current="true"` (champagne wash + 3px green
    edge bar + bold green timestamp) — this **is** the segment/turn list Phase 4 (§5.2)
    was going to build a bespoke highlight style for. Reuse it directly instead.
  - `.kt-player-row` / `.kt-track` / `.kt-progress` / `.kt-knob` / `.kt-tick` /
    `.kt-times` / `.kt-player-controls` — a seek bar with a **filled progress track and
    boundary ticks** already designed for chapter markers, which is exactly what
    Phase 4's segment/turn boundaries need. Reuse it for the audio player instead of a
    plain `<input type="range">`.
  - `.kt-card`, `.kt-btn` / `.kt-btn--secondary`, `.kt-chip`, `.kt-avatar`, `.kt-header`
    + `.kt-logo` — general-purpose, used across catalogue admin and the job UI (Phase
    2/3) for containers, buttons, and the app's own header/wordmark.
  - `.kt-status` — an **addendum added after this plan's first draft**, commissioned
    specifically for this app (§0.2). Covers exactly the two enumerations Phase 2/3
    need: the lesson pipeline status (`LessonStatus`, §3.1) as three pips (green =
    passed, gold = current, empty = not reached — the "gold = you are here" metaphor
    already used by the player and the active-row highlight) and job run status
    (`running`/`done`/`failed`) as a shape-coded glyph (turning ring / filled disc /
    filled square). Reuse directly — no bespoke status UI to design for either.
  - `.kt-time` (`font-family: mono; direction: ltr; unicode-bidi: isolate`) —
    **use this for every timestamp and every raw non-Hebrew token**, including
    diarization's `SPEAKER_00`-style labels (AL §2/§4.7). This corrects an
    under-specification in this plan's earlier draft: RTL correctness for embedded
    Latin/digit runs needs `unicode-bidi: isolate`, not just `dir="ltr"` — per the
    bundle's README, "the single most common bug in this kind of site."
- **The RTL requirements as hard requirements, not conventions to invent:**
  `dir="rtl" lang="he"` on `<html>`; logical CSS properties only
  (`inset-inline-*`/`margin-inline-*`/`padding-inline-*`/`border-inline-*`), never
  `left`/`right`; Hebrew line-height 1.6–1.65; 12px minimum font size; 44px minimum tap
  target on mobile (matters less for a desktop-first internal tool, but the vendored
  CSS already bakes it in at the 860px breakpoint, so no reason to strip it).
- **The logo** (`logo/mark.svg` + `.kt-wordmark`, per the header pattern in
  `example-page.html`) — cheap to include, gives the tool the same identity as the
  public site instead of looking unbranded.

**What this app explicitly skips**, per the README's own carve-out for this exact tool:

- **The two signature graphics** — `.kt-ruled` (ruled-ground background) and
  `.kt-watermark` (oversized letter behind page titles). Decorative, not needed for an
  internal tool, and skipping them is the README's own suggestion, not a corner cut.
- **The dual-mode search/ask field** (`.kt-searchbar`, `.kt-mode-toggle`) — that's the
  public site's search-vs-agent affordance; nothing in this app needs it. The header
  keeps the logo/wordmark, drops the search bar.
- **The automatic-summary notice** (`.kt-notice`) — required "on every page that
  displays generated summaries" on the public site; this app shows raw job
  results/logs, not generated summaries, so it doesn't apply. (Revisit if a future lab
  job type starts showing LLM-generated summaries in this UI — not the case for
  transcribe/diarize.)
- **Page-level layout for anything this bundle doesn't cover.** Only a lesson page and
  a content+sidebar shape are designed (README, "Still open"). Catalogue admin's
  CRUD tables/forms and the job run panel have **no prescribed layout** — they're
  composed from the primitives above (cards, buttons, list rows) using ordinary
  judgment, not extrapolated from the one designed page. Forms and data-table styling
  specifically aren't in the bundle at all (see §3.2/§4.7 for where this gap gets
  filled, using the same tokens rather than inventing new colors).

**Vendoring, not a cross-repo build dependency:** `documentation` is a sibling repo, not
a package `frontend/` can depend on at build time (no guarantee it's checked out on
every machine or in CI). `tokens.css`, `base.css`, and the `logo/` SVGs actually used
are **copied** into `frontend/src/styles/kt/` and `frontend/src/assets/logo/` at
implementation time, with a one-line comment noting the source path and that re-syncing
after a design update is a manual copy, not automatic. Fonts (Noto Serif Hebrew, Heebo,
JetBrains Mono) load from Google Fonts via `base.css`'s existing `@import url(...)` —
fine for an internal tool; the README's "self-host for production" note doesn't apply
here (no production deployment of this tool, G8).

**Load order matters:** Tailwind v4's `@import "tailwindcss";` pulls in Preflight (a CSS
reset that, among other things, strips default heading weight) — import it in
`index.css` **before** the vendored `tokens.css`/`base.css`, so `base.css`'s `h1, h2,
h3 { font-weight: 700; ... }` and friends win the cascade rather than getting reset
underneath them.

### 0.2 Status indicator addendum — `.kt-status`

The base bundle (§0.1) has no status/badge component at all — a real gap for a tool
whose two main screens are, at heart, "what state is this row in." Rather than
improvise one from `.kt-chip` (a topic-tag pill, wrong shape for 3–6 states repeated
down hundreds of rows) or invent a color the locked palette doesn't have, this was sent
back to design as a scoped addendum — not a new exploration, a targeted addition to the
same file set. It landed in the same commit history as the base bundle
(`../documentation/design/ui/README.md` "Status indicator (admin / lab tool)",
`base.css`, `tokens.css`, `example-page.html`'s third page).

**What it adds:**

- **One new token, deliberately scoped.** `--kt-rubric` ("the scribe's red ink") plus
  `--kt-rubric-wash`/`--kt-rubric-border` — the only color outside green/gold in the
  whole system, licensed for exactly one state (`failed`) and explicitly **not** for
  warnings, destructive buttons, or emphasis anywhere else. `failed` is encoded four
  redundant ways (rubric hue + a square glyph, shape-distinct from every other state's
  circle/pip + the only tinted wash in the set + 600 weight) so it never depends on
  color alone — consistent with the base system's existing "wash + edge bar + weight,
  never color alone" rule for the active-row highlight.
- **`.kt-pips`** — three small rectangles (same 3×9px proportions as the player's
  chapter ticks, §0.1) for the ordered lesson-pipeline state: passed stages green,
  current stage gold, unreached stages the empty track color.
- **`.kt-status--running` / `--done` / `--failed`** — for job runs, an unordered
  three-state set, differentiated by shape first (turning ring / filled disc / filled
  square) so it doesn't read as "just another color chip." The spin animation respects
  `prefers-reduced-motion`.

**Where this plan uses it**, replacing earlier placeholder language that guessed at
reusing `.kt-chip`:

- Catalogue admin's lesson status column (§3.1's `LessonStatus` enum) → `.kt-pips`,
  three states, exact match.
- The job run panel's live status (§4.6's `lab_jobs.status`) → `.kt-status--running`/
  `--done`/`--failed`, exact match — `running`'s spinner is also a free upgrade over the
  plan's earlier plain-text "watch status go `running` → `done`" description (§4.8).
- The lesson picker's separate cache-status column (§4.6 — `not_stored`/`stored`/
  `cached`, about local file presence, **not** the same enumeration as `LessonStatus`
  despite the overlapping word "stored") isn't one of the two states this addendum was
  scoped for, but reusing `.kt-status`'s visual language for it (three states, same
  glyph-plus-label shell) is a reasonable extension by the same logic that motivated the
  addendum in the first place, rather than a third bespoke pattern. Not designed
  explicitly — a judgment call to make at implementation time, not a blocker.

---

## 1. Phases

| Phase | Delivers | New runtime deps |
| --- | --- | --- |
| 1. Infrastructure | `lab` schema + `lab_jobs` migration; FastAPI skeleton; React/Vite/Tailwind skeleton; dev workflow | `fastapi`, `uvicorn`; frontend toolchain |
| 2. Catalogue admin | Rabbi/series/lesson CRUD, drill-down, lesson status, Reset All Lessons — retires `admin_app.py` | none |
| 3. Job execution | `LabJob` framework, lesson picker + auto-download, transcribe/diarize jobs, run/status API | `torch`, `transformers`, `pyannote.audio`, `soundfile` |
| 4. Results view | Range-request audio streaming; synced virtualized transcript/diarization lists; host heuristic; log view | none (frontend-only beyond phase 1's deps) |

Explicitly **out of scope**, per `admin-lab.md` §2's own list — not part of any phase
here: batch/sweep running, the merge job type, the run-comparison view, WER measurement,
live log streaming, and the UI-prototyping gallery's actual content (its existence is
covered by the frontend skeleton in Phase 1; what goes in it is undecided future work,
per AL §8).

---

## 2. Phase 1 — Infrastructure

### 2.1 Database: `lab` schema, drop the two-database scaffolding

One Alembic migration (`alembic/versions/`), following on from the existing two:

```python
op.execute("CREATE SCHEMA IF NOT EXISTS lab")
op.create_table(
    "lab_jobs",
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("lesson_id", sa.BigInteger, sa.ForeignKey("lessons.id"), nullable=False),
    sa.Column("job_type", sa.Text, nullable=False),
    sa.Column("job_version", sa.Text, nullable=False),
    sa.Column("job_description", sa.Text, nullable=False),
    sa.Column("job_version_notes", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("pid", sa.Integer, nullable=True),
    sa.Column("params", postgresql.JSONB, nullable=False),
    sa.Column("model_id", sa.Text, nullable=False),
    sa.Column("result_json", postgresql.JSONB, nullable=True),
    sa.Column("log", sa.Text, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("git_sha", sa.Text, nullable=False),
    sa.Column("git_dirty", sa.Boolean, nullable=False),
    schema="lab",
)
```

Exact column list per AL §5.1. `lesson_id` is an unqualified FK to `public.lessons.id` —
no schema-qualification needed, resolves via the default search path (AL §5.1).

**Model:** `src/data_pipelines/lab/models.py` gets a `LabJobRow` SQLAlchemy model
(`__tablename__ = "lab_jobs"`, `__table_args__ = {"schema": "lab"}`), following the same
`Base`/naming-convention setup as `db/base.py` — new declarative base or reuse `Base`
from `db.base` directly (reuse is simpler and there's no reason for a second metadata
object; confirm at implementation time that cross-schema FKs autogenerate cleanly under
one `Base`, which they should).

**Drop the two-database scaffolding**, now genuinely dead per AL §7:

- `config.py`: remove `Settings.lab_db` and the `lab: bool` parameter on
  `database_url()`.
- `alembic/env.py`: remove the `-x db=lab` handling; `get_url()` always targets
  `kol_torah`.
- `.env.example`: remove the `LAB_DB=kol_torah_lab` line and its comment.

### 2.2 Frontend skeleton

```
frontend/
    index.html          # <html lang="he" dir="rtl">; favicon from vendored logo/favicon.svg
    package.json
    vite.config.ts       # @tailwindcss/vite plugin; server.proxy: { "/api": "http://localhost:8000" }
    src/
        main.tsx
        App.tsx           # router root
        index.css         # @import "tailwindcss"; then @import "./styles/kt/tokens.css";
                            # then @import "./styles/kt/base.css"; then app-specific additions (§3.2/§4.7)
        styles/
            kt/             # vendored verbatim from ../documentation/design/ui/ — see §0.1
                tokens.css
                base.css
        assets/
            logo/           # mark.svg, favicon.svg, etc. — vendored from ../documentation/design/ui/logo/
        pages/
        components/
        api/              # typed fetch wrappers + generated OpenAPI types (§2.4)
```

`pnpm create vite frontend --template react-ts`, then add `tailwindcss
@tailwindcss/vite`, `@headlessui/react`, `react-router-dom`, `@tanstack/react-virtual`,
`@tanstack/react-query` (data-fetching/caching for the API layer — polling job status
(AL §2 "live status") and refetching after mutations are exactly its job; not in
`admin-lab.md` but a plain, uncontroversial fit, not a new architectural decision).

**Visual foundation is vendored, not designed here** — see §0.1 for the full reasoning.
Concretely for this phase: copy `tokens.css`/`base.css`/the used `logo/*.svg` files into
`frontend/src/`, wire the three `@import`s into `index.css` in the order given above, and
build the app shell (`<html lang="he" dir="rtl">`, a `.kt-header` with `.kt-logo` +
`.kt-wordmark`, `.kt-page`/`.kt-main` as the page container) directly from those classes
rather than from Tailwind's default look. Signature graphics (`.kt-ruled`,
`.kt-watermark`) and the search/ask bar (`.kt-searchbar`) are not used — §0.1.

**RTL rules, applied from the first page built, not retrofitted** — the hard
requirements are the design bundle's (§0.1), reproduced here as the concrete checklist
for this codebase:

- `<html dir="rtl" lang="he">` in `index.html` — the whole app mirrors by default.
- **Never use directional utilities** (`ml-*`, `mr-*`, `pl-*`, `pr-*`, `left-*`,
  `right-*`, `text-left`, `text-right`) in Tailwind-authored layout code. Always the
  logical equivalents (`ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`) — Tailwind v4
  maps these to CSS logical properties, which flip automatically with `dir`, matching
  the vendored `base.css`'s own convention (`inset-inline-*`, `margin-inline-*`, etc.).
  Worth a one-line note in `frontend/README.md` or a lint rule
  (`eslint-plugin-tailwindcss` has a rule for this; confirm it flags directional
  utilities at implementation time) so it doesn't erode over time.
- **English-only fields** (`name_en`, `title_en`, `slug`, `adapter_key`) render inside
  `<span dir="ltr">`. **Timestamps and any raw non-Hebrew token** (diarization's
  `SPEAKER_00`-style labels included) use the vendored `.kt-time` class specifically,
  not a generic `dir="ltr"` span — it additionally sets `unicode-bidi: isolate`, which
  plain `dir="ltr"` does not, and is the one most likely to silently render wrong if
  skipped (§0.1).
- Headless UI (§0) has no opinion on direction — it's unstyled, so RTL correctness is
  entirely a function of the classes applied to it, same as everywhere else.

### 2.3 Backend skeleton

```
src/data_pipelines/admin_lab_api/
    main.py       # FastAPI() app, CORS not needed (Vite proxy handles it in dev, AL §1.2)
    db.py         # get_db() Depends()-style generator yielding a sync Session,
                   # same engine-construction pattern as admin_app.py's get_engine()
    routers/
        catalogue.py   # Phase 2
        lessons.py     # Phase 3
        jobs.py         # Phase 3
        audio.py        # Phase 4
```

Run with `uv run uvicorn data_pipelines.admin_lab_api.main:app --reload --port 8000`
alongside `pnpm --dir frontend dev`. Document both commands together (a `Makefile`
target or a one-line note in this repo's README) since local dev always needs both
running — not specced further here, just flagged so it isn't forgotten.

At the end of Phase 1: an empty app that boots, a `/api/health` endpoint, and a Vite dev
server proxying to it — nothing functional yet, but the full request path (browser →
Vite → FastAPI → Postgres) is exercised end to end.

### 2.4 API schema generation

Per `CLAUDE.md` / AL §4.2: once there's a real OpenAPI schema to generate from (end of
Phase 2 at the latest), add `openapi-typescript` as a frontend dev dependency and a
script (`pnpm --dir frontend gen:api`) that fetches `/openapi.json` from the running
backend and writes `frontend/src/api/schema.d.ts`. `frontend/src/api/*` wrappers use
those generated types rather than hand-duplicating Pydantic model shapes. Not set up
until Phase 2 has real endpoints to generate from — no value doing this against an empty
skeleton.

### 2.5 Manual validation

- `uv run uvicorn data_pipelines.admin_lab_api.main:app --reload` serves `/api/health`.
- `pnpm --dir frontend dev` serves the app; a page fetching `/api/health` through the
  Vite proxy gets a response with no CORS errors in the console.
- Page renders RTL correctly: open dev tools, confirm `<html dir="rtl">`, confirm a
  test element using `ms-4` sits with margin on the *left* (RTL "start" = visual right
  in RTL... concretely: verify by eye that spacing mirrors correctly, not just that the
  class compiles).
- Visual foundation matches the bundle: open `../documentation/design/ui/example-page.html`
  in a browser side by side with the new app shell's header — same green
  (`--kt-green`), same wordmark font/weight, same header height/border treatment. This
  is the cheap early check that the vendored CSS actually loaded and cascaded correctly
  (§0.1's load-order note) before any real screen is built on top of it.
- `alembic upgrade head` creates the `lab` schema and empty `lab_jobs` table; `\dn` in
  `psql` shows both `public` and `lab`.

---

## 3. Phase 2 — Catalogue admin

Ports `admin_app.py`'s Rabbi/Series CRUD (unchanged in function, AL §1.4) and builds the
lessons drill-down and Reset All Lessons that `documents/admin.md` §3 specced for the
Streamlit app but were never built there — no reason to build them twice, so this phase
absorbs that work directly instead of finishing the Streamlit version first.

### 3.1 Lesson status helper

New `src/data_pipelines/db/status.py`, exactly as scoped in
`documents/plans/admin-updates-plan.md` §3 (written for the Streamlit app, never
implemented there — implement it here instead, it's storage-agnostic):

```python
class LessonStatus(StrEnum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    STORED = "stored"

def lesson_status(lesson: Lesson) -> LessonStatus: ...
```

This is the canonical statement of `database-schema.md` §4.5's three states — reused by
the series-detail endpoint below, and by nothing else yet. Query with
`selectinload(Lesson.audio_file)` / `selectinload(Lesson.download)` when listing a
series' lessons, to avoid N+1 (same note as the Streamlit plan).

### 3.2 Backend: `routers/catalogue.py`

REST endpoints, request/response bodies as Pydantic schemas
(`admin_lab_api/schemas/catalogue.py`, `model_config = ConfigDict(from_attributes=True)`
for read models built straight off the ORM objects):

| Route | Method | Notes |
| --- | --- | --- |
| `/api/rabbis` | GET | list, with series count per row |
| `/api/rabbis` | POST | create |
| `/api/rabbis/{id}` | PUT | update |
| `/api/rabbis/{id}` | DELETE | 409 if series still reference it (mirrors `admin_app.py`'s guard) |
| `/api/series` | GET | list, optional `?rabbi_id=` filter, with lesson count per row |
| `/api/series` | POST | create |
| `/api/series/{id}` | PUT | update |
| `/api/series/{id}` | DELETE | 409 if lessons still reference it |
| `/api/series/{id}/lessons` | GET | lessons for one series, each with `status` (§3.1), sorted `discovered_at` desc |
| `/api/series/{id}/reset` | GET | preview: lesson count + the CLI's warning text (for the confirm step) |
| `/api/series/{id}/reset` | POST | calls `delete_series_lessons()` from `pipelines/discover/reset_series.py` directly, returns deleted count |

Slug uniqueness violations surface as `IntegrityError` → caught, returned as 409 with a
message, same as `admin_app.py`'s `st.error(f"Slug '{slug}' is already in use.")` today.

### 3.3 Frontend

**Styling note (§0.1/§0.2):** the design bundle has no prescribed CRUD table/form
layout — only a lesson page and a content+sidebar shape are designed. These screens are
composed from the general-purpose primitives it does provide: `.kt-card` as the
table/form container, `.kt-btn`/`.kt-btn--secondary` for actions, and — since the §0.2
addendum landed — `.kt-status`/`.kt-pips` directly for the `LessonStatus` column, no
adaptation needed. That leaves two genuinely uncovered gaps: **a data-table row style**
and **form input/label styling**. Build both from `tokens.css`'s existing values
(`--kt-border`, `--kt-radius-md`, `--kt-text`/`--kt-text-subtle`, the spacing scale)
rather than introducing new colors or radii — e.g. a table row can reasonably reuse
`.kt-row`'s border-and-padding rhythm minus the timestamp column and active-row
treatment, since it's the same "list of things" shape. Land these as a small
`admin.css` alongside the vendored files (`frontend/src/styles/kt/admin.css`, not mixed
into the vendored copies, so a future re-sync from the design repo doesn't clobber
app-specific additions), not scattered inline styles.

- `RabbisPage` — table + add/edit/delete, port of `admin_app.py`'s `rabbis_tab`. Row
  click navigates to `SeriesPage` filtered to that rabbi (`?rabbi_id=`).
- `SeriesPage` — table + add/edit/delete, port of `series_tab`, with the rabbi-id query
  param pre-filtering and a visible "showing series for {rabbi} — clear filter"
  affordance, matching `admin-updates-plan.md` §2.1's reasoning (arriving from a link
  shouldn't silently hide the rest of the catalogue). Row click navigates to
  `SeriesDetailPage`.
- `SeriesDetailPage` — header (series name he/en, rabbi link, lesson type, adapter key),
  lessons table with status column, and the Reset All Lessons control:
  - Two-step confirm using the native `<dialog>` element (§0 — no Headless UI needed for
    this one), styled with `.kt-card` inside and a `.kt-btn`/`.kt-btn--secondary` pair
    for confirm/cancel: click "אפס את כל השיעורים" (a `.kt-btn` styled as destructive —
    the bundle has no dedicated danger color, so this reuses `.kt-btn` primary green
    rather than inventing a red the tokens don't define) → `dialog.showModal()` with the
    GET `/reset` preview's count and warning text ("S3 bucket not touched") → confirm
    POSTs, closes dialog, refetches the lesson list (now empty), shows a success
    toast/banner repeating the count and the bucket note.
- Query-param based routing throughout (`?rabbi_id=`, `?series_id=` via
  `useSearchParams`), not component state — mirrors `admin.md` §3.3's reasoning
  (shareable, survives reload) even though the underlying rerun problem that motivated
  it in Streamlit doesn't apply to React; the *property* (a drilled-down view is a real,
  bookmarkable link) is still worth keeping.

### 3.4 Retire `admin_app.py`

Once `SeriesDetailPage` + Reset All Lessons are verified working end to end (§3.5):

- Delete `src/data_pipelines/admin_app.py`.
- Remove `streamlit` from `pyproject.toml` (nothing else in the codebase imports it).
- **Leave `documents/admin.md` alone** — AL §1.4 explicitly defers retiring/rewriting it
  to a separate follow-up, not this plan. It'll read as describing a deleted app until
  that follow-up happens; not this document's problem to fix.
- `documents/plans/admin-updates-plan.md` becomes fully superseded by this phase (it
  specced the same three features for the Streamlit app). Move it to
  `documents/plans/implemented/` with a status note pointing here, same convention as
  `adapters-plan.md`.

### 3.5 Manual validation

Same checklist as `admin-updates-plan.md` §8, against the new UI instead of Streamlit:
rabbi → series drill-down with clearable filter; series → detail with lesson count and
per-row status matching the DB for a few spot-checked lessons; Reset All Lessons cancel
path leaves data untouched, confirm path deletes and a subsequent `s01_discover` run
repopulates the series (confirming bucket recovery still works — this is also an
indirect regression check on the pipeline itself, not just the new UI).

---

## 4. Phase 3 — Job execution

### 4.1 New dependencies

`torch`, `transformers`, `pyannote.audio`, `soundfile` — versions matching what
`design.md` §3 hand-tested on this machine (aarch64, CUDA 13; `torch` needs the CUDA
13-compatible wheel, confirm the exact install command — e.g. a specific `--index-url`
— against what was actually used for that test, since a plain `pip install torch` may
resolve to a CUDA version this machine doesn't have). This is the first time these land
in `pyproject.toml`; expect the install itself to need hand-verification on this
hardware, same caution `design.md` §3 already documents for `faster-whisper`/
`insanely-fast-whisper`.

### 4.2 `Settings`: `hf_token`

`config.py` gains `hf_token: SecretStr` (required, no default — same treatment as
`postgres_password`). Goes in `.env`/`.env.example`, per `pyannote.audio` 4.x's gated
component load at init (`design.md` §3).

### 4.3 `git_info.py`

New `src/data_pipelines/git_info.py` — not named in `admin-lab.md`, needed to satisfy
`design.md` invariant 4 ("every run records a git SHA and dirty flag"), which `lab_jobs`
rows need at insert time (§4.4 below):

```python
def current_git_sha() -> str: ...      # `git rev-parse HEAD`, subprocess
def is_git_dirty() -> bool: ...        # `git status --porcelain`, non-empty output
```

### 4.4 `src/data_pipelines/lab/` module

Exact layout from AL §6:

- `models.py` — `JobParams` base (`model_id: str`), `TranscriptionParams`/
  `TranscriptSegment`/`TranscriptionResult`, `DiarizationParams`/`DiarizationTurn`/
  `DiarizationResult`, `JobContext` (AL §4.2),
  plus `LabJobRow` (added in Phase 1, §2.1).
- `job.py` — the `LabJob[ParamsT, ResultT]` ABC (AL §4.1).
- `transcribe.py` — `TranscribeJob`. Model loading + `transformers` pipeline inference
  against `ivrit-ai/whisper-large-v3-turbo`, `language="he"` pinned (`design.md` §3). No
  API/DB imports — plain Python, reusable later by the real pipeline stage 4 (AL §6).
- `diarize.py` — `DiarizeJob`. `pyannote.audio` with
  `ivrit-ai/pyannote-speaker-diarization-3.1` + `AgglomerativeClustering` (`design.md`
  §3). Same no-framework-imports rule.
- `job_types.py` — `JOB_TYPES: dict[str, type[LabJob]]` registry (AL §4.1).
- `jobs.py` — `lab_jobs` CRUD: `create()` (inserts with `pid=null`, AL §4.3),
  `set_pid()` (the post-`Popen` write-back), `mark_done()`, `mark_failed()`, `get()`,
  `list_for_lesson()`, plus the liveness check (`os.kill(pid, 0)`, treating a `null` pid
  as dead too, AL §4.3).
- `log_capture.py` — `capture_job_log()` context manager (AL §4.5, exact code already in
  the design doc).
- `run_job.py` — subprocess entrypoint (`uv run python -m data_pipelines.lab.run_job
  <job_id>`), the five-step flow in AL §4.3.

### 4.5 `storage.py`: `download_from_bucket`

`pipelines/discover/storage.py` gains the missing counterpart to `upload_to_bucket`
(AL §4.6):

```python
def download_from_bucket(storage_key: str, dest_path: Path) -> None: ...
```

Plain `client.download_file(bucket, storage_key, str(dest_path))` — no new abstraction
needed beyond what's already in that module.

### 4.6 Backend: `routers/lessons.py`, `routers/jobs.py`

| Route | Method | Notes |
| --- | --- | --- |
| `/api/lab/lessons` | GET | filtered `public.lessons` (rabbi/series/`lesson_type`/explicit-id-list query params — `lesson_type` per `database-schema.md` §4.4, AL §2's own fix from "content type"), each row tagged with cache status: `not_stored` (no `audio_files` row, disabled), `stored` (row exists, file not at `local_cache_dir`), `cached` (file present locally) — rendered with `.kt-status`'s glyph-plus-label shell per §0.2, a reasonable extension of the addendum rather than a state it was explicitly designed for |
| `/api/lab/lessons/{id}/ensure-cached` | POST | if `stored`, synchronously calls `download_from_bucket` (§4.5) and returns once done — AL §4.6 |
| `/api/lab/lessons/{id}/jobs` | GET | `lab_jobs` rows for this lesson (run panel's "already running?" check, AL §4.3; also the future compare view's data source) |
| `/api/lab/jobs` | POST | body: `{lesson_id, job_type, params}`. Validates `params` against `JOB_TYPES[job_type].params_model()`, inserts row (`status="running"`, `pid=null`, `git_sha`/`git_dirty` from §4.3, `model_id=params.model_id` — the shared `JobParams` base, AL §4.2, is what makes this read generic instead of per-job-type) to get an `id`, then `subprocess.Popen([...,  str(row.id)])`, then writes the real `pid` back onto the row (AL §4.3 — insert has to precede `Popen` since `run_job.py` needs the row's `id` as its argument, so the real pid can't be known at insert time), returns the row |
| `/api/lab/jobs/{id}` | GET | current row. If `status == "running"` and either the pid is still `null` or the liveness check (§4.4) finds it dead, the backend self-heals: updates the row to `status="failed"`, `error="process appears to have died (pid no longer running)"`, `ended_at=now()`, *then* returns the updated row — so this is detected and recorded once, not recomputed on every poll (AL §4.3's "surfaced... with a manual retry" becomes a real terminal state, not a client-side guess) |

### 4.7 Frontend

Styling: same primitives and same gap as Phase 2 (§3.3) — `.kt-card` for the picker
table and the run panel, `.kt-btn` for launch/actions, the shared `admin.css` table row
style for the lesson list. Nothing new to add to that file for this phase.

- `LessonPickerPage` — filter controls (native `<select>`s for rabbi/series/
  `lesson_type`; a text input for explicit lesson-id list), table of matching lessons with cache
  status. Selecting a `stored`-but-not-`cached` row triggers `ensure-cached` with a
  loading state (AL §4.6). **The lessons query only runs once at least one filter is
  set** — confirmed at implementation time against real data (2185+ lessons already in
  the catalogue) that an unfiltered query renders a multi-thousand-row unvirtualized
  list, which is a real usability problem independent of list virtualization (that's
  only in scope for Phase 4's transcript/diarization lists, §4.8/§5.2, and wouldn't fix
  an admin picker showing thousands of rows by default anyway). With no filter set, the
  page shows a prompt ("select a rabbi, series, lesson type, or id list") instead of an
  empty or huge table.
- `JobRunPage` (reached from a lesson row) — run panel: for each job type in the
  registry (transcribe, diarize), either a "launch" form (params, defaulted from the
  job's `params_model()`) or, if `/lessons/{id}/jobs` shows one already `running`, its
  live status instead (`useQuery` with a short polling interval via `@tanstack/react-
  query`'s `refetchInterval`, AL §2 "live status") — rendered with `.kt-status--running`/
  `--done`/`--failed` (§0.2) directly, so a live run shows the spinning-ring glyph rather
  than plain "running" text, and a self-healed dead-pid failure (§4.6's GET
  `/jobs/{id}`) gets the full rubric treatment without any extra frontend logic to
  distinguish it from an ordinary failure. On completion, shows the raw `result_json`
  (pretty-printed, no polished rendering yet — that's Phase 4) and the log panel (§4.5's
  collapsed-by-default `<details>`, buildable now since it needs nothing from Phase 4).

### 4.8 Manual validation

Run a real transcription job end to end on a short cached lesson: launch from the UI,
watch the `.kt-status` glyph go from the spinning ring (`running`) to the filled green
disc (`done`), confirm `result_json`/`log`/`git_sha`/`git_dirty` are populated correctly
in the DB. Refresh the page mid-run — confirm the run panel shows the live status
instead of offering to launch a second job (AL §4.3's core guarantee). Kill the
subprocess by hand (`kill -9 <pid>`) mid-run and confirm the next poll flips the glyph
to the rubric square (`failed`, "process appears to have died") rather than spinning
forever. Repeat for diarization once the HF token is confirmed working.

---

## 5. Phase 4 — Results view

### 5.1 Backend: `routers/audio.py`

```
GET /api/lab/lessons/{id}/audio
```

Streams the file at `local_cache_dir / storage_key` with HTTP Range support, so the
browser `<audio>` element can seek without downloading the whole file (AL §1.2, §3). If
the lesson isn't cached, 404 (the frontend should have called `ensure-cached` via the
picker already, per Phase 3 — this endpoint doesn't trigger a download itself, it only
serves what's local). Implementation note: Starlette's `FileResponse` (bundled with
FastAPI) has supported `Range` requests natively since Starlette 0.37 — confirm the
pinned Starlette version at implementation time; if it predates that, fall back to a
small hand-written range-parsing wrapper rather than adding a new dependency for it.

### 5.2 Frontend: synced results, built on the vendored player and list components

This phase is where §0.1's component reuse pays off — the design bundle already
designed an audio player with a boundary-tick track and an active-row list pattern; both
map onto exactly what AL §2/§4.8 ask for, so this is porting, not designing.

- `PlaybackContext` (React context, plain `useState` — no state-management library
  needed for one shared `currentTime` + "which lesson" value) holds the shared playback
  position AL §4.8 describes: the `<audio>` element's `currentTime`, read/written by
  every piece that needs to move or react to it.
- `AudioPlayer` — built on the vendored `.kt-player-row`/`.kt-track`/`.kt-progress`/
  `.kt-knob`/`.kt-tick`/`.kt-times`/`.kt-player-controls` (§0.1), wrapping a real
  `<audio src={.../audio}>` element (no native `controls` — the vendored markup *is*
  the controls). Concretely: `.kt-track` becomes a `role="slider"` div whose
  `.kt-progress` width and `.kt-knob` `inset-inline-start` both track
  `currentTime / duration` as a percentage, updated on the `<audio>` element's
  `timeupdate`; click/drag on the track seeks. **`.kt-tick` marks are placed at every
  transcript segment boundary** (`inset-inline-start = start_ms / duration_ms`), the
  same slot the design uses for chapter boundaries — this is the one place the mapping
  from "public-site chapters" to "lab transcript segments" isn't quite 1:1
  (a two-hour Q&A lesson can have hundreds of segments vs. a handful of chapters), worth
  a quick visual check (§5.4) that dense ticks don't turn into visual noise; thin them
  (e.g. only diarization turn boundaries, which are far fewer) if so — a judgment call
  to make against the real rendered output, not decided here. **Resolved at
  implementation time:** prefer diarization turn boundaries when a diarize job exists
  (far fewer than segments); otherwise thin whichever set is in use (segments, if no
  diarize job) to at most ~80 evenly-sampled ticks — a plain cap, not a density
  calculation, since "wall of ticks" was the actual failure mode being avoided. `.kt-times` shows
  elapsed/total via `.kt-time` (mono, LTR-isolated, §0.1). Skip-back-15 and the
  "שיתוף מדקה זו" (share-from-minute) pill in `.kt-player-controls` are the public
  site's affordances, not needed here — reuse the row's structure/spacing, drop the
  buttons that don't apply.
- `SegmentList` / `TurnList` — `@tanstack/react-virtual` over `TranscriptSegment[]` /
  `DiarizationTurn[]` from the job's `result_json`, rendered with the vendored
  `.kt-list`/`.kt-row`/`.kt-row-time`/`.kt-row-title`/`.kt-row-summary` classes directly
  (`.kt-row-time` gets the `.kt-time` treatment already; `.kt-row-title` for the segment
  text itself since these lists have no separate title/summary split the way chapters
  do — collapse the two into one `.kt-row-title`-styled line, or use `-title` for a
  short lead-in and `-summary` for the rest if that reads better once real transcript
  text is in front of it). Each row: click sets `audio.currentTime` (seek); the row
  whose `[start_ms, end_ms)` contains the current `currentTime` gets
  **`aria-current="true"`** — not a bespoke highlight class, the vendored
  `.kt-row[aria-current="true"]` rule (champagne wash, green edge bar, bold green
  timestamp, §0.1) already does exactly this — and the virtualizer scrolls it into view
  as playback passes it (AL §2, §4.8). Both lists react to the same shared position, not
  two independent ones.

  **Resolved at implementation time — one shared `TimedList<T extends
  {start_ms, end_ms}>` component, not two.** `SegmentList`/`TurnList` turned out to be
  the same virtualizer/scroll/active-row/click-to-seek wiring with only the row's inner
  content differing — real duplication risk (subtly diverging virtualizer setups), not
  premature abstraction, so `TimedList` takes a `renderRow` render-prop instead. Segment
  rows use `.kt-row-summary` alone (no `.kt-row-title` line) — transcript text reads as
  body prose, not a heading. **A real CSS bug found here, worth flagging for any future
  virtualized list reusing `.kt-row[aria-current]`:** the scroll container needs
  `overflow-y: auto` to virtualize, but per the CSS Overflow spec, setting only one axis
  away from `visible` forces the *other* axis to `auto` too — silently clipping
  `.kt-row[aria-current]`'s own negative-margin "bleed to the card edge" (base.css) right
  at the scroll container's boundary, so the green edge bar just doesn't render (wash and
  bold timestamp still show, so it's easy to miss without literally sampling pixels).
  Fix: give the scroll container `margin-inline: calc(-1 * var(--kt-space-4))` +
  `padding-inline: var(--kt-space-4)` (cancels out visually, opens a same-size
  unclipped buffer for the bleed to land in, since overflow clips at the padding edge,
  not the content edge).
- `DiarizationTurn` rows show **two cues** (AL §2): the raw speaker label
  (`SPEAKER_00`, ...) rendered with `.kt-time` (mono, LTR-isolated — §0.1 corrects this
  from a plain `dir="ltr"` span) instead of Hebrew-styled text, and host-vs-not
  (computed client-side, §5.3) as a small `.kt-chip`-derived pill (the bundle's chip is
  built for topic tags, not a two-state boolean flag, but it's the closest existing
  "small labeled pill" primitive — reasonable to reuse rather than invent a new pill
  style for one boolean).
- **±15-minute jump control** — two `.kt-pill`-styled buttons (the same class the
  player's own skip-back-15 uses in the source design) above the lists, shared, not
  per-list: move `PlaybackContext`'s position by ±900s, which both the audio element and
  both virtualizers react to the same way a click-to-seek does (AL §4.8 — "jumping is
  just a coarser way of moving the same shared position").
- **Log view** — already built in Phase 3 (§4.7); wrap it in `.kt-card` for visual
  consistency with the rest of the page, no other changes here.

### 5.3 Host/not-host heuristic

Pure client-side function, `frontend/src/lib/hostHeuristic.ts`: sum duration
(`end_ms - start_ms`) per speaker label across all turns, the label with the largest
total is "host" (AL §4.7's starting rule, `design.md` §3's finding). Explicitly not
persisted anywhere (no new column, no write-back to `result_json`) — changing the rule
later is an edit to this one function, per AL §4.7's whole point.

### 5.4 Manual validation

Load a completed transcribe + diarize pair for the same lesson. Confirm: clicking a
transcript row seeks the player instantly with no reload; clicking a diarization turn
does the same; the currently-playing row in both lists highlights and scrolls into view
as playback proceeds unattended; the ±15-minute jump moves both lists and the player
together; the dominant speaker label is visibly marked as host and matches what's
audibly true on a lesson where that's easy to verify by ear. Test on a long (~2h) Q&A
lesson specifically, not just a short one — this is the case AL §4.8's virtual-scroll
design exists for, and it's also the concrete test of §5.2's tick-density question
(hundreds of segment ticks on the track vs. a handful of diarization turn ticks —
confirm which reads cleanly at that scale). Also confirm the player and lists visually
match `example-page.html`'s player/list-row treatment side by side — same
track/knob/tick colors, same active-row wash and edge bar.

---

## 6. Open questions carried from `admin-lab.md` §8

Not blocking, not resolved by this plan — flagged there, still true here: the
UI-prototyping gallery's actual content, Chainlit consistency for the (separate,
not-started) agentic search prototype, and the host-detection heuristic's correctness
(§5.3 fixes *how* it's shown, not whether total-duration-per-label is actually right —
expect it to change once diarization has run on more than one lesson).

Also open, from §0.1: the vendored bundle designs one page shape (lesson page) plus one
content+sidebar variant; nothing here has been checked against a real designer's eye,
only against the reference HTML. If a screen ends up looking meaningfully off once real
data is in it, that's a legitimate reason to go back to design rather than freelancing a
fix — the README says as much for user-facing pages, and the same caution is worth
extending to this tool's screens even though it's explicitly exempted from "careful"
visual design.

---

## 7. Related documents

- `documents/admin-lab.md` — the durable architecture reference this plan implements.
- `documents/admin.md` / `documents/plans/admin-updates-plan.md` — the Streamlit-era
  specs Phase 2 supersedes (§3.4).
- `documents/design.md` §3, §7, §8 — transcription/diarization model choices, the
  `lab` schema decision, and the lab's principles, all assumed rather than re-derived
  here.
- `../documentation/design/ui/README.md` — the visual design system (§0.1). Start there
  for anything styling-related; `tokens.css` and `base.css` are the values/patterns
  actually ported, `example-page.html` is the fidelity check.
- `../documentation/design/web-architecture.md` — the public site's stack (Django/
  django-ninja + React Router SSR), unrelated to this app's stack but the other
  consumer of the same design bundle — worth a skim if the two ever need to share
  frontend code (not currently planned).

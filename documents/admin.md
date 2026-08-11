# Kol Torah — Admin app

**Status:** Partially implemented — rabbi/series CRUD exists; lesson browsing and
drill-down navigation are planned (this document specs them; not yet built).
**Last updated:** 2026-08-11
**Code:** `src/data_pipelines/admin_app.py`

---

## 1. Purpose

A standalone Streamlit tool over the catalogue tables (`rabbis`, `series`, `lessons`) —
for entering rabbis/series by hand and for seeing where each series' lessons stand in the
discover/download/store pipeline. It talks directly to the production database.

**Not part of the lab** (`design.md` §8). The lab is a stateless viewer over the
experiment `runs` tables, built for comparing pipeline configurations across a small
lesson sample; the admin app is a viewer *and* editor over the live catalogue, with no
notion of a "run." The two share a stack (Streamlit) and nothing else — the admin app
imports nothing from the lab and vice versa.

Run with:

```bash
uv run streamlit run src/data_pipelines/admin_app.py
```

---

## 2. Current state (implemented)

Two tabs, both backed by a single SQLAlchemy `Session` opened per script run:

- **Rabbis** — table of all rabbis with a live series count per row; add/edit/delete
  forms. Delete is blocked while the rabbi still has series.
- **Series** — table of all series with rabbi, `lesson_type`, `adapter_key`, and a live
  lesson count per row; add/edit/delete forms. Delete is blocked while the series still
  has lessons.

Both tables already show the counts this document's planned work needs (§3) — what's
missing is turning a row into a link into the next level down, and the lessons level
itself doesn't exist yet.

---

## 3. Planned additions

### 3.1 Rabbi → series drill-down

Clicking a rabbi (or a "view series" affordance on its row) opens the Series view
pre-filtered to that rabbi, instead of the operator re-selecting the rabbi from the full
series list by hand.

### 3.2 Series → lessons drill-down, with per-lesson status

A new lessons view, reached from a series row: every lesson in that series, with its
title, `published_at`, and status.

**Status** is one of the three states in `database-schema.md` §4.5 — *discovered*,
*downloaded*, or *stored* — derived from whether the lesson has a `lesson_downloads` row
and/or an `audio_files` row. This view must compute status through the same shared
helper the discover pipeline stages use for their "needs download" / "needs store"
queries (`documents/pipelines/discover.md` §4–5), not re-derive the row-presence logic
independently — §4.5 is explicit that this is meant to exist in exactly one place. If
that helper doesn't already exist as a standalone, reusable function at the point this
view is built, extracting it is part of the work, not a follow-up.

A lesson with neither row is *discovered*; one with only `lesson_downloads` is
*downloaded*; one with `audio_files` is *stored*. There is no fourth, *failed* state to
show yet — see §5.

### 3.3 Navigation mechanism

Streamlit reruns the whole script top-to-bottom on every interaction and holds no state
across a browser reload (`design.md` §8.1 notes the same constraint for the lab). Two
ways to carry "which rabbi / which series am I drilled into" across that:

- `st.query_params` — the selected id lives in the URL, so a drill-down link is a real
  link (shareable, survives reload) and the page reruns read the id back out at the top.
- Streamlit's native multi-page support (`st.navigation` / a `pages/` directory) — gives
  each level its own page/URL path, with ids still passed as query params between them.

Given the app is only ever three levels deep (rabbis → series → lessons), either is
workable; the query-param approach needs no restructuring of the existing single-file
tab layout, while multi-page is the more idiomatic fit if the app grows further. Pick one
when this is implemented rather than mixing both.

### 3.4 Reset All Lessons

A destructive action on the series-detail view (§3.2): deletes every lesson row for that
series, via the same `delete_series_lessons()` function
`pipelines/discover/reset_series.py`'s CLI already uses — called directly, not shelled
out to as a subprocess. The bucket is untouched, exactly as the CLI documents, which
means a subsequent discover run reconstructs `audio_files` rows via bucket recovery
(`documents/pipelines/discover.md` §4.1) rather than re-downloading. Needs an explicit
confirmation step in the UI in place of the CLI's `--yes`/prompt gate — see
`documents/plans/admin-updates-plan.md` §5 for the concrete flow.

### 3.5 Visual theme

Colors only, borrowed from `../documentation/design/kol-torah-design-spec.md` (the
shared public-site/admin-CMS design system) via Streamlit's built-in `[theme]` config —
not full adoption. That spec's "Admin panel" is the public web tier's staff CMS
(`../documentation/design/web-architecture.md`), a different surface and stack from this
tool; fonts, RTL layout, and hairline/chip component specs stay there. See
`documents/plans/admin-updates-plan.md` §6 for exactly which tokens map to which
Streamlit theme keys and what's deliberately left out.

---

## 4. Deliberately out of scope for now

- **Editing lesson content** (title/description translation, `lesson_type` override,
  etc.). This view is for status visibility, not lesson data entry — lessons are written
  by the discover pipeline, not by hand.
- **Failed-attempt visibility.** A lesson whose download or store attempt failed is
  indistinguishable from one never attempted — no row records a failure yet
  (`database-schema.md` §5's known gap on `lesson_downloads`). Showing "failed" in this
  view needs that gap closed first (an explicit signal, or the deferred `stage_runs`
  table), not a workaround here.
- **Auth.** The lab has Google OIDC on its roadmap (`design.md` §8.2); the admin app has
  none today. It runs as a local/internal tool. Worth revisiting if it's ever exposed
  beyond that.

---

## 5. Related documents

- `documents/design.md` §8 — the lab, for contrast with this app's model.
- `documents/database-schema.md` §3 (tables), §4.5 (status derivation) — the data this
  app reads and, for rabbis/series, writes.
- `documents/pipelines/discover.md` §4–5 — the pipeline stages whose row-presence checks
  this app's status view must match, not reinvent; also `reset_series.py`, reused by §3.4.
- `../documentation/design/kol-torah-design-spec.md` — the design system §3.5 borrows a
  handful of color tokens from.
- `documents/plans/admin-updates-plan.md` — the concrete build plan for everything in §3.

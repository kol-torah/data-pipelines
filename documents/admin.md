# Kol Torah — Admin app (removed)

**Status: removed — there is no Streamlit admin app in this repo.**
**Removed:** 2026-08-17
**Code:** none. `src/data_pipelines/admin_app.py` and the `streamlit` dependency are
deleted; nothing in the codebase imports Streamlit.

This document used to spec a standalone Streamlit tool over the catalogue tables
(`rabbis`, `series`, `lessons`) — rabbi/series CRUD, plus a planned lessons drill-down
with per-lesson status and a "Reset All Lessons" action. **Don't go looking for that
code or those screens under that name.** It is kept here only so that references to
`admin.md` from older documents resolve to an explanation rather than a dead link; the
full historical text is in git history.

## What replaced it

Everything the admin app did — and everything §3 of the old version planned but never
built — now lives in the combined admin/lab tool:

- `documents/admin-lab.md` — the durable reference for that tool (React frontend +
  FastAPI backend). §1.2 explains why Streamlit was dropped; §1.4 covers the
  supersession of this document specifically.
- `documents/plans/implemented/admin-lab-plan.md` §3 — the build plan for the catalogue
  admin screens, as implemented.
- Code: `frontend/src/pages/{RabbisPage,SeriesPage,SeriesDetailPage}.tsx`,
  `src/data_pipelines/admin_lab_api/routers/catalogue.py`, and
  `src/data_pipelines/db/status.py` (the lesson-status helper this document's §3.2 asked
  for).

## Things this document used to be the reference for

- **Lesson status derivation** (*discovered* / *downloaded* / *stored*) —
  `documents/database-schema.md` §4.5 is the durable statement; the shared helper is
  `src/data_pipelines/db/status.py`.
- **Reset All Lessons** — still `delete_series_lessons()` in
  `src/data_pipelines/pipelines/discover/reset_series.py`, called directly by the
  catalogue router and still available as a CLI.
- **Visual theme** — the app now uses the design bundle vendored from
  `../documentation/design/ui/` (see `admin-lab.md` and the implemented plan's §0.1),
  not a handful of Streamlit theme colors.
- **Auth** — still none; the tool runs locally for one operator
  (`documents/design.md` §8.2, `admin-lab.md` §1.3).

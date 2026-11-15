# Plan: admin app — drill-down navigation, lesson status, series reset

**Status: superseded.** These three features (drill-down navigation, lesson status,
series reset) were built against the Streamlit `admin_app.py` this plan specced, but
`admin_app.py` was retired before that happened.
`documents/plans/implemented/admin-lab-plan.md` Phase 2 (§3) absorbed this work directly
into the new React/FastAPI admin tool instead —
see `src/data_pipelines/db/status.py` (§3 below, implemented verbatim) and
`src/data_pipelines/admin_lab_api/routers/catalogue.py`. Kept here for historical
context only; no longer updated as the code evolves.
**Code to touch:** `src/data_pipelines/admin_app.py`; reuses
`src/data_pipelines/pipelines/discover/reset_series.py` unchanged.

This is the concrete build plan. `documents/admin.md` is the durable reference for *why*
each piece exists and stays up to date as the code evolves; this document is a snapshot
of *how* to build it and is expected to go stale once implemented, same as
`documents/plans/implemented/adapters-plan.md`.

---

## 1. Scope

Three additions to the existing Rabbis/Series CRUD app (`documents/admin.md` §2–3):

1. Rabbi → series drill-down navigation.
2. A **series detail page**: one series, its lessons, each lesson's status.
3. A **Reset All Lessons** button on that series detail page, deleting every lesson row
   for that series.

Series → series-detail navigation (item 4 of the original ask, "how many lessons a
series has" plus a page listing them) falls out of items 1–2 using the same mechanism.

---

## 2. Page structure

Replace the current two `st.tabs` with three pages via `st.navigation`/`st.Page`, kept as
functions in the same file (no need to split into a `pages/` directory — `st.Page`
accepts a callable directly):

| Page             | Function              | Shows                                                    |
| ---------------- | ---------------------- | ---------------------------------------------------------- |
| Rabbis            | `rabbis_page()`         | today's Rabbis tab, unchanged, plus a drill-down per row    |
| Series            | `series_page()`         | today's Series tab, unchanged, plus a drill-down per row + optional rabbi filter |
| Series detail     | `series_detail_page()`  | **new** — one series' lessons, their status, the reset button |

`series_detail_page` is not in the nav bar directly — it's only reached by drilling in
from `series_page` (or a link from `rabbis_page` → `series_page` → `series_detail_page`),
the same way the existing app has no standalone "edit rabbi" page, just an expander
reached from the Rabbis tab.

### 2.1 Carrying the selected id

Row selection uses `st.dataframe(..., on_select="rerun", selection_mode="single-row")`
(available since Streamlit 1.35; this repo pins `streamlit>=1.61.1`, confirmed installed
at 1.61.1). On selection:

- `rabbis_page`: set `st.query_params["rabbi_id"]`, `st.switch_page` to `series_page`.
- `series_page`: set `st.query_params["series_id"]`, `st.switch_page` to
  `series_detail_page`.

`series_page` reads `st.query_params.get("rabbi_id")` at the top, if present, to
pre-filter its table to that rabbi's series (with a visible "showing series for {rabbi}
— clear filter" control, since arriving from a link shouldn't silently hide the rest of
the catalogue with no way back). Query params, not `st.session_state`, because they
survive a reload and make the drilled-down view linkable — consistent with
`documents/admin.md` §3.3's choice of query params over session state.

`series_detail_page` reads `st.query_params["series_id"]`; if absent (someone opens
the page directly with no id), show a message pointing back to the Series page rather
than erroring.

---

## 3. Lesson status helper

New module `src/data_pipelines/db/status.py` (alongside `models.py`, so both
`admin_app.py` and any pipeline code can import it without a new dependency direction):

```python
from enum import StrEnum

from data_pipelines.db.models import Lesson


class LessonStatus(StrEnum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    STORED = "stored"


def lesson_status(lesson: Lesson) -> LessonStatus:
    if lesson.audio_file is not None:
        return LessonStatus.STORED
    if lesson.download is not None:
        return LessonStatus.DOWNLOADED
    return LessonStatus.DISCOVERED
```

This is the canonical statement of `database-schema.md` §4.5's three states, in code.
`Lesson.audio_file` and `Lesson.download` are existing relationships (`db/models.py`) —
no new query logic, just wrapping the existing presence check in a named enum instead of
leaving it implicit at each call site.

**Not touching `s02_download.py` / `s03_store.py`.** Those stages filter "needs
download" / "needs store" as set-level SQL (`WHERE ... IS NULL`) across every lesson in a
series in one query — a different granularity than a per-row Python check, and correct
today. `database-schema.md` §4.5 asks for one *definition* of the three states, which
this module now is; it doesn't require the SQL-level filters and this per-lesson helper
to share literal code. Forcing that would mean touching pipeline stages for a UI-only
change — out of scope here.

**N+1 note for the lessons query:** `series_detail_page` loads every lesson for one
series and calls `lesson_status()` per row, which touches `audio_file` and `download` —
query with `selectinload(Lesson.audio_file)` / `selectinload(Lesson.download)` so that's
two extra queries total, not two per lesson.

---

## 4. `series_detail_page`

For the series read from `series_id`:

- Header: series name (he/en), rabbi (linking back to `rabbis_page`, same drill-down
  mechanism as §2.1), `lesson_type`, `adapter_key`.
- Table of lessons: `title_he`, `title_en`, `published_at`, `discovered_at`, **Status**
  (from §3), sorted by `discovered_at` descending (newest first — matches what an
  operator checking on a recent discover run wants to see).
- The **Reset All Lessons** button (§5), placed below the table, visually separated
  (e.g. its own `st.container` with a border, or pushed to an expander titled "Danger
  zone") so it doesn't read as part of the normal browsing flow.

---

## 5. Reset All Lessons

Reuses `delete_series_lessons(session, series) -> int` from
`pipelines/discover/reset_series.py` directly — it's already a plain function taking a
`Session` and a `Series`, with no CLI or subprocess coupling, so `series_detail_page`
just imports and calls it.

The CLI version requires typing `--yes` or answering a blocking `input()` prompt before
deleting — Streamlit has no blocking prompt, so the two-step confirmation has to be built
out of two reruns:

1. Click **"Reset All Lessons"** → set `st.session_state["confirm_reset"] = True`,
   rerun.
2. While that flag is set, show the lesson count and the same warning the CLI prints
   ("delete N lessons for `{slug}` (and their audio_files/lesson_downloads/
   lesson_duplicates rows)? The S3 bucket is not touched.") plus two buttons: **"Yes,
   delete N lessons"** (`type="primary"`) and **"Cancel"**.
3. **"Yes, ..."** calls `delete_series_lessons`, clears the flag, `st.rerun()`s into the
   now-empty lesson table with a success message repeating the deleted count and the
   "bucket not touched" note (an operator who doesn't know that will expect the next
   discover run to re-download, when it'll actually hit bucket recovery, per
   `discover.md` §4.1 — worth surfacing right there, not just in the docs). **"Cancel"**
   just clears the flag and reruns.

No `--yes`-equivalent skip in the UI — the two-click confirm *is* the UI's version of the
CLI's prompt, and there's no scripted/unattended path through the admin app that would
need one.

---

## 6. Visual theme — light-touch tokens from `kol-torah-design-spec.md`

`../documentation/design/kol-torah-design-spec.md` defines the shared design system for
the public site and **its** admin panel — but that "admin panel" is the public web
tier's staff CMS (`../documentation/design/web-architecture.md`, React Router SSR +
Django), a different surface, stack, and audience from this Streamlit ops tool. Full
adoption (Bellefair/Heebo, RTL layout, hairline component specs, status-chip components)
doesn't belong here. What's cheap and worth doing: pointing this app's color scheme at
the same tokens, via Streamlit's built-in theme config — no custom CSS/HTML injection,
no font loading.

Add `.streamlit/config.toml` (new file — doesn't exist today):

```toml
[theme]
base = "light"
primaryColor = "#5A6B3C"              # design-spec --accent (olive)
backgroundColor = "#FEFDF9"           # design-spec --adm-bg (admin content surface)
secondaryBackgroundColor = "#EEEBDF"  # design-spec --adm-side
textColor = "#34362E"                 # design-spec --text
borderColor = "rgba(30, 32, 25, 0.13)" # design-spec --hair

[theme.sidebar]
backgroundColor = "#EEEBDF"           # design-spec --adm-side, matches secondaryBackgroundColor
```

Confirmed available on the installed Streamlit (1.61.1): `theme.base`, `.primaryColor`,
`.backgroundColor`, `.secondaryBackgroundColor`, `.textColor`, `.borderColor`,
`.baseRadius`, `.font`/`.fontFaces`, and a `[theme.sidebar]` sub-section — verify the
exact accepted value syntax for `borderColor` (hex vs `rgba(...)`) and `baseRadius`
against Streamlit's theming docs when this is implemented, since that wasn't checked
against a running app, only against the config schema.

Left out deliberately, as beyond "light touch": custom fonts (`--adm-side` etc. assume
Bellefair/Heebo, which aren't loaded anywhere in this app and would need `fontFaces` +
`@font-face`, closer to full adoption than a color borrow); RTL layout (Streamlit's own
chrome — nav, buttons, sidebar — isn't mirrored by this config, and mirroring only
Hebrew-field text without the surrounding chrome would look inconsistent, not better);
hairline borders/status-chip components (`--hair`, `--live-bg`) beyond what
`borderColor` already gives for free.

**Status colors (§4's lesson table).** The design spec's chip pattern (§6.4: accent
background/text for "published," muted for "draft") doesn't map cleanly onto three
states with no notion of "published" — reusing it verbatim would misapply vocabulary
CLAUDE.md and `admin.md` are careful about elsewhere. Simplest borrow that stays
consistent with the rest of this section: render the **Status** column as plain text
(`st.dataframe`'s default), not colored chips — Streamlit's `st.dataframe` doesn't offer
per-cell background styling without a `pandas.Styler` (more CSS-adjacent machinery than
"light touch" calls for). If status needs to be visually scannable later, `st.badge` per
row (native Streamlit widget with color support, no injected CSS) done in a
`st.dataframe`-free, one-row-per-widget layout is the next thing to reach for — not part
of this pass.

---

## 7. Out of scope (unchanged from `documents/admin.md` §4)

Lesson content editing, failed-attempt status, and auth remain deferred for the reasons
already documented there — this plan doesn't revisit them.

---

## 8. Manual validation

Since this is a UI change, verify by running the app (`uv run streamlit run
src/data_pipelines/admin_app.py`) against a real series with a mix of discovered/
downloaded/stored lessons (or a freshly-reset one re-run through stage 1 only, for a
quick all-"discovered" series) and walking:

- Rabbis page → drill into a rabbi → Series page pre-filtered, filter clearable.
- Series page → drill into a series → Series detail page, lesson count matches the
  Series page's count for that row, statuses match what's actually in the DB
  (`lesson_downloads`/`audio_files` rows) for a couple of spot-checked lessons.
- Reset All Lessons: cancel path leaves lessons untouched; confirm path deletes them,
  count in the success message matches, and a re-run of `s01_discover` for that series
  repopulates it (confirming nothing else broke).
- Theme (§6): colors match the config values above, sidebar is visibly distinct from the
  content area, default widget text stays legible against `backgroundColor` (spot-check
  contrast — `kol-torah-design-spec.md` §9 flags `--muted` as failing AA for body text;
  don't let that value leak into anywhere Streamlit renders default-weight text).

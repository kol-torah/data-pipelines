# Kol Torah — admin/lab frontend

React + Vite + Tailwind v4, RTL-first. See `documents/admin-lab.md` and
`documents/plans/implemented/admin-lab-plan.md` (repo root) for the why; this file is
just the dev-loop mechanics.

## Running locally

Two processes, both needed:

```sh
uv run uvicorn data_pipelines.admin_lab_api.main:app --reload --port 8000   # from repo root
pnpm --dir frontend dev
```

Vite's dev server proxies `/api/*` to the backend (`vite.config.ts`), so the frontend
talks to `/api/...` with no CORS setup needed.

## RTL rule

Never use Tailwind's directional utilities (`ml-*`, `mr-*`, `pl-*`, `pr-*`, `left-*`,
`right-*`, `text-left`, `text-right`) — always the logical equivalents (`ms-*`, `me-*`,
`ps-*`, `pe-*`, `start-*`, `end-*`). They map to CSS logical properties and flip
automatically with `dir`, matching the vendored `base.css`'s own convention. See
`documents/plans/implemented/admin-lab-plan.md` §2.2.

## Styling

`src/styles/kt/` is vendored verbatim from `../documentation/design/ui/` — don't edit
those files directly; re-sync by re-copying from the source repo instead. App-specific
additions (table rows, form inputs — gaps the vendored bundle doesn't cover) go in a
separate `src/styles/kt/admin.css`, not mixed into the vendored copies.

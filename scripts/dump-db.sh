#!/usr/bin/env bash
# Dumps the kol_torah database for backup (design.md §7.3).
#
# Writes two files to OUTPUT_DIR (default: data/backups/scheduled):
#   kol_torah-public.dump  pg_dump custom format, `public` schema only — the `lab`
#                          schema is disposable by design (§7.1) and deliberately skipped.
#   lessons.yaml           export_lessons snapshot: schema-shaped rather than
#                          schema-coupled, so it stays usable after a migration that
#                          would make the dump awkward to restore.
#
# Filenames are fixed, not timestamped: history is the job of whatever backs this
# directory up (the machine-wide restic backup), and fixed names let it deduplicate.
#
# pg_dump runs inside the container over the local socket, using the container's own
# POSTGRES_USER/POSTGRES_DB, so this script never handles the password.
#
# Run as a user in the `docker` group (not root — `uv run` would leave root-owned files
# in .venv). Exits non-zero if either step fails.
#
# Restore into an empty database (e.g. a fresh container, whose init script has already
# created the database and the vector extension):
#   docker compose exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < kol_torah-public.dump

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-$REPO_ROOT/data/backups/scheduled}"
mkdir -p "$OUTPUT_DIR"

compose() {
	docker compose --project-directory "$REPO_ROOT" "$@"
}

if [[ -z "$(compose ps --status running -q postgres)" ]]; then
	echo "dump-db: postgres container is not running" >&2
	exit 1
fi

dump="$OUTPUT_DIR/kol_torah-public.dump"
compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -n public -Fc' >"$dump.tmp"
# A dump that pg_restore can't list is not a backup.
compose exec -T postgres pg_restore --list <"$dump.tmp" >/dev/null
mv "$dump.tmp" "$dump"
echo "dump-db: wrote $dump ($(du -h "$dump" | cut -f1))"

uv="$(command -v uv || echo "$HOME/.local/bin/uv")"
(cd "$REPO_ROOT" && "$uv" run --no-sync python -m data_pipelines.catalogue.export_lessons --output "$OUTPUT_DIR/lessons.yaml")

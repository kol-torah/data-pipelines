#!/bin/bash
# Runs once, on an empty data directory. Creates the lab database alongside the
# production one (design.md 7.1) and enables pgvector in both.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
	-c "CREATE DATABASE \"$LAB_DB\" OWNER \"$POSTGRES_USER\";"

for db in "$POSTGRES_DB" "$LAB_DB"; do
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" \
		-c "CREATE EXTENSION IF NOT EXISTS vector;"
done

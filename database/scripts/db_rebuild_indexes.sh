#!/usr/bin/env bash
# Bezpieczny REINDEX PostgreSQL przez reindexdb (bez składania SQL ze stringów).
# Usage: ./db_rebuild_indexes.sh -u USER -d DATABASE [-h HOST] [-p PORT] [-t TABLE]

set -euo pipefail

DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_USER=""
DB_NAME=""
TARGET_TABLE=""

die() { echo "ERROR: $*" >&2; exit 1; }
valid_identifier() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; }

while getopts ":u:d:h:p:t:" opt; do
    case "$opt" in
        u) DB_USER="$OPTARG" ;;
        d) DB_NAME="$OPTARG" ;;
        h) DB_HOST="$OPTARG" ;;
        p) DB_PORT="$OPTARG" ;;
        t) TARGET_TABLE="$OPTARG" ;;
        *) die "Niepoprawne argumenty" ;;
    esac
done

command -v reindexdb >/dev/null || die "Brak reindexdb w PATH"
valid_identifier "$DB_USER" || die "Niepoprawna nazwa użytkownika"
valid_identifier "$DB_NAME" || die "Niepoprawna nazwa bazy"
[[ -z "$TARGET_TABLE" ]] || valid_identifier "$TARGET_TABLE" || die "Niepoprawna nazwa tabeli"
[[ "$DB_PORT" =~ ^[0-9]{1,5}$ ]] || die "Niepoprawny port"
[[ -t 0 ]] || die "Hasło musi zostać podane w interaktywnym terminalu"
read -r -s -p "PostgreSQL password for '$DB_USER': " PGPASSWORD </dev/tty
echo
export PGPASSWORD
trap 'unset PGPASSWORD' EXIT INT TERM

args=(--host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$DB_NAME" --verbose)
if [[ -n "$TARGET_TABLE" ]]; then
    args+=(--table="$TARGET_TABLE")
fi
reindexdb "${args[@]}"

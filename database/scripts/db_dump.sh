#!/usr/bin/env bash
# Bezpieczny dump PostgreSQL w formacie custom (.dump).
# Usage: ./db_dump.sh -u USER -d DATABASE [-h HOST] [-p PORT] [-o DIR]

set -euo pipefail

DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_USER=""
DB_NAME=""
OUTPUT_DIR="./dumps"

die() { echo "ERROR: $*" >&2; exit 1; }
valid_identifier() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; }

while getopts ":u:d:h:p:o:" opt; do
    case "$opt" in
        u) DB_USER="$OPTARG" ;;
        d) DB_NAME="$OPTARG" ;;
        h) DB_HOST="$OPTARG" ;;
        p) DB_PORT="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
        *) die "Niepoprawne argumenty" ;;
    esac
done

command -v pg_dump >/dev/null || die "Brak pg_dump w PATH"
valid_identifier "$DB_USER" || die "Niepoprawna nazwa użytkownika"
valid_identifier "$DB_NAME" || die "Niepoprawna nazwa bazy"
[[ "$DB_PORT" =~ ^[0-9]{1,5}$ ]] || die "Niepoprawny port"
[[ -t 0 ]] || die "Hasło musi zostać podane w interaktywnym terminalu"
read -r -s -p "PostgreSQL password for '$DB_USER': " PGPASSWORD </dev/tty
echo
export PGPASSWORD
trap 'unset PGPASSWORD; [[ -n "${PARTIAL_FILE:-}" && -f "$PARTIAL_FILE" ]] && rm -f -- "$PARTIAL_FILE"' EXIT INT TERM

mkdir -p -- "$OUTPUT_DIR"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
DUMP_FILE="${OUTPUT_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
PARTIAL_FILE="${DUMP_FILE}.partial"

pg_dump \
    --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
    --format=custom --compress=9 --no-owner --no-acl \
    --file="$PARTIAL_FILE" "$DB_NAME"
mv -- "$PARTIAL_FILE" "$DUMP_FILE"
PARTIAL_FILE=""
echo "Dump zapisany: $DUMP_FILE"

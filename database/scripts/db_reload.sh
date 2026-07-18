#!/usr/bin/env bash
# Destrukcyjne odtworzenie PostgreSQL z pliku custom utworzonego przez db_dump.sh.
# Usage: ./db_reload.sh -u USER -d DATABASE -f FILE [-h HOST] [-p PORT] [-y]

set -euo pipefail

DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_USER=""
DB_NAME=""
DUMP_FILE=""
SKIP_CONFIRM=false

die() { echo "ERROR: $*" >&2; exit 1; }
valid_identifier() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; }

while getopts ":u:d:f:h:p:y" opt; do
    case "$opt" in
        u) DB_USER="$OPTARG" ;;
        d) DB_NAME="$OPTARG" ;;
        f) DUMP_FILE="$OPTARG" ;;
        h) DB_HOST="$OPTARG" ;;
        p) DB_PORT="$OPTARG" ;;
        y) SKIP_CONFIRM=true ;;
        *) die "Niepoprawne argumenty" ;;
    esac
done

for binary in pg_restore dropdb createdb; do
    command -v "$binary" >/dev/null || die "Brak $binary w PATH"
done
valid_identifier "$DB_USER" || die "Niepoprawna nazwa użytkownika"
valid_identifier "$DB_NAME" || die "Niepoprawna nazwa bazy"
[[ "$DB_PORT" =~ ^[0-9]{1,5}$ ]] || die "Niepoprawny port"
[[ -f "$DUMP_FILE" && -s "$DUMP_FILE" ]] || die "Brak lub pusty dump"
pg_restore --list "$DUMP_FILE" >/dev/null || die "Uszkodzony lub nieobsługiwany dump"

if [[ "$SKIP_CONFIRM" == false ]]; then
    [[ -t 0 ]] || die "Brak interaktywnego terminala; użyj -y świadomie"
    echo "UWAGA: baza '$DB_NAME' zostanie trwale usunięta i odtworzona."
    read -r -p "Wpisz nazwę bazy, aby potwierdzić: " CONFIRM </dev/tty
    [[ "$CONFIRM" == "$DB_NAME" ]] || die "Anulowano"
fi

[[ -t 0 ]] || die "Hasło musi zostać podane w interaktywnym terminalu"
read -r -s -p "PostgreSQL password for '$DB_USER': " PGPASSWORD </dev/tty
echo
export PGPASSWORD
trap 'unset PGPASSWORD' EXIT INT TERM

dropdb --if-exists --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" "$DB_NAME"
createdb --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" "$DB_NAME"
pg_restore \
    --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
    --dbname="$DB_NAME" --exit-on-error --no-owner --no-acl "$DUMP_FILE"
echo "Baza '$DB_NAME' została odtworzona."

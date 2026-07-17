-- Barcode per wersja językowa gry, z kolejką moderacji community.
-- Stara kolumna games.barcode nie zawierała języka. Nie zgadujemy wersji:
-- migracja zatrzymuje się, jeśli zawiera dane wymagające ręcznej klasyfikacji.

BEGIN;

CREATE TABLE IF NOT EXISTS game_barcodes (
    id              SERIAL PRIMARY KEY,
    public_id       UUID NOT NULL UNIQUE,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    barcode         VARCHAR(13) NOT NULL UNIQUE,
    language_code   VARCHAR(2) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    source          VARCHAR(20) NOT NULL DEFAULT 'community',
    created_by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at     TIMESTAMPTZ,
    CONSTRAINT ck_game_barcodes_status CHECK (status IN ('pending', 'approved')),
    CONSTRAINT ck_game_barcodes_source CHECK (source IN ('community', 'legacy')),
    CONSTRAINT ck_game_barcodes_language CHECK (language_code IN ('pl', 'en')),
    CONSTRAINT ck_game_barcodes_format CHECK (
        barcode ~ '^([0-9]{8}|[0-9]{12}|[0-9]{13})$'
    ),
    CONSTRAINT uq_game_barcodes_game_language_status
        UNIQUE (game_id, language_code, status)
);

DO $$
DECLARE
    has_unclassified_barcode BOOLEAN;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'games'
          AND column_name = 'barcode'
    ) THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM games WHERE barcode IS NOT NULL)'
            INTO has_unclassified_barcode;
        IF has_unclassified_barcode THEN
            RAISE EXCEPTION
                'games.barcode zawiera wartości bez języka; przypisz je ręcznie do pl/en przed migracją';
        END IF;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_game_barcodes_game_id ON game_barcodes(game_id);
CREATE INDEX IF NOT EXISTS ix_game_barcodes_status ON game_barcodes(status);

DROP INDEX IF EXISTS ix_games_barcode;
ALTER TABLE games DROP COLUMN IF EXISTS barcode;

COMMIT;

-- Ogranicza język barcode do aktualnie obsługiwanych wersji: polskiej i angielskiej.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM game_barcodes WHERE language_code NOT IN ('pl', 'en')
    ) THEN
        RAISE EXCEPTION
            'game_barcodes zawiera język spoza pl/en; sklasyfikuj rekordy przed migracją';
    END IF;
END
$$;

ALTER TABLE game_barcodes
    DROP CONSTRAINT IF EXISTS ck_game_barcodes_language;

ALTER TABLE game_barcodes
    ALTER COLUMN language_code TYPE VARCHAR(2);

ALTER TABLE game_barcodes
    ADD CONSTRAINT ck_game_barcodes_language
    CHECK (language_code IN ('pl', 'en'));

COMMIT;

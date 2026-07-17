-- Ujednolica format barcode z API i ORM: wyłącznie EAN-8, UPC-A oraz EAN-13.
-- Migracja jest potrzebna dla baz, na których wykonano już 0003.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM game_barcodes
        WHERE barcode !~ '^([0-9]{8}|[0-9]{12}|[0-9]{13})$'
    ) THEN
        RAISE EXCEPTION
            'game_barcodes zawiera barcode spoza EAN-8, UPC-A lub EAN-13; popraw dane przed migracją';
    END IF;
END
$$;

ALTER TABLE game_barcodes
    DROP CONSTRAINT IF EXISTS ck_game_barcodes_format;

ALTER TABLE game_barcodes
    ADD CONSTRAINT ck_game_barcodes_format
    CHECK (barcode ~ '^([0-9]{8}|[0-9]{12}|[0-9]{13})$');

COMMIT;

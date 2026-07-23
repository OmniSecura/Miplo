-- Lekkie tekstury pseudo-3D publikowane atomowo z zaakceptowanym modelem GLB.

BEGIN;

ALTER TABLE games
    ADD COLUMN IF NOT EXISTS box_face_front_url VARCHAR(500),
    ADD COLUMN IF NOT EXISTS box_face_side_url VARCHAR(500),
    ADD COLUMN IF NOT EXISTS box_face_top_url VARCHAR(500);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_games_box_face_urls_complete'
          AND conrelid = 'games'::regclass
    ) THEN
        ALTER TABLE games
            ADD CONSTRAINT ck_games_box_face_urls_complete CHECK (
                (
                    box_face_front_url IS NULL
                    AND box_face_side_url IS NULL
                    AND box_face_top_url IS NULL
                )
                OR
                (
                    box_face_front_url IS NOT NULL
                    AND box_face_side_url IS NOT NULL
                    AND box_face_top_url IS NOT NULL
                )
            );
    END IF;
END
$$;

COMMIT;

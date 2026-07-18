-- Półka użytkownika: własność egzemplarza, wypożyczanie i prywatne notatki.

BEGIN;

CREATE TABLE IF NOT EXISTS shelf_items (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id          INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    lendable         BOOLEAN NOT NULL DEFAULT FALSE,
    lending_deposit  NUMERIC(7,2),
    lending_notes    TEXT,
    condition        VARCHAR(20),
    notes            TEXT,
    added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_shelf_items_user_game UNIQUE (user_id, game_id),
    CONSTRAINT ck_shelf_items_condition CHECK (
        condition IS NULL OR condition IN ('new', 'good', 'used', 'damaged')
    ),
    CONSTRAINT ck_shelf_items_deposit CHECK (
        lending_deposit IS NULL OR lending_deposit BETWEEN 0 AND 9999
    ),
    CONSTRAINT ck_shelf_items_lending_notes_length CHECK (
        lending_notes IS NULL OR length(lending_notes) <= 500
    ),
    CONSTRAINT ck_shelf_items_notes_length CHECK (
        notes IS NULL OR length(notes) <= 500
    )
);

CREATE INDEX IF NOT EXISTS ix_shelf_items_user_id
    ON shelf_items(user_id);
CREATE INDEX IF NOT EXISTS ix_shelf_items_game_lendable
    ON shelf_items(game_id, lendable);

COMMIT;

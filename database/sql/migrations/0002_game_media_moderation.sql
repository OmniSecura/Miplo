-- PostgreSQL 15+ — rozszerzenie istniejącej bazy o moderację i media gier.
-- Uruchom kontrolowanie raz; przed produkcją wykonaj backup.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE games
    ADD COLUMN IF NOT EXISTS cover_candidate_path VARCHAR(500),
    ADD COLUMN IF NOT EXISTS model_candidate_path VARCHAR(500),
    ADD COLUMN IF NOT EXISTS model_job_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS model_submitted_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS model_is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS model_submitted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS community_contributions_enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE games DROP CONSTRAINT IF EXISTS ck_games_model_status;
ALTER TABLE games ADD CONSTRAINT ck_games_model_status CHECK (
    model_status IS NULL OR model_status IN (
        'pending', 'processing', 'awaiting_review', 'ready', 'failed'
    )
);

CREATE INDEX IF NOT EXISTS ix_games_model_job_id ON games(model_job_id);

CREATE TABLE IF NOT EXISTS game_images (
    id              SERIAL PRIMARY KEY,
    public_id       UUID NOT NULL UNIQUE,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    storage_path    VARCHAR(500) NOT NULL,
    image_url       VARCHAR(500),
    caption         VARCHAR(120),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_game_images_status CHECK (status IN ('pending', 'approved'))
);

CREATE INDEX IF NOT EXISTS ix_game_images_game_id ON game_images(game_id);
CREATE INDEX IF NOT EXISTS ix_game_images_status ON game_images(status);

-- Pierwszego administratora nadaj ręcznie po firebase_uid lub tagu, np.:
-- UPDATE users SET is_admin = TRUE WHERE tag = 'twoj_tag';

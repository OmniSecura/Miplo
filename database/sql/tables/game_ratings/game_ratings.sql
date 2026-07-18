-- Miplo / PostgreSQL 15+
-- Oceny społeczności oraz zgłoszenia recenzji.

CREATE TABLE IF NOT EXISTS game_ratings (
    id                  SERIAL PRIMARY KEY,
    public_id           UUID NOT NULL UNIQUE,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id             INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    rating              NUMERIC(3,1) NOT NULL,
    review              TEXT,
    contains_spoilers   BOOLEAN NOT NULL DEFAULT FALSE,
    source              VARCHAR(20) NOT NULL DEFAULT 'miplo',
    is_hidden           BOOLEAN NOT NULL DEFAULT FALSE,
    hidden_reason       VARCHAR(200),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_user_game_rating UNIQUE (user_id, game_id),
    CONSTRAINT ck_game_ratings_value CHECK (
        rating BETWEEN 1 AND 10 AND MOD(rating * 2, 1) = 0
    ),
    CONSTRAINT ck_game_ratings_source CHECK (source IN ('miplo', 'bgg_import')),
    CONSTRAINT ck_game_ratings_review_length CHECK (
        review IS NULL OR length(review) <= 5000
    ),
    CONSTRAINT ck_game_ratings_hidden_reason_length CHECK (
        hidden_reason IS NULL OR length(hidden_reason) <= 200
    )
);

CREATE TABLE IF NOT EXISTS review_reports (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating_id   INTEGER NOT NULL REFERENCES game_ratings(id) ON DELETE CASCADE,
    reason      VARCHAR(20) NOT NULL,
    details     TEXT,
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_user_review_report UNIQUE (user_id, rating_id),
    CONSTRAINT ck_review_reports_reason CHECK (
        reason IN ('spam', 'offensive', 'spoilers', 'off_topic')
    ),
    CONSTRAINT ck_review_reports_details_length CHECK (
        details IS NULL OR length(details) <= 500
    )
);

CREATE INDEX IF NOT EXISTS ix_ratings_user_id ON game_ratings(user_id);
CREATE INDEX IF NOT EXISTS ix_ratings_game_id ON game_ratings(game_id);
CREATE INDEX IF NOT EXISTS ix_ratings_game_rating ON game_ratings(game_id, rating);
CREATE INDEX IF NOT EXISTS ix_ratings_game_created
    ON game_ratings(game_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_review_reports_user_id ON review_reports(user_id);
CREATE INDEX IF NOT EXISTS ix_review_reports_rating_id ON review_reports(rating_id);
CREATE INDEX IF NOT EXISTS ix_review_reports_rating_resolved
    ON review_reports(rating_id, resolved);

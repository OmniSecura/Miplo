-- Miplo / PostgreSQL 15+
-- Cache BoardGameGeek oraz gry customowe społeczności.

CREATE TABLE IF NOT EXISTS game_types (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(100) NOT NULL UNIQUE,
    slug    VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS games (
    id              SERIAL PRIMARY KEY,
    bgg_id          INTEGER,
    slug            VARCHAR(200) NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    year_published  SMALLINT,
    min_players     SMALLINT,
    max_players     SMALLINT,
    playing_time    SMALLINT,
    rating          NUMERIC(4,2),
    weight          NUMERIC(3,2),
    cover_url       VARCHAR(500),
    cover_candidate_path VARCHAR(500),
    instruction_url VARCHAR(500),

    bgg_rank        INTEGER,
    users_rated     INTEGER,
    is_expansion    BOOLEAN NOT NULL DEFAULT FALSE,

    box_width       NUMERIC(5,2),
    box_height      NUMERIC(5,2),
    box_depth       NUMERIC(5,2),
    model_3d_url    VARCHAR(500),
    model_status    VARCHAR(20),
    model_candidate_path VARCHAR(500),
    model_job_id    VARCHAR(36),
    model_submitted_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    model_is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    model_submitted_at TIMESTAMPTZ,

    source          VARCHAR(10) NOT NULL DEFAULT 'bgg',
    is_verified     BOOLEAN NOT NULL DEFAULT TRUE,
    community_contributions_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,

    -- NULL = rekord z dumpa rankingowego, którego szczegółów /thing jeszcze nie pobrano.
    cached_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_games_source CHECK (source IN ('bgg', 'custom')),
    CONSTRAINT ck_games_model_status CHECK (
        model_status IS NULL OR model_status IN (
            'pending', 'processing', 'awaiting_review', 'ready', 'failed'
        )
    ),
    CONSTRAINT ck_games_min_players CHECK (min_players IS NULL OR min_players >= 1),
    CONSTRAINT ck_games_players_range CHECK (
        max_players IS NULL OR min_players IS NULL OR max_players >= min_players
    ),
    CONSTRAINT ck_games_rating CHECK (rating IS NULL OR rating BETWEEN 0 AND 10),
    CONSTRAINT ck_games_weight CHECK (weight IS NULL OR weight BETWEEN 0 AND 5)
);

CREATE TABLE IF NOT EXISTS game_game_types (
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    game_type_id    INTEGER NOT NULL REFERENCES game_types(id) ON DELETE CASCADE,
    PRIMARY KEY (game_id, game_type_id),
    CONSTRAINT uq_game_game_types_pair UNIQUE (game_id, game_type_id)
);

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

CREATE UNIQUE INDEX IF NOT EXISTS ix_games_bgg_id ON games(bgg_id) WHERE bgg_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_games_slug ON games(slug);
CREATE INDEX IF NOT EXISTS ix_games_title ON games(title);
CREATE INDEX IF NOT EXISTS ix_games_bgg_rank ON games(bgg_rank);
CREATE INDEX IF NOT EXISTS ix_games_is_expansion ON games(is_expansion);
CREATE INDEX IF NOT EXISTS ix_games_model_job_id ON games(model_job_id);
CREATE INDEX IF NOT EXISTS ix_game_types_slug ON game_types(slug);
CREATE INDEX IF NOT EXISTS ix_game_game_types_type_id ON game_game_types(game_type_id);
CREATE INDEX IF NOT EXISTS ix_game_images_game_id ON game_images(game_id);
CREATE INDEX IF NOT EXISTS ix_game_images_status ON game_images(status);
CREATE INDEX IF NOT EXISTS ix_game_barcodes_game_id ON game_barcodes(game_id);
CREATE INDEX IF NOT EXISTS ix_game_barcodes_status ON game_barcodes(status);

-- BGG może mieć wiele edycji o tej samej nazwie; customowych duplikatów nie dopuszczamy.
CREATE UNIQUE INDEX IF NOT EXISTS uq_games_custom_title_ci
    ON games (LOWER(title)) WHERE source = 'custom';

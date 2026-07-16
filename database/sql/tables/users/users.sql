-- ============================================================
-- Miplo — PostgreSQL 15+
-- ============================================================

-- Users: cień tożsamości z Firebase + dane apki
-- Firebase trzyma: hasło, MFA, OAuth providery, lockout, weryfikację maila.
-- Tu trzymamy TYLKO: łącznik do Firebase (firebase_uid) + dane Miplo.

CREATE TABLE users (
    id              SERIAL          PRIMARY KEY,
    firebase_uid    VARCHAR(128)    NOT NULL,
    email           VARCHAR(320)    NULL,           -- kopia z Firebase, dla wygody
    display_name    VARCHAR(80)     NULL,
    city            VARCHAR(120)    NULL,
    bio             TEXT            NULL,
    avatar_url      VARCHAR(500)    NULL,

    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_users_firebase_uid UNIQUE (firebase_uid)
);

-- Indeksy pod matchmaking i wyszukiwanie
CREATE INDEX idx_users_city ON users(city);
CREATE INDEX idx_users_firebase_uid ON users(firebase_uid);

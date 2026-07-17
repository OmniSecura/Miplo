-- ============================================================
-- Miplo — PostgreSQL 15+
-- ============================================================

-- Users: cień tożsamości z Firebase + dane apki
-- Firebase trzyma: hasło, MFA, OAuth providery, lockout, weryfikację maila.
-- Tu trzymamy TYLKO: łącznik do Firebase (firebase_uid) + dane Miplo.
-- Odpowiednik ORM: services/app/users/models/User.py

CREATE TABLE users (
    id              SERIAL          PRIMARY KEY,
    firebase_uid    VARCHAR(128)    NOT NULL,
    -- techniczny identyfikator publiczny / tag (URL-e, API); display_name jest do wyświetlania
    tag             VARCHAR(30)     NOT NULL,
    email           VARCHAR(320)    NULL,           -- kopia z Firebase, dla wygody
    display_name    VARCHAR(80)     NULL,
    city            VARCHAR(120)    NULL,
    bio             TEXT            NULL,
    avatar_url      VARCHAR(500)    NULL,

    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    is_admin        BOOLEAN         NOT NULL DEFAULT FALSE,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_users_firebase_uid UNIQUE (firebase_uid),
    CONSTRAINT uq_users_tag          UNIQUE (tag),
    -- defensywnie: format pilnowany też w bazie, nie tylko w Pydantic
    CONSTRAINT ck_users_tag_format   CHECK (tag ~ '^[a-z0-9_]{3,30}$')
);

-- Indeks pod matchmaking ("kto w mieście X ma grę Y")
CREATE INDEX idx_users_city ON users(city);

-- Uwaga: osobny indeks na firebase_uid jest zbędny — constraint UNIQUE
-- tworzy go automatycznie.

-- Rigveda SQLite Schema with Full-Text Search (FTS5)

CREATE TABLE IF NOT EXISTS mandalas (
    id INTEGER PRIMARY KEY,
    mandala INTEGER UNIQUE,
    total_suktas INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS suktas (
    id TEXT PRIMARY KEY, -- e.g. "1.1"
    mandala INTEGER NOT NULL,
    sukta INTEGER NOT NULL,
    total_riks INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS riks (
    id TEXT PRIMARY KEY, -- e.g. "1.1.1"
    mandala INTEGER NOT NULL,
    sukta INTEGER NOT NULL,
    rik INTEGER NOT NULL,
    ashtaka INTEGER,
    adhyaya INTEGER,
    varga INTEGER,
    anuvaka INTEGER,
    rishi TEXT,
    devata TEXT,
    chandas TEXT,
    samhita TEXT NOT NULL,
    padapatha TEXT,
    sayana_bhashya TEXT,
    audio_url TEXT,
    audio_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_riks_coords ON riks(mandala, sukta, rik);
CREATE INDEX IF NOT EXISTS idx_riks_ashtaka ON riks(ashtaka, adhyaya, varga);
CREATE INDEX IF NOT EXISTS idx_riks_rishi ON riks(rishi);
CREATE INDEX IF NOT EXISTS idx_riks_devata ON riks(devata);
CREATE INDEX IF NOT EXISTS idx_riks_chandas ON riks(chandas);

CREATE TABLE IF NOT EXISTS ancillary_texts (
    id TEXT PRIMARY KEY,
    text_name TEXT NOT NULL, -- "niruktam", "aitareya_brahmana", "bruhaddevatha"
    section TEXT,
    title TEXT,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ancillary_name ON ancillary_texts(text_name);

-- FTS5 Full-Text Search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS riks_fts USING fts5(
    id,
    mandala UNINDEXED,
    sukta UNINDEXED,
    rik UNINDEXED,
    samhita,
    padapatha,
    sayana_bhashya,
    rishi,
    devata,
    chandas,
    tokenize = 'unicode61'
);

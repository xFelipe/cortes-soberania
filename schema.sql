-- Canal Soberania — esquema SQLite
-- Rodar uma vez: sqlite3 data/canal.db < schema.sql

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =========================================================================
-- VIDEOS: vídeos descobertos nos canais monitorados
-- =========================================================================
CREATE TABLE IF NOT EXISTS videos (
    video_id            TEXT PRIMARY KEY,                -- YouTube ID (11 chars)
    canal_id            TEXT NOT NULL,                   -- ref a config/canais.yaml
    title               TEXT NOT NULL,
    description         TEXT,
    tags                TEXT,                            -- JSON array
    published_at        TEXT NOT NULL,                   -- ISO 8601
    duration_s          INTEGER,                         -- duração total
    view_count          INTEGER,
    like_count          INTEGER,
    comment_count       INTEGER,

    -- caminhos de artefatos
    audio_path          TEXT,                            -- data/audio/{id}.mp3
    video_path          TEXT,                            -- data/video/{id}.mp4
    caption_path        TEXT,                            -- data/captions/{id}.vtt (auto-sub)
    transcript_path     TEXT,                            -- data/transcripts/{id}.json (Whisper)

    -- máquina de estados (ver docs/pipeline.md)
    status              TEXT NOT NULL DEFAULT 'discovered',
    error_message       TEXT,                            -- preenche em status *_error

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_canal ON videos(canal_id);
CREATE INDEX IF NOT EXISTS idx_videos_published ON videos(published_at DESC);

-- =========================================================================
-- TRIAGE_RESULTS: resultado de cada uma das 3 triagens (auditoria)
-- =========================================================================
CREATE TABLE IF NOT EXISTS triage_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id            TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    stage               TEXT NOT NULL,                   -- 'metadata' | 'caption' | 'transcript'
    score               INTEGER NOT NULL,                -- 0-10
    is_relevant         INTEGER NOT NULL,                -- 0 ou 1
    themes_detected     TEXT,                            -- JSON array
    rationale           TEXT,
    raw_response        TEXT,                            -- JSON completo do LLM, para auditoria

    model_used          TEXT NOT NULL,                   -- claude-haiku-4-5, claude-sonnet-4-6
    tokens_in           INTEGER,
    tokens_out          INTEGER,
    cost_usd            REAL,

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_triage_video ON triage_results(video_id);
CREATE INDEX IF NOT EXISTS idx_triage_stage ON triage_results(stage);

-- =========================================================================
-- CLIPS: clipes identificados de cada vídeo
-- =========================================================================
CREATE TABLE IF NOT EXISTS clips (
    clip_id             TEXT PRIMARY KEY,                -- "{video_id}_{start_s}_{end_s}"
    video_id            TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,

    -- timing
    start_s             REAL NOT NULL,
    end_s               REAL NOT NULL,
    duracao_s           REAL GENERATED ALWAYS AS (end_s - start_s) VIRTUAL,

    -- identificação editorial
    hook                TEXT,
    payoff              TEXT,
    tema_soberania      TEXT,                            -- ex: "industria_defesa"
    score_viral         INTEGER,
    score_relevancia    INTEGER,
    justificativa       TEXT,

    -- artefatos de mídia
    clip_path_vertical      TEXT,                        -- data/clips/{clip_id}_vertical.mp4
    clip_path_horizontal    TEXT,
    thumb_path              TEXT,                        -- data/thumbs/{clip_id}.jpg

    -- metadados de publicação
    title               TEXT,
    description         TEXT,
    tags                TEXT,                            -- JSON array

    -- IDs dos uploads
    youtube_id          TEXT,                            -- video ID no YouTube após upload
    tiktok_id           TEXT,                            -- ID no TikTok
    youtube_publish_at  TEXT,                            -- ISO 8601, agendado

    -- estado
    status              TEXT NOT NULL DEFAULT 'identified',
    error_message       TEXT,

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
CREATE INDEX IF NOT EXISTS idx_clips_video ON clips(video_id);
CREATE INDEX IF NOT EXISTS idx_clips_youtube_publish ON clips(youtube_publish_at);

-- =========================================================================
-- API_COSTS: acompanhamento de custo agregado por dia
-- =========================================================================
CREATE TABLE IF NOT EXISTS api_costs (
    date                TEXT NOT NULL,                   -- YYYY-MM-DD
    provider            TEXT NOT NULL,                   -- 'anthropic' | 'youtube' | ...
    model               TEXT,                            -- opcional, para Anthropic
    tokens_in           INTEGER NOT NULL DEFAULT 0,
    tokens_out          INTEGER NOT NULL DEFAULT 0,
    requests            INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,

    PRIMARY KEY (date, provider, model)
);

-- =========================================================================
-- UPLOADS_LOG: registro de cada tentativa de upload (auditoria)
-- =========================================================================
CREATE TABLE IF NOT EXISTS uploads_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id             TEXT NOT NULL REFERENCES clips(clip_id) ON DELETE CASCADE,
    platform            TEXT NOT NULL,                   -- 'youtube' | 'tiktok'
    status              TEXT NOT NULL,                   -- 'success' | 'error' | 'manual_pending'
    platform_id         TEXT,                            -- ID retornado pela plataforma
    error_message       TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uploads_clip ON uploads_log(clip_id);

CREATE TABLE IF NOT EXISTS training_examples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task            TEXT NOT NULL,                  -- 'triage' | 'find_clips' | 'metadata'
    model           TEXT NOT NULL,
    system_prompt   TEXT,
    prompt          TEXT NOT NULL,
    completion      TEXT NOT NULL,
    tokens_in       INTEGER NOT NULL DEFAULT 0,
    tokens_out      INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    approved        INTEGER,                        -- NULL=uncurated, 1=approved, 0=rejected
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_training_task ON training_examples(task);

-- =========================================================================
-- Triggers para updated_at automático
-- =========================================================================
CREATE TRIGGER IF NOT EXISTS trg_videos_updated
AFTER UPDATE ON videos
BEGIN
    UPDATE videos SET updated_at = CURRENT_TIMESTAMP WHERE video_id = NEW.video_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_clips_updated
AFTER UPDATE ON clips
BEGIN
    UPDATE clips SET updated_at = CURRENT_TIMESTAMP WHERE clip_id = NEW.clip_id;
END;

-- =========================================================================
-- Views úteis
-- =========================================================================

-- Visão geral do funil
CREATE VIEW IF NOT EXISTS v_status_summary AS
SELECT status, COUNT(*) AS total
FROM videos
GROUP BY status
ORDER BY total DESC;

-- Clipes prontos para upload por plataforma
CREATE VIEW IF NOT EXISTS v_pending_youtube AS
SELECT clip_id, title, duracao_s, created_at
FROM clips
WHERE status = 'metadata_ready'
ORDER BY created_at ASC;

CREATE VIEW IF NOT EXISTS v_pending_tiktok AS
SELECT clip_id, title, duracao_s, clip_path_vertical
FROM clips
WHERE status IN ('scheduled_youtube', 'uploaded_youtube')
  AND tiktok_id IS NULL
ORDER BY created_at ASC;

-- Custo do mês corrente
CREATE VIEW IF NOT EXISTS v_custo_mes_atual AS
SELECT
    provider,
    model,
    SUM(tokens_in) AS tokens_in,
    SUM(tokens_out) AS tokens_out,
    SUM(requests) AS requests,
    SUM(cost_usd) AS cost_usd
FROM api_costs
WHERE date >= strftime('%Y-%m-01', 'now')
GROUP BY provider, model;

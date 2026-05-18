-- Migration 005: colunas de sync de status e métricas do YouTube nos clipes
-- Aplique com: sqlite3 data/canal.db < migrations/005_youtube_sync.sql

ALTER TABLE clips ADD COLUMN youtube_privacy_status TEXT;         -- private | public | unlisted
ALTER TABLE clips ADD COLUMN youtube_upload_status  TEXT;         -- processed | uploaded | rejected | failed | deleted
ALTER TABLE clips ADD COLUMN youtube_rejection_reason TEXT;       -- copyright | inappropriate | duplicate | termsOfUse | …
ALTER TABLE clips ADD COLUMN youtube_actual_published_at TEXT;    -- timestamp real da publicação (ISO 8601)
ALTER TABLE clips ADD COLUMN youtube_last_synced_at TEXT;         -- última vez que conferiu o YouTube

-- Métricas do vídeo vertical (Short — fonte de verdade do status)
ALTER TABLE clips ADD COLUMN youtube_view_count    INTEGER;
ALTER TABLE clips ADD COLUMN youtube_like_count    INTEGER;
ALTER TABLE clips ADD COLUMN youtube_comment_count INTEGER;

-- Espelhos informativos do horizontal (não dirigem status)
ALTER TABLE clips ADD COLUMN youtube_privacy_status_horizontal TEXT;
ALTER TABLE clips ADD COLUMN youtube_upload_status_horizontal  TEXT;
ALTER TABLE clips ADD COLUMN youtube_view_count_horizontal     INTEGER;
ALTER TABLE clips ADD COLUMN youtube_like_count_horizontal     INTEGER;
ALTER TABLE clips ADD COLUMN youtube_comment_count_horizontal  INTEGER;

CREATE INDEX IF NOT EXISTS idx_clips_youtube_last_synced ON clips(youtube_last_synced_at);

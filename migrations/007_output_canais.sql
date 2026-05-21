-- Migration 007: canais de saída (output canais) + target_canal_id em vídeos e clipes
-- Execução: sqlite3 data/canal.db < migrations/007_output_canais.sql

-- Tabela de canais de SAÍDA (cada output canal é um YouTube Shorts brand)
CREATE TABLE IF NOT EXISTS output_canais (
    id                 TEXT PRIMARY KEY,           -- slug (ex: 'soberania', 'churrasco')
    nome               TEXT NOT NULL,
    tema               TEXT NOT NULL DEFAULT '',
    criteria_path      TEXT NOT NULL DEFAULT '',   -- relativo à raiz do repo
    branding_dir       TEXT NOT NULL DEFAULT '',   -- ex: 'branding/soberania'
    youtube_channel_id TEXT NOT NULL DEFAULT '',
    youtube_token_path TEXT NOT NULL DEFAULT '',
    ativo              INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_output_canais_ativo ON output_canais(ativo);

-- Quais canais-fonte cada output canal monitora
CREATE TABLE IF NOT EXISTS output_canal_fontes (
    output_canal_id TEXT NOT NULL REFERENCES output_canais(id) ON DELETE CASCADE,
    fonte_canal_id  TEXT NOT NULL REFERENCES canais(id) ON DELETE CASCADE,
    PRIMARY KEY (output_canal_id, fonte_canal_id)
);

-- Qual output canal vai processar cada vídeo
ALTER TABLE videos ADD COLUMN target_canal_id TEXT NOT NULL DEFAULT 'soberania';

-- Qual output canal produziu cada clipe
ALTER TABLE clips ADD COLUMN target_canal_id TEXT NOT NULL DEFAULT 'soberania';

CREATE INDEX IF NOT EXISTS idx_videos_target_canal ON videos(target_canal_id);
CREATE INDEX IF NOT EXISTS idx_clips_target_canal ON clips(target_canal_id);

CREATE TRIGGER IF NOT EXISTS trg_output_canais_updated
AFTER UPDATE ON output_canais
BEGIN
    UPDATE output_canais SET updated_at = datetime('now') WHERE id = NEW.id;
END;

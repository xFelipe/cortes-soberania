-- Migration 006: tabela de canais (migra de config/canais.yaml para SQLite)
-- Execução: sqlite3 data/canal.db < migrations/006_canais_table.sql
-- O seed inicial (canais.yaml → banco) é feito automaticamente no boot da app.

CREATE TABLE IF NOT EXISTS canais (
    id                TEXT PRIMARY KEY,
    nome              TEXT NOT NULL,
    handle            TEXT NOT NULL DEFAULT '',
    channel_url       TEXT NOT NULL,
    tema_primario     TEXT NOT NULL DEFAULT '',
    peso              REAL NOT NULL DEFAULT 1.0,
    auto_publish      INTEGER NOT NULL DEFAULT 0,  -- 0=false 1=true
    tolerancia_cortes TEXT NOT NULL DEFAULT 'desconhecida',
    nota              TEXT NOT NULL DEFAULT '',
    ativo             INTEGER NOT NULL DEFAULT 1,  -- 0=false 1=true
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_canais_ativo ON canais(ativo);

CREATE TRIGGER IF NOT EXISTS trg_canais_updated
AFTER UPDATE ON canais
BEGIN
    UPDATE canais SET updated_at = datetime('now') WHERE id = NEW.id;
END;

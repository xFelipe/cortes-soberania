-- Migração 001: tabela de exemplos de treino para fine-tuning local
-- Rodar: sqlite3 data/canal.db < migrations/001_training_examples.sql

CREATE TABLE IF NOT EXISTS training_examples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- identificação da tarefa e modelo
    task            TEXT NOT NULL,   -- 'triage_metadata'|'triage_caption'|'triage_transcript'|'find_clips'|'metadata'
    model           TEXT NOT NULL,   -- modelo que gerou a resposta

    -- par de treino
    system_prompt   TEXT,            -- system prompt (se houver)
    prompt          TEXT NOT NULL,   -- mensagem do usuário (prompt completo com variáveis preenchidas)
    completion      TEXT NOT NULL,   -- resposta do modelo (texto bruto)

    -- métricas da chamada
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    cost_usd        REAL,

    -- curadoria humana (preencher depois de validar qualidade)
    approved        INTEGER DEFAULT NULL,  -- NULL=não curado  1=aprovado  0=rejeitado
    quality_note    TEXT,                  -- observação livre do curador

    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_training_task     ON training_examples(task);
CREATE INDEX IF NOT EXISTS idx_training_approved ON training_examples(approved);
CREATE INDEX IF NOT EXISTS idx_training_model    ON training_examples(model);

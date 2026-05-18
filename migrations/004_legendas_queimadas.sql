-- Indica se o vídeo-fonte já possui legendas queimadas na imagem.
-- NULL = não verificado (pipeline adiciona legenda normalmente)
-- 1    = tem legenda queimada (edit pula geração de ASS)
-- 0    = não tem (edit adiciona legenda normalmente)
ALTER TABLE videos ADD COLUMN legendas_queimadas INTEGER DEFAULT NULL;

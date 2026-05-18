-- Adiciona heartbeat de processamento em andamento.
-- processing_since: NULL = parado; preenchido = em processamento ativo (atualizado a cada ~60s).
-- Se estiver preenchido há mais de 3 minutos, o processo morreu e o item deve ser resetado.
ALTER TABLE videos ADD COLUMN processing_since TEXT;
ALTER TABLE clips  ADD COLUMN processing_since TEXT;

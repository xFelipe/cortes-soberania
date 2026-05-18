-- Controle por clipe de quais formatos devem ser gerados no stage Edit.
-- DEFAULT 1 garante que clipes existentes continuem gerando ambos os formatos.
ALTER TABLE clips ADD COLUMN render_vertical INTEGER DEFAULT 1;
ALTER TABLE clips ADD COLUMN render_horizontal INTEGER DEFAULT 1;

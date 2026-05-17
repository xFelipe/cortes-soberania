-- Migration 002: adiciona youtube_id_horizontal para upload do vídeo horizontal (16:9) separado do Short (9:16)
ALTER TABLE clips ADD COLUMN youtube_id_horizontal TEXT;
ALTER TABLE clips ADD COLUMN youtube_publish_at_horizontal TEXT;

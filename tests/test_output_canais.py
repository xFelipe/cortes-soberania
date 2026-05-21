"""Testes para a infraestrutura de output canais (Onda 10)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from canal_soberania.config import (
    OutputCanal,
    OutputCanaisConfig,
    load_output_canais,
    resolve_criteria_path,
    resolve_prompt_path,
)
from canal_soberania.db import connect, ensure_output_canais_seeded, init_db, insert_video
from canal_soberania.models import Video
from canal_soberania.repositories.sqlite import SqliteOutputCanaisRepository

SCHEMA = Path(__file__).parent.parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text())
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    c = connect(db_path)
    _apply_migrations(c)
    return c


def _output_canal(**kwargs: object) -> OutputCanal:
    defaults: dict[str, object] = {
        "id": "soberania",
        "nome": "Canal Soberania",
        "tema": "Soberania nacional",
        "fontes": [],
        "criteria_path": "",
        "branding_dir": "",
        "youtube_channel_id": "",
        "youtube_token_path": "config/youtube_token.json",
        "ativo": True,
    }
    defaults.update(kwargs)
    return OutputCanal.model_validate(defaults)


# ── migration e schema ────────────────────────────────────────────────────────


def test_migration_creates_output_canais_table(db: sqlite3.Connection) -> None:
    """Migration 007 deve criar tabelas output_canais e output_canal_fontes."""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "output_canais" in tables
    assert "output_canal_fontes" in tables


def test_migration_adds_target_canal_id_to_videos(db: sqlite3.Connection) -> None:
    """Migration 007 deve adicionar coluna target_canal_id à tabela videos."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(videos)").fetchall()}
    assert "target_canal_id" in cols


def test_migration_adds_target_canal_id_to_clips(db: sqlite3.Connection) -> None:
    """Migration 007 deve adicionar coluna target_canal_id à tabela clips."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(clips)").fetchall()}
    assert "target_canal_id" in cols


# ── SqliteOutputCanaisRepository ──────────────────────────────────────────────


def test_repository_upsert_and_get(db: sqlite3.Connection) -> None:
    repo = SqliteOutputCanaisRepository(db)
    canal = _output_canal(id="churrasco", nome="Canal Churrasco", tema="Churrasco BR")
    repo.upsert(canal)

    fetched = repo.get("churrasco")
    assert fetched is not None
    assert fetched.id == "churrasco"
    assert fetched.nome == "Canal Churrasco"


def test_repository_get_active(db: sqlite3.Connection) -> None:
    repo = SqliteOutputCanaisRepository(db)
    repo.upsert(_output_canal(id="ativo", nome="Ativo", ativo=True))
    repo.upsert(_output_canal(id="inativo", nome="Inativo", ativo=False))

    ativos = repo.get_active()
    ids = {c.id for c in ativos}
    assert "ativo" in ids
    assert "inativo" not in ids


def test_repository_get_all(db: sqlite3.Connection) -> None:
    repo = SqliteOutputCanaisRepository(db)
    repo.upsert(_output_canal(id="a", nome="A"))
    repo.upsert(_output_canal(id="b", nome="B", ativo=False))

    all_canais = repo.get_all()
    ids = {c.id for c in all_canais}
    assert {"a", "b"} == ids


def test_repository_upsert_fontes(db: sqlite3.Connection) -> None:
    repo = SqliteOutputCanaisRepository(db)
    repo.upsert(_output_canal(id="soberania"))

    # upsert_fontes sem fontes existentes em canais não deve lançar (FK graceful)
    repo.upsert_fontes("soberania", ["canal_que_nao_existe"])

    fontes = repo.get_fontes("soberania")
    # FK violation silenciada → entrada não inserida
    assert fontes == []


def test_repository_upsert_fontes_valid(db: sqlite3.Connection) -> None:
    """Fontes que existem na tabela canais devem ser inseridas."""
    # Insere um canal-fonte real
    db.execute(
        "INSERT OR IGNORE INTO canais (id, nome, handle, channel_url, tema_primario) VALUES (?,?,?,?,?)",
        ("podpah", "PodPah", "@Podpah", "https://youtube.com/@Podpah", "variado"),
    )
    db.commit()

    repo = SqliteOutputCanaisRepository(db)
    repo.upsert(_output_canal(id="soberania"))
    repo.upsert_fontes("soberania", ["podpah"])

    fontes = repo.get_fontes("soberania")
    assert fontes == ["podpah"]


def test_repository_delete(db: sqlite3.Connection) -> None:
    repo = SqliteOutputCanaisRepository(db)
    repo.upsert(_output_canal(id="tmp"))
    repo.delete("tmp")
    assert repo.get("tmp") is None


def test_repository_update(db: sqlite3.Connection) -> None:
    repo = SqliteOutputCanaisRepository(db)
    repo.upsert(_output_canal(id="canal1", nome="Antigo"))
    repo.update("canal1", nome="Novo")
    fetched = repo.get("canal1")
    assert fetched is not None
    assert fetched.nome == "Novo"


# ── resolve helpers ───────────────────────────────────────────────────────────


def test_resolve_criteria_path_fallback(tmp_path: Path) -> None:
    """Canal sem criteria_path e sem arquivo per-canal cai para criterios_relevancia.md."""
    oc = OutputCanal(id="inexistente", nome="X")
    path = resolve_criteria_path(oc)
    # O fallback aponta para o arquivo global real
    assert path.name == "criterios_relevancia.md"


def test_resolve_criteria_path_per_canal(tmp_path: Path) -> None:
    """Canal com criteria_path válido deve retornar esse caminho."""
    criteria_file = tmp_path / "soberania.md"
    criteria_file.write_text("# Critérios")

    # criteria_path relativo à raiz do repo não vai funcionar com tmp_path,
    # mas podemos testar usando o arquivo real criado em config/criterios/soberania.md
    repo_root = Path(__file__).parent.parent
    soberania_criteria = repo_root / "config" / "criterios" / "soberania.md"
    if soberania_criteria.exists():
        oc = OutputCanal(id="soberania", nome="Soberania", criteria_path="config/criterios/soberania.md")
        path = resolve_criteria_path(oc)
        assert path.name == "soberania.md"


def test_resolve_prompt_path_per_canal() -> None:
    """Canal com diretório prompts/{slug}/ deve retornar arquivo per-canal."""
    repo_root = Path(__file__).parent.parent
    soberania_prompt = repo_root / "prompts" / "soberania" / "triagem_metadata.txt"
    if soberania_prompt.exists():
        path = resolve_prompt_path("soberania", "triagem_metadata")
        assert "soberania" in str(path)


def test_resolve_prompt_path_fallback() -> None:
    """Canal sem diretório per-canal cai para arquivo global."""
    path = resolve_prompt_path("canal_inexistente_xyzabc", "triagem_metadata")
    assert path.name == "triagem_metadata.txt"
    assert "canal_inexistente_xyzabc" not in str(path)


# ── seed idempotente ──────────────────────────────────────────────────────────


def test_seed_output_canais_idempotent(db: sqlite3.Connection, tmp_path: Path) -> None:
    """Chamar ensure_output_canais_seeded duas vezes não duplica registros."""
    yaml_content = """
output_canais:
  - id: soberania
    nome: Canal Soberania nas Redes
    tema: Soberania nacional
    fontes: []
    criteria_path: ""
    branding_dir: ""
    youtube_channel_id: ""
    youtube_token_path: config/youtube_token.json
    ativo: true
"""
    yaml_path = tmp_path / "output_canais.yaml"
    yaml_path.write_text(yaml_content)

    ensure_output_canais_seeded(db, yaml_path)
    ensure_output_canais_seeded(db, yaml_path)

    count = db.execute("SELECT COUNT(*) FROM output_canais WHERE id = 'soberania'").fetchone()[0]
    assert count == 1


def test_seed_output_canais_skips_if_table_missing(tmp_path: Path) -> None:
    """ensure_output_canais_seeded não deve explodir se a migration 007 não foi aplicada."""
    db_path = tmp_path / "noschema.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Não aplica nenhuma migration — tabela output_canais não existe

    yaml_path = tmp_path / "output_canais.yaml"
    yaml_path.write_text("output_canais: []")

    # Não deve lançar exceção
    ensure_output_canais_seeded(conn, yaml_path)
    conn.close()


# ── insert_video com target_canal_id ─────────────────────────────────────────


def test_insert_video_stores_target_canal_id(db: sqlite3.Connection) -> None:
    """insert_video deve persistir target_canal_id no banco."""
    video = Video(
        video_id="dQw4w9WgXcQ",
        canal_id="podpah",
        title="Teste",
        published_at="2024-01-01T00:00:00Z",
        target_canal_id="churrasco",
    )
    with db:
        insert_video(db, video)

    row = db.execute("SELECT target_canal_id FROM videos WHERE video_id = ?", ("dQw4w9WgXcQ",)).fetchone()
    assert row is not None
    assert row["target_canal_id"] == "churrasco"


def test_insert_video_default_target_canal_id(db: sqlite3.Connection) -> None:
    """target_canal_id deve default para 'soberania' quando não especificado."""
    video = Video(
        video_id="abcdefghijk",
        canal_id="flow",
        title="Default canal",
        published_at="2024-01-01T00:00:00Z",
    )
    with db:
        insert_video(db, video)

    row = db.execute("SELECT target_canal_id FROM videos WHERE video_id = ?", ("abcdefghijk",)).fetchone()
    assert row is not None
    assert row["target_canal_id"] == "soberania"


# ── load_output_canais ────────────────────────────────────────────────────────


def test_load_output_canais_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
output_canais:
  - id: forró
    nome: Canal Forró BR
    tema: Forró nordestino
    fontes: [canal_a, canal_b]
    criteria_path: config/criterios/forro.md
    branding_dir: branding/forro
    youtube_channel_id: UC123
    youtube_token_path: config/token_forro.json
    ativo: true
"""
    yaml_path = tmp_path / "output_canais.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    cfg = load_output_canais(yaml_path)
    assert len(cfg.output_canais) == 1
    oc = cfg.output_canais[0]
    assert oc.id == "forró"
    assert oc.fontes == ["canal_a", "canal_b"]
    assert oc.ativo is True


def test_load_output_canais_missing_file(tmp_path: Path) -> None:
    """load_output_canais retorna config vazia se arquivo não existe."""
    cfg = load_output_canais(tmp_path / "nao_existe.yaml")
    assert cfg.output_canais == []

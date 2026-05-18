"""Entry point da GUI PySide6 — `cs-gui` ou `python -m canal_soberania.gui.main`."""

from __future__ import annotations

import sys


def main() -> None:
    # PySide6 importado aqui para que `import canal_soberania` não exija Qt instalado
    from PySide6.QtWidgets import QApplication, QMessageBox

    from canal_soberania.config import ensure_data_dirs, get_paths, load_settings
    from canal_soberania.db import connect, init_db
    from canal_soberania.logger import setup_logger
    from canal_soberania.services.pipeline_service import PipelineService

    app = QApplication(sys.argv)
    app.setApplicationName("Canal Soberania")
    app.setOrganizationName("canal-soberania")

    settings = load_settings()
    paths = get_paths(settings)

    ensure_data_dirs(paths)

    db_path = paths["db_path"]
    schema_path = paths["schema_path"]
    if not db_path.exists():
        if not schema_path.exists():
            QMessageBox.critical(
                None,
                "Schema não encontrado",
                f"Arquivo {schema_path} não existe.\n"
                "Execute `sqlite3 data/canal.db < schema.sql` manualmente.",
            )
            sys.exit(1)
        init_db(db_path, schema_path)

    setup_logger(paths["log_dir"], settings.log_level)

    conn = connect(db_path)
    service = PipelineService(conn=conn, settings=settings, paths=paths)

    from canal_soberania.gui.windows.main_window import MainWindow

    window = MainWindow(service)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

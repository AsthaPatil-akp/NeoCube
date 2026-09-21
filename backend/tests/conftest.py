"""Isolated pytest database: migrate before tests, delete only after connections close.

This module must set process environment variables before any application import so
Settings/engine never attach to the developer sqlite:///./app.db file.
"""

from __future__ import annotations

import gc
import os
import shutil
import tempfile
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_TEST_DB_DIR = tempfile.mkdtemp(prefix="neocube_pytest_")
TEST_DB_PATH = Path(_TEST_DB_DIR) / "test.db"

os.environ["DATABASE_URL"] = "sqlite:///" + TEST_DB_PATH.resolve().as_posix()
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["COOKIE_SECURE"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["N8N_WEBHOOK_URL"] = ""

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import settings
from app.database import engine
from app.main import ensure_categories, ensure_roles


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def alembic_head_revision() -> str:
    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_current_head()
    assert head is not None
    return head


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database():
    """Create the temp SQLite file, apply Alembic to head, seed catalog rows, then dispose before delete."""
    assert "app.db" not in settings.database_url
    assert TEST_DB_PATH.resolve().as_posix() in settings.database_url.replace("\\", "/")
    command.upgrade(_alembic_config(), "head")
    ensure_roles()
    ensure_categories()
    yield
    engine.dispose()
    gc.collect()
    shutil.rmtree(_TEST_DB_DIR)

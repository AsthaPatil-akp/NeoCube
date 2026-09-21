from sqlalchemy import inspect, text

from app.config import settings
from app.database import SessionLocal, engine
from tests.conftest import TEST_DB_PATH, alembic_head_revision


def test_settings_do_not_use_developer_database():
    assert settings.environment.lower() == "test"
    assert "app.db" not in settings.database_url
    assert TEST_DB_PATH.exists()
    assert TEST_DB_PATH.resolve().as_posix() in settings.database_url.replace("\\", "/")


def test_schema_is_alembic_head():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "alembic_version" in tables
    for name in (
        "roles",
        "users",
        "client_profiles",
        "supplier_profiles",
        "categories",
        "client_requirements",
        "supplier_offerings",
        "requirement_documents",
        "supplier_documents",
        "matches",
        "notifications",
        "rfqs",
        "quotations",
        "order_tracks",
        "supplier_reviews",
        "audit_logs",
    ):
        assert name in tables
    assert "route_estimates" not in tables
    match_cols = {col["name"] for col in inspector.get_columns("matches")}
    for name in (
        "route_distance_km",
        "estimated_transit_days",
        "delivery_status",
        "delivery_warning",
        "delivery_estimate_source",
    ):
        assert name not in match_cols
    assert "location" in {col["name"] for col in inspector.get_columns("client_requirements")}
    assert "location" in {col["name"] for col in inspector.get_columns("supplier_offerings")}
    req_cols = {col["name"] for col in inspector.get_columns("client_requirements")}
    off_cols = {col["name"] for col in inspector.get_columns("supplier_offerings")}
    for name in ("custom_category", "quantity_unit", "budget_currency", "budget_basis"):
        assert name in req_cols
    for name in ("custom_category", "quantity_unit", "price_amount", "price_currency", "price_basis"):
        assert name in off_cols
    assert "is_predefined" in {col["name"] for col in inspector.get_columns("categories")}
    assert "profile_photo" in {col["name"] for col in inspector.get_columns("users")}

    db = SessionLocal()
    try:
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        db.close()
    assert version == alembic_head_revision()
    assert version == "010_supplier_reviews"

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, select, text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Category, Role, User
from app.routers import admin as admin_router
from app.routers import ai_product_finder as ai_product_finder_router
from app.routers import auth as auth_router
from app.routers import catalog as catalog_router
from app.routers import documents as documents_router
from app.routers import notifications as notifications_router
from app.routers import n8n_bridge as n8n_bridge_router
from app.routers import offerings as offerings_router
from app.routers import requirements as requirements_router
from app.routers import rfqs as rfqs_router
from app.routers import suppliers as suppliers_router
from app.routers import users as users_router
from app.security import hash_password

logger = logging.getLogger("neocube")


def configure_app_logging() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False


configure_app_logging()

ROLE_NAMES = ("ADMIN", "CLIENT", "SUPPLIER")
DEFAULT_CATEGORIES = (
    "Steel & Metals",
    "Electronics",
    "Packaging",
    "Textiles",
    "Industrial Components",
    "Raw Materials",
    "Logistics",
    "Other",
)


def ensure_roles() -> None:
    db = SessionLocal()
    try:
        existing = set(db.scalars(select(Role.name)).all())
        for name in ROLE_NAMES:
            if name not in existing:
                db.add(Role(name=name))
        db.commit()
    finally:
        db.close()


def ensure_categories() -> None:
    db = SessionLocal()
    try:
        existing = {name.lower() for name in db.scalars(select(Category.name)).all()}
        for name in DEFAULT_CATEGORIES:
            if name.lower() not in existing:
                db.add(Category(name=name, is_predefined=True))
            else:
                row = db.scalar(select(Category).where(Category.name == name))
                if row is not None and not row.is_predefined:
                    row.is_predefined = True
        db.commit()
    finally:
        db.close()


def ensure_admin() -> None:
    if not settings.admin_email or not settings.admin_password:
        return
    if len(settings.admin_password) < 8:
        logger.warning("ADMIN_PASSWORD is too short; admin account was not created")
        return
    db = SessionLocal()
    try:
        email = settings.admin_email.strip().lower()
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            return
        role = db.scalar(select(Role).where(Role.name == "ADMIN"))
        if role is None:
            return
        db.add(
            User(
                email=email,
                password_hash=hash_password(settings.admin_password),
                role_id=role.id,
                full_name="Platform Admin",
            )
        )
        db.commit()
        logger.info("Seeded admin account for %s", email)
    finally:
        db.close()


def ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    additions = {
        "matches": {
            "semantic_score": "FLOAT",
            "ml_score": "FLOAT",
            "structured_score": "FLOAT",
            "final_score": "FLOAT",
            "match_status": "VARCHAR(32) DEFAULT 'NEW'",
            "explanation": "TEXT",
            "model_version": "VARCHAR(80)",
            "updated_at": "DATETIME",
        },
        "notifications": {
            "notification_type": "VARCHAR(40) DEFAULT 'INFO'",
            "related_type": "VARCHAR(80)",
            "related_id": "INTEGER",
        },
        "users": {
            "profile_photo": "VARCHAR(255)",
        },
        "categories": {
            "is_predefined": "BOOLEAN DEFAULT 1",
        },
        "client_requirements": {
            "custom_category": "VARCHAR(200)",
            "quantity_unit": "VARCHAR(40)",
            "budget_currency": "VARCHAR(8)",
            "budget_basis": "VARCHAR(16)",
        },
        "supplier_offerings": {
            "custom_category": "VARCHAR(200)",
            "quantity_unit": "VARCHAR(40)",
            "price_amount": "INTEGER",
            "price_currency": "VARCHAR(8)",
            "price_basis": "VARCHAR(16)",
            "product_image_path": "VARCHAR(255)",
            "product_image_filename": "VARCHAR(255)",
            "product_image_mime_type": "VARCHAR(80)",
            "product_image_source": "VARCHAR(40)",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if "product_image_embeddings" not in inspector.get_table_names():
            connection.execute(
                text(
                    """
                    CREATE TABLE product_image_embeddings (
                        id INTEGER NOT NULL PRIMARY KEY,
                        supplier_offering_id INTEGER NOT NULL UNIQUE,
                        model_version VARCHAR(80) NOT NULL,
                        embedding TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        FOREIGN KEY(supplier_offering_id) REFERENCES supplier_offerings (id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_product_image_embeddings_supplier_offering_id "
                    "ON product_image_embeddings (supplier_offering_id)"
                )
            )
        if "n8n_emitted_events" not in inspector.get_table_names():
            connection.execute(
                text(
                    """
                    CREATE TABLE n8n_emitted_events (
                        event_id VARCHAR(160) NOT NULL PRIMARY KEY,
                        event_type VARCHAR(80),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                    )
                    """
                )
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.environment.lower() != "test":
        Base.metadata.create_all(bind=engine)
        ensure_sqlite_columns()
    ensure_roles()
    ensure_categories()
    ensure_admin()
    logger.info("n8n webhook configured: %s", bool((settings.n8n_webhook_url or "").strip()))
    yield


app = FastAPI(title="NeoCube", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="neocube_session",
    same_site="lax",
    https_only=settings.session_https_only,
    max_age=60 * 60 * 24 * 7,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if isinstance(exc, RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": exc.errors()})
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong"})


@app.get("/health")
def health() -> dict[str, object]:
    from app.ml.model_store import load_match_model
    from app.ml.nlp import SemanticEncoder

    model = load_match_model()
    encoder = SemanticEncoder.load()
    return {
        "status": "ok",
        "environment": settings.environment,
        "model_loaded": model is not None,
        "model_version": None if model is None else model.version,
        "encoder_loaded": encoder.pipeline is not None,
    }


app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(catalog_router.router)
app.include_router(requirements_router.router)
app.include_router(offerings_router.router)
app.include_router(documents_router.router)
app.include_router(documents_router.supplier_router)
app.include_router(notifications_router.router)
app.include_router(n8n_bridge_router.router)
app.include_router(rfqs_router.router)
app.include_router(suppliers_router.router)
app.include_router(admin_router.router)
if settings.ai_product_finder_enabled:
    app.include_router(ai_product_finder_router.router)

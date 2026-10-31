from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_existing_db() -> None:
    """Best-effort schema updates for databases created by earlier versions.

    Creator Desk ships without Alembic, so missing columns on pre-existing
    tables are added here. Safe to run on every startup (no-op when columns
    already exist).
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "schedules" in tables:
        schedule_cols = {c["name"] for c in inspector.get_columns("schedules")}
        if "account_id" not in schedule_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE schedules ADD COLUMN account_id INTEGER")
                )


def init_db():
    import app.models  # noqa: F401  # ensure models are registered
    Base.metadata.create_all(bind=engine)
    _migrate_existing_db()

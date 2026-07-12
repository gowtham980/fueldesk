"""Engine / session factory."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from fueldesk.config import ensure_data_dir
from fueldesk.db.models import Base, FoodItem
from fueldesk.db.seed_foods import SEED_FOODS

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(db_file: Path | str | None = None) -> Engine:
    global _engine, _SessionLocal
    if db_file is not None:
        path = Path(db_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine

    if _engine is None:
        path = ensure_data_dir()
        url = f"sqlite:///{path}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(_engine, "connect")
        def _fk2(dbapi_conn, _):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    eng = engine or get_engine()
    if engine is not None:
        return sessionmaker(bind=eng, autoflush=False, autocommit=False)
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    return _SessionLocal


def init_db(engine: Engine | None = None) -> None:
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
    seed_foods_if_empty(eng)


def seed_foods_if_empty(engine: Engine) -> None:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        existing = session.scalar(select(FoodItem.id).limit(1))
        if existing is not None:
            return
        for row in SEED_FOODS:
            session.add(
                FoodItem(
                    name=row["name"],
                    calories=row["calories"],
                    protein=row["protein"],
                    carbs=row["carbs"],
                    fat=row["fat"],
                    tags=row.get("tags", []),
                )
            )
        session.commit()


def reset_engine() -> None:
    """Test helper: clear cached engine."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def session_scope(engine: Engine | None = None) -> Generator[Session, None, None]:
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

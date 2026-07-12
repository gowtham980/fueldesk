"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from fueldesk import __version__
from fueldesk.db.session import get_engine, init_db
from fueldesk.web.routes import router
from fueldesk.web.ai_routes import router as ai_router


def create_app(*, db_path: str | None = None) -> FastAPI:
    if db_path:
        import os

        os.environ["FUELDESK_DB"] = db_path
        from fueldesk.db.session import reset_engine

        reset_engine()

    engine = get_engine()
    init_db(engine)

    app = FastAPI(
        title="fueldesk",
        description="Local-first Personal Fuel & Training Protocol Desk",
        version=__version__,
    )
    # Flash messages via signed cookie sessions (local single-user)
    app.add_middleware(SessionMiddleware, secret_key="fueldesk-local-dev-key")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(router)
    app.include_router(ai_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "app": "fueldesk", "version": __version__}

    return app

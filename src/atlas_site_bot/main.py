from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from atlas_site_bot.api.routes import build_router
from atlas_site_bot.container import ApplicationContainer
from atlas_site_bot.settings import Settings


def create_app(
    settings: Settings | None = None,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_container = container or ApplicationContainer(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = resolved_container
        await resolved_container.start()
        try:
            yield
        finally:
            await resolved_container.stop()

    app = FastAPI(title="ATLAS Site Bot API", lifespan=lifespan)
    app.include_router(build_router(resolved_container))

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


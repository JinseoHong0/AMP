import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from backend.config import Settings
from backend.errors import install_error_handlers
from backend.poster_middleware import PosterRequestGuard
from backend.routers.posters import router as posters_router
from backend.services.llm import GeminiPosterClient
from backend.services.poster_uploads import PendingUploadStore
from backend.services.venue_matcher import SqliteVenueRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = PendingUploadStore(settings.upload_dir, settings.upload_ttl_hours)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await run_in_threadpool(store.cleanup)

        async def cleanup_periodically():
            while True:
                await asyncio.sleep(3600)
                await run_in_threadpool(store.cleanup)

        task = asyncio.create_task(cleanup_periodically())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="AMP API", version="1.1.0", lifespan=lifespan)
    app.state.poster_client = GeminiPosterClient(settings)
    app.state.venue_repository = SqliteVenueRepository(settings.database_path)
    app.state.upload_store = store
    install_error_handlers(app)
    app.add_middleware(PosterRequestGuard, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(posters_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "amp-api", "version": "1.1.0"}

    # INTEGRATION_TODO: The DB/event and recommendation owners add their routers here.
    return app


app = create_app()

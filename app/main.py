from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .providers import ProviderError, Settings
from .schemas import Discovery, Query
from .service import DiscoveryService


def create_app(settings=None, transport=None):
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.discovery = DiscoveryService(client, settings or Settings.load())
            yield

    app = FastAPI(title="Prospect Discovery", version="1.0.0", lifespan=lifespan,
                  description="Find public profiles by topic or audience, optionally narrowed by location. "
                              "Search provider excerpts supply the evidence.",
                  redoc_url=None)

    web = Path(__file__).resolve().parent / "web"
    app.mount("/assets", StaticFiles(directory=web), name="assets")

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(web / "index.html", media_type="text/html")

    @app.post("/prospect-discovery", response_model=Discovery, response_model_exclude_unset=True, summary="Discover public prospects",
              responses={429: {"description": "Local concurrency limit"}, 502: {"description": "Invalid upstream response"},
                         503: {"description": "Missing credentials or upstream unavailable"},
                         504: {"description": "Upstream timeout"}})
    async def discover(payload: Query, request: Request, response: Response):
        try:
            outcome = await request.app.state.discovery.discover(payload.query, payload.mode)
        except ProviderError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc),
                                headers={"Retry-After": "3"} if exc.status == 429 else None) from exc
        response.headers["Cache-Control"] = "no-store"
        if outcome.unavailable:
            response.headers["X-Unavailable-Sources"] = ", ".join(outcome.unavailable)
        return outcome.response

    return app


app = create_app()

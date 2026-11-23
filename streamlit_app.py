"""Community Cloud launcher. Streamlit owns the server and FastAPI owns the API routes."""
from contextlib import asynccontextmanager

from starlette.routing import Route
from streamlit.web.server.starlette import App

from app.main import app as api


@asynccontextmanager
async def api_lifespan(_):
    async with api.router.lifespan_context(api):
        yield


app = App(
    "app/streamlit_view.py",
    lifespan=api_lifespan,
    routes=[
        Route("/prospect-discovery", api, methods=["POST"]),
        Route("/docs", api, methods=["GET"]),
        Route("/openapi.json", api, methods=["GET"]),
    ],
)

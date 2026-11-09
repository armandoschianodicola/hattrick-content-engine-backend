import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from hattrick_backend.api.v1.router import router
from hattrick_backend.core.config import get_settings
from hattrick_backend.core.exceptions import AppError
from hattrick_backend.core.logging import configure_logging
from hattrick_backend.domain.enums import Platform
from hattrick_backend.infrastructure.ai.fake import FakeAIProvider
from hattrick_backend.infrastructure.ai.openai_provider import OpenAIProvider
from hattrick_backend.infrastructure.database.session import create_session_factory
from hattrick_backend.infrastructure.publishing.facebook import FacebookPublisher
from hattrick_backend.infrastructure.publishing.instagram import InstagramPublisher
from hattrick_backend.infrastructure.publishing.telegram import TelegramPublisher
from hattrick_backend.infrastructure.rendering.pillow_renderer import PillowRenderer
from hattrick_backend.infrastructure.retrieval.fake import FakeKnowledgeRetriever
from hattrick_backend.infrastructure.retrieval.pgvector_retriever import PgvectorRetriever
from hattrick_backend.infrastructure.storage import LocalAssetStorage


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    configure_logging()
    engine, sessions = create_session_factory(settings)
    openai = OpenAIProvider(settings)
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds, follow_redirects=False
    ) as client:
        app.state.sessions = sessions
        app.state.ai = FakeAIProvider() if settings.ai_provider == "fake" else openai
        app.state.retriever = (
            FakeKnowledgeRetriever()
            if settings.retrieval_provider == "fake"
            else (
                PgvectorRetriever(
                    sessions,
                    openai,
                    settings.embedding_model,
                    settings.embedding_dimensions,
                    settings.retrieval_min_similarity,
                )
            )
        )
        app.state.renderer = PillowRenderer(settings.font_path)
        app.state.storage = LocalAssetStorage(settings.assets_directory)
        app.state.publishers = {
            Platform.TELEGRAM: TelegramPublisher(
                settings.telegram_bot_token.get_secret_value()
                if settings.telegram_bot_token
                else None,
                settings.telegram_chat_id.get_secret_value() if settings.telegram_chat_id else None,
                client,
            ),
            Platform.FACEBOOK: FacebookPublisher(),
            Platform.INSTAGRAM: InstagramPublisher(),
        }
        try:
            yield
        finally:
            await openai.close()
            await engine.dispose()


def create_app():
    app = FastAPI(title="Hattrick Educational Content Engine", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            # Handle here so ServerErrorMiddleware/Uvicorn never logs a raw exception that
            # might include an external URL containing a bot token or database credentials.
            logging.getLogger(__name__).error("unexpected_request_failure")
            response = error_response(request, "internal_error", "An internal error occurred", 500)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error_response(request, code, message, status, details=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", None),
                    "details": details,
                }
            },
        )

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return error_response(request, exc.code, exc.message, exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        messages = {404: "Endpoint not found", 405: "Method not allowed"}
        return error_response(
            request, "http_error", messages.get(exc.status_code, "Request failed"), exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return error_response(request, "validation_error", "Invalid request", 422, details)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error("database_operation_failed")
        return error_response(
            request, "database_unavailable", "Database operation unavailable", 503
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger(__name__).error("unexpected_request_failure")
        return error_response(request, "internal_error", "An internal error occurred", 500)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready(request: Request):
        async with request.app.state.sessions() as session:
            # Check migration readiness as well as connectivity; never create tables at startup.
            await session.execute(text("SELECT id FROM backend.posts LIMIT 1"))
        if get_settings().retrieval_provider == "pgvector":
            await request.app.state.retriever.list_topics(1, 0)
        return {"status": "ready"}

    return app


app = create_app()

from fastapi import Depends, Request

from hattrick_backend.application.services.retrieval_service import RetrievalService
from hattrick_backend.core.config import get_settings


async def session_dependency(request: Request):
    async with request.app.state.sessions() as session:
        try:
            yield session
        finally:
            await session.rollback()


def retrieval_dependency(request: Request, settings=Depends(get_settings)):
    return RetrievalService(request.app.state.retriever, settings.allow_illustrative_evidence)

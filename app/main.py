from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.ingest_middleware import IngestCorsMiddleware
from app.db.database import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    lifespan=lifespan,
)

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Added after CORSMiddleware so it runs first: ingest routes get their own, open CORS rules.
app.add_middleware(IngestCorsMiddleware, path_prefix=f"{settings.API_V1_PREFIX}/ingest")

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import WEB_DIST, resolve_db_path
from .db import Database
from .errors import ApiError
from .routers import api

log = logging.getLogger("app")


def create_app(database: Database | None = None, *, serve_static: bool = True) -> FastAPI:
    db = database or Database(resolve_db_path())
    db.init_schema()

    application = FastAPI(
        title="Certificate Admin Console",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.state.db = db
    application.include_router(api.router, prefix="/api")

    @application.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status_code)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            {
                "code": "validation_error",
                "message": "Invalid request",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
            status_code=422,
        )

    if serve_static and (WEB_DIST / "index.html").is_file():
        application.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
    else:

        @application.get("/", include_in_schema=False)
        def api_only_root() -> JSONResponse:
            return JSONResponse(
                {
                    "status": "api-only",
                    "hint": "Run ./start.sh to build and serve the console UI.",
                }
            )

    return application

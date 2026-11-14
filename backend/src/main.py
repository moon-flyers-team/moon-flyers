"""App setup only. Endpoints live in `routers/`, logic in `services/`."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import lunar_horizon_dem
from .routers import compare, health, landing_windows, sites
from .services import ephemeris
from .services.errors import (DomainError, EphemerisUnavailableError, InvalidInputError, LimitExceededError,
                              UnknownSiteError)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate an optional host-mounted LOLA dataset before serving.

    Only the deployment overlay sets LOLA_DEM_DIR. Validation is metadata-only here
    (labels, file sizes, calibration, and the polar/global agreement check) so a bad
    or half-copied dataset fails the deploy instead of serving wrong terrain.
    """
    directory = os.environ.get("LOLA_DEM_DIR")
    app.state.lola_dem_dir = None
    if directory:
        summary = lunar_horizon_dem.verify_dataset(directory)
        app.state.lola_dem_dir = Path(directory)
        logging.getLogger(__name__).warning(
            "LOLA DEM dataset validated at %s (%d products)", directory, len(summary["products"]))
    yield


app = FastAPI(title="Moon Flyers API", lifespan=lifespan)

DATA_SOURCE_HEADER = "X-Moon-Flyers-Data-Source"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[DATA_SOURCE_HEADER],
)


@app.middleware("http")
async def mark_data_source(request: Request, call_next):
    """Tells the frontend whether the data is mock (it shows a banner) or real."""
    response = await call_next(request)
    response.headers[DATA_SOURCE_HEADER] = ephemeris.DATA_SOURCE
    return response


ERROR_STATUS = {UnknownSiteError: 404, LimitExceededError: 422, InvalidInputError: 422,
                EphemerisUnavailableError: 502}


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError):
    """The one place where domain errors become HTTP responses."""
    return JSONResponse(status_code=ERROR_STATUS.get(type(exc), 400), content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Malformed JSON → 400. Well-formed but invalid input → FastAPI's default 422."""
    if any(e.get("type") == "json_invalid" for e in exc.errors()):
        return JSONResponse(status_code=400, content={"detail": "invalid JSON body"})
    return await request_validation_exception_handler(request, exc)


app.include_router(health.router)
app.include_router(sites.router)
app.include_router(compare.router)
app.include_router(landing_windows.router)

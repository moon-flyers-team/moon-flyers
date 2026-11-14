"""App setup only. Endpoints live in `routers/`, logic in `services/`."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import compare, health, landing_windows, sites
from .services import ephemeris
from .services.errors import DomainError, LimitExceededError, UnknownSiteError

app = FastAPI(title="Moon Flyers API")

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


ERROR_STATUS = {UnknownSiteError: 404, LimitExceededError: 422}


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

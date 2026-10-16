import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from harambeeone_api.accounts import router as accounts_router
from harambeeone_api.audit import router as audit_router
from harambeeone_api.billing import router as billing_router
from harambeeone_api.dashboard import router as dashboard_router
from harambeeone_api.database import database_is_ready
from harambeeone_api.finance import router as finance_router
from harambeeone_api.onboarding import router as onboarding_router
from harambeeone_api.periods import router as periods_router
from harambeeone_api.portals import router as portals_router
from harambeeone_api.reconciliation import router as reconciliation_router
from harambeeone_api.reports import router as reports_router
from harambeeone_api.requirements import router as requirements_router
from harambeeone_api.sponsors import router as sponsors_router
from harambeeone_api.students import router as students_router
from harambeeone_api.support import router as support_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await run_in_threadpool(database_is_ready)
    except SQLAlchemyError:
        logger.warning("Database warm-up failed; readiness will report unavailable")
    yield


app = FastAPI(title="HarambeeOne API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(students_router)
app.include_router(accounts_router)
app.include_router(onboarding_router)
app.include_router(periods_router)
app.include_router(portals_router)
app.include_router(audit_router)
app.include_router(billing_router)
app.include_router(finance_router)
app.include_router(requirements_router)
app.include_router(reconciliation_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(sponsors_router)
app.include_router(support_router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "The finance database is temporarily unavailable",
            "code": "DATABASE_UNAVAILABLE",
        },
    )


@app.get("/health", tags=["health"])
def liveness() -> dict[str, str | bool]:
    return {
        "ok": True,
        "service": "harambeeone-api",
        "time": datetime.now(UTC).isoformat(),
    }


@app.get("/health/readiness", tags=["health"])
def readiness() -> dict[str, str | bool]:
    try:
        ready = database_is_ready()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from error
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )
    return {"ok": True, "database": "ready"}

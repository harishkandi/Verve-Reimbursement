import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import admin, auth, claims, inbox, payouts, reports
from .config import settings
from .services.errors import DomainError

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Verve Reimbursements", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(DomainError)
def domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


for module in (auth, claims, inbox, payouts, reports, admin):
    app.include_router(module.router)

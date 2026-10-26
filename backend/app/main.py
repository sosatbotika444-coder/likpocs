from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.admissions_api import public_router, staff_router
from app.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment == "production":
        if settings.jwt_secret == "replace-this-secret-before-release" or len(settings.jwt_secret) < 32:
            raise RuntimeError("Production muhitida kamida 32 belgili JWT_SECRET sozlang.")
        if len(settings.initial_operator_password) < 12:
            raise RuntimeError("INITIAL_OPERATOR_PASSWORD kamida 12 belgidan iborat bo‘lishi shart.")
    yield


app = FastAPI(
    title=settings.app_name,
    description="RS Best Hostel yotoqxona boshqaruv API xizmati.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(self)"
    if request.url.path.startswith("/api/public"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Kiritilgan ma’lumotlarni tekshirib, qayta urinib ko‘ring."})


@app.exception_handler(SQLAlchemyError)
async def database_error(_: Request, __: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Ma’lumotlar bazasi bilan bog‘lanib bo‘lmadi. Birozdan so‘ng qayta urinib ko‘ring."})


app.include_router(router)
app.include_router(staff_router)
app.include_router(public_router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "RS Best Hostel", "status": "ok", "api": "/api"}

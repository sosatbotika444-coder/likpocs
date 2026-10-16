from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
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
    description="DormFlow yotoqxona boshqaruv API xizmati.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Kiritilgan ma’lumotlarni tekshirib, qayta urinib ko‘ring."})


@app.exception_handler(SQLAlchemyError)
async def database_error(_: Request, __: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Ma’lumotlar bazasi bilan bog‘lanib bo‘lmadi. Birozdan so‘ng qayta urinib ko‘ring."})


app.include_router(router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "DormFlow", "status": "ok", "api": "/api"}

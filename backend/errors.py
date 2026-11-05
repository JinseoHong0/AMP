from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(status: int, code: str, message: str, details: dict | None = None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_request: Request, error: ApiError):
        return error_response(error.status, error.code, error.message, error.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Do not echo request bodies, image bytes, secrets or provider error strings.
        fields = [".".join(map(str, item["loc"])) for item in error.errors()]
        return error_response(
            422, "VALIDATION_ERROR", "요청 값을 확인해 주세요.", {"fields": fields}
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException):
        return error_response(error.status_code, "INVALID_REQUEST", "요청 형식을 확인해 주세요.")

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _error: Exception):
        return error_response(500, "INTERNAL_ERROR", "요청을 처리하지 못했습니다.")

from __future__ import annotations

class AppError(Exception):
    status_code = 500
    code = "app_error"

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class LLMError(AppError):
    status_code = 502
    code = "llm_error"


class GraphError(AppError):
    status_code = 503
    code = "graph_error"


class RateLimitError(LLMError):
    status_code = 429
    code = "rate_limit"


class UnprocessableError(AppError):
    status_code = 422
    code = "unprocessable_entity"

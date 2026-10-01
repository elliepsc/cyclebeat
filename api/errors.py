"""RFC 7807 errors, in one place.

E.3 requires `{type, title, detail, status}` on failures, and requires the "no valid session
possible" case to use it too. Registering the handlers centrally means every non-2xx shares a
shape — including FastAPI's own validation errors, which would otherwise answer with its
`{"detail": [...]}` and silently break the contract on the most common failure of all.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.schemas import Problem

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ApiError(Exception):
    """An error the API raises deliberately, carrying its own status and reasons."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        reasons: list[str] | None = None,
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        self.reasons = reasons or []
        super().__init__(detail or title)


class NotFoundError(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__(status=404, title="Not Found", detail=detail)


class UnprocessableError(ApiError):
    """422 — well-formed but unsatisfiable.

    This is what a refusal from the planner becomes: `NoValidSessionError.reasons` travels
    into `reasons` unchanged, which is exactly what phase 3 built those codes for.
    """

    def __init__(self, detail: str, reasons: list[str] | None = None) -> None:
        super().__init__(
            status=422, title="Unprocessable Entity", detail=detail, reasons=reasons
        )


def _problem(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _problem(
            Problem(
                title=exc.title, status=exc.status, detail=exc.detail, reasons=exc.reasons
            )
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Flattened to `field: message` strings. FastAPI's native shape is a list of dicts,
        # which is not RFC 7807 and is not what openapi.yaml promises.
        reasons = [
            f"{'.'.join(str(p) for p in err.get('loc', ()) if p != 'body')}: {err.get('msg', '')}"
            for err in exc.errors()
        ]
        return _problem(
            Problem(
                title="Unprocessable Entity",
                status=422,
                detail="The request body failed validation.",
                reasons=reasons,
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            Problem(
                title=str(exc.detail) if exc.detail else "Error",
                status=exc.status_code,
                detail=str(exc.detail) if exc.detail else None,
            )
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        """The last uncovered path: without this, a 500 answers `text/plain`.

        A generated TypeScript client typed against `Problem` would get plain text exactly
        when it is least able to cope. The exception itself is deliberately NOT put in the
        body — E.4's rule for the copilot ("erreurs → message structuré, pas de stack") is the
        right instinct for the whole API, and a stack trace in a response is an information
        leak. It still propagates to the logs.
        """
        return _problem(
            Problem(
                title="Internal Server Error",
                status=500,
                detail="The request could not be completed.",
            )
        )

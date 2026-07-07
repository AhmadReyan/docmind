"""API error type carrying the contract's ``{"detail": str, "code": str}`` shape."""

from fastapi import HTTPException


class ApiError(HTTPException):
    """HTTPException with an explicit machine-readable ``code`` per docs/api-contract.md."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code

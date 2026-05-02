from __future__ import annotations

from fastapi import HTTPException, status


class AuthenticationRequired(HTTPException):
    def __init__(self, detail: str = "Authentification requise.") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class PermissionDenied(HTTPException):
    def __init__(self, detail: str = "Permission refusee.") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

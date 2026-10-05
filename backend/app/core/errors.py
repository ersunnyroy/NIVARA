from __future__ import annotations

from fastapi import HTTPException, status


def not_found(what: str = "Resource") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def bad_request(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, msg)


def forbidden(msg: str = "Not allowed") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)


def unavailable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)

"""Structured error responses."""
from fastapi import HTTPException, status


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found", "message": what})


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "bad_request", "message": message})


def payload_too_large(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail={"error": "payload_too_large", "message": message},
    )

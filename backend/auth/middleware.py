"""JWT cookie authentication middleware."""
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.auth.crypto import COOKIE_NAME, decode_token

_EXEMPT_PATHS = frozenset({
    "/api/auth/login",
    "/api/logs/stream",
})


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Static files and non-API paths pass through freely
        if not path.startswith("/api/") or path in _EXEMPT_PATHS:
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        try:
            payload = decode_token(token)
        except ValueError:
            resp = JSONResponse({"detail": "Session expired"}, status_code=401)
            resp.delete_cookie(COOKIE_NAME, samesite="strict")
            return resp

        request.state.user = {
            "id": int(payload["sub"]),
            "username": payload["usr"],
            "is_admin": bool(payload["adm"]),
        }
        return await call_next(request)

"""FastAPI dependency injectors for auth."""
from fastapi import HTTPException, Request


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def require_admin(request: Request) -> dict:
    user = get_current_user(request)
    if not user["is_admin"]:
        raise HTTPException(403, "Admin access required")
    return user

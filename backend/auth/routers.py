"""Auth endpoints: login, logout, me, user management (admin only)."""
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator

from backend.auth import db
from backend.auth.crypto import COOKIE_NAME, create_token, hash_password, verify_password
from backend.auth.dependencies import get_current_user, require_admin
from backend.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


# ── Pydantic models ───────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("Username must be 1–64 characters")
        if not _USERNAME_RE.match(v):
            raise ValueError("Only letters, digits, _ . - allowed")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    created_at: str
    last_login: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest, response: Response) -> dict:
    user = await db.get_user_by_username(req.username)
    if user is None or not verify_password(req.password, user["hashed_pw"]):
        raise HTTPException(401, "Invalid username or password")
    await db.update_last_login(user["id"])
    token = create_token(user["id"], user["username"], bool(user["is_admin"]))
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=settings.jwt_secure_cookie,
        max_age=settings.jwt_expire_hours * 3600,
        path="/",
    )
    return {"username": user["username"], "is_admin": bool(user["is_admin"])}


@router.post("/logout")
async def logout(response: Response, _user: dict = Depends(get_current_user)) -> dict:
    response.delete_cookie(COOKIE_NAME, samesite="strict", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users() -> list[UserOut]:
    rows = await db.list_users()
    return [UserOut(**dict(r)) for r in rows]


@router.post("/users", dependencies=[Depends(require_admin)], status_code=201)
async def create_user(body: UserCreate) -> UserOut:
    try:
        hashed = hash_password(body.password)
        uid = await db.create_user(body.username, hashed, body.is_admin)
        row = await db.get_user_by_id(uid)
        return UserOut(**dict(row))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: int) -> dict:
    try:
        ok = await db.delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not ok:
        raise HTTPException(404, "User not found")
    return {"deleted": user_id}

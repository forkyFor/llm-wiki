"""First-run admin account bootstrap."""
import logging
import secrets

from backend.auth import db
from backend.auth.crypto import hash_password
from backend.config import settings

logger = logging.getLogger(__name__)


async def bootstrap_admin() -> None:
    rows = await db.list_users()
    if rows:
        return  # Users already exist — skip bootstrap

    username = settings.admin_username or "admin"
    password = settings.admin_password or secrets.token_urlsafe(16)
    auto_generated = not settings.admin_password

    hashed = hash_password(password)
    await db.create_user(username, hashed, is_admin=True)

    if auto_generated:
        sep = "=" * 60
        logger.warning(sep)
        logger.warning("AUTH BOOTSTRAP — SAVE THESE CREDENTIALS:")
        logger.warning("  Username : %s", username)
        logger.warning("  Password : %s", password)
        logger.warning("  Set ADMIN_USERNAME / ADMIN_PASSWORD in .env to control.")
        logger.warning(sep)
    else:
        logger.info("Auth: admin user '%s' created from .env credentials", username)

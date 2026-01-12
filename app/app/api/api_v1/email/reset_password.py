import time

from fastapi import Depends, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.api_v1 import api_router_v1
from app.util.rest_util import get_failed_response
from app.celery_worker.tasks import task_send_email_forgot_password
from app.database import get_db
from app.models import User, UserToken
import hashlib


class PasswordResetRequest(BaseModel):
    email: str


@api_router_v1.post("/password/reset", status_code=200)
async def reset_password(
    password_reset_request: PasswordResetRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    email = password_reset_request.email

    email_hash = hashlib.sha512(email.lower().encode("utf-8")).hexdigest()
    statement = select(User).where(User.origin == 0).where(User.email_hash == email_hash)
    results = await db.execute(statement)
    result_user = results.first()
    if not result_user:
        return get_failed_response("no account found using this email", response)

    user: User = result_user.User
    access_expiration_time = 1800  # 30 minutes
    refresh_expiration_time = 18000  # 5 hours
    token_expiration = int(time.time()) + access_expiration_time
    refresh_token_expiration = int(time.time()) + refresh_expiration_time
    reset_token = user.generate_auth_token(access_expiration_time).decode("ascii")
    refresh_reset_token = user.generate_refresh_token(refresh_expiration_time).decode("ascii")

    subject = "Hex Place - Change your password"
    _ = task_send_email_forgot_password.delay(email, subject, reset_token, refresh_reset_token)

    user_token = UserToken(
        user_id=user.id,
        access_token=reset_token,
        refresh_token=refresh_reset_token,
        token_expiration=token_expiration,
        refresh_token_expiration=refresh_token_expiration,
    )
    db.add(user_token)
    await db.commit()

    return {
        "result": True,
        "message": "password check was good",
    }

import time
from typing import Optional
from fastapi import Request, Depends
from pydantic import BaseModel
from sqlalchemy import func
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.api_v1 import api_router_v1
from app.celery_worker.tasks import task_send_email
from app.config.config import settings
from app.database import get_db
from app.models import User, UserToken
from app.util.email.delete_account_email import delete_account_email
from app.util.rest_util import get_failed_response
from app.util.util import refresh_user_token
from sqlalchemy.orm import selectinload


class RemoveAccountRequest(BaseModel):
    email: str


@api_router_v1.post("/remove/account", status_code=200)
async def remove_account(
    remove_account_request: RemoveAccountRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:

    email = remove_account_request.email
    statement = (
        select(User)
        .where(func.lower(User.email) == email.lower())
        .options(selectinload(User.friends))
        .options(selectinload(User.tokens))
    )
    results = await db.execute(statement)
    result = results.all()
    if result is None or result == []:
        return get_failed_response(
            "no account found with that email", response
        )

    user = result[0].User
    access_expiration_time = 1800  # 30 minutes
    refresh_expiration_time = 18000  # 5 hours
    token_expiration = int(time.time()) + access_expiration_time
    refresh_token_expiration = int(time.time()) + refresh_expiration_time
    delete_token = user.generate_auth_token(access_expiration_time).decode("ascii")
    refresh_delete_token = user.generate_refresh_token(refresh_expiration_time).decode("ascii")

    subject = "Hex Place - Delete your account"
    body = delete_account_email.format(
        base_url=settings.BASE_URL, token=delete_token, refresh_token=refresh_delete_token
    )
    _ = task_send_email.delay(user.username, email, subject, body)

    user_token = UserToken(
        user_id=user.id,
        access_token=delete_token,
        refresh_token=refresh_delete_token,
        token_expiration=token_expiration,
        refresh_token_expiration=refresh_token_expiration,
    )
    db.add(user_token)
    await db.commit()

    return {
        "result": True,
        "message": "Account deletion email has been sent",
    }


class RemoveAccountVerifyRequest(BaseModel):
    access_token: str
    refresh_token: str


@api_router_v1.post("/remove/account/verify", status_code=200)
async def remove_account_verify(
    remove_account_verify_request: RemoveAccountVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:

    access_token = remove_account_verify_request.access_token
    refresh_token = remove_account_verify_request.refresh_token
    user: Optional[User] = await refresh_user_token(db, access_token, refresh_token)
    if not user:
        return get_failed_response("user not found", response)

    email = user.email
    statement = (
        select(User)
        .where(func.lower(User.email) == email.lower())
        .options(selectinload(User.friends))
        .options(selectinload(User.tokens))
    )
    results = await db.execute(statement)
    users = results.all()
    if users is None or users == []:
        return get_failed_response(
            "no account found with that email", response
        )

    for user in users:
        log_user = user.User
        user_tokens = log_user.tokens
        for user_token in user_tokens:
            await db.delete(user_token)
    await db.commit()

    for user in users:
        await db.delete(user.User)
    await db.commit()

    return {
        "result": True,
        "message": "Account has been removed",
    }

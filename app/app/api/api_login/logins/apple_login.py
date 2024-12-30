from urllib.parse import urlencode

import requests
from app.api.api_login.logins.login_user_origin import login_user_origin
from app.celery_worker.tasks import task_generate_avatar
from app.config.config import settings
from app.database import get_db
from app.api.api_login import api_router_login
from app.util.rest_util import get_failed_response
from app.util.util import get_user_tokens
from fastapi import Depends, Request, status, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from time import time 


def decode_apple_token(token):
    return jwt.decode(token, audience=settings.APPLE_CLIENT_ID ,options={"verify_signature": False})


async def log_user_in(
        userinfo_response,
        db: AsyncSession = Depends(get_db),
):
    id_token = userinfo_response.json()["id_token"]
    apple_token = decode_apple_token(id_token)
    users_email = apple_token["email"]
    users_name = apple_token["email"].split("@")[0]

    [user, user_created] = await login_user_origin(users_name, users_email, 4, db)

    if user:
        user_token = get_user_tokens(user, 30, 60)
        db.add(user_token)
        await db.commit()
        access_token = user_token.access_token
        refresh_token = user_token.refresh_token

        if user_created:
            db.add(user)
            await db.refresh(user)
            await db.commit()
            _ = task_generate_avatar.delay(user.avatar_filename(), user.id)
        else:
            await db.commit()

        return [True, [access_token, refresh_token, user, user_created]]
    else:
        return [False, [None, None, None, None]]


def generate_token():
    private_key = settings.APPLE_AUTH_KEY
    team_id = settings.APPLE_TEAM_ID
    client_id = settings.APPLE_CLIENT_ID
    key_id = settings.APPLE_KEY_ID
    validity_minutes = 15
    timestamp_now = int(time())
    timestamp_exp = timestamp_now + (60 * validity_minutes)
    data = {
            "iss": team_id,
            "iat": timestamp_now,
            "exp": timestamp_exp,
            "aud": settings.APPLE_AUD_URL,
            "sub": client_id
        }
    token = jwt.encode(payload=data, key=private_key.encode("utf-8"), algorithm="ES256", headers={"kid": key_id})
    return token


@api_router_login.get("/apple/callback")
async def apple_callback(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    print("apple callback!")
    request_base_url = str(request.base_url)
    print("request_base_url", request_base_url)
    request_base_url = request_base_url.replace("http://", "https://", 1)
    print("request_base_url", request_base_url)
    login_url = request_base_url.replace("/login/apple/callback", "/")
    print("login_url", login_url)
    print(f"full url: {request.url}")
    print(f"code: {code}")


@api_router_login.get("/apple/verify")
async def apple_verify(
    code: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    apple_key_url = settings.APPLE_AUTHORIZE

    userinfo_response = requests.post(
        apple_key_url, headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": settings.APPLE_CLIENT_ID,
            "client_secret": generate_token(),
            "code": code,
            "grant_type": settings.APPLE_GRANT_TYPE,
            "redirect_uri": settings.APPLE_REDIRECT_URL,
        }
    )

    if not userinfo_response.json().get("access_token") or not userinfo_response.json().get("refresh_token") or not userinfo_response.json().get("id_token"): 
        return get_failed_response("User email not available or not verified by Google.", response)

    [success, [_, _, user, user_created]] = await log_user_in(userinfo_response, db)

    if success:
        # Valid login, we refresh the token for this user.
        user_token = get_user_tokens(user)
        db.add(user_token)
        await db.commit()

        if user_created:
            user = user.serialize_no_detail
        else:
            user = user.serialize

        # We don't refresh the user object because we know all we want to know
        login_response = {
            "result": True,
            "message": "user logged in successfully.",
            "access_token": user_token.access_token,
            "refresh_token": user_token.refresh_token,
            "user": user,
        }

        return login_response
    else:
        return get_failed_response("An error occurred", response)


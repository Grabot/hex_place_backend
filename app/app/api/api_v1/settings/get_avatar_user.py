import base64
from typing import Optional

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1 import api_router_v1
from app.database import get_db
from app.models import User
from app.util.rest_util import get_failed_response
from app.util.s3_util import download_avatar
from app.util.util import check_token, get_auth_token


@api_router_v1.post("/get/avatar/user", status_code=200)
async def get_avatar_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth_token = get_auth_token(request.headers.get("Authorization"))

    if auth_token == "":
        return get_failed_response("An error occurred", response)

    user_avatar: Optional[User] = await check_token(db, auth_token)
    if not user_avatar:
        return get_failed_response("An error occurred", response)

    if user_avatar.is_default():
        file_name = user_avatar.avatar_filename_default()
        encrypted = False
    else:
        file_name = user_avatar.avatar_filename()
        encrypted = True

    image_bytes = download_avatar(user_avatar.avatar_s3_key(file_name), encrypted=encrypted)
    if image_bytes is None:
        return get_failed_response("An error occurred", response)

    return {"result": True, "avatar": base64.encodebytes(image_bytes).decode()}

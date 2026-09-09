import base64
import io
from typing import Optional

from fastapi import Depends, Request, Response
from PIL import Image
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1 import api_router_v1
from app.database import get_db
from app.models import User
from app.util.rest_util import get_failed_response
from app.util.s3_util import upload_avatar
from app.util.util import check_token, get_auth_token


class ChangeAvatarRequest(BaseModel):
    avatar: str
    avatar_small: str


@api_router_v1.post("/change/avatar", status_code=200)
async def change_avatar(
    change_avatar_request: ChangeAvatarRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth_token = get_auth_token(request.headers.get("Authorization"))

    if auth_token == "":
        return get_failed_response("An error occurred", response)

    user: Optional[User] = await check_token(db, auth_token)
    if not user:
        return get_failed_response("An error occurred", response)

    new_avatar = change_avatar_request.avatar
    new_avatar_small = change_avatar_request.avatar_small

    new_avatar_pil = Image.open(io.BytesIO(base64.b64decode(new_avatar)))
    new_avatar_small_pil = Image.open(io.BytesIO(base64.b64decode(new_avatar_small)))

    file_name = user.avatar_filename()
    file_name_small = user.avatar_filename_small()

    full_buffer = io.BytesIO()
    new_avatar_pil.save(full_buffer, format="PNG")
    small_buffer = io.BytesIO()
    new_avatar_small_pil.save(small_buffer, format="PNG")

    upload_avatar(full_buffer.getvalue(), user.avatar_s3_key(file_name))
    upload_avatar(small_buffer.getvalue(), user.avatar_s3_key(file_name_small))

    user.set_default_avatar(False)
    db.add(user)
    await db.commit()

    return {
        "result": True,
        "message": "success",
    }

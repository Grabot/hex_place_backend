from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.api_v1 import api_router_v1
from app.celery_worker.tasks import task_generate_avatar
from app.database import get_db
from app.models import User


@api_router_v1.api_route("/avatar/creation", methods=["GET", "POST"], status_code=200)
async def avatar_creation(
    db: AsyncSession = Depends(get_db),
) -> dict:
    statement = select(User)
    results = await db.execute(statement)
    # results.all() returns list of Row tuples
    users = [row[0] for row in results.all()]

    created = 0
    for user in users:
        task_generate_avatar.delay(user.avatar_filename(), user.id)
        created += 1

    return {
        "result": True,
        "message": f"Avatar creation queued for {created} users",
        "count": created,
    }

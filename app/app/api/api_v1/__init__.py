from fastapi import APIRouter

api_router_v1 = APIRouter()

from . import avatar_creation, email, guild, initialization_call, map, message, settings, social, test, user_access

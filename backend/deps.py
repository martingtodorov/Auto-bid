"""
Shared dependencies for router modules.
Exposes the Motor database client, rate limiter, and the get_current_user /
require_admin FastAPI dependencies so that routers can import from one place.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_client = AsyncIOMotorClient(MONGO_URL)
db = _client[DB_NAME]

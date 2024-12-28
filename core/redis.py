import redis.asyncio as redis
from core.settings import settings

redis = redis.from_url(settings.REDIS_CONNECTION_URL)

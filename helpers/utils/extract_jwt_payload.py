from jwt import decode
from core.settings import settings

async def extract_jwt_payload(jwt_token):
  return await decode(jwt_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
